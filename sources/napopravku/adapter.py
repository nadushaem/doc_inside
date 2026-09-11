from sources.base import DoctorRef
from sources.napopravku import catalog, fetcher
from sources.napopravku.parser import SOURCE_NAME


class NapopravkuSource:
    name = SOURCE_NAME

    def list_doctors(self, speciality_slug: str, city: str) -> list[DoctorRef]:
        return catalog.list_doctors(speciality_slug, city)

    def fetch_new_reviews(self, doctor: DoctorRef, known_review_ids: set[str]) -> list[dict]:
        return fetcher.fetch_new_reviews(doctor.profile_url, known_review_ids)