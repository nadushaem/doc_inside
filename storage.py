import json
import os


def save_json(data, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[DEBUG] Сохранено в {output_path}")


def load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def json_exists(path: str) -> bool:
    return os.path.exists(path)


def merge_reviews(existing: list[dict], new: list[dict], make_id) -> tuple[list[dict], int]:
    existing_ids = {make_id(r) for r in existing}
    added = [r for r in new if make_id(r) not in existing_ids]
    return existing + added, len(added)