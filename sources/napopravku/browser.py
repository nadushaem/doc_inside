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