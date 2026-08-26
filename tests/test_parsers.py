from datetime import date, datetime
from decimal import Decimal

import pytest

from backend.ingestion.job_id_hash import make_job_id
from backend.ingestion.parsers import (
    parse_company_type,
    parse_employment_type,
    parse_language,
    parse_location,
    parse_posting_date,
    parse_remote,
    parse_salary,
)
from backend.models import CompanyType, CountryCode, Currency, EmploymentType, Language


class TestParseSalary:
    def test_structured_annual(self):
        salary = parse_salary({"value": 145000, "currency": "USD"})
        assert salary.min_annual == Decimal(145000)
        assert salary.min_hourly is None
        assert salary.currency is Currency.USD
        assert salary.inferred_currency is False

    def test_structured_hourly(self):
        salary = parse_salary({"value": 65, "currency": "USD", "unit": "hourly"})
        assert salary.min_hourly == Decimal(65)
        assert salary.min_annual is None
        # The unit was stated, so nothing had to be guessed.
        assert salary.inferred_period is False

    def test_bare_number_assumes_usd(self):
        salary = parse_salary(150000)
        assert salary.min_annual == Decimal(150000)
        assert salary.currency is Currency.USD
        assert salary.inferred_currency is True

    @pytest.mark.parametrize(
        "value, annual, hourly",
        [
            (150000, Decimal(150000), None),
            (62.5, None, Decimal("62.5")),
            # The threshold decides annual-vs-hourly when the feed doesn't say.
            (999, None, Decimal(999)),
            (1000, Decimal(1000), None),
        ],
    )
    def test_period_inferred_from_magnitude(self, value, annual, hourly):
        salary = parse_salary(value)
        assert (salary.min_annual, salary.min_hourly) == (annual, hourly)
        assert salary.inferred_period is True

    def test_stated_unit_beats_magnitude(self):
        # 65 looks hourly, and here it genuinely is - but the unit, not the size,
        # is what settled it.
        assert parse_salary({"value": 65, "unit": "per hour"}).min_hourly == Decimal(65)
        assert parse_salary({"value": 900, "unit": "yearly"}).min_annual == Decimal(900)

    def test_non_usd_is_flagged_not_converted(self):
        salary = parse_salary({"value": 85000, "currency": "GBP"})
        assert salary.currency is Currency.OTHER
        assert salary.min_annual == Decimal(85000)

    def test_strips_currency_symbols_and_separators(self):
        assert parse_salary("$120,000 per year").min_annual == Decimal(120000)

    @pytest.mark.parametrize("value", [None, "", 0, -5, "negotiable", {}, {"value": None}])
    def test_unusable_values_give_no_salary(self, value):
        assert parse_salary(value) is None

    @pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), True])
    def test_non_finite_and_bool_give_no_salary(self, value):
        # Infinity serializes to invalid JSON, NaN raises on comparison, and
        # Decimal("True") raises outright - none of them may reach a Salary.
        assert parse_salary(value) is None

    @pytest.mark.parametrize("value", ["90k", "USD 90k", "1.5e5", "1e999999"])
    def test_a_letter_glued_to_the_number_is_unusable(self, value):
        # Stripping the letter changes the magnitude: "90k" is not 90/hour.
        assert parse_salary(value) is None

    @pytest.mark.parametrize("value", ["120.000,50", "1,00", "12.5.3"])
    def test_ambiguous_separators_are_unusable(self, value):
        # Which separator is the decimal point is a guess, and a wrong salary on
        # the board is worse than no salary.
        assert parse_salary(value) is None

    def test_grouped_thousands_still_parse(self):
        assert parse_salary("$120,000.50").min_annual == Decimal("120000.50")

    def test_range_is_not_supported_yet(self):
        # Documented in assumptions.md: a range parses to nothing rather than
        # silently picking one end of it.
        assert parse_salary("120000-140000") is None


class TestParseLocation:
    def test_structured(self):
        location = parse_location({"city": "Austin", "state": "TX", "country": "USA"})
        assert (location.city, location.region) == ("Austin", "TX")
        assert location.country_code is CountryCode.US

    def test_flat_string(self):
        location = parse_location("New York, NY, USA")
        assert (location.city, location.region) == ("New York", "NY")
        assert location.country_code is CountryCode.US

    def test_two_part_string_has_no_region(self):
        location = parse_location("London, UK")
        assert (location.city, location.region) == ("London", None)
        assert location.country_code is CountryCode.OTHER

    def test_country_only(self):
        location = parse_location("Canada")
        assert location.country_code is CountryCode.CA
        assert location.city is None

    def test_city_only(self):
        location = parse_location("Austin")
        assert location.city == "Austin"
        assert location.country_code is None

    def test_remote_is_not_a_place(self):
        location = parse_location("Remote")
        assert location.country_code is None
        assert location.city is None

    def test_blank_parts_are_dropped(self):
        location = parse_location({"city": "", "state": "CA", "country": "USA"})
        assert location.city is None
        assert location.region == "CA"

    @pytest.mark.parametrize("value", [None, "", "   ", ","])
    def test_unusable_values_give_no_location(self, value):
        assert parse_location(value) is None

    @pytest.mark.parametrize(
        "country, expected",
        [
            ("USA", CountryCode.US),
            ("United States", CountryCode.US),
            ("us", CountryCode.US),
            ("Canada", CountryCode.CA),
            ("CA", CountryCode.CA),
            ("Germany", CountryCode.OTHER),
            ("UK", CountryCode.OTHER),
        ],
    )
    def test_country_spellings(self, country, expected):
        assert parse_location({"country": country}).country_code is expected


