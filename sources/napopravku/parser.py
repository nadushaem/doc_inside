import re
from datetime import datetime
from bs4 import BeautifulSoup

SOURCE_NAME = "napopravku"

DATE_PATTERN = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def parse_review_date(date_raw: str | None) -> str | None:
    match = DATE_PATTERN.match((date_raw or "").strip())
    if not match:
        return None
    day, month, year = match.groups()
    return datetime(int(year), int(month), int(day)).isoformat()


def normalize_text(text: str | None) -> str | None:
    if text is None:
        return None
    text = text.replace("\u200b", "")
    return re.sub(r"\s+", " ", text).strip()


def parse_rating(review_card) -> int | None:
    """Считает количество активных звезд в блоке рейтинга конкретного отзыва."""
    rating_block = review_card.select_one(".review__rating .n-rating__wrp")
    if rating_block is None:
        return None
    active_stars = rating_block.select(".n-rating__star--active")
    count = len(active_stars)
    return count if count > 0 else None


def parse_reviews(html: str, doctor_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    reviews = []

    for card in soup.select("div[id^='response']"):
        text_tag = card.select_one(".review__text")
        text = normalize_text(text_tag.get_text(separator=" ", strip=True)) if text_tag else None

        if not text:
            continue

        date_tag = card.select_one(".review__header .review__rating > .review-interaction__description")
        date_raw = date_tag.get_text(strip=True) if date_tag else None

        reviews.append({
            "text": text,
            "source": SOURCE_NAME,
            "doctor_url": doctor_url,
            "date_raw": date_raw,
            "date_iso": parse_review_date(date_raw),
            "rating": parse_rating(card),
            "site_sentiment": None,
        })

    return reviews


def parse_doctor_profile(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    university = None
    graduation_year = None

    for section in soup.select(".doctor-description__section"):
        title = section.select_one(".doctor-description__title")
        if not title or "образован" not in title.get_text(strip=True).lower():
            continue
        for text_block in section.select(".doctor-description__text"):
            if text_block.find_parent("ul") is not None:
                continue
            raw = normalize_text(text_block.get_text(" ", strip=True))
            if not raw:
                continue
            m = re.match(r"(.+?)\s*\((\d{4})\)\s*$", raw)
            if m:
                university, year_str = m.groups()
                graduation_year = int(year_str)
            else:
                university = raw
            break
        break

    return {
        "university": university,
        "graduation_year": graduation_year,
    }