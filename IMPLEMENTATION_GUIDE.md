# Storage + API Implementation Guide

A step-by-step build plan for the two remaining pieces: **storing** approved jobs and
**serving** them to the React frontend. Written so you can type every line yourself and
understand why it's there.

---

## Part 0 — Where you are right now

I ran your pipeline against `backend/data/mock/jobs.json`. It works:

```
parsed:   20
approved: 11
rejected:  9   (3 not full-time, 1 staffing firm, 1 missing title, 3 no market, 1 not full-time)
```

What exists and is good:

| Layer | Status |
|---|---|
| `models/Job.py` | Solid. Enums + dataclasses, nullable-by-default, `raw` kept on `Salary`/`Location`. |
| `models/Market.py` | Good call. Policy-as-data is exactly the "flexible, add UK-remote-at-90k later" hook the brief asks for. |
| `ingestion/parsers/` | Good. Each parser is pure `Any -> domain type`, easy to test. |
| `ingestion/job_id_hash.py` | Good. Deterministic ids are what make a repository possible at all. |
| `approval/approval.py` | Works, but throws away the rejections (returns only `approved`). |
| `storage.py` | Empty file. |
| API | Does not exist. |
| Frontend | Vite starter template. |

Three real gaps block storage + API, and you have to close them **first**:

1. **`posting_date` is never parsed.** It's still a `str` (`'2023-10-03'`, and one is `''`).
   You cannot sort by date until it's a `date`.
2. **Salary is not comparable across rows.** One job has `min_annual=145000`, another has
   `min_hourly=62.5`. "Sort by salary" has no meaning until there's one comparable number.
3. **Approval discards rejections.** Requirement 5 says rejected jobs must be *stored* with
   reasons, not just `logger.info`'d and dropped.

There are also three small bugs in `ingestion.py` worth fixing while you're in there — see Step 1.4.

---

## Part 1 — The two design decisions, and why

### Decision 1: Storage = a repository interface + an in-memory implementation

The brief says "in-memory list, mocked database, or local file" and "structure and design
should be production ready". Those pull in opposite directions, and the standard resolution
is: **define the contract as a `Protocol`, implement it in memory.**

```
JobRepository (Protocol)          <- what the API depends on
   └── InMemoryJobRepository      <- what actually runs today
   └── PostgresJobRepository      <- what you'd write in month two, no caller changes
```

Why not just have the API hold a `list[Job]` and filter it inline?

- **Filtering/sorting/paging belong behind the interface.** In a real system those become
  `WHERE`, `ORDER BY`, `LIMIT`/`OFFSET` pushed into the database. If the router does the
  filtering, swapping to Postgres means rewriting the router. If the *repository* does it,
  you write one new class.
- **It's the thing that makes the API testable.** Your route tests inject a repository
  seeded with three fixture jobs. No file I/O, no pipeline, no ingestion run.

Two protocols, not one: `JobRepository` (approved jobs, queryable) and `RejectionLog`
(rejected jobs + reasons, append-only). They have genuinely different shapes — one is read-heavy
and searchable, one is write-once and audited — so don't force them into one interface.

**Query object over long parameter lists.** `search(query: JobQuery)` instead of
`search(q, country, sort_by, order, limit, offset)`. When you add `employment_type` or
`min_salary` next month you add a field with a default, and no existing call site breaks.

**Immutable snapshot instead of a lock.** The repo stores `tuple[Job, ...]`. Readers grab a
local reference first (`jobs = self._jobs`) then work on it; `replace_all` rebinds the
attribute. Attribute rebinding is atomic in CPython, so a re-ingest can never hand a reader a
half-updated list. FastAPI runs sync endpoints in a threadpool, so this matters.

### Decision 2: API = FastAPI, thin routers, Pydantic response models

Use **FastAPI**. Not because it's trendy — because it does three things you'd otherwise write
by hand: query-param validation and coercion (`limit: int = Query(ge=1, le=100)`), dependency
injection (which is how you swap the repository in tests), and an OpenAPI schema you can point
the frontend types at.

The critical rule: **your `@dataclass` domain models are not your wire format.**

| Internal (`models/`) | Wire (`api/schemas.py`) |
|---|---|
| `Decimal("145000")` | `145000.0` |
| `date(2023, 10, 3)` | `"2023-10-03"` |
| `Salary(min_annual=..., min_hourly=None, raw={...})` | `{"amount": 145000, "period": "annual", ...}` |
| `Location.raw` (scraped junk) | not exposed |

Keeping a separate Pydantic layer means you can refactor `Salary` without breaking the
frontend, and you never accidentally leak `raw` scraped data. This is one extra file and it is
worth it — it's the single most common thing interviewers look for in a "production ready"
API layer.

**Endpoints:**

```
GET /api/health                 -> {"status": "ok", "jobs": 11}
GET /api/jobs                   -> paged, filtered, sorted list
      ?q=engineer               search by title (case-insensitive substring)
      &country=USA              filter by country
      &sort_by=salary           salary | posting_date | title
      &order=desc               asc | desc
      &limit=20&offset=0
GET /api/jobs/{job_id}          -> one job, or 404
GET /api/countries              -> ["Canada", "UK", "USA"]  (for the filter dropdown)
GET /api/rejections             -> rejected jobs + reasons (requirement 5's "logged for review")
```

`/api/countries` is a separate path, **not** `/api/jobs/countries`, because that would be
shadowed by `/api/jobs/{job_id}`.

**Pagination from day one.** Your `assumptions.md` to-do already lists "long lists". A
`{items, total, limit, offset}` envelope costs nothing now and means the frontend never needs
restructuring later.

---

## Part 2 — Setup

You're on system Python 3.9, but the code uses `StrEnum` (3.11+) and `X | None` (3.10+).
You already have `uv`. Pin the project properly.

### Step 2.1 — `pyproject.toml` (new file, at `ladders/pyproject.toml`)

```toml
[project]
name = "ladders"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "httpx>=0.27"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

`pythonpath = ["."]` is what fixes the "imports and package resolve" to-do in your
`assumptions.md` — it makes `from backend.models import Job` work under pytest without any
`sys.path` hacking.

### Step 2.2 — create the environment

```bash
cd testproj/ladders
uv venv --python 3.12
uv pip install -e ".[dev]"
```

`-e` (editable) installs your `backend` package into the venv by reference, so
`from backend.storage import ...` resolves from anywhere without `PYTHONPATH=.`.

---

## Part 3 — Close the three model gaps

### Step 3.1 — Parse the posting date

**New file: `backend/ingestion/parsers/parse_posting_date.py`**

```python
from datetime import date, datetime
from typing import Any

from backend.ingestion.parsers.helpers import to_clean_string

# Scraped feeds are inconsistent. Widen this list, don't widen the parser.
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d %B %Y", "%B %d, %Y")


