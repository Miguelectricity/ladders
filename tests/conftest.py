from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.ingestion import ingestion
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


FIXTURE_FEED_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURE_FEED = FIXTURE_FEED_DIR / "feed.json"


@pytest.fixture
def feed_dir(monkeypatch):
    """Ingest from the tests' own feed instead of backend/data/mock.

    The shipped feeds are sample data and change; every count asserted in these
    tests is a fact about tests/fixtures/feed.json, which does not.
    """
    monkeypatch.setattr(ingestion, "FEED_DIR", FIXTURE_FEED_DIR)
    monkeypatch.setattr(ingestion, "DEFAULT_FEED", FIXTURE_FEED)
    return FIXTURE_FEED_DIR


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
