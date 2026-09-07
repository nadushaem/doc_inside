USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
LOCALE = "ru-RU"

BASE_DOMAIN = "https://prodoctorov.ru"

PAGE_LOAD_TIMEOUT_MS = 30_000
BETWEEN_PAGES_DELAY_MS = 3_000  # увеличил с 2 до 3 сек — при 830 врачах вежливость важнее скорости
MAX_PAGES_SAFETY_LIMIT = 60

MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

CITIES = ["ekaterinburg"]

SPECIALITIES = {
    "ginekolog": "Акушер-гинеколог",
    "kosmetolog": "Косметолог",
    "endokrinolog": "Эндокринолог",
    "plasticheskiy-hirurg": "Пластический хирург",
}