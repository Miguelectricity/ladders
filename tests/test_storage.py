from datetime import date

import pytest

from backend.models import CountryCode, Location
from backend.storage.storage import JobStore, SortField

from .conftest import usd


def at(country_code) -> Location:
    return Location(raw=None, city="Somewhere", region=None, country_code=country_code)


@pytest.fixture
def store(make_job):
    """Five approved jobs, deliberately out of order on every sortable field."""
    store = JobStore()
    store.approved = [
        make_job(id="1", title="Backend Engineer", location=at(CountryCode.US),
                 salary=usd(annual=145_000), posting_date=date(2023, 10, 3)),
        make_job(id="2", title="Frontend Engineer", location=at(CountryCode.CA),
                 salary=usd(annual=110_000), posting_date=date(2023, 10, 15)),
        make_job(id="3", title="Data Scientist", location=at(CountryCode.CA),
                 salary=usd(hourly=62), posting_date=date(2023, 10, 10)),
        make_job(id="4", title="Product Manager", location=at(CountryCode.US),
                 salary=usd(annual=200_000), posting_date=date(2023, 10, 1)),
        make_job(id="5", title="QA Engineer", location=at(CountryCode.US),
                 salary=None, posting_date=None),
    ]
    return store


def ids(page):
    return [job.id for job in page.items]


class TestSearch:
    def test_returns_everything_by_default(self, store):
        assert store.search().total == 5

    def test_by_title(self, store):
        assert sorted(ids(store.search(query="Engineer"))) == ["1", "2", "5"]

    def test_is_case_insensitive(self, store):
        assert ids(store.search(query="backend")) == ["1"]

    def test_matches_partial_words(self, store):
        assert sorted(ids(store.search(query="ngine"))) == ["1", "2", "5"]

    def test_ignores_surrounding_whitespace(self, store):
        assert ids(store.search(query="  backend  ")) == ["1"]

    def test_no_matches(self, store):
        page = store.search(query="Chef")
        assert page.items == []
        assert page.total == 0

    def test_does_not_search_the_description(self, store):
        # Titles only, per the requirement.
        assert store.search(query="Senior Engineer.").total == 0


class TestFilter:
    def test_by_country(self, store):
        assert sorted(ids(store.search(country=CountryCode.US))) == ["1", "4", "5"]
        assert sorted(ids(store.search(country=CountryCode.CA))) == ["2", "3"]

    def test_combined_with_a_query(self, store):
        assert ids(store.search(query="Engineer", country=CountryCode.CA)) == ["2"]

    def test_jobs_without_a_location_are_excluded(self, store, make_job):
        store.approved = [*store.approved, make_job(id="6", location=None)]
        assert "6" not in ids(store.search(country=CountryCode.US, page_size=100))


class TestRemoteFilter:
    @pytest.fixture
    def store(self, make_job):
        store = JobStore()
        store.approved = [
            make_job(id="remote-us", location=at(CountryCode.US), is_remote=True),
            make_job(id="office-us", location=at(CountryCode.US), is_remote=False),
            make_job(id="remote-ca", location=at(CountryCode.CA), is_remote=True),
            make_job(id="unknown-us", location=at(CountryCode.US), is_remote=None),
        ]
        return store

    def test_off_by_default(self, store):
        # Not passing the filter is "any arrangement", not "on-site".
        assert store.search().total == 4

    def test_remote_only(self, store):
        assert sorted(ids(store.search(remote=True))) == ["remote-ca", "remote-us"]

    def test_on_site_only(self, store):
        # The API supports it even though the UI toggle never asks for it.
        assert sorted(ids(store.search(remote=False))) == ["office-us", "unknown-us"]

    def test_unknown_arrangement_counts_as_not_remote(self, store):
        # Same reading approval takes, so the two never disagree about a job.
        assert "unknown-us" not in ids(store.search(remote=True))

    def test_narrows_with_country_rather_than_replacing_it(self, store):
        # A remote job in Toronto answers to both filters; together they mean
        # "remote, and in Canada".
        assert ids(store.search(country=CountryCode.CA, remote=True)) == ["remote-ca"]
        assert sorted(ids(store.search(country=CountryCode.US, remote=True))) == ["remote-us"]

    def test_narrows_with_a_query(self, store, make_job):
        store.approved = [
            make_job(id="a", title="Remote Engineer", is_remote=True),
            make_job(id="b", title="Remote Designer", is_remote=True),
        ]
        assert ids(store.search(query="Engineer", remote=True)) == ["a"]

    def test_is_part_of_the_cache_key(self, store):
        # Two searches differing only by this flag must not share an entry.
        assert store.search(remote=True).total == 2
        assert store.search(remote=False).total == 2
        assert store.search().total == 4


