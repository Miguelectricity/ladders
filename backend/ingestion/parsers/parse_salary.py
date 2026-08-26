from decimal import Decimal, InvalidOperation
from typing import Any

from backend.ingestion.parsers.helpers import to_clean_string
from backend.models import Currency, Salary

HOURLY_THRESHOLD = Decimal(1000)
DEFAULT_CURRENCY = "USD"
HOURLY_UNITS = {"hourly", "hour", "hr", "per hour", "/hr"}
ANNUAL_UNITS = {"annual", "annually", "year", "yearly", "per year", "/yr"}
ALLOWED = frozenset("0123456789.-")


def coerce_to_decimal(value: Any):
    if isinstance(value, Decimal):
        return value
    
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    
    if isinstance(value, str):
        cleaned = "".join(ch for ch in value if ch in ALLOWED)
        if not cleaned:
            return None
        
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
        
    return None


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
    )
    
    
    