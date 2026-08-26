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