from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def goto_with_retry(page, url: str, timeout: int, retries: int = 3, retry_delay_ms: int = 5_000):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        except PlaywrightTimeoutError as e:
            last_error = e
            print(f"[WARNING] таймаут при загрузке {url} (попытка {attempt}/{retries})")
            page.wait_for_timeout(retry_delay_ms)
    raise last_error