def parse_posting_date(value: Any) -> date | None:
    """A calendar date, or None when the feed gave us nothing usable."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = to_clean_string(value)
    if text is None:
        return None

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None
```

Two things to notice:

- The `datetime` check comes **before** the `date` check. `datetime` subclasses `date`, so
  `isinstance(a_datetime, date)` is `True` — reversed, you'd return a `datetime` where the
  type says `date`.
- Unparseable dates return `None` rather than raising. That's the "handled gracefully"
  instruction: the `""` posting_date in row 16 (Growth Marketing Manager) must not kill the
  whole feed. It sorts last instead.

**Edit `backend/ingestion/parsers/__init__.py`** — add the import and the `__all__` entry:

```python
from .parse_posting_date import parse_posting_date
```

### Step 3.2 — Make salary comparable

**Edit `backend/models/Job.py`.** Add a constant above `Salary` and a property inside it:

```python
# 40 h/week x 52 weeks. The conventional US full-time year; a single named
# constant so the assumption is visible and changeable in one place.
HOURS_PER_YEAR = Decimal(2080)


@dataclass
class Salary:
    raw: Any
    min_annual: Decimal | None
    min_hourly: Decimal | None
    currency: Currency | None
    inferred_currency: bool = False
    inferred_period: bool = False

    @property
    def annual_equivalent(self) -> Decimal | None:
        """One comparable number, so hourly and annual postings can be ranked together.

        Derived rather than stored: there is exactly one source of truth
        (`min_annual` / `min_hourly`) and it cannot drift out of sync.
        """
        if self.min_annual is not None:
            return self.min_annual
        if self.min_hourly is not None:
            return self.min_hourly * HOURS_PER_YEAR
        return None
```

A `@property`, not a field, and not something computed in the parser. Derived values that are
cheap should be derived — storing it would give you two fields that can disagree.

> Note the honest limitation: `annual_equivalent` does **not** convert currency. A GBP 85,000
> job and a USD 85,000 job compare as equal. That matches the assumption already in your
> `assumptions.md` ("sorting only by a single currency type"). Say so in the README rather
> than pretending otherwise — real FX would need a rates service, which the brief lets you mock.

> **Bug to fix while you're here:** `parse_salary` computes `inferred_period` and then never
> passes it to the `Salary(...)` constructor, so it's always `False`. Add
> `inferred_period=inferred_period,` to the return. The test in Part 9
> (`test_salary_bare_number_below_threshold_is_treated_as_hourly`) is written to catch it.

### Step 3.3 — Give locations a display/filter label

`CountryCode` is `US | CA | OTHER`. That's the right shape for *policy* (markets care about
three buckets) but useless for a *filter dropdown* — every non-US/CA job collapses into
"other". Keep both: the code for rules, a label for humans.

**Edit `backend/models/Job.py`**, add one field to `Location`:

```python
@dataclass
class Location:
    raw: Any
    city: str | None
    region: str | None
    country_code: CountryCode | None
    country_label: str | None = None   # as written in the feed: "USA", "Canada", "UK"
```

**Edit `backend/ingestion/parsers/parse_location.py`**, in `build_location`:

```python
def build_location(raw: Any, city: Any, region: Any, country: Any) -> Location:
    country = to_clean_string(country)
    return Location(
        raw=raw,
        city=to_clean_string(city),
        region=to_clean_string(region),
        country_code=to_country_code(country),
        country_label=country,          # <- add this line
    )
```

One line, and now `/api/countries` can return `["Canada", "UK", "USA"]` instead of
`["CA", "OTHER", "US"]`.

### Step 3.4 — Fix `ingestion.py` (three existing bugs)

Read your current `process_raw` closely. It computes `title`, `company`, `location` into
locals for the id hash, then **ignores them** and re-reads the raw dict for the `Job`:

```python
title=raw_job.get("title"),          # raw, so "" stays "" instead of becoming None
company=raw_job.get("company"),      # same
location=parse_location(...),        # parsed a second time, wasted work
```

And `FEED = HERE / "mock" / "jobs.json"` points at
`backend/ingestion/mock/jobs.json`, which doesn't exist — the real file is at
`backend/data/mock/jobs.json`.

**Rewrite `backend/ingestion/ingestion.py`:**

```python
import json
import logging
from pathlib import Path
from typing import Any

from backend.ingestion.job_id_hash import make_job_id
from backend.ingestion.parsers import (
    parse_company_type,
    parse_employment_type,
    parse_language,
    parse_location,
    parse_posting_date,
    parse_salary,
)
from backend.ingestion.parsers.helpers import to_clean_string
from backend.models import Job

logger = logging.getLogger(__name__)

DEFAULT_FEED = Path(__file__).resolve().parents[1] / "data" / "mock" / "jobs.json"


def load_raw(path: Path = DEFAULT_FEED) -> list[dict[str, Any]]:
    """Read a feed file. A malformed *file* is fatal; malformed *rows* are not."""
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, list):
        raise ValueError(f"{path}: expected a JSON array of postings")

    return [row for row in payload if isinstance(row, dict)]


def to_job(raw_job: dict[str, Any]) -> Job:
    """One raw posting -> one internal Job. Never raises on bad field values."""
    title = to_clean_string(raw_job.get("title"))
    company = to_clean_string(raw_job.get("company"))
    location = parse_location(raw_job.get("location"))
    posting_date = parse_posting_date(raw_job.get("posting_date"))

    return Job(
        id=make_job_id(
            title=title,
            company=company,
            location=location,
            posting_date=raw_job.get("posting_date"),
        ),
        title=title,
        description=to_clean_string(raw_job.get("description")),
        company=company,
        location=location,
        salary=parse_salary(raw_job.get("salary")),
        employment_type=parse_employment_type(raw_job.get("employment_type")),
        posting_date=posting_date,
        company_type=parse_company_type(raw_job.get("company_type")),
        language=parse_language(raw_job.get("language")),
        is_remote=bool(raw_job.get("remote")),
    )


def process_raw(raw_jobs: list[dict[str, Any]]) -> list[Job]:
    """Convert a feed. A row that blows up is skipped and logged, not fatal."""
    jobs: list[Job] = []
    for index, raw_job in enumerate(raw_jobs):
        try:
            jobs.append(to_job(raw_job))
        except Exception:
            logger.exception("Skipping unparseable posting at index %d", index)
    return jobs
```

Changes and why:

- **`to_job` extracted from the loop.** Now you can unit-test "this one weird dict produces
  this one Job" without building a list. This is what "design with tests in mind" means in
  practice.
- **`parents[1]`** walks up from `backend/ingestion/` to `backend/`, so the path resolves to
  the real `backend/data/mock/jobs.json`.
- **`make_job_id` gets the raw date, not the parsed one.** The id must stay stable even for
  rows whose date fails to parse — if you passed `None`, every unparseable-date job from the
  same company would collide.
- **The try/except is per row.** Requirement 2: "robust against invalid data". One poisoned
  row must not lose the other 19.
- **`bool(...)` on remote** — a missing `remote` key becomes `False`, not `None`.

**Also edit `backend/models/Job.py`** to tighten the field now that it's actually parsed:

```python
posting_date: date | None      # was: date | str | None  # parse this later
```

---

## Part 4 — Make approval report rejections

Right now `approve_jobs` returns `approved` and drops the reasons on the floor. Storage needs
both halves, so change what approval *returns* rather than what it logs.

### Step 4.1 — A decision type

**New file: `backend/models/Decision.py`**

```python
from dataclasses import dataclass
from enum import StrEnum

from backend.models.Job import Job


class RejectionReason(StrEnum):
    """Machine-readable rejection codes.

    An enum rather than a free-text string: codes can be counted, filtered and
    asserted on in tests without depending on English wording.
    """
    MISSING_TITLE = "missing-title"
    NOT_FULL_TIME = "not-full-time"
    STAFFING_FIRM = "staffing-firm"
    NO_ELIGIBLE_MARKET = "no-eligible-market"


@dataclass(frozen=True)
class JobDecision:
    """The outcome of running the approval rules over one job."""
    job: Job
    reasons: tuple[RejectionReason, ...] = ()

    @property
    def approved(self) -> bool:
        return not self.reasons
```

`approved` is a property derived from `reasons`, not a separate `bool` field. You cannot
construct the contradictory state `approved=True, reasons=("staffing-firm",)`. That's the
brief's "prevent invalid states" instruction applied at the smallest possible scale.

`frozen=True` because a decision is a historical fact — nothing should mutate it after the
fact.

**Edit `backend/models/__init__.py`** to re-export them:

```python
from backend.models.Decision import JobDecision, RejectionReason
```
...and add `"JobDecision", "RejectionReason"` to `__all__`.

### Step 4.2 — Rules as a list

**Rewrite `backend/approval/approval.py`:**

```python
from collections.abc import Callable, Sequence

from backend.models import (
    MARKETS,
    CompanyType,
    Currency,
    EmploymentType,
    Job,
    JobDecision,
    Market,
    RejectionReason,
)

# A rule looks at a job (and the market table) and returns a reason to reject,
# or None to stay silent. Adding a criterion = writing one function and adding
# it to RULES. Nothing else changes.
Rule = Callable[[Job, Sequence[Market]], RejectionReason | None]


def is_job_in_market(job: Job, market: Market) -> bool:
    job_country_code = job.location.country_code if job.location else None
    if market.countries is not None and job_country_code not in market.countries:
        return False

    if market.remote_only and not job.is_remote:
        return False

    if job.salary is None:
        return False

    # Assumption: thresholds are stated in USD, so we only enforce them on USD
    # postings. A non-USD salary is not evidence of being under the bar.
    if job.salary.currency is Currency.USD:
        if job.salary.min_annual is not None and market.min_annual_salary is not None:
            if job.salary.min_annual < market.min_annual_salary:
                return False
        elif job.salary.min_hourly is not None and market.min_hourly_salary is not None:
            if job.salary.min_hourly < market.min_hourly_salary:
                return False

    if market.languages and job.language not in market.languages:
        return False

    return True


def _requires_title(job: Job, markets: Sequence[Market]) -> RejectionReason | None:
    if not (job.title or "").strip():
        return RejectionReason.MISSING_TITLE
    return None


def _requires_full_time(job: Job, markets: Sequence[Market]) -> RejectionReason | None:
    if job.employment_type is not EmploymentType.FULL_TIME:
        return RejectionReason.NOT_FULL_TIME
    return None


def _rejects_staffing_firms(job: Job, markets: Sequence[Market]) -> RejectionReason | None:
    if job.company_type is CompanyType.STAFFING_FIRM:
        return RejectionReason.STAFFING_FIRM
    return None


def _requires_eligible_market(job: Job, markets: Sequence[Market]) -> RejectionReason | None:
    if any(is_job_in_market(job, market) for market in markets):
        return None
    return RejectionReason.NO_ELIGIBLE_MARKET


RULES: tuple[Rule, ...] = (
    _requires_title,
    _requires_full_time,
    _rejects_staffing_firms,
    _requires_eligible_market,
)


def evaluate(
    job: Job,
    markets: Sequence[Market] = MARKETS,
    rules: Sequence[Rule] = RULES,
) -> JobDecision:
    """Run every rule and collect *all* failures, not just the first."""
    reasons = tuple(
        reason
        for rule in rules
        if (reason := rule(job, markets)) is not None
    )
    return JobDecision(job=job, reasons=reasons)


def evaluate_all(
    jobs: Sequence[Job],
    markets: Sequence[Market] = MARKETS,
    rules: Sequence[Rule] = RULES,
) -> list[JobDecision]:
    return [evaluate(job, markets, rules) for job in jobs]
```

What changed from your version and why:

- **No more `continue` on first failure.** Your loop stopped at the first reason, so the
  empty-title staffing-firm contract job reported only `"No title"`. Now it reports all three.
  A reviewer looking at the rejection log wants the full picture, not the first tripwire.
- **`markets` and `rules` are parameters with defaults.** A test can pass a single synthetic
  market and assert precisely, without touching the global `MARKETS` table.
- **No logging in here.** Approval decides; the caller records. Mixing the two is what makes
  the function hard to test (you'd have to capture log output to assert behaviour).
- **`is not` for enum comparison.** `EmploymentType` is a `StrEnum`, so `!=` also works, but
  `is`/`is not` says "same enum member" rather than "equal string" and is what you want.

Adding the brief's hypothetical future rule — "remote UK jobs approved at 90k USD+" — is now
purely a data change in `MARKETS`:

```python
Market(
    name="Remote UK",
    countries=frozenset({CountryCode.OTHER}),   # would want a UK code in CountryCode
    remote_only=True,
    min_annual_salary=Decimal(90_000),
    min_hourly_salary=None,
    languages=frozenset({Language.EN}),
),
```

No approval code changes at all. That's the payoff of the market table you already built.

---

## Part 5 — The storage layer

Delete the empty `backend/storage.py`; it becomes a package.

```bash
rm backend/storage.py
mkdir backend/storage
touch backend/storage/__init__.py
```

### Step 5.1 — The query vocabulary

**New file: `backend/storage/query.py`**

```python
from dataclasses import dataclass
from enum import StrEnum


class SortField(StrEnum):
    SALARY = "salary"
    POSTING_DATE = "posting_date"
    TITLE = "title"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass(frozen=True)
class JobQuery:
    """Everything the caller can ask for, in one value.

    New filters arrive as new fields with defaults, so no existing caller or
    implementation signature has to change.
    """
    search: str | None = None
    country: str | None = None
    sort_by: SortField = SortField.POSTING_DATE
    order: SortOrder = SortOrder.DESC
    limit: int = DEFAULT_LIMIT
    offset: int = 0


@dataclass(frozen=True)
class Page[T]:
    """A window into a result set, plus the total so the UI can paginate."""
    items: list[T]
    total: int
    limit: int
    offset: int
```

`class Page[T]` is PEP 695 generics syntax — 3.12+, which is why Part 2 pins the version. On
older Python you'd write `Generic[T]` from `typing`.

Making `SortField`/`SortOrder` enums rather than strings pays off twice: the repository can
`match` on them exhaustively, and FastAPI will automatically reject `?sort_by=banana` with a
422 and list the valid values in the OpenAPI docs. You get input validation for free by
choosing the right type.

### Step 5.2 — The contracts

**New file: `backend/storage/repository.py`**

```python
from collections.abc import Iterable, Sequence
from typing import Protocol

from backend.models import Job, JobDecision
from backend.storage.query import JobQuery, Page


class JobRepository(Protocol):
    """Read/write access to *approved* jobs.

    A Protocol, not an ABC: implementations don't have to import or inherit from
    this, they just have to have the right methods. The API layer depends on this
    name and never on a concrete class.
    """

    def replace_all(self, jobs: Iterable[Job]) -> None:
        """Atomically swap the contents for a fresh ingestion run."""
        ...

    def get(self, job_id: str) -> Job | None:
        """One job by id, or None when it isn't there (not an exception)."""
        ...

    def search(self, query: JobQuery) -> Page[Job]:
        """Filter, sort and paginate. All of it happens here, never in a router."""
        ...

    def countries(self) -> list[str]:
        """Distinct country labels present in the stored jobs, sorted."""
        ...


