# dedupe.py
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from itertools import combinations

from storage import load_json, save_json, json_exists

INDEX_PATH = "data/processed/doctors/index.json"
MATCHES_PATH = "data/processed/doctors/matches.json"
MANUAL_DECISIONS_PATH = "data/processed/doctors/manual_decisions.json"

UNI_SIMILARITY_THRESHOLD = 0.8
SURNAME_TYPO_THRESHOLD = 0.85

UNI_STOPWORDS = {
    "фгбоу", "гбоу", "гоу", "фгоу", "во", "впо", "федеральное", "государственное",
    "бюджетное", "образовательное", "учреждение", "высшего", "профессионального",
    "образования", "минздрава", "минздравсоцразвития", "россии", "рф",
    "министерства", "здравоохранения", "российской", "федерации", "имени", "им",
}

# латинские буквы, которые выглядят как кириллические (после lower())
HOMOGLYPHS = str.maketrans("aeopcxykmthb", "аеорсхукмтнв")

# варианты, которые не ловит общее правило в canon()
NAME_ALIASES = {
    "ильична": "ильинична",
    "кузьмична": "кузьминична",
    "фомична": "фоминична",
    "лукична": "лукинична",
}

PATRONYMIC_RE = re.compile(r"(вич|вна|чна|оглы|кызы|улы)$")
FEMALE_SURNAME_RE = re.compile(r"(ова|ева|ина|ына|ая|айте|ене|уте)$")

PATRONYMIC_TYPO_THRESHOLD = 0.8
UNPARSED_PATH = "data/processed/doctors/unparsed_names.json"

# порядок вывода на ручную проверку
KIND_ORDER = ["exact", "double_surname", "maiden_bracket", "typo", "patronymic_typo", "surname_change"]
KIND_TITLES = {
    "exact": "полное совпадение ФИО",
    "double_surname": "двойная фамилия",
    "maiden_bracket": "девичья фамилия в скобках",
    "typo": "возможная опечатка в фамилии",
    "patronymic_typo": "возможная опечатка в отчестве",
    "surname_change": "возможная смена фамилии",
}


# ---------- имена ----------

def canon(token: str) -> str:
    """Ключ для сравнения: Наталья/Наталия, Юрьевна/Юриевна и т.п. дают одно и то же."""
    token = NAME_ALIASES.get(token, token)
    token = token.replace("ь", "").replace("ъ", "")
    token = re.sub(r"и(?=[аеиоуыэюя])", "", token)
    return token


