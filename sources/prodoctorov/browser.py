from contextlib import contextmanager

from playwright.sync_api import Page, sync_playwright

from sources.prodoctorov.config import LOCALE, USER_AGENT


@contextmanager
def get_page():
    """Контекстный менеджер: отдаёт готовую Playwright-страницу, сам закрывает браузер по выходу."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT, locale=LOCALE)
        page: Page = context.new_page()
        try:
            yield page
        finally:
            browser.close()