class RejectionLog(Protocol):
    """Append-only record of what was rejected and why."""

    def record(self, decisions: Iterable[JobDecision]) -> None:
        ...

    def all(self) -> Sequence[JobDecision]:
        ...
```

Two deliberate choices to notice:

- **`get` returns `None`, it does not raise.** "Not found" is an ordinary outcome for a lookup,
  not an exceptional one. Translating that `None` into an HTTP 404 is the *router's* job —
  storage doesn't know HTTP exists.
- **`replace_all`, not `add`.** Ingestion is a batch job producing a complete snapshot. A
  whole-set swap models that honestly and gives you the atomic-rebind property below. If you
  later stream individual postings, `upsert(job)` is a new method, not a redesign.

### Step 5.3 — The in-memory implementation

**New file: `backend/storage/memory.py`**

```python
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal

from backend.ingestion.parsers.helpers import collapse
from backend.models import Job, JobDecision
from backend.storage.query import JobQuery, Page, SortField, SortOrder

SortKey = Decimal | date | str


def _sort_key(job: Job, field: SortField) -> SortKey | None:
    """The value a job is ranked by, or None when the job can't be ranked."""
    match field:
        case SortField.SALARY:
            return job.salary.annual_equivalent if job.salary else None
        case SortField.POSTING_DATE:
            return job.posting_date
        case SortField.TITLE:
            return job.title.lower() if job.title else None


def _matches(job: Job, query: JobQuery) -> bool:
    if query.search:
        needle = query.search.strip().lower()
        if needle and needle not in (job.title or "").lower():
            return False

    if query.country:
        label = job.location.country_label if job.location else None
        if label is None or collapse(label) != collapse(query.country):
            return False

    return True


def _sorted(jobs: list[Job], field: SortField, order: SortOrder) -> list[Job]:
    """Sort, keeping unrankable jobs last in *both* directions.

    Partitioning first (rather than sorting with a None-aware key) is what makes
    that true: a plain `reverse=True` would flip the missing values to the front,
    which is never what a user wants.
    """
    rankable: list[Job] = []
    unrankable: list[Job] = []
    for job in jobs:
        (rankable if _sort_key(job, field) is not None else unrankable).append(job)

    # `job.id` as a tiebreak keeps the order total and stable across runs.
    rankable.sort(
        key=lambda job: (_sort_key(job, field), job.id),
        reverse=order is SortOrder.DESC,
    )
    return rankable + unrankable


