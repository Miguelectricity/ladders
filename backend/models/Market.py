from dataclasses import dataclass
from decimal import Decimal

from backend.models.Job import CountryCode, Language, Currency


@dataclass(frozen=True)
class Market:
    name: str
    countries: frozenset[CountryCode] | None
    remote_only: bool
    min_annual_salary: Decimal | None
    min_hourly_salary: Decimal | None
    languages: frozenset[Language] | None
        

MARKETS = [
    Market(
        name="US",
        countries=frozenset({CountryCode.US}),
        remote_only=False,
        min_annual_salary=Decimal(100_000),
        min_hourly_salary=Decimal(45),
        languages=frozenset({Language.EN}),
    ),
    Market(
        name="Canada",
        countries=frozenset({CountryCode.CA}),
        remote_only=False,
        min_annual_salary=Decimal(100_000),
        min_hourly_salary=Decimal(45),
        languages=frozenset({Language.EN, Language.FR}),
    ),
    Market(
        name="Remote (any)",
        countries=None,
        remote_only=True,
        min_annual_salary=Decimal(100_000),
        min_hourly_salary=Decimal(45),
        languages=frozenset({Language.EN}),
    ),
]