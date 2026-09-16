import re
from sources.base import DoctorRef
from sources.prodoctorov.browser import get_page
from sources.prodoctorov.config import (
    BASE_DOMAIN, PAGE_LOAD_TIMEOUT_MS, BETWEEN_PAGES_DELAY_MS, MAX_PAGES_SAFETY_LIMIT,
)

DOCTOR_LINK_PATTERN = re.compile(r"/vrach/(\d+-[^/#?]+)")


def build_doctor_url(doctor_slug: str, city: str) -> str:
    return f"{BASE_DOMAIN}/{city}/vrach/{doctor_slug}/"


def list_doctors(speciality_slug: str, city: str) -> list[DoctorRef]:
    """Собирает уникальные slug'и всех врачей заданной специальности в городе."""
    base_url = f"{BASE_DOMAIN}/{city}/{speciality_slug}/"
    all_slugs = set()
    names: dict[str, str] = {}  # slug -> full_name (берём самый длинный вариант текста)

    with get_page() as page:
        page_num = 1
        while True:
            url = base_url if page_num == 1 else f"{base_url}?page={page_num}"
            resp = page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            page.wait_for_timeout(BETWEEN_PAGES_DELAY_MS)

            links = page.eval_on_selector_all(
                "a[href*='/vrach/']",
                """els => els.map(e => ({
                    href: e.href,
                    text: e.textContent.replace(/\\s+/g, ' ').trim()
                }))"""
            )
            page_slugs = set()
            for l in links:
                m = DOCTOR_LINK_PATTERN.search(l["href"])
                if not m:
                    continue
                slug = m.group(1)
                page_slugs.add(slug)
                if l["text"] and len(l["text"]) > len(names.get(slug, "")):
                    names[slug] = l["text"]

            new_count = len(page_slugs - all_slugs)
            print(f"[DEBUG] Каталог {speciality_slug}/{city}, страница {page_num}: status={resp.status}, новых={new_count}, итого={len(all_slugs) + new_count}")

            if resp.status != 200 or len(page_slugs) == 0:
                break
            if page_num > 1 and new_count == 0:
                break

            all_slugs.update(page_slugs)

            if page_num > MAX_PAGES_SAFETY_LIMIT:
                print("[WARNING] Превышен лимит страниц каталога.")
                break
            page_num += 1

    return [
        DoctorRef(site_doctor_id=slug, profile_url=build_doctor_url(slug, city), full_name=names.get(slug))
        for slug in sorted(all_slugs)
    ]