from typing import Any


def to_clean_string(value: Any) -> str | None:
    """Strip, and treat blank as absent."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def collapse(value: str) -> str:
    """Lowercase alphanumerics only, so separators and casing stop mattering."""
    return "".join(ch for ch in value.lower() if ch.isalnum())