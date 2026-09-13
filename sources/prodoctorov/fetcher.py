from sources.prodoctorov.browser import get_page
from sources.prodoctorov.config import PAGE_LOAD_TIMEOUT_MS, BETWEEN_PAGES_DELAY_MS, MAX_PAGES_SAFETY_LIMIT
from sources.prodoctorov.parser import parse_reviews, parse_doctor_profile
from ids import make_review_id


def fetch_new_reviews(profile_url: str, known_review_ids: set[str]) -> tuple[list[dict], dict]:
    base_url = profile_url.rstrip("/") + "/otzivi/"
    collected = []
    profile = {}

    with get_page() as page:
        resp = page.goto(profile_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        page.wait_for_timeout(BETWEEN_PAGES_DELAY_MS)
        if resp.status == 200:
            profile = parse_doctor_profile(page.content())
        else:
            print(f"[WARNING] prodoctorov: не удалось открыть профиль {profile_url} (status={resp.status})")

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

    return collected, profile