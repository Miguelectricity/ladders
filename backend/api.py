from backend.approval.approval import approve_jobs
from backend.ingestion.ingestion import load_raw, process_raw
from backend.models.Job import CountryCode
from backend.storage.storage import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, SortField, store
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["GET"])

COUNTRY_LABELS = {
    CountryCode.US: "United States",
    CountryCode.CA: "Canada",
    CountryCode.OTHER: "Other",
}

store.approved, store.rejected = approve_jobs(process_raw(load_raw()))


@app.get("/api/jobs")
def list_jobs(
    query: str | None = None,
    country: CountryCode | None = None,
    sort_by: SortField = SortField.POSTING_DATE,
    descending: bool = True,
    page: int = Query(0, ge=0),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    return store.search(query, country, sort_by, descending, page, page_size)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


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