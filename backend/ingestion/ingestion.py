

from decimal import Decimal
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
    parse_remote,
    parse_salary,
    parse_posting_date,
)
from backend.ingestion.parsers.helpers import to_clean_string
from backend.models import Job

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent
FEED_DIR = BACKEND_ROOT / "data" / "mock"
DEFAULT_FEED = FEED_DIR / "jobs.json"
FEED_GLOB = "*.json"

class FeedError(ValueError):
    """The whole feed is unusable - unreadable, not JSON, or not a list."""

def load_raw(path: Path = DEFAULT_FEED) -> list[Any]:
    try:
        with path.open() as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise FeedError(f"Could not read feed {path}: {e}") from e

    if not isinstance(raw, list):
        raise FeedError(f"Feed {path} must be a list of postings, got {type(raw).__name__}")

    return raw

def load_feeds(directory: Path = FEED_DIR) -> list[Any]:
    """Every feed in a directory, concatenated into one batch of raw records.

    Drop another .json in and it gets picked up on the next startup. One
    unreadable file is logged and skipped - the same bargain process_raw()
    makes for one bad record - but a directory that yields nothing at all is
    an error, since serving an empty board silently is worse than not starting.
    """
    records = []
    for path in sorted(directory.glob(FEED_GLOB)):
        try:
            feed = load_raw(path)
        except FeedError as e:
            logger.error(f"Skipping feed: {e}")
            continue
        logger.info(f"Loaded {len(feed)} records from {path.name}")
        records.extend(feed)

    if not records:
        raise FeedError(f"No usable feeds in {directory}")

    return records

def process_raw(jobs: list[Any]) -> tuple[list[Job], list[tuple[int, str]]]:
    new_jobs = []
    failures = []
    seen_ids = set()

    for index, raw_job in enumerate(jobs):
        if not isinstance(raw_job, dict):
            failures.append((index, f"Expected an object, got {type(raw_job).__name__}"))
            continue

        # a bad record should cost us one posting, not the rest of the feed
        try:
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
                description=to_clean_string(raw_job.get("description")),
                company=company,
                location=location,
                salary=parse_salary(raw_job.get("salary")),
                employment_type=parse_employment_type(raw_job.get("employment_type")),
                posting_date=posting_date,
                company_type=parse_company_type(raw_job.get("company_type")),
                language=parse_language(raw_job.get("language")),
                is_remote=parse_remote(raw_job.get("remote"))
            )
        except Exception as e:
            failures.append((index, f"{type(e).__name__}: {e}"))
            continue

        # the same posting twice (or in the other feed format) keeps the first copy
        if new_job.id in seen_ids:
            logger.info(f"Duplicate posting {new_job.id} at record {index}, skipping")
            continue
        seen_ids.add(new_job.id)

        new_jobs.append(new_job)

    for index, reason in failures:
        logger.warning(f"Skipped record {index}: {reason}")

    return new_jobs, failures
