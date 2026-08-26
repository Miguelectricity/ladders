from dataclasses import dataclass
from enum import StrEnum
from backend.models import Job, CountryCode

class SortField(StrEnum):
    SALARY_HOURLY = "salary_hourly"
    SALARY_ANNUAL = "salary_annual"
    POSTING_DATE = "posting_date"
    TITLE = "title"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


DEFAULT_LIMIT = 20
MAX_LIMIT = 100

def _sort_key(job: Job, sort_by: SortField):
    if sort_by == SortField.SALARY_ANNUAL:
        return job.salary.min_annual if job.salary else None
    if sort_by == SortField.SALARY_HOURLY:
        return job.salary.min_hourly if job.salary else None
    if sort_by == SortField.POSTING_DATE:
        return job.posting_date
    title = (job.title or "").strip()
    return title.lower() if title else None

class JobStore:
    def __init__(self) -> None:
        self.approved: list[Job] = []
        self.rejected: list[tuple[Job, list[str]]] = []
    
    def get(self, job_id: str) -> Job | None:
        return next((j for j in self.approved if j.id == job_id), None)

    def search(
        self,
        query: str | None = None,
        country: CountryCode | None = None,
        sort_by: SortField = SortField.POSTING_DATE,
        descending: bool = True,
    ) -> list[Job]:
        results = self.approved

        if query:
            needle = query.strip().lower()
            results = [j for j in results if needle in (j.title or "").lower()]

        if country:
            wanted = country.lower()
            results = [
                j for j in results
                if j.location and (j.location.country_code or "").lower() == wanted
            ]

        # Jobs with no value for the sort field go last, either direction.
        keyed = [(_sort_key(j, sort_by), j) for j in results]
        rankable = [(key, j) for key, j in keyed if key is not None]
        missing = [j for key, j in keyed if key is None]
        rankable.sort(key=lambda pair: pair[0], reverse=descending)
        return [j for _, j in rankable] + missing
    
store = JobStore()