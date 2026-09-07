from scraper.catalog import fetch_doctor_slugs
from scraper.fetcher import fetch_new_reviews_html, build_doctor_url
from scraper.parser import parse_reviews
from storage import save_json, load_json, json_exists, merge_reviews
from scraper.config import SPECIALITIES, CITIES
from scraper.ids import make_review_id

DOCTORS_PER_SPECIALITY_LIMIT = 5

INDEX_PATH = "data/processed/doctors/index.json"
doctor_index = load_json(INDEX_PATH) if json_exists(INDEX_PATH) else {}

targets = [(spec, city) for spec in SPECIALITIES for city in CITIES]

for speciality_slug, city in targets:
    known_slugs_for_speciality = {
        slug for slug, info in doctor_index.items()
        if speciality_slug in info["specialities"] and info["city"] == city
    }

    fresh_slugs = set(fetch_doctor_slugs(speciality_slug, city))
    new_doctors = fresh_slugs - known_slugs_for_speciality

    print(f"[DEBUG] {speciality_slug}/{city}: всего {len(fresh_slugs)}, новых врачей {len(new_doctors)}")

    for slug in fresh_slugs:
        entry = doctor_index.setdefault(slug, {"city": city, "specialities": []})
        if speciality_slug not in entry["specialities"]:
            entry["specialities"].append(speciality_slug)

    slugs_to_process = sorted(fresh_slugs)
    if DOCTORS_PER_SPECIALITY_LIMIT is not None:
        slugs_to_process = slugs_to_process[:DOCTORS_PER_SPECIALITY_LIMIT]
        print(f"[DEBUG] Тестовый режим: беру только {len(slugs_to_process)} врачей из {len(fresh_slugs)}")

    for slug in slugs_to_process:
        reviews_path = f"data/processed/reviews/{slug}.json"
        existing_reviews = load_json(reviews_path) if json_exists(reviews_path) else []
        known_ids = {make_review_id(r) for r in existing_reviews}

        doctor_url = build_doctor_url(slug, city)
        pages_html = fetch_new_reviews_html(slug, known_ids, city)

        new_reviews = []
        for html in pages_html:
            new_reviews.extend(parse_reviews(html, doctor_url))

        merged, added_count = merge_reviews(existing_reviews, new_reviews, make_review_id)
        if added_count > 0:
            save_json(merged, reviews_path)
            print(f"[DEBUG] {slug}: добавлено {added_count} новых отзывов")
        else:
            print(f"[DEBUG] {slug}: новых отзывов нет")

save_json(doctor_index, INDEX_PATH)