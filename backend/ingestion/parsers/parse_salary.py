import re
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.ingestion.parsers.helpers import to_clean_string
from backend.models import Currency, Salary

HOURLY_THRESHOLD = Decimal(1000)
DEFAULT_CURRENCY = "USD"
HOURLY_UNITS = {"hourly", "hour", "hr", "per hour", "/hr"}
ANNUAL_UNITS = {"annual", "annually", "year", "yearly", "per year", "/yr"}

# A letter touching a digit changes what the number means - "90k" is not 90 and
# "1.5e5" is not 1.55 - so the value is unusable rather than strippable.
GLUED_LETTER = re.compile(r"\d[^\W\d_]|[^\W\d_]\d")

# Words ("per year") and symbols ("$") sit beside the number without changing
# it, so they come off before the number is validated.
NOISE = re.compile(r"[^\W\d_]+|[^\d,.\-]")

# What is left has to be a number outright: bare, or comma-grouped in threes.
# Anything else - "120000-140000", "12.5.3", "120.000,50" - is ambiguous, and a
# wrong salary on the board is worse than no salary.
NUMERIC = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")


def coerce_to_decimal(value: Any) -> Decimal | None:
    # bool is a subclass of int, and Decimal("True") raises rather than returning.
    if isinstance(value, bool):
        return None

    if isinstance(value, Decimal):
        amount = value

    elif isinstance(value, (int, float)):
        try:
            amount = Decimal(str(value))
        except InvalidOperation:
            return None

    elif isinstance(value, str):
        text = value.strip()
        if GLUED_LETTER.search(text):
            return None

        cleaned = NOISE.sub("", text)
        if not NUMERIC.fullmatch(cleaned):
            return None

        try:
            amount = Decimal(cleaned.replace(",", ""))
        except InvalidOperation:
            return None

    else:
        return None

    # JSON admits Infinity and NaN. Infinity survives every check below and only
    # fails at serialization, where it 500s the whole listing rather than
    # costing one posting; NaN raises on the first comparison.
    return amount if amount.is_finite() else None


def parse_salary(value: Any) -> Salary | None:
    if isinstance(value, dict):
        amount = coerce_to_decimal(value.get("value"))
        currency = to_clean_string(value.get("currency"))
        unit = to_clean_string(value.get("unit"))
    else:
        amount = coerce_to_decimal(value)
        currency = None
        unit = None

    if amount is None or amount <= 0:
        return None

    unit = unit.lower() if unit else None
    if unit in HOURLY_UNITS:
        is_hourly = True
        inferred_period = False
    elif unit in ANNUAL_UNITS:
        is_hourly = False
        inferred_period = False
    else:
        is_hourly = amount < HOURLY_THRESHOLD
        inferred_period = True

    return Salary(
        raw=value,
        min_annual=None if is_hourly else amount,
        min_hourly=amount if is_hourly else None,
        currency=(
            Currency.USD
            if (currency or DEFAULT_CURRENCY).upper() == Currency.USD
            else Currency.OTHER
        ),
        inferred_currency=currency is None,
        inferred_period=inferred_period,
    )
