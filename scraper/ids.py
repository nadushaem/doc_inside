import hashlib


def make_review_id(review: dict) -> str:
    doctor_url = review.get("doctor_url") or ""
    author = review.get("author") or ""
    date_raw = review.get("date_raw") or ""
    text = review.get("text") or ""

    raw = f"{doctor_url}|{author}|{date_raw}|{text[:50]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]