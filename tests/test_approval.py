import logging
from decimal import Decimal

import pytest

from backend.approval.approval import approve_jobs, is_job_in_market
from backend.models import (
    CompanyType,
    CountryCode,
    Currency,
    EmploymentType,
    Language,
    Location,
    Market,
)

from .conftest import usd


def approve_one(job):
    """(is_approved, reason) for a single job."""
    approved, rejected = approve_jobs([job])
    if approved:
        return True, None
    return False, rejected[0][1]


def at(country_code) -> Location:
    return Location(raw=None, city="Somewhere", region=None, country_code=country_code)


class TestApproved:
    def test_a_us_job_meeting_every_rule(self, make_job):
        assert approve_one(make_job()) == (True, None)

    def test_canada_in_english(self, make_job):
        job = make_job(location=at(CountryCode.CA), language=Language.EN)
        assert approve_one(job)[0] is True

    def test_canada_in_french(self, make_job):
        job = make_job(location=at(CountryCode.CA), language=Language.FR)
        assert approve_one(job)[0] is True

    def test_remote_from_anywhere(self, make_job):
        job = make_job(location=at(CountryCode.OTHER), is_remote=True)
        assert approve_one(job)[0] is True

    def test_hourly_at_the_threshold(self, make_job):
        job = make_job(salary=usd(hourly=45))
        assert approve_one(job)[0] is True

    def test_annual_at_the_threshold(self, make_job):
        job = make_job(salary=usd(annual=100_000))
        assert approve_one(job)[0] is True


class TestRejected:
    @pytest.mark.parametrize("title", [None, "", "   "])
    def test_missing_title(self, make_job, title):
        assert approve_one(make_job(title=title)) == (False, "No title")

    @pytest.mark.parametrize(
        "employment_type",
        [EmploymentType.PART_TIME, EmploymentType.CONTRACT, EmploymentType.INTERNSHIP, EmploymentType.UNKNOWN],
    )
    def test_not_full_time(self, make_job, employment_type):
        assert approve_one(make_job(employment_type=employment_type)) == (False, "Not full-time")

    def test_staffing_firm(self, make_job):
        assert approve_one(make_job(company_type=CompanyType.STAFFING_FIRM)) == (False, "Staffing firm")

    def test_consulting_agency_is_allowed(self, make_job):
        # Only staffing firms are excluded by the criteria.
        assert approve_one(make_job(company_type=CompanyType.CONSULTING_AGENCY))[0] is True

    def test_in_person_outside_us_and_canada(self, make_job):
        job = make_job(location=at(CountryCode.OTHER), is_remote=False)
        assert approve_one(job) == (False, "Not in any approved markets")

    def test_no_location_and_not_remote(self, make_job):
        assert approve_one(make_job(location=None, is_remote=False))[0] is False

    @pytest.mark.parametrize("salary", [usd(annual=99_999), usd(hourly=44)])
    def test_below_the_salary_floor(self, make_job, salary):
        assert approve_one(make_job(salary=salary)) == (False, "Not in any approved markets")

    def test_no_salary_at_all(self, make_job):
        assert approve_one(make_job(salary=None))[0] is False

    def test_french_in_the_us(self, make_job):
        # French is accepted in Canada, not in the US market.
        assert approve_one(make_job(location=at(CountryCode.US), language=Language.FR))[0] is False

    @pytest.mark.parametrize("language", [Language.UNKNOWN])
    def test_unrecognised_language(self, make_job, language):
        assert approve_one(make_job(language=language))[0] is False


class TestKnownGaps:
    def test_non_usd_salary_skips_the_salary_check(self, make_job):
        """Documents assumptions.md, not desired behaviour.

        is_job_in_market only compares salaries stated in USD, so a remote job
        priced in another currency clears the floor without being checked - the
        UK posting in the sample feed is approved on an 85,000 GBP salary. Left
        as-is pending an FX decision.
        """
        job = make_job(
            location=at(CountryCode.OTHER),
            is_remote=True,
            salary=usd(annual=1, currency=Currency.OTHER),
        )
        assert approve_one(job)[0] is True

    def test_only_the_first_failed_rule_is_reported(self, make_job):
        # A job can break several rules; the reason names the one checked first.
        job = make_job(title=None, employment_type=EmploymentType.CONTRACT)
        assert approve_one(job) == (False, "No title")


class TestMarkets:
    """The markets list is the extension point for new approval conditions."""

    def test_a_new_market_can_admit_a_job_the_others_reject(self, make_job):
        remote_uk = Market(
            name="Remote UK",
            countries=frozenset({CountryCode.OTHER}),
            remote_only=True,
            min_annual_salary=Decimal(90_000),
            min_hourly_salary=None,
            languages=frozenset({Language.EN}),
        )
        job = make_job(location=at(CountryCode.OTHER), is_remote=True, salary=usd(annual=95_000))

        assert is_job_in_market(job, remote_uk) is True

    def test_a_market_rejects_below_its_own_floor(self, make_job):
        strict = Market(
            name="Strict",
            countries=frozenset({CountryCode.US}),
            remote_only=False,
            min_annual_salary=Decimal(200_000),
            min_hourly_salary=None,
            languages=frozenset({Language.EN}),
        )
        assert is_job_in_market(make_job(salary=usd(annual=150_000)), strict) is False

    def test_remote_only_market_ignores_office_jobs(self, make_job):
        remote_only = Market(
            name="Remote",
            countries=None,
            remote_only=True,
            min_annual_salary=None,
            min_hourly_salary=None,
            languages=None,
        )
        assert is_job_in_market(make_job(is_remote=False), remote_only) is False
        assert is_job_in_market(make_job(is_remote=True), remote_only) is True


class TestApproveJobs:
    def test_splits_the_batch(self, make_job):
        good = make_job(id="good")
        bad = make_job(id="bad", title=None)

        approved, rejected = approve_jobs([good, bad])

        assert [job.id for job in approved] == ["good"]
        assert [job.id for job, _ in rejected] == ["bad"]

    def test_every_rejection_carries_a_reason(self, make_job):
        _, rejected = approve_jobs([make_job(title=None), make_job(salary=None)])
        assert all(reason for _, reason in rejected)

    def test_empty_batch(self):
        assert approve_jobs([]) == ([], [])

    def test_rejections_are_logged(self, make_job, caplog, monkeypatch):
        # configure_logging() takes the `backend` logger off the root handler,
        # which is where caplog listens, so put it back for this test.
        monkeypatch.setattr(logging.getLogger("backend"), "propagate", True)

        with caplog.at_level(logging.INFO, logger="backend.approval.approval"):
            approve_jobs([make_job(title=None)])

        assert "No title" in caplog.text
