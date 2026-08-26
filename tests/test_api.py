import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import app


@pytest.fixture
def client():
    # The `with` block runs lifespan, which is what ingests the feed.
    with TestClient(app) as client:
        yield client


def test_importing_the_app_ingests_nothing():
    """Ingestion belongs to startup, not to import.

    Checked in a fresh interpreter: within this session the fixture below has
    usually run already, so the in-process store says nothing about import.
    """
    source = (
        "import backend.api;"
        "from backend.storage.storage import store;"
        "assert store.approved == [], store.approved"
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


class TestListJobs:
    def test_returns_the_approved_feed(self, client):
        body = client.get("/api/jobs").json()
        assert body["total"] == 11
        assert body["page"] == 0

    def test_page_shape(self, client):
        body = client.get("/api/jobs?page_size=3").json()
        assert set(body) == {"items", "total", "page", "page_size"}
        assert len(body["items"]) == 3

    def test_job_shape(self, client):
        job = client.get("/api/jobs?page_size=1").json()["items"][0]
        assert set(job) == {
            "id", "title", "description", "company", "location", "salary",
            "employment_type", "posting_date", "company_type", "language", "is_remote",
        }

    def test_search_by_title(self, client):
        body = client.get("/api/jobs?query=engineer").json()
        assert body["total"] == 4
        assert all("engineer" in job["title"].lower() for job in body["items"])

    def test_filter_by_country(self, client):
        body = client.get("/api/jobs?country=US&page_size=100").json()
        assert body["total"] == 7
        assert all(job["location"]["country_code"] == "US" for job in body["items"])

    def test_sort_by_salary(self, client):
        items = client.get(
            "/api/jobs?sort_by=salary_annual&descending=true&page_size=100"
        ).json()["items"]
        salaries = [job["salary"]["min_annual"] for job in items if job["salary"]["min_annual"]]
        assert salaries == sorted(salaries, reverse=True)

    def test_sort_by_posting_date(self, client):
        items = client.get(
            "/api/jobs?sort_by=posting_date&descending=false&page_size=100"
        ).json()["items"]
        dates = [job["posting_date"] for job in items if job["posting_date"]]
        assert dates == sorted(dates)

    def test_paging(self, client):
        first = client.get("/api/jobs?page=0&page_size=5").json()
        second = client.get("/api/jobs?page=1&page_size=5").json()
        assert first["total"] == second["total"] == 11
        assert {job["id"] for job in first["items"]}.isdisjoint(
            job["id"] for job in second["items"]
        )

    @pytest.mark.parametrize(
        "query", ["page_size=0", "page_size=101", "page=-1", "country=XX", "sort_by=bogus"]
    )
    def test_rejects_bad_parameters(self, client, query):
        assert client.get(f"/api/jobs?{query}").status_code == 422


class TestGetJob:
    def test_by_id(self, client):
        listed = client.get("/api/jobs?page_size=1").json()["items"][0]
        assert client.get(f"/api/jobs/{listed['id']}").json() == listed

    def test_unknown_id(self, client):
        assert client.get("/api/jobs/nope").status_code == 404


class TestCountries:
    def test_lists_only_countries_that_have_jobs(self, client):
        codes = [row["code"] for row in client.get("/api/countries").json()]
        assert codes == ["US", "CA", "other"]  # enum order, so OTHER sorts last

    def test_codes_are_what_the_filter_accepts(self, client):
        for row in client.get("/api/countries").json():
            assert client.get(f"/api/jobs?country={row['code']}").status_code == 200


def test_raw_scrape_is_not_exposed(client):
    # Location.raw and Salary.raw are provenance for debugging, not API surface.
    assert '"raw"' not in client.get("/api/jobs?page_size=100").text
