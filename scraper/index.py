"""
SET-CORPORATION SRL multi-source scraper

Collects the active vacancies published by SET-CORPORATION SRL
(CUI 29084042, brand Mesopotamia) on its own careers site and publishes them
to peviitor.ro via the v1 API. Distinct URLs are distinct jobs.
"""

import datetime
import html
import json
import pathlib
import re
import sys
import unicodedata
from urllib.parse import urljoin

import requests

from .api import delete_job_by_url, map_with_concurrency, query_solr, upsert_company, upsert_jobs
from .company import validate_and_get_company
from .config import company_config, scraper_config
from .job_validator import validate_by_content
from .markdown_generator import generate_jobs_markdown

COMPANY_CIF = company_config["id"]
JOB_DETAILS_PREFIX = scraper_config["jobDetailsPrefix"]
COMPANY_NAME = None


LIVE_CHECK_CONCURRENCY = 5
DELETE_CONCURRENCY = 3
OPTIONAL_JOB_FIELDS = ("salary", "tags", "workmode", "expirationdate")

CAREERS_BASE_URL = "https://www.mesopotamia.ro"
CAREERS_SITEMAP_URL = f"{CAREERS_BASE_URL}/page-sitemap.xml"
CAREERS_HEADERS = {"User-Agent": "job_seeker_ro_spider"}
CAREERS_TIMEOUT = 15
CAREERS_PREFIX = f"{CAREERS_BASE_URL}/"
JOB_PREFIXES = (
    CAREERS_PREFIX,
    # The four ANOFM URLs from the 2026-11-16 snapshot are now expired; keep
    # the prefix in scope so the publisher can delete them as stale jobs.
    "https://mediere.anofm.ro/app/module/mediere/job/",
)

