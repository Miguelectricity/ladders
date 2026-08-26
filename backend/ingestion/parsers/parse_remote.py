from typing import Any

from backend.ingestion.parsers.helpers import collapse, to_clean_string

# Scraped feeds spell the remote flag as a bool, a number, or a word. Anything
# we don't recognise stays unknown rather than guessing a working arrangement.
REMOTE_VALUES = {
    "true", "yes", "y", "1",
    "remote", "fullyremote", "remoteanywhere", "anywhere",
    "workfromhome", "wfh", "telecommute",
}
ON_SITE_VALUES = {
    "false", "no", "n", "0",
    "onsite", "onpremise", "inperson", "inoffice", "office", "hybrid",
}


def parse_remote(value: Any) -> bool | None:
    """True/False when the feed says so, None when it doesn't say anything usable."""
    if isinstance(value, bool):
        return value

    # bool is a subclass of int, so this only sees real numbers.
    if isinstance(value, (int, float)):
        return value != 0

    text = to_clean_string(value)
    if text is None:
        return None

    collapsed = collapse(text)
    if collapsed in REMOTE_VALUES:
        return True
    if collapsed in ON_SITE_VALUES:
        return False
    return None
