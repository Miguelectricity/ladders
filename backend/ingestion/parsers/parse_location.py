from typing import Any

from backend.ingestion.parsers.helpers import collapse, to_clean_string
from backend.models import CountryCode, Location

# The only countries CountryCode can name. Every other country falls to OTHER,
# so this table doubles as the set of country spellings we recognise on sight.
COUNTRIES = {
    "usa": CountryCode.US, "us": CountryCode.US, "unitedstates": CountryCode.US,
    "unitedstatesofamerica": CountryCode.US, "america": CountryCode.US,
    "canada": CountryCode.CA, "ca": CountryCode.CA, "can": CountryCode.CA,
}

# Location strings that describe a working arrangement rather than a place.
REMOTE_TOKENS = {"remote", "remoteanywhere", "anywhere", "worldwide", "global", "distributed"}


def to_country_code(value: str | None) -> CountryCode | None:
    """US and Canada by name; any other country we were given is OTHER."""
    if value is None:
        return None

    return COUNTRIES.get(collapse(value), CountryCode.OTHER)


def build_location(raw: Any, city: Any, region: Any, country: Any) -> Location:
    country = to_clean_string(country)
    return Location(
        raw=raw,
        city=to_clean_string(city),
        region=to_clean_string(region),
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
        if collapse(only) in COUNTRIES:
            return build_location(value, None, None, only)
        return build_location(value, only, None, None)

    return build_location(value, parts[0], ", ".join(parts[1:-1]) or None, parts[-1])
