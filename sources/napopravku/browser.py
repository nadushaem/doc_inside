from contextlib import contextmanager
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

from sources.napopravku.config import (
    USER_AGENT, LOCALE, GOTO_RETRIES, GOTO_RETRY_DELAY_MS,
)


@contextmanager
def get_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT, locale=LOCALE)
        page: Page = context.new_page()
        try:
            yield page
        finally:
            browser.close()


def goto_with_retry(page, url: str, timeout: int):
    last_error = None
    for attempt in range(1, GOTO_RETRIES + 1):
        try:
            return page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        except PlaywrightTimeoutError as e:
            last_error = e
            print(f"[WARNING] napopravku: таймаут при загрузке {url} (попытка {attempt}/{GOTO_RETRIES})")
            page.wait_for_timeout(GOTO_RETRY_DELAY_MS)
    raise last_error