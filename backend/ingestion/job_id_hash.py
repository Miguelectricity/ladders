import hashlib
from datetime import date, datetime
from typing import Any

from backend.ingestion.parsers.helpers import collapse, to_clean_string
from backend.models import Location

ID_LENGTH = 16
FIELD_SEPARATOR = "|"


def _normalize(value: Any) -> str:
    """Reduce a field to its identity-bearing characters, or '' when absent."""
    text = to_clean_string(value)
    return collapse(text) if text else ""


def _date_key(value: Any) -> str:
    """ISO form, so a parsed date hashes the same as the string it came from.

    Without this the date reaches _normalize() as a date object, to_clean_string()
    returns None for anything that isn't a str, and the date drops out of the key
    entirely - collapsing two postings that differ only by when they were posted.
    """
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        value = value.isoformat()
    return _normalize(value)


def _location_key(location: Location | None) -> str:
    if location is None:
        return ""
    parts = (location.city, location.region, location.country_code)
    return ",".join(_normalize(part) for part in parts)


def make_job_id(
    title: str | None,
    company: str | None,
    location: Location | None,
    posting_date: Any,
) -> str:
    """A deterministic id for a posting.

    Stable across runs, processes and feed formats, so re-ingesting the same
    posting produces the same id and duplicates collapse instead of piling up.
    """
    key = FIELD_SEPARATOR.join((
        _normalize(company),
        _normalize(title),
        _location_key(location),
        _date_key(posting_date),
    ))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:ID_LENGTH]