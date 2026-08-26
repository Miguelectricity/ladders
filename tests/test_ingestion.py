import json
from datetime import date
from decimal import Decimal

import pytest

from backend.ingestion.ingestion import (
    DEFAULT_FEED,
    FeedError,
    load_feeds,
    load_raw,
    process_raw,
)
from backend.models import CompanyType, CountryCode, EmploymentType, Language

STRUCTURED = {
    "title": "Backend Engineer",
    "description": "Join our backend team.",
    "company": "NextGen Systems",
    "location": {"city": "Austin", "state": "TX", "country": "USA"},
    "salary": {"value": 145000, "currency": "USD"},
    "employment_type": "Full-Time",
    "posting_date": "2023-10-03",
    "company_type": "Direct Employer",
    "language": "English",
    "remote": False,
}

FLAT = {
    "title": "Senior Software Engineer",
    "description": "We are looking for a Senior Software Engineer.",
    "company": "Tech Innovators Inc.",
    "location": "New York, NY, USA",
    "salary": 150000,
    "employment_type": "Full-Time",
    "posting_date": "2023-10-01",
    "company_type": "Direct Employer",
    "language": "English",
    "remote": False,
}


class TestLoadRaw:
    def test_reads_the_bundled_feed(self):
        assert len(load_raw()) == 20

    def test_missing_file(self, tmp_path):
        with pytest.raises(FeedError):
            load_raw(tmp_path / "nope.json")

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "feed.json"
        path.write_text("{not json")
        with pytest.raises(FeedError):
            load_raw(path)

    def test_top_level_must_be_a_list(self, tmp_path):
        path = tmp_path / "feed.json"
        path.write_text(json.dumps({"jobs": []}))
        with pytest.raises(FeedError):
            load_raw(path)


class TestLoadFeeds:
    def test_reads_every_feed_in_the_directory(self, tmp_path):
        (tmp_path / "a.json").write_text(json.dumps([STRUCTURED]))
        (tmp_path / "b.json").write_text(json.dumps([FLAT, FLAT]))

        assert len(load_feeds(tmp_path)) == 3

    def test_reads_them_in_a_stable_order(self, tmp_path):
        (tmp_path / "b.json").write_text(json.dumps([FLAT]))
        (tmp_path / "a.json").write_text(json.dumps([STRUCTURED]))

        titles = [record["title"] for record in load_feeds(tmp_path)]
        assert titles == ["Backend Engineer", "Senior Software Engineer"]

    def test_ignores_files_that_are_not_json(self, tmp_path):
        (tmp_path / "feed.json").write_text(json.dumps([STRUCTURED]))
        (tmp_path / "notes.txt").write_text("not a feed")
        (tmp_path / "feed.json.bak").write_text("{broken")

        assert len(load_feeds(tmp_path)) == 1

    def test_one_broken_feed_does_not_stop_the_others(self, tmp_path):
        (tmp_path / "good.json").write_text(json.dumps([STRUCTURED]))
        (tmp_path / "broken.json").write_text("{not json")

        assert len(load_feeds(tmp_path)) == 1

    def test_nothing_usable_is_an_error(self, tmp_path):
        # An empty board is worse than a boot that says why.
        (tmp_path / "broken.json").write_text("{not json")
        with pytest.raises(FeedError):
            load_feeds(tmp_path)

    def test_empty_directory_is_an_error(self, tmp_path):
        with pytest.raises(FeedError):
            load_feeds(tmp_path)

    def test_duplicates_across_feeds_collapse(self, tmp_path):
        # The same posting listed by two sources is still one job.
        (tmp_path / "source_a.json").write_text(json.dumps([STRUCTURED, FLAT]))
        (tmp_path / "source_b.json").write_text(json.dumps([STRUCTURED]))

        jobs, failures = process_raw(load_feeds(tmp_path))

        assert failures == []
        assert len(jobs) == 2

    def test_the_bundled_directory_is_the_default(self):
        assert load_feeds() == load_raw(DEFAULT_FEED)


