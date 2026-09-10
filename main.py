from sources.prodoctorov.adapter import ProdoctorovSource
from storage import save_json, load_json, json_exists, merge_reviews
from config import SPECIALITIES, CITIES, DOCTORS_PER_SPECIALITY_LIMIT
from ids import make_review_id

ACTIVE_SOURCES = [ProdoctorovSource()]

INDEX_PATH = "data/processed/doctors/index.json"
doctor_index = load_json(INDEX_PATH) if json_exists(INDEX_PATH) else {}

targets = [(spec, city) for spec in SPECIALITIES for city in CITIES]

for source in ACTIVE_SOURCES:
    for speciality_slug, city in targets:
        index_key_prefix = f"{source.name}:"
        known_refs_for_speciality = {
            key.removeprefix(index_key_prefix)
            for key, info in doctor_index.items()
            if key.startswith(index_key_prefix)
            and speciality_slug in info["specialities"]
            and info["city"] == city
        }

        fresh_doctors = source.list_doctors(speciality_slug, city)
        fresh_ids = {d.site_doctor_id for d in fresh_doctors}
        new_ids = fresh_ids - known_refs_for_speciality

        print(f"[DEBUG] {source.name}/{speciality_slug}/{city}: всего {len(fresh_ids)}, новых врачей {len(new_ids)}")

        for doctor in fresh_doctors:
            index_key = f"{source.name}:{doctor.site_doctor_id}"
            entry = doctor_index.setdefault(index_key, {
                "source": source.name,
                "site_doctor_id": doctor.site_doctor_id,
                "profile_url": doctor.profile_url,
                "city": city,
                "specialities": [],
            })
            if speciality_slug not in entry["specialities"]:
                entry["specialities"].append(speciality_slug)

        doctors_to_process = sorted(fresh_doctors, key=lambda d: d.site_doctor_id)
        if DOCTORS_PER_SPECIALITY_LIMIT is not None:
            doctors_to_process = doctors_to_process[:DOCTORS_PER_SPECIALITY_LIMIT]
            print(f"[DEBUG] Тестовый режим: беру только {len(doctors_to_process)} врачей из {len(fresh_doctors)}")

        for doctor in doctors_to_process:
            reviews_path = f"data/processed/reviews/{source.name}/{doctor.site_doctor_id}.json"
            existing_reviews = load_json(reviews_path) if json_exists(reviews_path) else []
            known_ids = {make_review_id(r) for r in existing_reviews}

            new_reviews = source.fetch_new_reviews(doctor, known_ids)

            merged, added_count = merge_reviews(existing_reviews, new_reviews, make_review_id)
            if added_count > 0:
                save_json(merged, reviews_path)
                print(f"[DEBUG] {doctor.site_doctor_id}: добавлено {added_count} новых отзывов")
            else:
                print(f"[DEBUG] {doctor.site_doctor_id}: новых отзывов нет")

save_json(doctor_index, INDEX_PATH)