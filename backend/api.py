from contextlib import asynccontextmanager
from dataclasses import asdict
import logging
from typing import Any

from backend.approval.approval import approve_jobs
from backend.ingestion.ingestion import FeedError, load_feeds, process_raw
from backend.logging_config import configure_logging
from backend.models.Job import CountryCode
from backend.storage.storage import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, SortField, store
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

COUNTRY_LABELS = {
    CountryCode.US: "United States",
    CountryCode.CA: "Canada",
    CountryCode.OTHER: "Other",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ingest on startup rather than at import.

    Importing this module has no side effects, so tests can import the app and
    load their own fixtures, and a bad feed fails the boot with a clear error
    instead of an unimportable module.

    Every feed in the data directory is read, so adding one is a matter of
    dropping a file in and restarting - see reingest.sh.
    """
    configure_logging()
    try:
        ingested_jobs, _ = process_raw(load_feeds())
    except FeedError:
        logger.exception("Could not ingest the feed")
        raise
    store.approved, store.rejected = approve_jobs(ingested_jobs)
    logger.info(f"Serving {len(store.approved)} approved jobs")
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["GET"])


def to_public(value: Any) -> dict:
    """Serialize a dataclass, dropping the `raw` scrape we keep for debugging.

    Location.raw and Salary.raw are provenance, not API surface.
    """
    return asdict(value, dict_factory=lambda fields: {k: v for k, v in fields if k != "raw"})


@app.get("/api/jobs")
def list_jobs(
    query: str | None = None,
    country: CountryCode | None = None,
    sort_by: SortField = SortField.POSTING_DATE,
    descending: bool = True,
    page: int = Query(0, ge=0),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    return to_public(store.search(query, country, sort_by, descending, page, page_size))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return to_public(job)


@app.get("/api/countries")
def countries():
    """Filter options for the country dropdown, limited to countries with jobs.

    `code` is what /api/jobs?country= expects back; `label` is for display.
    """
    present = {j.location.country_code for j in store.approved
               if j.location and j.location.country_code}
    # Iterate the enum, not the set, so the order is stable and OTHER sorts last.
    return [
        {"code": code, "label": COUNTRY_LABELS[code]}
        for code in CountryCode
        if code in present
    ]