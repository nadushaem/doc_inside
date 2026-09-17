import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import combinations

from storage import load_json, save_json, json_exists

INDEX_PATH = "data/processed/doctors/index.json"
MATCHES_PATH = "data/processed/doctors/matches.json"
MANUAL_DECISIONS_PATH = "data/processed/doctors/manual_decisions.json"
UNPARSED_PATH = "data/processed/doctors/unparsed_names.json"

# --- пороги скоринга ---
AUTO_THRESHOLD_EXACT = 3.5   # полное ФИО + хоть что-то не противоречит
AUTO_THRESHOLD_FUZZY = 5.0   # нечёткое ФИО + совпали и год, и вуз
REVIEW_THRESHOLD = 1.5       # ниже — считаем тёзками и не показываем

SURNAME_TYPO_THRESHOLD = 0.85
PATRONYMIC_TYPO_STRONG = 0.8
PATRONYMIC_TYPO_WEAK = 0.65
NAME_VARIANT_THRESHOLD = 0.6
SLUG_MATCH_THRESHOLD = 0.85
SLUG_OWN_THRESHOLD = 0.8      # если slug непохож на свою фамилию — это старая фамилия
UNI_FUZZY_THRESHOLD = 0.8
MAX_BLOCK_SIZE = 60

KIND_BASE_TITLES = {
    "exact": "полное совпадение ФИО",
    "double_surname": "двойная фамилия",
    "maiden_bracket": "девичья фамилия в скобках",
    "slug_surname": "старая фамилия в slug",
    "surname_typo": "опечатка в фамилии",
    "patronymic_typo": "опечатка в отчестве",
    "missing_patronymic": "отчество указано только на одном сайте",
    "name_variant": "разное написание имени",
    "surname_change": "возможная смена фамилии",
}
KIND_ORDER = list(KIND_BASE_TITLES)


def sim(a: str | None, b: str | None) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


# ======================================================================
# ИМЕНА
# ======================================================================

HOMOGLYPHS = str.maketrans("aeopcxykmthb", "аеорсхукмтнв")
TURKIC_MARKERS = {"кызы", "гызы", "оглы", "улы", "уулу"}
PATRONYMIC_SUFFIXES = ("инична", "овна", "евна", "ична", "вна", "ович", "евич", "вич")
PATRONYMIC_RE = re.compile(r"(вич|вна|чна)$")
FEMALE_SURNAME_RE = re.compile(r"(ова|ева|ина|ына|ая|айте|ене|уте)$")

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch",
    "ш": "sh", "щ": "sh", "ъ": "", "ы": "y", "ь": "", "ю": "yu", "я": "ya",
}


def translit(s: str) -> str:
    return "".join(TRANSLIT.get(c, c) for c in s)


def canon(token: str) -> str:
    """Ключ сравнения: Наталья/Наталия, Юля/Юлия, Брусницина/Брусницына дают одно и то же."""
    token = token.replace("ь", "").replace("ъ", "").replace("ы", "и")
    return re.sub(r"и(?=[аеиоуэюя])", "", token)


def patronymic_root(patr: str) -> str:
    """Юрьевна/Юриевна -> юр, Рафиговна/Рафиг кызы -> рафиг, Ильинична/Ильична -> ил."""
    if not patr:
        return ""
    words = patr.split()
    if len(words) > 1 and words[-1] in TURKIC_MARKERS:
        root = words[0]
    else:
        root = patr
        for suf in PATRONYMIC_SUFFIXES:
            if root.endswith(suf) and len(root) > len(suf) + 1:
                root = root[:-len(suf)]
                break
    return canon(root).rstrip("и")


