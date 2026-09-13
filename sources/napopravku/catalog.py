from sources.base import DoctorRef
from sources.napopravku.browser import get_page, goto_with_retry
from sources.napopravku.config import (
    BASE_DOMAIN, PAGE_LOAD_TIMEOUT_MS, BETWEEN_PAGES_DELAY_MS,
    MAX_PAGES_SAFETY_LIMIT, CITY_SLUGS, SPECIALITY_SLUGS,
)


def list_doctors(speciality_slug: str, city: str) -> list[DoctorRef]:
    """
    Собирает врачей заданной специальности в городе со страниц каталога napopravku.
    speciality_slug/city — внутренние ключи проекта, переводятся в URL-сегменты
    сайта через CITY_SLUGS/SPECIALITY_SLUGS.
    """
    city_slug = CITY_SLUGS.get(city, city)
    spec_slug = SPECIALITY_SLUGS.get(speciality_slug, speciality_slug)
    base_url = f"{BASE_DOMAIN}/{city_slug}/doctors/{spec_slug}/"

    doctors: dict[str, dict] = {}  # site_doctor_id -> {"url": ..., "name": ...}

    with get_page() as page:
        page_num = 1
        while True:
            url = base_url if page_num == 1 else f"{base_url}page-{page_num}/"
            resp = goto_with_retry(page, url, PAGE_LOAD_TIMEOUT_MS)
            page.wait_for_timeout(BETWEEN_PAGES_DELAY_MS)

            cards = page.eval_on_selector_all(
                "div[id^='item-'].doctor-card-v2:not(.doctor-card-v2--telemed)",
                """els => els.map(el => {
                    const link = el.querySelector('.object-info__title-link');
                    return {
                        id: el.id,
                        href: link ? link.href : null,
                        name: link ? link.textContent.trim() : null
                    };
                })"""
            )

            new_count = 0
            for card in cards:
                if not card["href"]:
                    continue
                site_id = card["id"].replace("item-", "")
                if site_id not in doctors:
                    new_count += 1
                doctors[site_id] = {"url": card["href"], "name": card["name"]}

            print(
                f"[DEBUG] Каталог napopravku {speciality_slug}/{city}, страница {page_num}: status={resp.status}, новых={new_count}, итого={len(doctors)}")

            if resp.status != 200 or len(cards) == 0:
                break
            if page_num > 1 and new_count == 0:
                break
            if page_num > MAX_PAGES_SAFETY_LIMIT:
                print("[WARNING] Превышен лимит страниц каталога napopravku.")
                break
            page_num += 1

    return [
        DoctorRef(site_doctor_id=site_id, profile_url=info["url"], full_name=info["name"])
        for site_id, info in sorted(doctors.items())
    ]