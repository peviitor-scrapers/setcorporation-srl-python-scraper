"""Unit tests for the careers-site index pipeline."""

import json
from unittest.mock import Mock

from scraper import index

COMPANY = "SET-CORPORATION SRL"
CIF = "29084042"
SITE = "https://www.mesopotamia.ro"


class _Response:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_map_to_job_model_adds_company_and_status():
    index.COMPANY_NAME = COMPANY
    raw = {"url": f"{SITE}/manager-roman/", "title": "Manager Roman", "location": ["Roman"]}
    job = index.map_to_job_model(raw, CIF)
    assert job["company"] == COMPANY
    assert job["cif"] == CIF
    assert job["status"] == "scraped"
    assert job["location"] == ["Roman"]
    assert job["date"]


def test_map_to_job_model_without_location():
    raw = {"url": f"{SITE}/cariera/", "title": "Cariera"}
    job = index.map_to_job_model(raw, CIF, company_name=COMPANY)
    assert "location" not in job


def test_map_to_job_model_keeps_optional_fields():
    raw = {
        "url": f"{SITE}/cariera-ploiesti/",
        "title": "Carieră Ploiești",
        "salary": "4000-5000 RON",
        "tags": ["cariera", "ploiesti"],
        "workmode": "on-site",
        "expirationdate": "2027-01-31",
    }
    job = index.map_to_job_model(raw, CIF, company_name=COMPANY)
    assert job["salary"] == "4000-5000 RON"
    assert job["tags"] == ["cariera", "ploiesti"]
    assert job["workmode"] == "on-site"
    assert job["expirationdate"] == "2027-01-31"


def test_transform_jobs_for_solr_uppercases_company():
    jobs = [{"url": "https://x/job", "title": "Test", "location": ["Roman"]}]
    transformed = index.transform_jobs_for_solr({"company": COMPANY, "jobs": jobs})
    assert transformed["company"] == COMPANY
    assert transformed["jobs"][0]["location"] == ["Roman"]


def test_transform_jobs_for_solr_location_fallback():
    jobs = [{"url": "https://x/job", "title": "Test", "location": []}]
    transformed = index.transform_jobs_for_solr({"company": COMPANY, "jobs": jobs})
    assert transformed["jobs"][0]["location"] == ["România"]


def test_transform_jobs_for_solr_missing_location_fallback():
    jobs = [{"url": "https://x/job", "title": "Test"}]
    transformed = index.transform_jobs_for_solr({"company": COMPANY, "jobs": jobs})
    assert transformed["jobs"][0]["location"] == ["România"]


def _stub_main(monkeypatch, tmp_path, raw_jobs):
    monkeypatch.setattr(index, "query_solr", lambda cif: {"numFound": 0, "docs": []})
    monkeypatch.setattr(index, "upsert_jobs", lambda jobs: None)
    monkeypatch.setattr(index, "delete_job_by_url", lambda url: None)
    monkeypatch.setattr(index, "upsert_company", lambda cfg: None)
    monkeypatch.setattr(index, "validate_and_get_company", lambda: {
        "company": COMPANY, "cif": CIF, "address": "SCHEIA"})
    monkeypatch.setattr(index, "search_company_careers", lambda company: raw_jobs)
    monkeypatch.setattr(index, "drop_dead_urls", lambda jobs: jobs)
    return tmp_path


def test_main_writes_summary(tmp_path, monkeypatch):
    fake_jobs = [
        {"url": f"{SITE}/cariera-{i}/", "title": f"Job {i}", "location": ["Roman"]}
        for i in range(3)
    ]
    root = _stub_main(monkeypatch, tmp_path, fake_jobs)

    index.main(root=root)

    out = tmp_path / "scraper" / "jobs.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["jobs"]) == 3
    assert data["company"] == COMPANY
    assert data["source"] == "mesopotamia.ro"
    assert (tmp_path / "docs" / "jobs.md").exists()


