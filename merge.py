# merge.py
import hashlib
from storage import load_json, save_json

INDEX_PATH = "data/processed/doctors/index.json"
MATCHES_PATH = "data/processed/doctors/matches.json"
MERGED_PATH = "data/processed/doctors/merged.json"


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def make_person_id(cluster_keys: list[str]) -> str:
    """Хэш от отсортированных ключей источников — детерминирован, не зависит от порядка обработки."""
    raw = "|".join(sorted(cluster_keys))
    return "person_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def main():
    index = load_json(INDEX_PATH)
    matches = load_json(MATCHES_PATH)

    uf = UnionFind()
    for key in index:
        uf.find(key)
    for pair in matches["auto"] + matches["manual_confirmed"]:
        k1, k2 = pair["doctors"][0]["key"], pair["doctors"][1]["key"]
        uf.union(k1, k2)

    clusters: dict[str, list[str]] = {}
    for key in index:
        root = uf.find(key)
        clusters.setdefault(root, []).append(key)

    merged = {}
    for keys in clusters.values():
        person_id = make_person_id(keys)
        entries = [index[k] for k in keys]
        best = max(entries, key=lambda e: (
            bool(e.get("full_name")), bool(e.get("university")), bool(e.get("graduation_year"))
        ))
        merged[person_id] = {
            "full_name": best.get("full_name"),
            "university": best.get("university"),
            "graduation_year": best.get("graduation_year"),
            "city": best.get("city"),
            "specialities": sorted({s for e in entries for s in e["specialities"]}),
            "sources": [
                {"source": e["source"], "site_doctor_id": e["site_doctor_id"], "profile_url": e["profile_url"]}
                for e in entries
            ],
        }

    save_json(merged, MERGED_PATH)
    print(f"[DEBUG] Врачей в индексе: {len(index)}, уникальных персон после склейки: {len(merged)}")


if __name__ == "__main__":
    main()