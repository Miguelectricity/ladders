from datetime import date
from decimal import Decimal

import pytest

from backend.models import (
    CompanyType,
    CountryCode,
    Currency,
    EmploymentType,
    Job,
    Language,
    Location,
    Salary,
)


def usd(annual=None, hourly=None, currency=Currency.USD) -> Salary:
    return Salary(
        raw=None,
        min_annual=Decimal(annual) if annual is not None else None,
        min_hourly=Decimal(hourly) if hourly is not None else None,
        currency=currency,
    )


@pytest.fixture
def make_job():
    """Builds a job that passes every approval rule.

    Tests override one field at a time, so a failure names the rule it broke.
    """
    def build(**overrides) -> Job:
        fields = dict(
            id="job-1",
            title="Senior Engineer",
            description="We are looking for a Senior Engineer.",
            company="Acme",
            location=Location(raw=None, city="Austin", region="TX", country_code=CountryCode.US),
            salary=usd(annual=150_000),
            employment_type=EmploymentType.FULL_TIME,
            posting_date=date(2023, 10, 3),
            company_type=CompanyType.DIRECT_EMPLOYER,
            language=Language.EN,
            is_remote=False,
        )
        fields.update(overrides)
        return Job(**fields)

    return build
