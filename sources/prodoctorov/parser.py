import re
from datetime import datetime
from bs4 import BeautifulSoup

from sources.prodoctorov.config import MONTHS_RU

SOURCE_NAME = "prodoctorov"


def parse_review_date(date_raw: str | None) -> str | None:
    match = re.match(r"(\d{2}) (\S+) (\d{4}) в (\d{2}):(\d{2})", date_raw or "")
    if not match:
        return None
    day, month_name, year, hour, minute = match.groups()
    month = MONTHS_RU.get(month_name.lower())
    if not month:
        return None
    return datetime(int(year), month, int(day), int(hour), int(minute)).isoformat()


def normalize_text(text: str | None) -> str | None:
    if text is None:
        return None
    text = text.replace("\u200b", "")
    return re.sub(r"\s+", " ", text).strip()


def clean_text_node(tag) -> str | None:
    if tag is None:
        return None
    tag_copy = BeautifulSoup(str(tag), "html.parser")
    for junk in tag_copy.select(".b-review-card__reply-body-more, .b-review-card-rates-show-more"):
        junk.decompose()
    return normalize_text(tag_copy.get_text(separator=" ", strip=True))


def parse_reviews(html: str, doctor_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    reviews = []

    for card in soup.select(".b-review-card"):
        classes = card.get("class", [])
        is_positive = any("positive" in c for c in classes)
        is_negative = any("negative" in c for c in classes)

        comment_tag = card.select_one(".b-review-card__comment")
        date_tag = card.select_one(".b-review-card__datetime")

        text = clean_text_node(comment_tag)
        if not text:
            continue

        date_raw = date_tag.get_text(strip=True) if date_tag else None

        reviews.append({
            "text": text,
            "source": SOURCE_NAME,
            "doctor_url": doctor_url,
            "date_raw": date_raw,
            "date_iso": parse_review_date(date_raw),
            "rating": None,  # на prodoctorov числового рейтинга в HTML нет
            "site_sentiment": "positive" if is_positive else ("negative" if is_negative else "neutral"),
        })

    return reviews


def parse_doctor_profile(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    name_tag = soup.select_one('h1 [itemprop="name"]')
    full_name = normalize_text(name_tag.get_text(" ", strip=True)) if name_tag else None

    university = None
    graduation_year = None
    degree_speciality = None
    current_title = None

    for el in soup.select(".b-doctor-details__data-title, .b-doctor-details__item-description"):
        if "b-doctor-details__data-title" in el.get("class", []):
            current_title = normalize_text(el.get_text(" ", strip=True))
            continue

        label_tag = el.select_one(".text-info--text:last-child")
        label = label_tag.get_text(strip=True).lower() if label_tag else ""
        if "базовое" not in label:
            continue  # ординатура/интернатура/доп. образование пропускаем

        divs = el.find_all("div", recursive=False)
        if len(divs) >= 2:
            year_text = divs[0].get_text(strip=True)
            degree_speciality = normalize_text(divs[1].get_text(" ", strip=True))
            if year_text.isdigit():
                graduation_year = int(year_text)
        university = current_title
        break  # берём первое базовое образование, специалитет обычно один

    return {
        "full_name": full_name,
        "university": university,
        "graduation_year": graduation_year,
        "degree_speciality": degree_speciality,
    }