def test_main_preserves_enriched_fields(tmp_path, monkeypatch):
    fake_jobs = [{
        "url": f"{SITE}/manager-roman/",
        "title": "Manager Roman",
        "location": ["Roman"],
        "salary": "4000-5000 RON",
        "tags": ["manager", "roman"],
        "workmode": "on-site",
        "expirationdate": "2027-01-31",
    }]
    root = _stub_main(monkeypatch, tmp_path, fake_jobs)

    index.main(root=root)

    job = json.loads((tmp_path / "scraper" / "jobs.json").read_text(encoding="utf-8"))["jobs"][0]
    assert job["salary"] == "4000-5000 RON"
    assert job["tags"] == ["manager", "roman"]
    assert job["workmode"] == "on-site"
    assert job["expirationdate"] == "2027-01-31"


def test_main_dedupes_careers_urls(tmp_path, monkeypatch):
    job = {"url": f"{SITE}/manager-valcea/", "title": "Manager Vâlcea"}
    root = _stub_main(monkeypatch, tmp_path, [job, dict(job)])

    index.main(root=root)

    data = json.loads((tmp_path / "scraper" / "jobs.json").read_text(encoding="utf-8"))
    assert len(data["jobs"]) == 1


def test_main_canary_aborts_before_any_write(tmp_path, monkeypatch):
    upserted = []
    root = _stub_main(monkeypatch, tmp_path, [])
    monkeypatch.setattr(index, "upsert_jobs", lambda jobs: upserted.append(jobs))
    monkeypatch.setattr(index, "upsert_company", lambda cfg: (_ for _ in ()).throw(AssertionError("no write")))

    index.main(root=root)

    assert upserted == []
    assert not (tmp_path / "scraper" / "jobs.json").exists()


def test_drop_dead_urls_drops_soft_404(monkeypatch):
    good = {"url": f"{SITE}/good/", "title": "Good"}
    old = {"url": f"{SITE}/old/", "title": "Old"}
    monkeypatch.setattr(index, "validate_by_content", lambda url: {
        "url": url, "status": "active" if url.endswith("good/") else "expired",
        "http_status": 200, "error": None})

    assert index.drop_dead_urls([good, old]) == [good]


def test_careers_page_is_for_company_checks_cif_and_name():
    page = "<footer>SC SET-CORPORATION SRL J33/836/2011 RO 29084042</footer>"
    assert index._careers_page_is_for_company(page, COMPANY)
    assert not index._careers_page_is_for_company(page.replace("29084042", "00000000"), COMPANY)
    assert not index._careers_page_is_for_company(page, "ALTCEVA SRL")


def test_careers_sitemap_urls_only_known_pages(monkeypatch):
    sitemap = "".join(
        f"<loc>{url}</loc>" for url in list(index.CAREERS_JOBS)[:2]
    ) + "<loc>https://www.mesopotamia.ro/stores/</loc>"
    monkeypatch.setattr(index.requests, "get", lambda *a, **k: _Response(sitemap))

    assert index._careers_sitemap_urls() == tuple(list(index.CAREERS_JOBS)[:2])


def test_careers_title_prefers_title_tag():
    url = f"{SITE}/manager-roman/"
    page = "<title>Manager - Roman - Mesopotamia Romania - gustul care nu se uită!</title>"
    assert index._careers_title(url, page) == "Manager - Roman"


def test_search_company_careers_maps_distinct_urls(monkeypatch):
    urls = list(index.CAREERS_JOBS)[:2]
    sitemap = "".join(f"<loc>{u}</loc>" for u in urls)
    page = ("<title>Manager - Roman - Mesopotamia Romania</title>"
            "<footer>SC SET-CORPORATION SRL RO 29084042</footer>")
    responses = [_Response(sitemap), _Response(page), _Response(page)]
    monkeypatch.setattr(index.requests, "get", lambda *a, **k: responses.pop(0))

    jobs = index.search_company_careers(COMPANY)

    assert [job["url"] for job in jobs] == urls
    assert jobs[0]["title"] == "Manager - Roman"
    assert jobs[0]["location"] == ["România"]
    assert all("contact_name" not in job and "description" not in job for job in jobs)
