import re
from scraper.browser import get_page
from scraper.config import BASE_DOMAIN, PAGE_LOAD_TIMEOUT_MS, BETWEEN_PAGES_DELAY_MS, MAX_PAGES_SAFETY_LIMIT

DOCTOR_LINK_PATTERN = re.compile(r"/vrach/(\d+-[^/#?]+)")


def fetch_doctor_slugs(speciality_slug: str, city: str) -> list[str]:
    """Собирает уникальные slug'и всех врачей заданной специальности в городе, обходя пагинацию каталога."""
    base_url = f"{BASE_DOMAIN}/{city}/{speciality_slug}/"
    all_slugs = set()

    with get_page() as page:
        page_num = 1
        while True:
            url = base_url if page_num == 1 else f"{base_url}?page={page_num}"
            resp = page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            page.wait_for_timeout(BETWEEN_PAGES_DELAY_MS)

            links = page.eval_on_selector_all(
                "a[href*='/vrach/']",
                "els => [...new Set(els.map(e => e.href))]"
            )
            page_slugs = {m.group(1) for l in links if (m := DOCTOR_LINK_PATTERN.search(l))}
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

    return sorted(all_slugs)