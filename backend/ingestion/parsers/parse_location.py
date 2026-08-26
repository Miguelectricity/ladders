from typing import Any

from ladders.backend.ingestion.parsers.helpers import collapse, to_clean_string
from ladders.backend.models import Location

COUNTRIES = {
    "usa": "US", "us": "US", "unitedstates": "US", "unitedstatesofamerica": "US", "america": "US",
    "canada": "CA", "ca": "CA", "can": "CA",
    "uk": "GB", "gb": "GB", "unitedkingdom": "GB", "greatbritain": "GB",
    "england": "GB", "scotland": "GB", "wales": "GB",
    "germany": "DE", "de": "DE", "deutschland": "DE",
    "ireland": "IE", "ie": "IE", "eire": "IE",
}

# Location strings that describe a working arrangement rather than a place.
REMOTE_TOKENS = {"remote", "remoteanywhere", "anywhere", "worldwide", "global", "distributed"}


def to_country_code(value: str | None) -> str | None:
    if value is None:
        return None

    return COUNTRIES.get(collapse(value))


def build_location(raw: Any, city: Any, region: Any, country: Any) -> Location:
    country = to_clean_string(country)
    return Location(
        raw=raw,
        city=to_clean_string(city),
        region=to_clean_string(region),
        country=country,
        country_code=to_country_code(country),
    )


def parse_location(value: Any) -> Location | None:
    if isinstance(value, dict):
        return build_location(value, value.get("city"), value.get("state"), value.get("country"))

    text = to_clean_string(value)
    if text is None:
        return None

    if collapse(text) in REMOTE_TOKENS:
        return build_location(value, None, None, None)

    parts = [part for part in (to_clean_string(part) for part in text.split(",")) if part]
    if not parts:
        return None

    if len(parts) == 1:
        only = parts[0]
        if to_country_code(only):
            return build_location(value, None, None, only)
        return build_location(value, only, None, None)

    return build_location(value, parts[0], ", ".join(parts[1:-1]) or None, parts[-1])
