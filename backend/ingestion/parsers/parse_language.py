from typing import Any

from ladders.backend.ingestion.parsers.helpers import collapse, to_clean_string
from ladders.backend.models import Language

LANGUAGES = {
    "english": Language.EN,
    "en": Language.EN,
    "enus": Language.EN,
    "enca": Language.EN,
    "engb": Language.EN,
    "anglais": Language.EN,
    "french": Language.FR,
    "fr": Language.FR,
    "frca": Language.FR,
    "frfr": Language.FR,
    "francais": Language.FR,
    "français": Language.FR,
}


def parse_language(value: Any) -> Language:
    text = to_clean_string(value)
    if text is None:
        return Language.UNKNOWN

    return LANGUAGES.get(collapse(text), Language.UNKNOWN)