class TestSort:
    def test_by_salary_descending(self, store):
        page = store.search(sort_by=SortField.SALARY_ANNUAL, descending=True)
        assert ids(page)[:3] == ["4", "1", "2"]

    def test_by_salary_ascending(self, store):
        page = store.search(sort_by=SortField.SALARY_ANNUAL, descending=False)
        assert ids(page)[:3] == ["2", "1", "4"]

    def test_by_posting_date_descending(self, store):
        page = store.search(sort_by=SortField.POSTING_DATE, descending=True)
        assert ids(page)[:4] == ["2", "3", "1", "4"]

    def test_by_posting_date_ascending(self, store):
        page = store.search(sort_by=SortField.POSTING_DATE, descending=False)
        assert ids(page)[:4] == ["4", "1", "3", "2"]

    def test_by_title(self, store):
        page = store.search(sort_by=SortField.TITLE, descending=False)
        assert ids(page)[0] == "1"  # Backend Engineer

    def test_hourly_and_annual_sort_separately(self, store):
        # Only job 3 states an hourly rate, so it is the only rankable one.
        page = store.search(sort_by=SortField.SALARY_HOURLY, descending=True)
        assert ids(page)[0] == "3"

    @pytest.mark.parametrize("descending", [True, False])
    def test_jobs_missing_the_sort_field_go_last(self, store, descending):
        # Job 5 has no salary; it should never lead either ordering.
        page = store.search(sort_by=SortField.SALARY_ANNUAL, descending=descending)
        assert ids(page)[-1] == "5"


class TestPaging:
    def test_slices_after_filtering(self, store):
        page = store.search(sort_by=SortField.TITLE, descending=False, page=0, page_size=2)
        assert len(page.items) == 2
        assert page.total == 5  # the whole result set, not the slice

    def test_pages_do_not_overlap(self, store):
        first = store.search(sort_by=SortField.TITLE, page=0, page_size=2)
        second = store.search(sort_by=SortField.TITLE, page=1, page_size=2)
        assert set(ids(first)).isdisjoint(ids(second))

    def test_total_pages_rounds_up(self, store):
        assert store.search(page_size=2).total_pages == 3

    def test_page_past_the_end_is_empty(self, store):
        page = store.search(page=99, page_size=10)
        assert page.items == []
        assert page.total == 5

    def test_page_size_is_clamped(self, store):
        assert store.search(page_size=10_000).page_size <= 100

    def test_negative_page_is_clamped(self, store):
        assert store.search(page=-3).page == 0


class TestGet:
    def test_by_id(self, store):
        assert store.get("3").title == "Data Scientist"

    def test_unknown_id(self, store):
        assert store.get("nope") is None


class TestCache:
    def test_repeated_searches_agree(self, store):
        first = store.search(query="Engineer", sort_by=SortField.TITLE)
        second = store.search(query="Engineer", sort_by=SortField.TITLE)
        assert ids(first) == ids(second)

    def test_replacing_the_jobs_invalidates_it(self, store, make_job):
        assert store.search().total == 5
        store.approved = [make_job(id="only")]
        assert ids(store.search()) == ["only"]

    def test_in_place_edits_need_an_explicit_invalidate(self, store, make_job):
        store.search()  # warm the cache
        store.approved.append(make_job(id="6"))
        store.invalidate_cache()
        assert store.search(page_size=100).total == 6

    def test_bounded(self, store):
        # Distinct queries must not grow the cache without limit.
        for i in range(200):
            store.search(query=f"query-{i}")
        assert len(store._ordered_cache) <= 32
