

from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from backend.ingestion.job_id_hash import make_job_id
from backend.ingestion.parsers import (
    parse_company_type,
    parse_employment_type,
    parse_language,
    parse_location,
    parse_salary,
    parse_posting_date,
)
from backend.ingestion.parsers.helpers import to_clean_string
from backend.models import Job

# temporary
HERE  = Path(__file__).resolve().parent
FEED = HERE / "mock" / "jobs.json"

def load_raw(path: Path = FEED) -> list[dict]:
    with path.open() as f:
        return json.load(f)
    
def process_raw(jobs: list[dict]) -> list[Job]:
    new_jobs = []
    for raw_job in jobs:
        title = to_clean_string(raw_job.get("title"))
        company = to_clean_string(raw_job.get("company"))
        location = parse_location(raw_job.get("location"))
        posting_date = parse_posting_date(raw_job.get("posting_date"))
        
        new_job = Job(
            id=make_job_id(
                title=title,
                company=company,
                location=location,
                posting_date=posting_date,
            ),
            title=title,
            description=raw_job.get("description"),
            company=company,
            location=location,
            salary=parse_salary(raw_job.get("salary")),
            employment_type=parse_employment_type(raw_job.get("employment_type")),
            posting_date=posting_date,
            company_type=parse_company_type(raw_job.get("company_type")),
            language=parse_language(raw_job.get("language")),
            is_remote=raw_job.get("remote")
        )
        
        new_jobs.append(new_job)
        
    return new_jobs  