class TestProcessRaw:
    def test_both_feed_formats(self):
        jobs, failures = process_raw([STRUCTURED, FLAT])

        assert failures == []
        structured, flat = jobs
        assert structured.location.country_code is CountryCode.US
        assert structured.salary.min_annual == Decimal(145000)
        assert flat.location.country_code is CountryCode.US
        assert flat.salary.min_annual == Decimal(150000)

    def test_maps_every_field(self):
        (job,), _ = process_raw([STRUCTURED])

        assert job.title == "Backend Engineer"
        assert job.company == "NextGen Systems"
        assert job.employment_type is EmploymentType.FULL_TIME
        assert job.company_type is CompanyType.DIRECT_EMPLOYER
        assert job.language is Language.EN
        assert job.posting_date == date(2023, 10, 3)
        assert job.is_remote is False

    def test_blank_strings_become_none(self):
        (job,), _ = process_raw([{**STRUCTURED, "title": "  ", "description": ""}])
        assert job.title is None
        assert job.description is None

    def test_scraped_remote_flag_is_parsed_not_trusted(self):
        # The string "false" is truthy in Python; taking it raw would flip the
        # job to remote and let it skip the US/Canada geography check.
        (job,), _ = process_raw([{**STRUCTURED, "remote": "false"}])
        assert job.is_remote is False

    @pytest.mark.parametrize("record", [None, "a string", 42, [], True])
    def test_non_object_records_are_skipped(self, record):
        jobs, failures = process_raw([record])
        assert jobs == []
        assert len(failures) == 1

    def test_one_bad_record_does_not_lose_the_feed(self):
        jobs, failures = process_raw([None, STRUCTURED, "junk", FLAT])

        assert [job.title for job in jobs] == ["Backend Engineer", "Senior Software Engineer"]
        assert [index for index, _ in failures] == [0, 2]

    def test_failures_carry_the_record_position(self):
        _, failures = process_raw([STRUCTURED, 42])
        (index, reason), = failures
        assert index == 1
        assert "int" in reason

    def test_wrongly_typed_fields_degrade_instead_of_raising(self):
        # Nothing here is the type the feed promised.
        jobs, failures = process_raw([
            {"title": 123, "location": 5, "salary": "n/a", "posting_date": [], "remote": {}}
        ])
        (job,) = jobs
        assert failures == []
        assert job.title is None
        assert job.location is None
        assert job.salary is None
        assert job.posting_date is None
        assert job.is_remote is None

    def test_empty_feed(self):
        assert process_raw([]) == ([], [])


class TestDeduplication:
    def test_the_same_posting_twice_is_stored_once(self):
        jobs, _ = process_raw([STRUCTURED, STRUCTURED])
        assert len(jobs) == 1

    def test_the_whole_feed_is_idempotent(self):
        raw = load_raw()
        once, _ = process_raw(raw)
        twice, _ = process_raw(raw + raw)
        assert len(twice) == len(once)

    def test_the_first_copy_wins(self):
        later = {**STRUCTURED, "description": "Edited after the fact."}
        (job,), _ = process_raw([STRUCTURED, later])
        assert job.description == "Join our backend team."

    def test_the_same_posting_in_either_format_collapses(self):
        # Same posting, one feed spells the location as an object.
        flat = {**FLAT, "location": "New York, NY, USA"}
        structured = {**FLAT, "location": {"city": "New York", "state": "NY", "country": "USA"}}
        jobs, _ = process_raw([flat, structured])
        assert len(jobs) == 1

    def test_distinct_postings_are_kept(self):
        jobs, _ = process_raw([STRUCTURED, FLAT])
        assert len(jobs) == 2


def test_the_bundled_feed_parses_cleanly():
    jobs, failures = process_raw(load_raw())
    assert failures == []
    assert len(jobs) == 20
    assert DEFAULT_FEED.exists()
