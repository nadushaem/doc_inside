from sources.prodoctorov.browser import get_page
from sources.prodoctorov.config import PAGE_LOAD_TIMEOUT_MS, BETWEEN_PAGES_DELAY_MS, MAX_PAGES_SAFETY_LIMIT
from sources.prodoctorov.parser import parse_reviews
from ids import make_review_id


def fetch_new_reviews(profile_url: str, known_review_ids: set[str]) -> list[dict]:
    """
    Идёт по страницам пагинации отзывов врача (от новых к старым) и сразу
    парсит их в готовые словари. Останавливается, как только встречает
    страницу с уже известным review_id. Если known_review_ids пуст —
    ведёт себя как полный обход.
    """
    base_url = profile_url.rstrip("/") + "/otzivi/"
    collected = []

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

            page_reviews = parse_reviews(page.content(), profile_url)
            page_ids = {make_review_id(r) for r in page_reviews}

            if known_review_ids and page_ids & known_review_ids:
                print(f"[DEBUG] Найдены уже известные отзывы на странице {page_num}, останавливаюсь.")
                new_on_this_page = [r for r in page_reviews if make_review_id(r) not in known_review_ids]
                collected.extend(new_on_this_page)
                break

            collected.extend(page_reviews)

            if page_num > MAX_PAGES_SAFETY_LIMIT:
                print("[WARNING] Превышен лимит страниц.")
                break
            page_num += 1

    return collected