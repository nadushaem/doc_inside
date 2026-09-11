USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
LOCALE = "ru-RU"

BASE_DOMAIN = "https://napopravku.ru"

PAGE_LOAD_TIMEOUT_MS = 30_000
BETWEEN_PAGES_DELAY_MS = 3_000
MAX_PAGES_SAFETY_LIMIT = 60          # для каталога (постраничная пагинация)
MAX_SHOW_MORE_CLICKS = 60            # для отзывов ("Показать ещё")

CITY_SLUGS = {
    "ekaterinburg": "ekb",
}

SPECIALITY_SLUGS = {
    "ginekolog": "ginekolog",
    "kosmetolog": "kosmetolog",
    "endokrinolog": "endokrinolog",
    "plasticheskiy-hirurg": "plasticheskiy-hirurg",
}

GOTO_RETRIES = 3
GOTO_RETRY_DELAY_MS = 5_000