from sources.napopravku.browser import get_page, goto_with_retry
from sources.napopravku.config import PAGE_LOAD_TIMEOUT_MS, BETWEEN_PAGES_DELAY_MS, MAX_SHOW_MORE_CLICKS
from sources.napopravku.parser import parse_reviews, parse_doctor_profile
from ids import make_review_id

SHOW_MORE_SELECTOR = ".doctor-review__btn-wrapper button.doctor-review__btn"
SORT_BY_DATE_SELECTOR = "text=по дате"


def _sort_reviews_by_date(page) -> None:
    try:
        page.click(SORT_BY_DATE_SELECTOR, timeout=5_000)
        page.wait_for_timeout(BETWEEN_PAGES_DELAY_MS)
    except Exception:
        print("[WARNING] Не удалось переключить сортировку отзывов на 'по дате' — порядок может быть ненадёжным.")


def fetch_new_reviews(profile_url: str, known_review_ids: set[str]) -> list[dict]:
    with get_page() as page:
        goto_with_retry(page, profile_url, PAGE_LOAD_TIMEOUT_MS)
        page.wait_for_timeout(BETWEEN_PAGES_DELAY_MS)

        first_html = page.content()
        profile = parse_doctor_profile(first_html)

        _sort_reviews_by_date(page)

        clicks = 0
        while True:
            html = page.content()
            all_reviews_so_far = parse_reviews(html, profile_url)
            ids_so_far = {make_review_id(r) for r in all_reviews_so_far}

            if known_review_ids and ids_so_far & known_review_ids:
                print(f"[DEBUG] napopravku: найдены уже известные отзывы после {clicks} кликов 'Показать ещё', останавливаюсь.")
                break

            show_more = page.query_selector(SHOW_MORE_SELECTOR)
            if show_more is None:
                print(f"[DEBUG] napopravku: кнопка 'Показать ещё' исчезла после {clicks} кликов.")
                break

            show_more.click()
            page.wait_for_timeout(BETWEEN_PAGES_DELAY_MS)
            clicks += 1

            if clicks > MAX_SHOW_MORE_CLICKS:
                print("[WARNING] napopravku: превышен лимит кликов 'Показать ещё'.")
                break

        html = page.content()
        all_reviews = parse_reviews(html, profile_url)

    new_reviews = all_reviews if not known_review_ids else [
        r for r in all_reviews if make_review_id(r) not in known_review_ids
    ]
    return new_reviews, profile