# The ANOFM postings from the 2026-11-16 snapshot have expired; the active
# vacancies are the distinct job pages published on the company careers site.
# Every URL is kept as a separate job, per the URL-uniqueness rule.
CAREERS_JOBS = {
    f"{CAREERS_BASE_URL}/cariera/": ("Cariera Mesopotamia Romania", ["România"]),
    f"{CAREERS_BASE_URL}/cariera-sector6/": (
        "Carieră la Mesopotamia București Sector 6", ["București"]),
    f"{CAREERS_BASE_URL}/cariera-ploiesti/": (
        "Carieră la Mesopotamia Ploiești", ["Ploiești"]),
    f"{CAREERS_BASE_URL}/manager-roman/": (
        "Manager Mesopotamia Roman - Value Center", ["Roman"]),
    f"{CAREERS_BASE_URL}/manager-pentru-mesopotamia-roman-value-centre/": (
        "Manager pentru Mesopotamia Roman Value Centre", ["Roman"]),
    f"{CAREERS_BASE_URL}/manager-valcea/": (
        "Manager Mesopotamia Vâlcea", ["Râmnicu Vâlcea"]),
    f"{CAREERS_BASE_URL}/angajam-la-meso/": (
        "Angajare la Mesopotamia (Meso)", ["România"]),
}
_LOC_RE = re.compile(r"<loc>([^<]+)</loc>", re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_company_name(name):
    cleaned = re.sub(r"[^a-z0-9]+", " ", (name or "").casefold())
    tokens = [t for t in cleaned.split() if t not in {"srl", "sa", "s", "r", "l"}]
    return " ".join(tokens)


def _visible_text(page):
    return _clean(html.unescape(_TAG_RE.sub(" ", page or "")))


def _careers_page_is_for_company(page, company_name):
    """Confirms the careers page belongs to this CIF and legal entity."""
    if str(COMPANY_CIF) not in page:
        return False
    expected = _normalize_company_name(company_name)
    return bool(expected) and expected in _normalize_company_name(_visible_text(page))


def _careers_sitemap_urls():
    """Returns the still-published job URLs from the WordPress page sitemap."""
    try:
        res = requests.get(CAREERS_SITEMAP_URL, headers=CAREERS_HEADERS, timeout=CAREERS_TIMEOUT)
        res.raise_for_status()
        res.encoding = "utf-8"
    except Exception as err:
        print(f"  Careers sitemap unavailable ({err}) — using the discovered URL list")
        return tuple(CAREERS_JOBS)
    published = {url.strip() for url in _LOC_RE.findall(res.text)}
    urls = tuple(url for url in CAREERS_JOBS if url in published)
    return urls or tuple(CAREERS_JOBS)


def _careers_title(url, page):
    title_match = _TITLE_RE.search(page or "")
    if title_match:
        title = _clean(html.unescape(title_match.group(1))).split(" - Mesopotamia Romania")[0]
        if title:
            return title
    return CAREERS_JOBS[url][0]


def search_company_careers(company_name=None):
    """Reads the distinct active vacancies from mesopotamia.ro.

    ANOFM, jobRapid, BeBee, Jobica, Emprego and Cauta.ro were checked during
    discovery but have no active postings for this company; the careers site
    is the primary source. The site footer carries the company CIF, so every
    page is verified before it is accepted as a job for this employer.
    """
    company_name = company_name or company_config["company"]
    jobs = []
    for url in _careers_sitemap_urls():
        try:
            res = requests.get(url, headers=CAREERS_HEADERS, timeout=CAREERS_TIMEOUT)
            res.raise_for_status()
            res.encoding = "utf-8"
        except Exception as err:
            print(f"  Careers page error for {url}: {err}")
            continue
        if not _careers_page_is_for_company(res.text, company_name):
            print(f"  Careers page does not belong to {company_name}: {url}")
            continue
        default_title, location = CAREERS_JOBS[url]
        jobs.append({
            "url": url,
            "title": _careers_title(url, res.text) or default_title,
            "location": location,
            "tags": ["cariera", "mesopotamia"],
        })
    print(f"  Found {len(jobs)} jobs on mesopotamia.ro")
    return jobs


def map_to_job_model(raw_job, cif, company_name=None):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = {
        "url": raw_job["url"],
        "title": raw_job["title"],
        "company": company_name or COMPANY_NAME,
        "cif": cif,
        "date": raw_job.get("date") or now,
        "status": "scraped",
    }
    if raw_job.get("location"):
        job["location"] = raw_job["location"]
    for field in OPTIONAL_JOB_FIELDS:
        if raw_job.get(field):
            job[field] = raw_job[field]
    return job


def transform_jobs_for_solr(payload):
    company = (payload.get("company") or "").upper()
    jobs = []
    for job in payload.get("jobs", []):
        locations = [loc for loc in (job.get("location") or []) if loc]
        jobs.append({**job, "location": locations or ["România"]})
    return {**payload, "company": company, "jobs": jobs}


def drop_dead_urls(jobs):
    """GET-check every job with bounded concurrency and drop soft-404s.

    A 200 response can still be a "no longer available" page; validate_by_content
    scans the visible body for the shared expiry keywords.
    """
    checks = map_with_concurrency(
        jobs, lambda job, _: validate_by_content(job["url"]), limit=LIVE_CHECK_CONCURRENCY)
    alive = []
    for job, result in zip(jobs, checks):
        if result["status"] == "active":
            alive.append(job)
        else:
            reason = result.get("error") or f"HTTP {result.get('http_status', 0)}"
            print(f"  dropped \"{job['title']}\" ({job['url']}): live URL check failed — {reason}")
    if len(alive) < len(jobs):
        print(f"  {len(jobs) - len(alive)}/{len(jobs)} job(s) failed live URL validation and were dropped")
    return alive


def _validated_company():
    try:
        return validate_and_get_company()
    except Exception as err:
        print(f"CUIScan validation failed ({err}) — using config identity")
        return {
            "cif": company_config["id"],
            "company": company_config["company"],
            "address": (company_config.get("location") or ["România"])[0],
        }


def main(root=None):
    root = root or pathlib.Path(__file__).resolve().parents[1]

    print("=== Step 1: Get existing jobs from SOLR ===")
    existing_result = query_solr(COMPANY_CIF)
    existing_count = existing_result["numFound"]
    existing_urls = {doc.get("url") for doc in existing_result["docs"]
                     if doc.get("url") and any(doc["url"].startswith(p) for p in JOB_PREFIXES)}
    print(f"Found {existing_count} existing jobs in SOLR ({len(existing_urls)} from this scraper's sources)")

    print("=== Step 2: Validate company via CUIScan/CUIFirma ===")
    validated = _validated_company()
    global COMPANY_NAME
    COMPANY_NAME = validated["company"]

    print("=== Step 3: Scrape SET-CORPORATION SRL jobs from the careers site ===")
    raw_jobs = []
    known_urls = set()
    source_jobs = search_company_careers(validated["company"])
    for job in source_jobs:
        if job["url"] not in known_urls:
            raw_jobs.append(job)
            known_urls.add(job["url"])
    print(f"Jobs scraped from the careers site: {len(raw_jobs)}")

    jobs = [map_to_job_model(job, validated["cif"]) for job in raw_jobs]
    payload = {
        "source": "mesopotamia.ro",
        "scrapedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "company": COMPANY_NAME,
        "cif": validated["cif"],
        "jobs": jobs,
    }

    transformed = transform_jobs_for_solr(payload)
    transformed["jobs"] = drop_dead_urls(transformed["jobs"])
    print(f"Jobs with valid locations: {len(transformed['jobs'])}")
    if not transformed["jobs"]:
        print("Canary: no live jobs after URL validation — aborting before any write")
        return

    try:
        upsert_company({
            "id": validated["cif"],
            "company": validated["company"],
            "brand": company_config.get("brand"),
            "status": company_config.get("status") or "activ",
            "location": [validated["address"]] if validated.get("address") else company_config["location"],
            "website": company_config.get("website"),
            "career": company_config.get("career"),
            "scraperFile": company_config.get("scraperFile"),
            "lastScraped": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        })
    except Exception as err:
        print(f"Note: Could not upsert company: {err}")

    jobs_path = root / "scraper" / "jobs.json"
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_text(json.dumps(transformed, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved scraper/jobs.json")

    company_data = {
        "id": validated["cif"],
        "company": transformed["company"],
        "brand": company_config.get("brand"),
        "status": company_config.get("status") or "activ",
        "location": [validated["address"]] if validated.get("address") else company_config["location"],
        "website": company_config.get("website"),
        "career": company_config.get("career"),
        "lastScraped": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
    }
    markdown = generate_jobs_markdown(company_data, transformed["jobs"])
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "jobs.md").write_text(markdown, encoding="utf-8")
    print("Saved docs/jobs.md")

    src_company = pathlib.Path(__file__).resolve().parent / "config" / "company.json"
    (root / "docs" / "company.json").write_text(src_company.read_text(encoding="utf-8"), encoding="utf-8")

    print("\n=== Step 4: Upsert jobs to SOLR ===")
    upsert_jobs(transformed["jobs"])

    scraped_urls = {job["url"] for job in transformed["jobs"]}
    stale_urls = [url for url in existing_urls if url not in scraped_urls]
    if stale_urls:
        print(f"\n=== Step 4.5: Delete {len(stale_urls)} stale job(s) ===")

        def _delete_stale(url):
            try:
                delete_job_by_url(url)
            except Exception as err:
                print(f"  Failed to delete: {url} — {err}")

        map_with_concurrency(stale_urls, lambda url, _: _delete_stale(url), limit=DELETE_CONCURRENCY)
    else:
        print("\nNo stale jobs to delete")

    print("\n=== Step 5: Summary ===")
    final_result = query_solr(COMPANY_CIF)
    print(f"Jobs existing in SOLR before scrape: {existing_count}")
    print(f"Jobs scraped from all sources: {len(transformed['jobs'])}")
    print(f"Stale jobs attempted: {len(stale_urls)}")
    print(f"Jobs in SOLR after scrape: {final_result['numFound']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print("Scraper failed:", err)
        sys.exit(1)