class InMemoryJobRepository:
    """Approved jobs held in process. Swap for a database implementation later."""

    def __init__(self, jobs: Iterable[Job] = ()) -> None:
        self._jobs: tuple[Job, ...] = tuple(jobs)
        self._by_id: dict[str, Job] = {job.id: job for job in self._jobs}

    def replace_all(self, jobs: Iterable[Job]) -> None:
        snapshot = tuple(jobs)
        # Build first, then rebind. Attribute rebinding is atomic in CPython, so a
        # concurrent reader sees either the whole old set or the whole new one,
        # never a half-written list. No lock needed.
        self._by_id = {job.id: job for job in snapshot}
        self._jobs = snapshot

    def get(self, job_id: str) -> Job | None:
        return self._by_id.get(job_id)

    def search(self, query: JobQuery) -> Page[Job]:
        jobs = self._jobs                       # take the snapshot once
        matched = [job for job in jobs if _matches(job, query)]
        ordered = _sorted(matched, query.sort_by, query.order)
        window = ordered[query.offset : query.offset + query.limit]
        return Page(
            items=window,
            total=len(ordered),                 # total *before* paging, for the UI
            limit=query.limit,
            offset=query.offset,
        )

    def countries(self) -> list[str]:
        labels = {
            job.location.country_label
            for job in self._jobs
            if job.location and job.location.country_label
        }
        return sorted(labels)


class InMemoryRejectionLog:
    """Rejected jobs plus reasons, kept for review."""

    def __init__(self) -> None:
        self._decisions: list[JobDecision] = []

    def record(self, decisions: Iterable[JobDecision]) -> None:
        self._decisions.extend(decisions)

    def all(self) -> Sequence[JobDecision]:
        return tuple(self._decisions)   # a copy, so callers can't mutate our state
```

Points worth internalising:

- **Order of operations is filter → sort → paginate.** Any other order gives wrong answers:
  paginating before sorting returns the wrong page, and `total` computed after paginating is
  always just `limit`.
- **`total` is the count of matches, not the count returned.** The frontend needs it to render
  "showing 1–20 of 47" and to decide whether a "next" button is live.
- **The dict is a deliberate index.** `get` is O(1) instead of a scan — the same reason a real
  table has a primary key.
- **`_sort_key` uses `match` with no `case _`.** If you add a fourth `SortField` and forget to
  handle it here, the function silently returns `None` — so keep the enum and this match
  adjacent in your mental model, and cover it with a test.

Slicing past the end (`ordered[500:520]`) returns `[]` rather than raising, so an out-of-range
`offset` gives an empty page. That's the right behaviour — no special-casing needed.

### Step 5.4 — Package exports

**Edit `backend/storage/__init__.py`:**

```python
from backend.storage.memory import InMemoryJobRepository, InMemoryRejectionLog
from backend.storage.query import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    JobQuery,
    Page,
    SortField,
    SortOrder,
)
from backend.storage.repository import JobRepository, RejectionLog

__all__ = [
    "DEFAULT_LIMIT", "MAX_LIMIT", "InMemoryJobRepository", "InMemoryRejectionLog",
    "JobQuery", "JobRepository", "Page", "RejectionLog", "SortField", "SortOrder",
]
```

---

## Part 6 — Wire the pipeline together

One place that knows the whole flow: read → parse → decide → store. Nothing else imports
ingestion and approval together.

**New file: `backend/pipeline.py`**

```python
import logging
from dataclasses import dataclass
from pathlib import Path

