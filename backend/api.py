from backend.approval.approval import approve_jobs
from backend.ingestion.ingestion import load_raw, process_raw
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.storage import store

app = FastAPI
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["GET"])

store.approved, store.rejected = approve_jobs(process_raw(load_raw()))


@app.get("/api/jobs")
def list_all_jobs(page: int = 0, page_size: int = 10):
    return approved