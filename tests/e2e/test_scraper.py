"""End-to-end test: live careers-site scrape for SET-CORPORATION SRL.

Skips (rather than fails) when mesopotamia.ro is unreachable, so CI does not
break on transient network issues.
"""

import socket

import pytest

from scraper import index


def _site_reachable():
    try:
        with socket.create_connection(("www.mesopotamia.ro", 443), timeout=5):
            return True
    except OSError:
        return False


def test_scrape_real_careers_site():
    if not _site_reachable():
        pytest.skip("www.mesopotamia.ro not reachable")
    jobs = index.search_company_careers()
    assert isinstance(jobs, list)
    assert jobs, "expected at least one active careers page"
    for job in jobs:
        assert job["url"].startswith(index.CAREERS_PREFIX)
        assert job["title"]
        assert "contact_name" not in job
        assert "description" not in job
    urls = {j["url"] for j in jobs}
    assert len(urls) == len(jobs), "duplicate job URLs found"