class TestParseEnums:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("Full-Time", EmploymentType.FULL_TIME),
            ("full time", EmploymentType.FULL_TIME),
            ("Permanent", EmploymentType.FULL_TIME),
            ("Part-Time", EmploymentType.PART_TIME),
            ("Internship", EmploymentType.INTERNSHIP),
            ("Contract", EmploymentType.CONTRACT),
            ("", EmploymentType.UNKNOWN),
            (None, EmploymentType.UNKNOWN),
            ("Seasonal", EmploymentType.UNKNOWN),
        ],
    )
    def test_employment_type(self, value, expected):
        assert parse_employment_type(value) is expected

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("Direct Employer", CompanyType.DIRECT_EMPLOYER),
            ("Staffing Firm", CompanyType.STAFFING_FIRM),
            ("staffing agency", CompanyType.STAFFING_FIRM),
            ("Consulting Agency", CompanyType.CONSULTING_AGENCY),
            ("", CompanyType.UNKNOWN),
            (None, CompanyType.UNKNOWN),
        ],
    )
    def test_company_type(self, value, expected):
        assert parse_company_type(value) is expected

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("English", Language.EN),
            ("en-US", Language.EN),
            ("French", Language.FR),
            ("Français", Language.FR),
            ("German", Language.UNKNOWN),
            ("", Language.UNKNOWN),
            (None, Language.UNKNOWN),
        ],
    )
    def test_language(self, value, expected):
        assert parse_language(value) is expected


class TestParseRemote:
    @pytest.mark.parametrize("value", [True, 1, "true", "Yes", "Remote", "WFH"])
    def test_remote(self, value):
        assert parse_remote(value) is True

    @pytest.mark.parametrize("value", [False, 0, "false", "No", "On-site", "hybrid"])
    def test_on_site(self, value):
        assert parse_remote(value) is False

    @pytest.mark.parametrize("value", [None, "", "maybe", [], {"remote": True}])
    def test_unknown_stays_unknown(self, value):
        # Not False: a missing flag is not a claim that the job is on-site.
        assert parse_remote(value) is None


class TestParsePostingDate:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("2023-10-03", date(2023, 10, 3)),
            ("2023/10/03", date(2023, 10, 3)),
            ("10/03/2023", date(2023, 10, 3)),
            ("October 3, 2023", date(2023, 10, 3)),
            (date(2023, 10, 3), date(2023, 10, 3)),
            (datetime(2023, 10, 3, 9, 30), date(2023, 10, 3)),
        ],
    )
    def test_known_formats(self, value, expected):
        assert parse_posting_date(value) == expected

    @pytest.mark.parametrize("value", [None, "", "yesterday", "2023-13-45", 20231003])
    def test_unusable_values_give_no_date(self, value):
        assert parse_posting_date(value) is None


class TestMakeJobId:
    def test_is_deterministic(self, make_job):
        job = make_job()
        args = (job.title, job.company, job.location, job.posting_date)
        assert make_job_id(*args) == make_job_id(*args)

    def test_ignores_formatting_of_the_same_posting(self):
        # The two feed formats spell the same posting differently.
        structured = parse_location({"city": "New York", "state": "NY", "country": "USA"})
        flat = parse_location("New York, NY, USA")
        assert make_job_id("Engineer", "Acme", structured, "2023-10-01") == make_job_id(
            "Engineer", "Acme", flat, "2023-10-01"
        )

    @pytest.mark.parametrize(
        "title, company",
        [("Other Engineer", "Acme"), ("Engineer", "Other Co")],
    )
    def test_different_postings_get_different_ids(self, title, company):
        location = parse_location("Austin, TX, USA")
        baseline = make_job_id("Engineer", "Acme", location, "2023-10-01")
        assert make_job_id(title, company, location, "2023-10-01") != baseline

    def test_posting_date_affects_the_id(self):
        location = parse_location("Austin, TX, USA")
        assert make_job_id("Engineer", "Acme", location, date(2023, 10, 1)) != make_job_id(
            "Engineer", "Acme", location, date(2024, 1, 1)
        )

    @pytest.mark.parametrize(
        "posting_date",
        [date(2023, 10, 1), datetime(2023, 10, 1, 9, 30), "2023-10-01", "2023/10/01"],
    )
    def test_a_date_hashes_the_same_however_it_is_spelled(self, posting_date):
        # process_raw() passes a parsed date; a caller may pass the raw string.
        location = parse_location("Austin, TX, USA")
        assert make_job_id("Engineer", "Acme", location, posting_date) == make_job_id(
            "Engineer", "Acme", location, "2023-10-01"
        )

    def test_a_missing_date_still_produces_an_id(self):
        location = parse_location("Austin, TX, USA")
        assert make_job_id("Engineer", "Acme", location, None)