from backend.approval.approval import evaluate_all
from backend.ingestion.ingestion import DEFAULT_FEED, load_raw, process_raw
from backend.storage import (
    InMemoryJobRepository,
    InMemoryRejectionLog,
    JobRepository,
    RejectionLog,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    repository: JobRepository
    rejections: RejectionLog
    ingested: int
    approved: int
    rejected: int


def run_pipeline(
    feed: Path = DEFAULT_FEED,
    repository: JobRepository | None = None,
    rejections: RejectionLog | None = None,
) -> PipelineResult:
    """Ingest a feed, apply approval, and load the results into storage.

    The stores are parameters so tests (and a future Postgres-backed run) can
    supply their own. Defaults keep the common case a one-liner.
    """
    repository = repository if repository is not None else InMemoryJobRepository()
    rejections = rejections if rejections is not None else InMemoryRejectionLog()

    jobs = process_raw(load_raw(feed))
    decisions = evaluate_all(jobs)

    approved = [d.job for d in decisions if d.approved]
    rejected = [d for d in decisions if not d.approved]

    repository.replace_all(approved)
    rejections.record(rejected)

    for decision in rejected:
        logger.info(
            "Rejected %s %r at %s: %s",
            decision.job.id,
            decision.job.title,
            decision.job.company,
            ", ".join(decision.reasons),
        )

    logger.info(
        "Ingested %d postings: %d approved, %d rejected",
        len(jobs), len(approved), len(rejected),
    )

    return PipelineResult(
        repository=repository,
        rejections=rejections,
        ingested=len(jobs),
        approved=len(approved),
        rejected=len(rejected),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_pipeline()
```

Note `repository if repository is not None else ...` rather than `repository or ...`. An empty
repository is falsy-adjacent territory; `is not None` is the habit that avoids a whole class of
bug.

**Check it before moving on:**

```bash
uv run python -m backend.pipeline
```

You should see 9 rejection lines and `Ingested 20 postings: 11 approved, 9 rejected`. The
empty-title job should now list three reasons, not one.

---

## Part 7 — The API layer

```bash
mkdir -p backend/api/routers
touch backend/api/__init__.py backend/api/routers/__init__.py
```

### Step 7.1 — Wire schemas (the translation layer)

**New file: `backend/api/schemas.py`**

```python
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel

from backend.models import Job, JobDecision


class LocationOut(BaseModel):
    city: str | None
    region: str | None
    country: str | None
    country_code: str | None

    @classmethod
    def from_domain(cls, location) -> Self | None:
        if location is None:
            return None
        return cls(
            city=location.city,
            region=location.region,
            country=location.country_label,
            country_code=location.country_code,
        )


class SalaryOut(BaseModel):
    amount: float
    period: Literal["annual", "hourly"]
    currency: str
    annual_equivalent: float
    # Surfaced so the UI can mark values we guessed rather than read.
    inferred_currency: bool
    inferred_period: bool

    @classmethod
    def from_domain(cls, salary) -> Self | None:
        if salary is None:
            return None
        annual = salary.annual_equivalent
        if annual is None:
            return None
        is_hourly = salary.min_hourly is not None
        return cls(
            amount=float(salary.min_hourly if is_hourly else salary.min_annual),
            period="hourly" if is_hourly else "annual",
            currency=salary.currency or "USD",
            annual_equivalent=float(annual),
            inferred_currency=salary.inferred_currency,
            inferred_period=salary.inferred_period,
        )


class JobOut(BaseModel):
    id: str
    title: str
    description: str | None
    company: str | None
    location: LocationOut | None
    salary: SalaryOut | None
    employment_type: str
    posting_date: date | None
    company_type: str
    language: str
    is_remote: bool

    @classmethod
    def from_domain(cls, job: Job) -> Self:
        return cls(
            id=job.id,
            title=job.title or "",
            description=job.description,
            company=job.company,
            location=LocationOut.from_domain(job.location),
            salary=SalaryOut.from_domain(job.salary),
            employment_type=job.employment_type or "unknown",
            posting_date=job.posting_date,
            company_type=job.company_type or "unknown",
            language=job.language or "unknown",
            is_remote=bool(job.is_remote),
        )


class JobPageOut(BaseModel):
    items: list[JobOut]
    total: int
    limit: int
    offset: int


class RejectionOut(BaseModel):
    id: str
    title: str
    company: str | None
    reasons: list[str]

    @classmethod
    def from_domain(cls, decision: JobDecision) -> Self:
        return cls(
            id=decision.job.id,
            title=decision.job.title or "",
            company=decision.job.company,
            reasons=list(decision.reasons),
        )
```

The important ideas:

- **`from_domain` classmethods put the mapping in one place.** Routers stay one line long, and
  when `Salary` changes shape you edit exactly one function.
- **`Decimal -> float` is a conscious wire-format decision.** JSON has no decimal type and JS
  has no integer-safe decimal either. Money stays `Decimal` internally where the comparisons
  happen, and becomes `float` only for display. Say this out loud if asked — it shows you know
  why `Decimal` was there in the first place.
- **`title: str` (not `str | None`) on the way out.** Approved jobs are guaranteed to have a
  title by the approval rules, so the API can promise it. The `or ""` is a belt-and-braces
  coercion for the rejection feed, where titles genuinely can be empty.
- **`period` is a `Literal`, not a bare `str`.** It appears in the OpenAPI schema as an enum,
  so the TypeScript type you write in Part 8 can be a union rather than `string`.

### Step 7.2 — Dependencies

**New file: `backend/api/dependencies.py`**

```python
from typing import Annotated

from fastapi import Depends, Request

from backend.storage import JobRepository, RejectionLog


def get_repository(request: Request) -> JobRepository:
    """Pull the repository off app state.

    Routers ask for this dependency instead of importing a global. That single
    indirection is what lets a test build an app with a fixture repository.
    """
    return request.app.state.repository


def get_rejections(request: Request) -> RejectionLog:
    return request.app.state.rejections


RepositoryDep = Annotated[JobRepository, Depends(get_repository)]
RejectionsDep = Annotated[RejectionLog, Depends(get_rejections)]
```

The `Annotated` aliases at the bottom exist so route signatures read as
`repository: RepositoryDep` instead of repeating `Annotated[JobRepository, Depends(...)]`
in every handler.

### Step 7.3 — The jobs router

**New file: `backend/api/routers/jobs.py`**

```python
from fastapi import APIRouter, HTTPException, Query, status

from backend.api.dependencies import RepositoryDep
from backend.api.schemas import JobOut, JobPageOut
from backend.storage import DEFAULT_LIMIT, MAX_LIMIT, JobQuery, SortField, SortOrder

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=JobPageOut, summary="Search approved jobs")
def list_jobs(
    repository: RepositoryDep,
    q: str | None = Query(default=None, max_length=200, description="Match on job title"),
    country: str | None = Query(default=None, max_length=100),
    sort_by: SortField = SortField.POSTING_DATE,
    order: SortOrder = SortOrder.DESC,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> JobPageOut:
    page = repository.search(
        JobQuery(
            search=q,
            country=country,
            sort_by=sort_by,
            order=order,
            limit=limit,
            offset=offset,
        )
    )
    return JobPageOut(
        items=[JobOut.from_domain(job) for job in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{job_id}", response_model=JobOut, summary="Fetch one approved job")
def get_job(job_id: str, repository: RepositoryDep) -> JobOut:
    job = repository.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobOut.from_domain(job)
```

Look at how little this router does: build a `JobQuery`, hand it to storage, map the result.
No filtering, no sorting, no slicing. That's the whole point of Part 5 — the router is the
*HTTP* layer and nothing more.

The validation is entirely declarative. `le=MAX_LIMIT` stops a client asking for a million
rows; `ge=0` stops a negative offset (which, given Python slicing, would silently return the
wrong window — a real bug you've now made unrepresentable). `SortField` as the annotation
means `?sort_by=banana` is a 422 before your code runs.

Route order matters: `""` is declared before `/{job_id}`, and `/api/countries` lives in a
different router precisely so it can never be swallowed by the `{job_id}` wildcard.

### Step 7.4 — The meta router

**New file: `backend/api/routers/meta.py`**

```python
from fastapi import APIRouter

from backend.api.dependencies import RejectionsDep, RepositoryDep
from backend.api.schemas import RejectionOut
from backend.storage import JobQuery

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health", summary="Liveness plus a load sanity check")
def health(repository: RepositoryDep) -> dict[str, object]:
    # `total` is the count *before* paging, so limit=1 buys the full count for
    # the price of one row -- and asks the repository only what its interface
    # promises, instead of reaching into its internals.
    page = repository.search(JobQuery(limit=1))
    return {"status": "ok", "jobs": page.total}


@router.get("/countries", response_model=list[str], summary="Filter options")
def countries(repository: RepositoryDep) -> list[str]:
    """Derived from the data, so the dropdown can never offer an empty filter."""
    return repository.countries()


@router.get("/rejections", response_model=list[RejectionOut], summary="Rejection log")
def rejections(rejections: RejectionsDep) -> list[RejectionOut]:
    """Requirement 5's "rejected jobs are logged for review", made inspectable."""
    return [RejectionOut.from_domain(d) for d in rejections.all()]
```

Resist the temptation to write `health` as `len(repository._jobs)`. The underscore is the
repository telling you that field is not part of its contract, and a Postgres implementation
would not have it. Every question the API asks storage should go through a Protocol method.

Deriving `/api/countries` from stored data rather than hardcoding `["USA", "Canada"]` means the
filter dropdown automatically stays correct when the market table changes and UK remote jobs
start being approved.

### Step 7.5 — The application

**New file: `backend/api/app.py`**

```python
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routers import jobs, meta
from backend.pipeline import run_pipeline
from backend.storage import JobRepository, RejectionLog

logger = logging.getLogger(__name__)

# The Vite dev server. In production the frontend is built and served as static
# files from the same origin, and this list becomes unnecessary.
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app(
    repository: JobRepository | None = None,
    rejections: RejectionLog | None = None,
) -> FastAPI:
    """Build the app.

    A factory, not a module-level `app = FastAPI()`, so tests can construct an
    app around fixture storage. When both stores are supplied the ingestion
    pipeline is skipped entirely — no file reads in unit tests.
    """
    preloaded = repository is not None and rejections is not None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if preloaded:
            app.state.repository = repository
            app.state.rejections = rejections
        else:
            result = run_pipeline(repository=repository, rejections=rejections)
            app.state.repository = result.repository
            app.state.rejections = result.rejections
            logger.info(
                "Startup ingestion: %d approved, %d rejected",
                result.approved, result.rejected,
            )
        yield
        # Nothing to tear down for in-memory storage. A database implementation
        # would close its connection pool here.

    app = FastAPI(
        title="Ladders Job Search API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(jobs.router)
    app.include_router(meta.router)
    return app


app = create_app()
```

Why `lifespan` and not a module-level `run_pipeline()` call at import time:

- Import-time side effects make the module impossible to import in a test without triggering a
  file read.
- `lifespan` runs once per application, on startup, and gives you a matching shutdown hook for
  free — which is where a real database would close its pool.

`allow_methods=["GET"]` rather than `["*"]`: the API is read-only, so say so.

**New file: `backend/main.py`** (the runner)

```python
import logging

import uvicorn


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run("backend.api.app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
```

The app is passed as an import string, not an object — that's what `reload=True` needs in order
to re-import after a file change.

**Check it:**

```bash
uv run python -m backend.main
```

Then, in another terminal:

```bash
curl -s 'localhost:8000/api/health'
curl -s 'localhost:8000/api/countries'
curl -s 'localhost:8000/api/jobs?sort_by=salary&order=desc&limit=3' | python3 -m json.tool
curl -s 'localhost:8000/api/jobs?q=engineer'
curl -s 'localhost:8000/api/jobs?country=Canada'
curl -s 'localhost:8000/api/jobs?limit=999'          # expect 422
curl -s 'localhost:8000/api/jobs/does-not-exist'     # expect 404
```

And open <http://localhost:8000/docs> — FastAPI generates that from the annotations you wrote.
Use it to sanity-check that `sort_by` shows exactly three values and `limit` shows its bounds.

Expected on the salary sort: `Senior Software Engineer` (150000) first, then
`Backend Engineer` (145000), then `Cybersecurity Specialist` (135000). `Data Scientist` at
$62.50/hr should land at 130,000 annual-equivalent — verify it sorts between 135000 and 125000,
because that single row proves your `annual_equivalent` normalisation actually works.

---

## Part 8 — The React frontend

### Step 8.1 — Proxy instead of fighting CORS

**Edit `frontend/vite.config.ts`:**

```ts
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // The browser only ever talks to localhost:5173, so requests are
      // same-origin and CORS never enters the picture. It also means the
      // frontend uses relative URLs -- identical in dev and production.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
```

The CORS middleware from Step 7.5 stays as a safety net for anyone running the frontend without
the proxy, but with this in place you should never need it.

### Step 8.2 — Types that mirror the API

**New file: `frontend/src/api/types.ts`**

```ts
// Hand-mirrored from backend/api/schemas.py. Keep the two in sync; if this API
// grows, generate this file from /openapi.json instead of maintaining it.

export type SortField = 'salary' | 'posting_date' | 'title'
export type SortOrder = 'asc' | 'desc'
export type SalaryPeriod = 'annual' | 'hourly'

export interface Location {
  city: string | null
  region: string | null
  country: string | null
  country_code: string | null
}

export interface Salary {
  amount: number
  period: SalaryPeriod
  currency: string
  annual_equivalent: number
  inferred_currency: boolean
  inferred_period: boolean
}

export interface Job {
  id: string
  title: string
  description: string | null
  company: string | null
  location: Location | null
  salary: Salary | null
  employment_type: string
  posting_date: string | null   // ISO date, e.g. "2023-10-03"
  company_type: string
  language: string
  is_remote: boolean
}

export interface JobPage {
  items: Job[]
  total: number
  limit: number
  offset: number
}

export interface JobFilters {
  q: string
  country: string
  sortBy: SortField
  order: SortOrder
  offset: number
}

export const PAGE_SIZE = 20

export const DEFAULT_FILTERS: JobFilters = {
  q: '',
  country: '',
  sortBy: 'posting_date',
  order: 'desc',
  offset: 0,
}
```

`| null` and not `?:` — the API always sends the key, it's the *value* that can be null.
Modelling that accurately means TypeScript forces you to handle the missing-salary case, which
is exactly the corner case the brief is testing you on.

### Step 8.3 — The fetch client

**New file: `frontend/src/api/client.ts`**

```ts
import type { JobFilters, JobPage } from './types'
import { PAGE_SIZE } from './types'

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal })
  if (!response.ok) {
    throw new ApiError(`Request failed (${response.status})`, response.status)
  }
  return (await response.json()) as T
}

export function fetchJobs(filters: JobFilters, signal: AbortSignal): Promise<JobPage> {
  // URLSearchParams handles the escaping. Never build a query string by
  // concatenation -- a title search for "C++ & Rust" would break it.
  const params = new URLSearchParams({
    sort_by: filters.sortBy,
    order: filters.order,
    limit: String(PAGE_SIZE),
    offset: String(filters.offset),
  })
  // Omit empty filters entirely rather than sending `q=`, so the server sees
  // "no filter" and not "filter on the empty string".
  if (filters.q.trim()) params.set('q', filters.q.trim())
  if (filters.country) params.set('country', filters.country)

  return getJson<JobPage>(`/api/jobs?${params}`, signal)
}

export function fetchCountries(signal: AbortSignal): Promise<string[]> {
  return getJson<string[]>('/api/countries', signal)
}
```

### Step 8.4 — Debounce hook

**New file: `frontend/src/hooks/useDebouncedValue.ts`**

```ts
import { useEffect, useState } from 'react'

/** Trails `value` by `delay` ms, so typing doesn't fire a request per keystroke. */
export function useDebouncedValue<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    // Cleanup cancels the pending timer whenever `value` changes again, which
    // is the entire debounce mechanism -- not an afterthought.
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}
```

### Step 8.5 — The data hook

**New file: `frontend/src/hooks/useJobs.ts`**

```ts
import { useEffect, useState } from 'react'
import { fetchJobs } from '../api/client'
import type { JobFilters, JobPage } from '../api/types'
import { useDebouncedValue } from './useDebouncedValue'

interface JobsState {
  page: JobPage | null
  loading: boolean
  error: string | null
}

export function useJobs(filters: JobFilters): JobsState {
  const debouncedQuery = useDebouncedValue(filters.q)
  const [state, setState] = useState<JobsState>({
    page: null,
    loading: true,
    error: null,
  })

  useEffect(() => {
    const controller = new AbortController()
    setState((previous) => ({ ...previous, loading: true, error: null }))

    fetchJobs({ ...filters, q: debouncedQuery }, controller.signal)
      .then((page) => setState({ page, loading: false, error: null }))
      .catch((error: unknown) => {
        // An aborted request isn't a failure -- a newer one has superseded it.
        if (error instanceof DOMException && error.name === 'AbortError') return
        const message = error instanceof Error ? error.message : 'Unknown error'
        setState({ page: null, loading: false, error: message })
      })

    // Aborting on cleanup is what prevents a slow early request from landing
    // after a fast later one and overwriting fresher results.
    return () => controller.abort()
  }, [debouncedQuery, filters.country, filters.sortBy, filters.order, filters.offset])

  return state
}
```

The `AbortController` is the part people skip and then spend an afternoon debugging. Type
"engineer" fast, and requests for `e`, `en`, `eng`… all fly. Without cancellation, whichever
*finishes* last wins, which is not necessarily the one you typed last. Debouncing reduces the
problem; aborting eliminates it.

The dependency array lists `filters.country` etc. individually rather than `filters`, because
`filters` is a fresh object every render and would re-fire the effect forever.

### Step 8.6 — Components

**New file: `frontend/src/components/JobCard.tsx`**

```tsx
import type { Job } from '../api/types'

const currencyFormat = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

function formatSalary(job: Job): string {
  if (!job.salary) return 'Salary not stated'
  const { amount, period, currency } = job.salary
  const value =
    currency === 'USD'
      ? currencyFormat.format(amount)
      : `${amount.toLocaleString()} ${currency}`
  return period === 'hourly' ? `${value}/hr` : value
}

function formatLocation(job: Job): string {
  if (job.is_remote && !job.location?.country) return 'Remote'
  const parts = [job.location?.city, job.location?.region, job.location?.country]
  const place = parts.filter(Boolean).join(', ') || 'Location not stated'
  return job.is_remote ? `${place} (Remote)` : place
}

export function JobCard({ job }: { job: Job }) {
  return (
    <article className="job-card">
      <h3>{job.title}</h3>
      <p className="job-company">{job.company ?? 'Company not stated'}</p>
      <ul className="job-meta">
        <li>{formatLocation(job)}</li>
        <li>{formatSalary(job)}</li>
        <li>{job.posting_date ?? 'Date unknown'}</li>
      </ul>
      {job.description && <p className="job-description">{job.description}</p>}
    </article>
  )
}
```

Every field that can be null gets an explicit fallback string. "Salary not stated" is a better
answer than a blank space or `NaN`, and the brief specifically asks you to handle missing data
gracefully — this is where the user actually sees whether you did.

**New file: `frontend/src/components/JobFilters.tsx`**

```tsx
import type { JobFilters as Filters, SortField, SortOrder } from '../api/types'

interface Props {
  filters: Filters
  countries: string[]
  onChange: (patch: Partial<Filters>) => void
}

export function JobFilters({ filters, countries, onChange }: Props) {
  return (
    <div className="filters">
      <label>
        <span>Search title</span>
        <input
          type="search"
          value={filters.q}
          placeholder="e.g. engineer"
          onChange={(e) => onChange({ q: e.target.value })}
        />
      </label>

      <label>
        <span>Country</span>
        <select
          value={filters.country}
          onChange={(e) => onChange({ country: e.target.value })}
        >
          <option value="">All countries</option>
          {countries.map((country) => (
            <option key={country} value={country}>{country}</option>
          ))}
        </select>
      </label>

      <label>
        <span>Sort by</span>
        <select
          value={filters.sortBy}
          onChange={(e) => onChange({ sortBy: e.target.value as SortField })}
        >
          <option value="posting_date">Posting date</option>
          <option value="salary">Salary</option>
          <option value="title">Title</option>
        </select>
      </label>

      <label>
        <span>Order</span>
        <select
          value={filters.order}
          onChange={(e) => onChange({ order: e.target.value as SortOrder })}
        >
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
      </label>
    </div>
  )
}
```

`onChange` takes a `Partial<Filters>` patch rather than one callback per control. One handler
in `App`, and the reset-to-page-one rule lives in exactly one place instead of four.

**New file: `frontend/src/components/Pagination.tsx`**

```tsx
import { PAGE_SIZE } from '../api/types'

interface Props {
  total: number
  offset: number
  onOffsetChange: (offset: number) => void
}

export function Pagination({ total, offset, onOffsetChange }: Props) {
  const first = total === 0 ? 0 : offset + 1
  const last = Math.min(offset + PAGE_SIZE, total)

  return (
    <nav className="pagination">
      <button
        type="button"
        disabled={offset === 0}
        onClick={() => onOffsetChange(Math.max(0, offset - PAGE_SIZE))}
      >
        Previous
      </button>
      <span>{first}–{last} of {total}</span>
      <button
        type="button"
        disabled={last >= total}
        onClick={() => onOffsetChange(offset + PAGE_SIZE)}
      >
        Next
      </button>
    </nav>
  )
}
```

This is where the `total` you were careful to compute before paging earns its keep.

### Step 8.7 — App

**Rewrite `frontend/src/App.tsx`:**

```tsx
import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { fetchCountries } from './api/client'
import type { JobFilters as Filters } from './api/types'
import { DEFAULT_FILTERS } from './api/types'
import { JobCard } from './components/JobCard'
import { JobFilters } from './components/JobFilters'
import { Pagination } from './components/Pagination'
import { useJobs } from './hooks/useJobs'

function App() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [countries, setCountries] = useState<string[]>([])
  const { page, loading, error } = useJobs(filters)

  useEffect(() => {
    const controller = new AbortController()
    fetchCountries(controller.signal)
      .then(setCountries)
      .catch(() => setCountries([]))   // dropdown degrades to "All countries"
    return () => controller.abort()
  }, [])

  // Any filter change resets to page one: staying on offset 60 after narrowing
  // to 3 results shows an empty page, which reads as "broken".
  const updateFilters = useCallback((patch: Partial<Filters>) => {
    setFilters((current) => ({ ...current, ...patch, offset: 0 }))
  }, [])

  const changePage = useCallback((offset: number) => {
    setFilters((current) => ({ ...current, offset }))
  }, [])

  return (
    <main className="app">
      <header>
        <h1>Job Search</h1>
        <p>Approved postings from the ingestion pipeline.</p>
      </header>

      <JobFilters filters={filters} countries={countries} onChange={updateFilters} />

      {error && <p className="status error" role="alert">Couldn't load jobs: {error}</p>}
      {loading && !page && <p className="status">Loading jobs…</p>}
      {page && page.total === 0 && (
        <p className="status">No jobs match those filters. Try widening your search.</p>
      )}

      {page && page.total > 0 && (
        <>
          <div className="job-list" aria-busy={loading}>
            {page.items.map((job) => <JobCard key={job.id} job={job} />)}
          </div>
          <Pagination total={page.total} offset={page.offset} onOffsetChange={changePage} />
        </>
      )}
    </main>
  )
}

export default App
```

Four distinct render states — error, first load, empty result, results — each with its own
message. "Make sure you catch different use cases on the job search experience" is asking about
exactly this. `aria-busy` keeps the previous results on screen while a refetch is in flight
instead of flashing a spinner, which feels considerably better when typing.

Also delete the starter assets you no longer reference: `src/assets/hero.png`,
`src/assets/react.svg`, `src/assets/vite.svg`, and the matching rules in `App.css`.

**Check it:**

```bash
# terminal 1
uv run python -m backend.main
# terminal 2
cd frontend && npm install && npm run dev
```

Work through: empty search shows 11 jobs; typing `engineer` narrows to 4; country `Canada`
gives 3; sort by salary descending puts `Senior Software Engineer` first; clearing everything
returns to 11.

---

## Part 9 — Tests

The brief says "design with tests in mind", and every choice above was made partly for this.
Now collect the payoff.

```bash
mkdir -p tests
touch tests/__init__.py
```

**New file: `tests/conftest.py`**

```python
from datetime import date
from decimal import Decimal

import pytest

from backend.models import (
    CompanyType, CountryCode, Currency, EmploymentType, Job, Language, Location, Salary,
)


def make_job(**overrides) -> Job:
    """A valid, approvable job. Tests override only the field under test.

    A builder rather than literal Job(...) calls: when Job gains a field, you
    edit one function instead of every test.
    """
    defaults = dict(
        id="test-1",
        title="Backend Engineer",
        description="Build APIs.",
        company="NextGen Systems",
        location=Location(
            raw=None, city="Austin", region="TX",
            country_code=CountryCode.US, country_label="USA",
        ),
        salary=Salary(
            raw=None, min_annual=Decimal(145_000), min_hourly=None,
            currency=Currency.USD,
        ),
        employment_type=EmploymentType.FULL_TIME,
        posting_date=date(2023, 10, 3),
        company_type=CompanyType.DIRECT_EMPLOYER,
        language=Language.EN,
        is_remote=False,
    )
    return Job(**{**defaults, **overrides})


@pytest.fixture
def job_factory():
    return make_job
```

**New file: `tests/test_parsers.py`** — the corner cases from the brief, one assert each:

```python
from datetime import date
from decimal import Decimal

from backend.ingestion.parsers import parse_location, parse_posting_date, parse_salary
from backend.models import CountryCode, Currency


def test_salary_dict_annual():
    salary = parse_salary({"value": 145000, "currency": "USD"})
    assert salary.min_annual == Decimal(145000)
    assert salary.min_hourly is None


def test_salary_bare_number_below_threshold_is_treated_as_hourly():
    salary = parse_salary(62.5)
    assert salary.min_hourly == Decimal("62.5")
    assert salary.inferred_period is True          # we guessed; say so


def test_salary_hourly_annual_equivalent():
    assert parse_salary(62.5).annual_equivalent == Decimal(130_000)


def test_salary_missing_returns_none():
    assert parse_salary(None) is None
    assert parse_salary({"value": 0}) is None


def test_location_string_form():
    location = parse_location("New York, NY, USA")
    assert (location.city, location.region, location.country_code) == (
        "New York", "NY", CountryCode.US,
    )


def test_location_bare_remote_has_no_country():
    assert parse_location("Remote").country_code is None


def test_location_null_returns_none():
    assert parse_location(None) is None


def test_posting_date_blank_is_none():
    assert parse_posting_date("") is None


def test_posting_date_iso():
    assert parse_posting_date("2023-10-03") == date(2023, 10, 3)
```

**New file: `tests/test_approval.py`**

```python
from decimal import Decimal

from backend.approval.approval import evaluate
from backend.models import (
    CompanyType, CountryCode, Currency, EmploymentType, Language, Location,
    RejectionReason, Salary,
)
from tests.conftest import make_job


def test_baseline_job_is_approved():
    assert evaluate(make_job()).approved


def test_missing_title_is_rejected():
    decision = evaluate(make_job(title=""))
    assert RejectionReason.MISSING_TITLE in decision.reasons


def test_internship_is_rejected():
    decision = evaluate(make_job(employment_type=EmploymentType.INTERNSHIP))
    assert RejectionReason.NOT_FULL_TIME in decision.reasons


def test_staffing_firm_is_rejected():
    decision = evaluate(make_job(company_type=CompanyType.STAFFING_FIRM))
    assert RejectionReason.STAFFING_FIRM in decision.reasons


def test_under_salary_threshold_is_rejected():
    salary = Salary(raw=None, min_annual=Decimal(72_000), min_hourly=None,
                    currency=Currency.USD)
    assert not evaluate(make_job(salary=salary)).approved


def test_french_is_allowed_in_canada_but_not_the_us():
    canada = Location(raw=None, city="Montreal", region="QC",
                      country_code=CountryCode.CA, country_label="Canada")
    assert evaluate(make_job(location=canada, language=Language.FR)).approved
    assert not evaluate(make_job(language=Language.FR)).approved   # US default


def test_all_failing_rules_are_reported_not_just_the_first():
    decision = evaluate(make_job(
        title="",
        employment_type=EmploymentType.CONTRACT,
        company_type=CompanyType.STAFFING_FIRM,
    ))
    assert len(decision.reasons) >= 3
```

That last test is the one that would have failed against your current `continue`-based
implementation — worth writing first and watching it go red.

**New file: `tests/test_storage.py`**

```python
from datetime import date
from decimal import Decimal

from backend.models import Currency, Salary
from backend.storage import InMemoryJobRepository, JobQuery, SortField, SortOrder
from tests.conftest import make_job


def annual(amount: int) -> Salary:
    return Salary(raw=None, min_annual=Decimal(amount), min_hourly=None,
                  currency=Currency.USD)


def hourly(amount: str) -> Salary:
    return Salary(raw=None, min_annual=None, min_hourly=Decimal(amount),
                  currency=Currency.USD)


def test_search_matches_title_case_insensitively():
    repo = InMemoryJobRepository([
        make_job(id="a", title="Backend Engineer"),
        make_job(id="b", title="UX Designer"),
    ])
    page = repo.search(JobQuery(search="ENGINEER"))
    assert [job.id for job in page.items] == ["a"]


def test_country_filter():
    repo = InMemoryJobRepository([make_job(id="a")])
    assert repo.search(JobQuery(country="usa")).total == 1     # collapsed match
    assert repo.search(JobQuery(country="Canada")).total == 0


def test_hourly_and_annual_sort_on_one_scale():
    repo = InMemoryJobRepository([
        make_job(id="annual", salary=annual(120_000)),
        make_job(id="hourly", salary=hourly("62.5")),   # 130,000 annualised
    ])
    page = repo.search(JobQuery(sort_by=SortField.SALARY, order=SortOrder.DESC))
    assert [job.id for job in page.items] == ["hourly", "annual"]


def test_missing_values_sort_last_in_both_directions():
    repo = InMemoryJobRepository([
        make_job(id="none", posting_date=None),
        make_job(id="dated", posting_date=date(2023, 10, 3)),
    ])
    for order in (SortOrder.ASC, SortOrder.DESC):
        page = repo.search(JobQuery(sort_by=SortField.POSTING_DATE, order=order))
        assert page.items[-1].id == "none"


def test_total_counts_matches_not_the_page():
    repo = InMemoryJobRepository([make_job(id=str(i)) for i in range(25)])
    page = repo.search(JobQuery(limit=10, offset=20))
    assert page.total == 25
    assert len(page.items) == 5


def test_offset_past_the_end_is_an_empty_page_not_an_error():
    repo = InMemoryJobRepository([make_job(id="a")])
    assert repo.search(JobQuery(offset=500)).items == []
```

**New file: `tests/test_api.py`**

```python
import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.storage import InMemoryJobRepository, InMemoryRejectionLog
from tests.conftest import make_job


@pytest.fixture
def client():
    """An app wired to fixture storage -- no feed file, no ingestion run."""
    repository = InMemoryJobRepository([
        make_job(id="a", title="Backend Engineer"),
        make_job(id="b", title="UX Designer"),
    ])
    app = create_app(repository=repository, rejections=InMemoryRejectionLog())
    with TestClient(app) as test_client:      # `with` is what runs lifespan
        yield test_client


def test_list_returns_every_job(client):
    body = client.get("/api/jobs").json()
    assert body["total"] == 2
    assert body["limit"] == 20 and body["offset"] == 0


def test_search_narrows_results(client):
    body = client.get("/api/jobs", params={"q": "designer"}).json()
    assert [item["id"] for item in body["items"]] == ["b"]


def test_unknown_id_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_invalid_sort_field_is_422(client):
    assert client.get("/api/jobs", params={"sort_by": "banana"}).status_code == 422


def test_limit_above_maximum_is_422(client):
    assert client.get("/api/jobs", params={"limit": 999}).status_code == 422


def test_salary_is_serialised_as_a_number(client):
    salary = client.get("/api/jobs").json()["items"][0]["salary"]
    assert salary["annual_equivalent"] == 145000.0
    assert salary["period"] == "annual"
```

Note `with TestClient(app)`. Without the context manager, FastAPI's `lifespan` never runs and
`app.state.repository` is never set — every request 500s with `AttributeError`. It's the single
most common FastAPI testing mistake.

**New file: `tests/test_pipeline.py`** — one end-to-end check against the real feed:

```python
from backend.pipeline import run_pipeline
from backend.storage import JobQuery


def test_real_feed_produces_the_expected_split():
    result = run_pipeline()
    assert result.ingested == 20
    assert result.approved == 11
    assert result.rejected == 9


def test_every_approved_job_has_a_title_and_a_salary():
    result = run_pipeline()
    for job in result.repository.search(JobQuery(limit=100)).items:
        assert job.title
        assert job.salary is not None


def test_every_rejection_carries_at_least_one_reason():
    result = run_pipeline()
    for decision in result.rejections.all():
        assert decision.reasons
```

**Run them:**

```bash
uv run pytest -q
```

---

## Part 10 — Build order and checklist

Do it in this order; each step is independently runnable, so you never have a long stretch of
broken code.

- [ ] **1.** `pyproject.toml`, `uv venv`, `uv pip install -e ".[dev]"`
- [ ] **2.** `parse_posting_date.py` + export it → test it
- [ ] **3.** `Salary.annual_equivalent`, `Location.country_label`, `Job.posting_date: date | None`
- [ ] **4.** Fix `ingestion.py` (feed path, cleaned fields, per-row try/except, `to_job`)
- [ ] **5.** `models/Decision.py`, rewrite `approval.py` → `uv run pytest tests/test_approval.py`
- [ ] **6.** `storage/` package: `query.py`, `repository.py`, `memory.py`, `__init__.py`
- [ ] **7.** `pipeline.py` → `uv run python -m backend.pipeline` prints 20 / 11 / 9
- [ ] **8.** `api/schemas.py`, `api/dependencies.py`, `api/routers/{jobs,meta}.py`, `api/app.py`, `main.py`
- [ ] **9.** `uv run python -m backend.main`, exercise every curl in Step 7.5, read `/docs`
- [ ] **10.** Vite proxy, `api/types.ts`, `api/client.ts`, hooks, components, `App.tsx`
- [ ] **11.** Tests, then `uv run pytest -q`
- [ ] **12.** README with setup steps; fold `assumptions.md` into it

### Final structure

```
ladders/
├── pyproject.toml
├── README.md
├── backend/
│   ├── main.py                     # uvicorn entrypoint
│   ├── pipeline.py                 # ingest -> approve -> store
│   ├── models/
│   │   ├── Job.py                  # + annual_equivalent, country_label
│   │   ├── Market.py               # approval policy as data
│   │   └── Decision.py             # NEW: JobDecision, RejectionReason
│   ├── ingestion/
│   │   ├── ingestion.py            # fixed
│   │   ├── job_id_hash.py
│   │   └── parsers/
│   │       └── parse_posting_date.py   # NEW
│   ├── approval/
│   │   └── approval.py             # rules list, returns decisions
│   ├── storage/                    # NEW package (replaces empty storage.py)
│   │   ├── query.py                # JobQuery, Page, SortField, SortOrder
│   │   ├── repository.py           # JobRepository / RejectionLog protocols
│   │   └── memory.py               # in-memory implementations
│   ├── api/                        # NEW
│   │   ├── app.py                  # create_app + lifespan
│   │   ├── schemas.py              # wire format
│   │   ├── dependencies.py         # DI
│   │   └── routers/{jobs,meta}.py
│   └── data/mock/jobs.json
├── frontend/src/
│   ├── api/{types,client}.ts
│   ├── hooks/{useJobs,useDebouncedValue}.ts
│   ├── components/{JobCard,JobFilters,Pagination}.tsx
│   └── App.tsx
└── tests/
    ├── conftest.py
    └── test_{parsers,approval,storage,api,pipeline}.py
```

### Things to be able to defend out loud

Interviewers ask "why" more than "what". Have an answer ready for each:

1. **Why a `Protocol` instead of just a list?** So filtering/sorting/paging live where a
   database would do them, and so the API can be tested without ingestion.
2. **Why separate Pydantic schemas from the dataclasses?** So the wire format can stay stable
   while the domain model evolves, and so scraped `raw` data never leaks.
3. **Why `annual_equivalent` as a property?** One source of truth; a stored copy can drift.
   And its limitation — no FX conversion — is documented rather than hidden.
4. **Why does approval return reasons instead of logging them?** Because deciding and recording
   are different jobs, and only the first one is testable without capturing log output.
5. **Why collect all rejection reasons rather than the first?** The rejection log is for human
   review; "first tripwire" is less useful than the full picture.
6. **Why pagination for 11 rows?** The envelope costs nothing now and prevents a frontend
   rewrite when the feed is 50,000 rows.
7. **Why does missing data sort last in both directions?** Because "no salary listed" is not
   "salary of zero", and users never want the unknowns at the top.

### Known limitations to write into your README

Being explicit about these reads as judgment, not as gaps:

- Salary comparison ignores exchange rates; non-USD postings are not held to the USD threshold,
  and sorting ranks them by nominal value.
- `CountryCode` collapses everything outside US/CA into `OTHER`. Adding the UK-remote market
  from the brief would need a real country code first — a deliberately deferred change.
- Language is taken from the feed's `language` field rather than detected from the description.
- Storage is in-memory, so the rejection log and ingested set reset on restart.
- Search matches titles only, as specified — not company or description.
