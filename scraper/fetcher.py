from scraper.browser import get_page
from scraper.config import (
    BASE_DOMAIN,
    PAGE_LOAD_TIMEOUT_MS,
    BETWEEN_PAGES_DELAY_MS,
    MAX_PAGES_SAFETY_LIMIT,
)
from scraper.parser import parse_reviews
from scraper.ids import make_review_id


def fetch_all_reviews_html(doctor_slug: str, city: str = "ekaterinburg") -> list[str]:
    """Скачивает HTML всех страниц пагинации отзывов конкретного врача."""
    base_url = f"{BASE_DOMAIN}/{city}/vrach/{doctor_slug}/otzivi/"
    pages_html = []

    with get_page() as page:
        page_num = 1
        while True:
            url = base_url if page_num == 1 else f"{base_url}{page_num}/"
            resp = page.goto(url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
            page.wait_for_timeout(BETWEEN_PAGES_DELAY_MS)

            count = page.eval_on_selector_all(".b-review-card", "els => els.length")
            print(f"[DEBUG] Страница {page_num}: status={resp.status}, карточек={count}")

            if resp.status != 200 or count == 0:
                break

            pages_html.append(page.content())

            if page_num > MAX_PAGES_SAFETY_LIMIT:
                print("[WARNING] Превышен лимит страниц.")
                break

            page_num += 1

    return pages_html


def fetch_new_reviews_html(doctor_slug: str, known_review_ids: set[str], city: str = "ekaterinburg") -> list[str]:
    """
    Как fetch_all_reviews_html, но останавливается, как только на странице
    встречается хотя бы один уже известный review_id — считаем, что дальше
    все отзывы уже собраны в прошлые разы (пагинация идёт от новых к старым).
    Если known_review_ids пуст (первый сбор) — ведёт себя как полный обход.
    """
    base_url = f"{BASE_DOMAIN}/{city}/vrach/{doctor_slug}/otzivi/"
    pages_html = []

    with get_page() as page:
        page_num = 1
        while True:
            url = base_url if page_num == 1 else f"{base_url}{page_num}/"
            resp = page.goto(url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
            page.wait_for_timeout(BETWEEN_PAGES_DELAY_MS)

            count = page.eval_on_selector_all(".b-review-card", "els => els.length")
            print(f"[DEBUG] Страница {page_num}: status={resp.status}, карточек={count}")

            if resp.status != 200 or count == 0:
                break

            html = page.content()
            pages_html.append(html)

            # проверяем пересечение с уже известными отзывами
            page_reviews = parse_reviews(html, build_doctor_url(doctor_slug, city))
            page_ids = {make_review_id(r) for r in page_reviews}

            if known_review_ids and page_ids & known_review_ids:
                print(f"[DEBUG] Найдены уже известные отзывы на странице {page_num}, останавливаюсь.")
                break

            if page_num > MAX_PAGES_SAFETY_LIMIT:
                break
            page_num += 1

    return pages_html


def build_doctor_url(doctor_slug: str, city: str = "ekaterinburg") -> str:
    return f"{BASE_DOMAIN}/{city}/vrach/{doctor_slug}/"