def _clean(s: str) -> str:
    s = re.sub(r"[^а-я\s-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _parts(tokens: list[str]) -> set[str]:
    return {canon(p) for t in tokens for p in t.split("-") if p}


@dataclass
class Name:
    surname_key: str
    surname_parts: set
    maiden_parts: set
    name: str
    patronymic: str
    patr_root: str
    full_key: str
    is_female: bool
    latin: str
    alt_latin: dict = field(default_factory=dict)  # латинская фамилия -> вес сигнала


def parse_full_name(raw: str | None) -> Name | None:
    if not raw:
        return None
    low = raw.lower().translate(HOMOGLYPHS).replace("ё", "е").replace("э", "е")
    maiden_tokens = _clean(" ".join(re.findall(r"\((.*?)\)", low))).split()

    tokens: list[str] = []
    for t in _clean(re.sub(r"\(.*?\)", " ", low)).split():
        if t in TURKIC_MARKERS and tokens:
            tokens[-1] += " " + t          # «Рафиг кызы» — одно отчество
        else:
            tokens.append(t)
    if len(tokens) < 2:
        return None

    idx = next((i for i, t in enumerate(tokens)
                if i >= 1 and (" " in t or PATRONYMIC_RE.search(t))), None)
    guessed = False
    if idx is None:
        if len(tokens) == 2:
            sur, name, patr = tokens[:1], tokens[1], ""
        elif len(tokens) == 3:             # «Яблонскайте Оксана Вито»
            sur, name, patr, guessed = tokens[:1], tokens[1], tokens[2], True
        else:
            return None
    elif idx >= 2:                         # Фамилия Имя Отчество [мусор]
        sur, name, patr = tokens[:idx - 1], tokens[idx - 1], tokens[idx]
    else:                                  # Имя Отчество Фамилия
        sur, name, patr = tokens[2:3], tokens[0], tokens[1]
    if not sur:
        return None

    if guessed or not patr:
        is_female = bool(FEMALE_SURNAME_RE.search(sur[-1])) or name.endswith(("а", "я"))
    else:
        is_female = patr.endswith(("на", "кызы", "гызы"))

    surname_key = " ".join(canon(t) for t in sur)
    root = patronymic_root(patr)
    name_c = canon(name)
    return Name(
        surname_key=surname_key,
        surname_parts=_parts(sur),
        maiden_parts=_parts(maiden_tokens),
        name=name_c,
        patronymic=canon(patr.replace(" ", "")),
        patr_root=root,
        full_key=f"{surname_key}|{name_c}|{root}",
        is_female=is_female,
        latin=translit("-".join(sur)),
        alt_latin={translit(m): 1.5 for m in maiden_tokens},
    )


def attach_slug_surname(name: Name, info: dict) -> None:
    """Если фамилия в slug не похожа на текущую — это, скорее всего, прежняя фамилия."""
    slug = info.get("profile_url", "").rstrip("/").rsplit("/", 1)[-1]
    if info["source"] == "prodoctorov":
        slug, weight = re.sub(r"^\d+-", "", slug), 1.5
    else:
        # napopravku переиспользует профили, поэтому сигнал слабее
        slug, weight = re.sub(r"^\d+", "", slug).split("-")[0], 0.5
    if slug and sim(slug, name.latin) < SLUG_OWN_THRESHOLD:
        name.alt_latin[slug] = max(weight, name.alt_latin.get(slug, 0))


# ======================================================================
# ОБРАЗОВАНИЕ
# ======================================================================

UNI_STOPWORDS = {
    "фгбоу", "гбоу", "гоу", "фгоу", "во", "впо", "федеральное", "государственное",
    "бюджетное", "образовательное", "учреждение", "высшего", "профессионального",
    "образования", "минздрава", "минздравсоцразвития", "россии", "рф", "мз",
    "министерства", "здравоохранения", "российской", "федерации", "имени", "им",
    "государственный", "государственная", "медицинский", "медицинская",
    "университет", "академия", "институт", "екатеринбург", "г", "по", "специальности",
}
COURSE_RE = re.compile(r"повышени\w* квалификац|переподготовк|сестринское дело в косметолог"
                       r"|мезотерап|интенсив|дополнительное образование")
COLLEGE_RE = re.compile(r"колледж|училищ|техникум|школа красоты|институт (эстетики|красоты)")

# порядок важен: более специфичные правила выше
UNI_RULES = [
    ("ugmado", r"уральск\w* государственн\w* медицинск\w* академи\w* дополнительн"),
    ("usmu", r"уральск\w* (государственн\w* )?медицинск|свердловск\w* государственн\w*.*медицинск\w* институт"
             r"|\bугм[ау]\b"),
    ("tyumen", r"тюменск\w*.*медицинск"),
    ("perm", r"пермск\w*.*медицинск|\bпгму\b"),
    ("susmu", r"южно уральск\w*.*медицинск|челябинск\w*.*медицинск|\bюугму\b"),
    ("omsk", r"омск\w*.*медицинск|\bомгму\b"),
    ("orenburg", r"оренбургск\w*.*медицинск"),
    ("izhevsk", r"ижевск\w*.*медицинск"),
    ("bashkir", r"башкирск\w*.*медицинск"),
    ("kirov", r"кировск\w*.*медицинск"),
    ("karaganda", r"караганд"),
    ("kemerovo", r"кемеровск\w*.*медицинск"),
    ("krsu", r"(кыргызско|киргизско) российск\w* славянск"),
    ("kgma", r"ахунбаева|кыргызск\w* государственн\w* медицинск"),
    ("tajik", r"таджикск\w*.*медицинск|абуали"),
    ("sibgmu", r"сибирск\w*.*медицинск|\bсибгму\b"),
    ("kazan", r"казанск\w*.*медицинск"),
    ("rnimu", r"пирогова|\bрниму\b"),
    ("sechenov", r"сеченова"),
    ("tashkent_ped", r"ташкентск\w* педиатрическ"),
    ("tashkent", r"ташкентск"),
    ("yerevan", r"ереванск\w*.*медицинск|гераци"),
    ("amur", r"амурск\w*.*медицинск"),
    ("astrakhan", r"астраханск\w*.*медицинск"),
    ("pacific", r"тихоокеанск\w*.*медицинск"),
    ("dagestan", r"дагестанск\w*.*медицинск"),
    ("rostov", r"ростовск\w*.*медицинск"),
    ("saratov", r"саратовск\w*.*медицинск"),
    ("samara", r"самарск\w*.*медицинск"),
    ("krasnoyarsk", r"красноярск\w*.*медицинск"),
    ("chita", r"читинск\w*.*медицинск"),
    ("volgograd", r"волгоградск\w*.*медицинск"),
    ("lugansk", r"луганск\w*.*медицинск"),
]
YEAR_RE = re.compile(r"(?<!\d)(19[5-9]\d|20[0-3]\d)(?!\d)")


@dataclass
class Education:
    uni_id: str | None = None
    uni_norm: str | None = None
    year: int | None = None
    level: str | None = None  # "higher" / "college"


def parse_education(info: dict) -> Education:
    raw, year = info.get("university"), info.get("graduation_year")
    if not raw:
        return Education(year=year)

    text = raw.lower().replace("ё", "е")
    unreliable = bool(COURSE_RE.search(text))
    if not year and not unreliable:
        m = YEAR_RE.search(text)
        if m:
            year = int(m.group(1))

    text = re.sub(r"\(.*?\)|«.*?»", " ", text)
    text = re.sub(r"диплом с отличием|лечебн\w* дел\w*|педиатри\w*|\d+", " ", text)
    text = re.sub(r"[^а-яa-z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if COLLEGE_RE.search(text):
        level, uni_id = "college", None
    else:
        uni_id = next((uid for uid, rx in UNI_RULES if re.search(rx, text)), None)
        level = "higher" if uni_id or re.search(r"университет|академи|институт", text) else None

    norm = " ".join(t for t in text.split() if t not in UNI_STOPWORDS) or None
    if unreliable and uni_id is None:
        norm = None  # в поле описание курсов, а не вуза
    return Education(uni_id=uni_id, uni_norm=norm, year=year, level=level)


# ======================================================================
# КЛАССИФИКАЦИЯ И СКОРИНГ ПАР
# ======================================================================

@dataclass
class Person:
    key: str
    info: dict
    name: Name
    edu: Education


def slug_signal(pa: Name, pb: Name) -> float:
    best = 0.0
    for alt, w in pa.alt_latin.items():
        if max(sim(alt, pb.latin), *(sim(alt, x) for x in pb.alt_latin), 0) >= SLUG_MATCH_THRESHOLD:
            best = max(best, w)
    for alt, w in pb.alt_latin.items():
        if sim(alt, pa.latin) >= SLUG_MATCH_THRESHOLD:
            best = max(best, w)
    return best


def classify(pa: Name, pb: Name) -> tuple[str, float] | None:
    """Тип совпадения ФИО и базовый балл. None — точно разные люди."""
    if pa.full_key == pb.full_key:
        return "exact", 3.0

    same_name = pa.name == pb.name
    same_patr = bool(pa.patr_root) and pa.patr_root == pb.patr_root
    same_surname = pa.surname_key == pb.surname_key

    if same_name and same_patr:
        if pa.surname_parts & pb.surname_parts:
            return "double_surname", 1.5
        if (pa.maiden_parts & pb.surname_parts or pb.maiden_parts & pa.surname_parts
                or pa.maiden_parts & pb.maiden_parts):
            return "maiden_bracket", 1.5
        w = slug_signal(pa, pb)
        if w:
            return "slug_surname", w
        if sim(pa.surname_key, pb.surname_key) >= SURNAME_TYPO_THRESHOLD:
            return "surname_typo", 1.5
        if pa.is_female and pb.is_female:
            return "surname_change", 0.5
        return None

    if same_surname and same_name:
        if not pa.patronymic or not pb.patronymic:
            return "missing_patronymic", 1.0
        s = max(sim(pa.patronymic, pb.patronymic), sim(pa.patr_root, pb.patr_root))
        if s >= PATRONYMIC_TYPO_STRONG:
            return "patronymic_typo", 1.5
        if s >= PATRONYMIC_TYPO_WEAK:
            return "patronymic_typo", 0.5
        return None

    if same_surname and same_patr:
        return "name_variant", 1.5 if sim(pa.name, pb.name) >= NAME_VARIANT_THRESHOLD else 0.5

    return None


def score_pair(kind: str, base: float, a: Person, b: Person, namesakes: bool) -> tuple[float, list[str], bool]:
    score, notes, veto = base, [f"{KIND_BASE_TITLES[kind]} (+{base})"], False
    ea, eb = a.edu, b.edu

    if ea.year and eb.year:
        if ea.year == eb.year:
            score += 2
            notes.append(f"год выпуска {ea.year} (+2)")
        elif abs(ea.year - eb.year) == 1:
            notes.append(f"годы {ea.year}/{eb.year} отличаются на 1 (0)")
        else:
            score -= 5
            veto = True
            notes.append(f"разные годы {ea.year}/{eb.year} (-5)")

    if ea.uni_id and eb.uni_id:
        if ea.uni_id == eb.uni_id:
            score += 1.5
            notes.append(f"вуз {ea.uni_id} (+1.5)")
        else:
            score -= 2
            notes.append(f"разные вузы {ea.uni_id}/{eb.uni_id} (-2)")
    elif ea.uni_norm and eb.uni_norm:
        s = sim(ea.uni_norm, eb.uni_norm)
        delta = 1 if s >= UNI_FUZZY_THRESHOLD else -1
        score += delta
        notes.append(f"вузы похожи на {s:.2f} ({delta:+})")

    if ea.level and eb.level and ea.level != eb.level:
        score -= 1
        notes.append("вуз vs колледж (-1)")

    if set(a.info["specialities"]) & set(b.info["specialities"]):
        score += 0.5
        notes.append("общая специальность (+0.5)")
    else:
        score -= 0.5
        notes.append("нет общей специальности (-0.5)")

    if namesakes:
        score -= 2
        notes.append("есть тёзки в одном источнике (-2)")

    return score, notes, veto


def pair_id(key_a: str, key_b: str) -> str:
    return "|".join(sorted([key_a, key_b]))


def make_pair(a: Person, b: Person, kind: str, score: float, notes: list[str]) -> dict:
    def doc(p: Person):
        return {"key": p.key, "source": p.info["source"], "profile_url": p.info["profile_url"],
                "full_name": p.info.get("full_name"), "university": p.info.get("university"),
                "university_id": p.edu.uni_id, "graduation_year": p.edu.year,
                "specialities": p.info["specialities"]}
    return {"pair_id": pair_id(a.key, b.key), "kind": kind, "score": round(score, 2),
            "same_source": a.info["source"] == b.info["source"],
            "reason": "; ".join(notes), "doctors": [doc(a), doc(b)]}


# ======================================================================
# КЛАСТЕРЫ
# ======================================================================

class DSU:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def build_clusters(buckets: dict, index: dict) -> list[dict]:
    dsu = DSU()
    confirmed = set()
    for bucket in ("auto", "manual_confirmed"):
        for p in buckets[bucket]:
            a, b = (d["key"] for d in p["doctors"])
            dsu.union(a, b)
            if bucket == "manual_confirmed":
                confirmed.add(p["pair_id"])

    groups = defaultdict(set)
    for k in dsu.parent:
        groups[dsu.find(k)].add(k)

    rejected = {p["pair_id"] for p in buckets["manual_rejected"]}
    clusters = []
    for i, keys in enumerate(sorted(groups.values(), key=lambda s: sorted(s)), 1):
        problems = []
        per_source = Counter(index[k]["source"] for k in keys)
        for a, b in combinations(sorted(keys), 2):
            pid = pair_id(a, b)
            if pid in rejected:
                problems.append(f"пара {pid} отклонена вручную, но попала в кластер транзитивно")
            elif index[a]["source"] == index[b]["source"] and pid not in confirmed:
                problems.append(f"два профиля одного источника без подтверждения: {pid}")
        clusters.append({
            "cluster_id": f"cluster_{i:05d}",
            "keys": sorted(keys),
            "sources": dict(per_source),
            "needs_review": bool(problems),
            "problems": problems,
        })
    return clusters


# ======================================================================
# MAIN
# ======================================================================

def main():
    index = load_json(INDEX_PATH)
    decisions = load_json(MANUAL_DECISIONS_PATH) if json_exists(MANUAL_DECISIONS_PATH) else {}

    persons, unparsed = {}, []
    for key, info in index.items():
        name = parse_full_name(info.get("full_name"))
        if name is None:
            unparsed.append(key)
            continue
        attach_slug_surname(name, info)
        persons[key] = Person(key, info, name, parse_education(info))

    # --- блокировка: сравниваем только внутри общих ключей ---
    blocks = defaultdict(list)
    fullname_counts = Counter()
    for key, p in persons.items():
        city, n = p.info.get("city"), p.name
        fullname_counts[(city, n.full_key, p.info["source"])] += 1
        blocks[("full", city, n.full_key)].append(key)
        blocks[("sur_name", city, n.surname_key, n.name)].append(key)
        if n.patr_root:
            blocks[("name_patr", city, n.name, n.patr_root)].append(key)
            blocks[("sur_patr", city, n.surname_key, n.patr_root)].append(key)

    candidates = set()
    for bkey, keys in blocks.items():
        if len(keys) > MAX_BLOCK_SIZE:
            print(f"[WARNING] блок {bkey} слишком большой ({len(keys)}), пропускаю")
            continue
        candidates.update(tuple(sorted(pair)) for pair in combinations(keys, 2))

    buckets = {"auto": [], "manual_confirmed": [], "manual_rejected": [], "pending": []}
    skipped = Counter()

    for ka, kb in sorted(candidates):
        a, b = persons[ka], persons[kb]
        cls = classify(a.name, b.name)
        if cls is None:
            skipped["разные ФИО"] += 1
            continue
        kind, base = cls
        city = a.info.get("city")
        namesakes = kind == "exact" and any(
            fullname_counts[(city, a.name.full_key, src)] > 1
            for src in (a.info["source"], b.info["source"])
        )
        score, notes, veto = score_pair(kind, base, a, b, namesakes)
        pair = make_pair(a, b, kind, score, notes)
        same_source = pair["same_source"]

        decision = decisions.get(pair["pair_id"])
        if decision is True:
            buckets["manual_confirmed"].append(pair)
            continue
        if decision is False:
            buckets["manual_rejected"].append(pair)
            continue

        threshold = AUTO_THRESHOLD_EXACT if kind == "exact" else AUTO_THRESHOLD_FUZZY
        if not veto and not same_source and score >= threshold:
            buckets["auto"].append(pair)
        elif score >= REVIEW_THRESHOLD:
            buckets["pending"].append(pair)
        else:
            skipped[f"низкий балл ({kind})"] += 1

    buckets["pending"].sort(key=lambda p: (KIND_ORDER.index(p["kind"]), -p["score"]))
    clusters = build_clusters(buckets, index)
    save_json({**buckets, "clusters": clusters}, MATCHES_PATH)

    # ---------- диагностика ----------
    print(f"[DEBUG] Врачей в индексе: {len(index)}, ФИО не разобрано: {len(unparsed)}, "
          f"пар-кандидатов: {len(candidates)}")
    print(f"[DEBUG] Автосовпадений: {len(buckets['auto'])}, подтверждено: {len(buckets['manual_confirmed'])}, "
          f"отклонено: {len(buckets['manual_rejected'])}, ждут проверки: {len(buckets['pending'])}")
    print(f"[DEBUG] Отброшено: {dict(skipped)}")

    for title, bucket in (("auto", buckets["auto"]), ("pending", buckets["pending"])):
        by_kind = Counter(p["kind"] for p in bucket)
        print(f"    {title}: " + ", ".join(f"{KIND_BASE_TITLES[k]}={by_kind[k]}" for k in KIND_ORDER if by_kind[k]))

    in_clusters = sum(len(c["keys"]) for c in clusters)
    print(f"\n[DEBUG] Кластеров: {len(clusters)} (записей в них {in_clusters}, "
          f"лишних записей {in_clusters - len(clusters)}); требуют проверки: "
          f"{sum(c['needs_review'] for c in clusters)}")
    for c in clusters:
        if c["needs_review"]:
            names = [index[k].get("full_name") for k in c["keys"]]
            print(f"    {c['cluster_id']}: {names}")
            for pr in c["problems"]:
                print(f"        ! {pr}")

    if unparsed:
        save_json([{"key": k, "full_name": index[k].get("full_name"),
                    "profile_url": index[k]["profile_url"]} for k in unparsed], UNPARSED_PATH)
        print(f"\n[DEBUG] Не разобрано ФИО: {len(unparsed)}, список в {UNPARSED_PATH}")

    if buckets["pending"]:
        print("\n=== Ручная проверка ===")
        print(f"Решения вписывай в {MANUAL_DECISIONS_PATH} в виде {{\"pair_id\": true/false}}\n")
    for i, pair in enumerate(buckets["pending"], 1):
        mark = " [ОДИН ИСТОЧНИК]" if pair["same_source"] else ""
        print(f"[{i}/{len(buckets['pending'])}] [{KIND_BASE_TITLES[pair['kind']]}]{mark} "
              f"балл {pair['score']}: {pair['reason']}")
        for d in pair["doctors"]:
            print(f"    {d['source']:<12} {d['full_name']} | {d['university_id'] or d['university']} "
                  f"| {d['graduation_year']}  {d['profile_url']}")
        print(f"    pair_id: {pair['pair_id']}\n")


if __name__ == "__main__":
    main()