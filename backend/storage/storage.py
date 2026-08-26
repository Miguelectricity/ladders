from collections import OrderedDict
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


DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100

# Bounded so that distinct `?query=` strings can't grow the cache without limit.
CACHE_MAX_ENTRIES = 32

# (normalized query, normalized country, remote, sort field, descending)
type _CacheKey = tuple[str | None, str | None, bool | None, "SortField", bool]


@dataclass(frozen=True)
class Page[T]:
    """One window into a result set, plus the total so the UI can draw page controls."""
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size

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
        self._approved: list[Job] = []
        self.rejected: list[tuple[Job, list[str]]] = []
        # Filter+sort results, keyed by the query that produced them. Paging
        # through a result set is then a slice rather than a re-sort.
        self._ordered_cache: OrderedDict[_CacheKey, list[Job]] = OrderedDict()

    @property
    def approved(self) -> list[Job]:
        return self._approved

    @approved.setter
    def approved(self, jobs: list[Job]) -> None:
        self._approved = jobs
        self.invalidate_cache()

    def invalidate_cache(self) -> None:
        """Drop every memoized ordering.

        The setter calls this, so reassigning `approved` is safe. Mutating the
        list in place (`store.approved.append(...)`) is not seen — call this
        yourself after doing that.
        """
        self._ordered_cache.clear()

    def get(self, job_id: str) -> Job | None:
        return next((j for j in self._approved if j.id == job_id), None)

    def _ordered(self, key: _CacheKey) -> list[Job]:
        """The full filtered, sorted result set for one query. Memoized."""
        cached = self._ordered_cache.get(key)
        if cached is not None:
            self._ordered_cache.move_to_end(key)
            return cached

        normalized_query, normalized_country, remote, sort_by, descending = key
        results = self._approved

        if normalized_query:
            results = [j for j in results if normalized_query in (j.title or "").lower()]

        if normalized_country:
            results = [
                j for j in results
                if j.location and (j.location.country_code or "").lower() == normalized_country
            ]

        # Independent of country: a remote job in Toronto answers to both. An
        # unknown arrangement counts as not remote, as it does in approval.
        if remote is not None:
            results = [j for j in results if bool(j.is_remote) is remote]

        # Jobs with no value for the sort field go last, either direction.
        keyed = [(_sort_key(j, sort_by), j) for j in results]
        rankable = [(k, j) for k, j in keyed if k is not None]
        missing = [j for k, j in keyed if k is None]
        rankable.sort(key=lambda pair: pair[0], reverse=descending)
        ordered = [j for _, j in rankable] + missing

        self._ordered_cache[key] = ordered
        if len(self._ordered_cache) > CACHE_MAX_ENTRIES:
            self._ordered_cache.popitem(last=False)  # evict least recently used
        return ordered

    def search(
        self,
        query: str | None = None,
        country: CountryCode | None = None,
        remote: bool | None = None,
        sort_by: SortField = SortField.POSTING_DATE,
        descending: bool = True,
        page: int = 0,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Page[Job]:
        # Normalizing into the key means "  ENGINEER " and "engineer" share an entry.
        ordered = self._ordered((
            query.strip().lower() or None if query else None,
            country.lower() if country else None,
            remote,
            sort_by,
            descending,
        ))

        # Slice only after filtering and sorting, so `total` counts every match
        # and page N means the same thing from one request to the next.
        page = max(page, 0)
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        start = page * page_size
        return Page(
            items=ordered[start : start + page_size],
            total=len(ordered),
            page=page,
            page_size=page_size,
        )
    
store = JobStore()