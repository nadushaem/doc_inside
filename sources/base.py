from typing import Protocol, NamedTuple


class DoctorRef(NamedTuple):
    """Ссылка на врача внутри конкретного источника."""
    site_doctor_id: str
    profile_url: str


class Source(Protocol):
    """Контракт, который обязан реализовать каждый источник данных."""

    name: str  # уникальное имя источника, напр. "prodoctorov"

    def list_doctors(self, speciality_slug: str, city: str) -> list[DoctorRef]:
        """Список врачей заданной специальности в городе."""
        ...

    def fetch_new_reviews(
        self,
        doctor: DoctorRef,
        known_review_ids: set[str],
    ) -> list[dict]:
        """
        Новые отзывы врача, которых ещё нет в known_review_ids.
        Каждый отзыв — словарь с полями:
        text (обяз.), source (обяз.), doctor_url (обяз.),
        date_raw, date_iso, rating (опц.), site_sentiment (опц.)
        """
        ...