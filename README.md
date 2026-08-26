# Job Ingestion and Search

Ingests job postings from JSON feeds of differing shapes, decides whether each
one may be published, and serves the approved ones through a search UI.

## Running it

```sh
./dev.sh
```

Installs anything missing, then starts the API on **:8000** and the frontend on
**:5173**. Open <http://localhost:5173>. Ctrl-C stops both.

Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) and
[Node](https://nodejs.org). To run the halves separately:

```sh
uv run uvicorn backend.api:app --reload --port 8000
cd frontend && npm run dev
```

## Tests

```sh
uv run pytest
```

## How it fits together

The pipeline is four stages, each usable on its own:

```
feed.json -> ingestion -> approval -> storage -> API -> UI
```

| Package | Responsibility |
| --- | --- |
| `backend/models` | The internal representation (`Job`) and the approval policies (`Market`). |
| `backend/ingestion` | Reads a feed and maps records onto `Job`, one parser per field. |
| `backend/approval` | Applies the criteria; returns approved jobs and rejections with reasons. |
| `backend/storage` | Holds approved jobs; filters, sorts and pages them. |
| `backend/api.py` | FastAPI endpoints. Ingests once at startup. |
| `frontend/` | React + TypeScript search UI. |

**Ingestion** is per-field parsers over raw values. Feeds are scraped, so every
field is treated as untrusted: a value of the wrong shape becomes `None` or
`UNKNOWN` rather than propagating, a record that cannot be parsed is collected
as a failure instead of aborting the run, and records are keyed by a content
hash so re-ingesting a feed is idempotent. A feed that is unreadable, not JSON,
or not a list raises `FeedError` — there is nothing to salvage.

**Approval** splits into two parts. Rules that hold everywhere (title present,
full-time, not a staffing firm) are checked directly. Everything geographic —
country, salary floor, language — lives in `MARKETS`, and a job is approved if
it fits any one market. Adding "remote UK at 90k USD" is a new `Market` entry,
not a new branch.

**Storage** is an in-memory list behind `JobStore`, standing in for a database.
Filtering and sorting are memoized per query so paging is a slice rather than a
re-sort; `search()` returns a `Page` with the total, so the UI can draw page
controls.

## API

| Endpoint | Notes |
| --- | --- |
| `GET /api/jobs` | `query`, `country`, `sort_by`, `descending`, `page`, `page_size` |
| `GET /api/jobs/{id}` | 404 when unknown |
| `GET /api/countries` | Filter options, limited to countries that have jobs |

`sort_by` is one of `posting_date`, `salary_annual`, `salary_hourly`, `title`.
Jobs missing the sorted field sort last in both directions. Interactive docs at
<http://localhost:8000/docs>.

## Notes

`assumptions.md` records the judgement calls and what is still open — chiefly
that salaries are only compared when quoted in USD, so a non-USD posting clears
the floor unchecked. Rejected jobs are logged with their reason rather than
stored; the storage layer keeps them in memory for a future review endpoint.