def _clean(s: str) -> str:
    s = s.lower().replace("ё", "е").translate(HOMOGLYPHS)
    s = re.sub(r"[^а-я\s-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _parts(tokens: list[str]) -> set[str]:
    return {canon(p) for t in tokens for p in t.split("-") if p}


def parse_full_name(raw: str | None) -> dict | None:
    if not raw:
        return None
    lowered = raw.lower().replace("ё", "е").translate(HOMOGLYPHS)
    maiden_raw = " ".join(re.findall(r"\((.*?)\)", lowered))
    tokens = _clean(re.sub(r"\(.*?\)", " ", lowered)).split()
    if len(tokens) < 2:
        return None

    patr_idx = next((i for i, t in enumerate(tokens) if i >= 1 and PATRONYMIC_RE.search(t)), None)
    patronymic_guessed = False

    if patr_idx is None:
        if len(tokens) == 2:
            surname_tokens, name, patronymic = [tokens[0]], tokens[1], ""
        elif len(tokens) == 3:
            # нестандартное отчество (Вито, Андраники, Жамыбекова) или опечатка:
            # берём основной формат сайтов «Фамилия Имя Отчество»
            surname_tokens, name, patronymic = [tokens[0]], tokens[1], tokens[2]
            patronymic_guessed = True
        else:
            return None
    elif patr_idx >= 2:                       # Фамилия Имя Отчество [мусор]
        surname_tokens, name, patronymic = tokens[:patr_idx - 1], tokens[patr_idx - 1], tokens[patr_idx]
    else:                                     # Имя Отчество Фамилия
        surname_tokens, name, patronymic = tokens[2:3], tokens[0], tokens[1]

    if not surname_tokens:
        return None

    surname_key = " ".join(canon(t) for t in surname_tokens)
    name_c, patr_c = canon(name), canon(patronymic)

    if patronymic_guessed:
        is_female = bool(FEMALE_SURNAME_RE.search(surname_tokens[-1])) or patronymic.endswith("а")
    else:
        is_female = patronymic.endswith(("на", "кызы"))

    return {
        "surname_key": surname_key,
        "surname_parts": _parts(surname_tokens),
        "maiden_parts": _parts(_clean(maiden_raw).split()) if maiden_raw else set(),
        "name_key": f"{name_c} {patr_c}".strip(),
        "surname_name_key": f"{surname_key} {name_c}",
        "patronymic_key": patr_c,
        "full_key": f"{surname_key} {name_c} {patr_c}".strip(),
        "has_patronymic": bool(patronymic),
        "patronymic_guessed": patronymic_guessed,
        "is_female": is_female,
    }


# ---------- образование ----------

def get_education(info: dict) -> tuple[str | None, int | None]:
    uni, year = info.get("university"), info.get("graduation_year")
    if uni and not year:  # "Уральская ... академия, 2006" / "... (2006)"
        m = re.search(r"[,\s(]+(\d{4})\)?\s*$", uni)
        if m:
            year, uni = int(m.group(1)), uni[:m.start()].strip()
    return uni, year


def normalize_university(uni: str | None) -> str | None:
    if not uni:
        return None
    uni = uni.lower().replace("ё", "е")
    uni = re.sub(r"[^а-яa-z0-9\s]", " ", uni)
    tokens = [t for t in uni.split() if t not in UNI_STOPWORDS]
    return " ".join(tokens) or None


def university_similarity(a: str | None, b: str | None) -> float | None:
    a, b = normalize_university(a), normalize_university(b)
    if not a or not b:
        return None
    return SequenceMatcher(None, a, b).ratio()


def compare_education(a: dict, b: dict) -> tuple[bool, str]:
    uni_a, year_a = get_education(a)
    uni_b, year_b = get_education(b)
    if year_a and year_b and year_a != year_b:
        return False, f"разные годы выпуска: {year_a} vs {year_b}"

    sim = university_similarity(uni_a, uni_b)
    if sim is None:
        return False, "образование не указано на одном из сайтов"
    if sim >= UNI_SIMILARITY_THRESHOLD:
        return True, f"вуз совпал (сходство {sim:.2f})"
    return False, f"вузы различаются (сходство {sim:.2f})"


def classify_surname_mismatch(pa: dict, pb: dict, a: dict, b: dict) -> tuple[str | None, str | None]:
    """Имя+отчество совпали, фамилии разные. Возвращает (kind, reason) или (None, None), если это просто тёзки."""
    if pa["surname_parts"] & pb["surname_parts"]:
        return "double_surname", "у фамилий есть общая часть"
    if pa["maiden_parts"] & pb["surname_parts"] or pb["maiden_parts"] & pa["surname_parts"]:
        return "maiden_bracket", "девичья фамилия совпала с фамилией на другом сайте"

    sim = SequenceMatcher(None, pa["surname_key"], pb["surname_key"]).ratio()
    if sim >= SURNAME_TYPO_THRESHOLD:
        return "typo", f"фамилии похожи (сходство {sim:.2f})"

    # смена фамилии: без сильных сигналов это просто тёзки по имени-отчеству
    if not (pa["is_female"] and pb["is_female"]):
        return None, None
    uni_a, year_a = get_education(a)
    uni_b, year_b = get_education(b)
    if not (year_a and year_b and year_a == year_b):
        return None, None
    uni_sim = university_similarity(uni_a, uni_b)
    if uni_sim is not None and uni_sim < UNI_SIMILARITY_THRESHOLD:
        return None, None
    if not set(a["specialities"]) & set(b["specialities"]):
        return None, None
    return "surname_change", f"разные фамилии, но совпали год выпуска ({year_a}) и специальность"


# ---------- пары ----------

def pair_id(key_a: str, key_b: str) -> str:
    return "|".join(sorted([key_a, key_b]))


def make_pair(key_a, a, key_b, b, reason, kind) -> dict:
    def doc(key, info):
        uni, year = get_education(info)
        return {"key": key, "source": info["source"], "profile_url": info["profile_url"],
                "full_name": info.get("full_name"), "university": uni, "graduation_year": year}

    return {
        "pair_id": pair_id(key_a, key_b),
        "kind": kind,
        "doctors": [doc(key_a, a), doc(key_b, b)],
        "reason": reason,
    }


def main():
    index = load_json(INDEX_PATH)
    decisions = load_json(MANUAL_DECISIONS_PATH) if json_exists(MANUAL_DECISIONS_PATH) else {}

    parsed, unparsed = {}, []
    for key, info in index.items():
        p = parse_full_name(info.get("full_name"))
        if p is None:
            unparsed.append((key, info.get("full_name")))
        else:
            parsed[key] = p

    exact_groups, name_groups, surname_name_groups = defaultdict(list), defaultdict(list), defaultdict(list)
    for key, p in parsed.items():
        city = index[key].get("city")
        exact_groups[(p["full_key"], city)].append(key)
        if p["has_patronymic"]:
            name_groups[(p["name_key"], city)].append(key)
            surname_name_groups[(p["surname_name_key"], city)].append(key)

    buckets = {"auto": [], "manual_confirmed": [], "manual_rejected": [], "pending": []}

    def route(key_a, key_b, is_match, reason, kind):
        pair = make_pair(key_a, index[key_a], key_b, index[key_b], reason, kind)
        decision = decisions.get(pair["pair_id"])
        if decision is True:
            buckets["manual_confirmed"].append(pair)
        elif decision is False:
            buckets["manual_rejected"].append(pair)
        elif is_match:
            buckets["auto"].append(pair)
        else:
            buckets["pending"].append(pair)

    # 1. полное совпадение ФИО
    exact_matched = set()
    for keys in exact_groups.values():
        per_source = Counter(index[k]["source"] for k in keys)
        if len(per_source) < 2:
            continue
        has_namesakes = any(c > 1 for c in per_source.values())
        for a, b in combinations(keys, 2):
            if index[a]["source"] == index[b]["source"]:
                continue
            is_match, reason = compare_education(index[a], index[b])
            if has_namesakes:
                is_match, reason = False, f"несколько тёзок; {reason}"
            exact_matched.update((a, b))
            route(a, b, is_match, reason, "exact")

    # 2. имя+отчество совпали, фамилия разная — только ручная проверка
    skipped_namesakes = 0
    for keys in name_groups.values():
        for a, b in combinations(keys, 2):
            A, B = index[a], index[b]
            if A["source"] == B["source"] or a in exact_matched or b in exact_matched:
                continue
            if parsed[a]["full_key"] == parsed[b]["full_key"]:
                continue
            kind, reason = classify_surname_mismatch(parsed[a], parsed[b], A, B)
            if kind is None:
                skipped_namesakes += 1
                continue
            route(a, b, False, reason, kind)

    # 3. фамилия+имя совпали, отчества похожи (опечатка) — только ручная проверка
    for keys in surname_name_groups.values():
        for a, b in combinations(keys, 2):
            A, B = index[a], index[b]
            if A["source"] == B["source"] or a in exact_matched or b in exact_matched:
                continue
            pa, pb = parsed[a], parsed[b]
            if pa["full_key"] == pb["full_key"]:
                continue
            sim = SequenceMatcher(None, pa["patronymic_key"], pb["patronymic_key"]).ratio()
            if sim >= PATRONYMIC_TYPO_THRESHOLD:
                route(a, b, False, f"отчества похожи (сходство {sim:.2f})", "patronymic_typo")

    buckets["pending"].sort(key=lambda p: (KIND_ORDER.index(p["kind"]), p["doctors"][0]["full_name"] or ""))
    save_json(buckets, MATCHES_PATH)

    # ---------- диагностика ----------
    print(f"[DEBUG] Врачей в индексе: {len(index)}, не удалось разобрать ФИО: {len(unparsed)}")
    print(f"[DEBUG] Автосовпадений: {len(buckets['auto'])}, подтверждено вручную: {len(buckets['manual_confirmed'])}, "
          f"отклонено: {len(buckets['manual_rejected'])}, ждут проверки: {len(buckets['pending'])}")
    print(f"[DEBUG] Пар «то же имя-отчество, другая фамилия» без доп. сигналов (пропущены): {skipped_namesakes}")

    pending_by_kind = Counter(p["kind"] for p in buckets["pending"])
    for kind in KIND_ORDER:
        if pending_by_kind[kind]:
            print(f"    {KIND_TITLES[kind]}: {pending_by_kind[kind]}")

    matched_keys = {d["key"] for b in ("auto", "manual_confirmed") for p in buckets[b] for d in p["doctors"]}
    pending_keys = {d["key"] for p in buckets["pending"] for d in p["doctors"]}
    print("\n[DEBUG] По источникам:")
    for source, total in Counter(i["source"] for i in index.values()).most_common():
        keys = {k for k, i in index.items() if i["source"] == source}
        print(f"    {source:<12} всего {total:>5}, склеено {len(keys & matched_keys):>5}, "
              f"на проверке {len(keys & pending_keys):>5}")

    if unparsed:
        save_json([{"key": k, "full_name": n, "profile_url": index[k]["profile_url"]} for k, n in unparsed],
                  UNPARSED_PATH)
        print(f"\n[DEBUG] Не удалось разобрать ФИО: {len(unparsed)}, список в {UNPARSED_PATH}")
        for key, name in unparsed[:20]:
            print(f"    {key}: {name!r}  {index[key]['profile_url']}")

    if buckets["pending"]:
        print("\n=== Ручная проверка ===")
        print(f"Решения вписывай в {MANUAL_DECISIONS_PATH} в виде {{\"pair_id\": true/false}}\n")
    for i, pair in enumerate(buckets["pending"], 1):
        print(f"[{i}/{len(buckets['pending'])}] [{KIND_TITLES[pair['kind']]}] {pair['reason']}")
        for d in pair["doctors"]:
            print(f"    {d['source']:<12} {d['full_name']}  {d['profile_url']}")
        print(f"    pair_id: {pair['pair_id']}\n")


if __name__ == "__main__":
    main()