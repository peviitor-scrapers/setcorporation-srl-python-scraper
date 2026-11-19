[![Oportunitati si Cariere](https://github.com/peviitor-scrapers/setcorporation-srl-python-scraper/actions/workflows/job-seeker-ro-spider.yml/badge.svg)](https://github.com/peviitor-scrapers/setcorporation-srl-python-scraper/actions/workflows/job-seeker-ro-spider.yml)
[![Automation Tests](https://github.com/peviitor-scrapers/setcorporation-srl-python-scraper/actions/workflows/automation-testing.yml/badge.svg)](https://github.com/peviitor-scrapers/setcorporation-srl-python-scraper/actions/workflows/automation-testing.yml)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Website](https://img.shields.io/website?url=https%3A%2F%2Fpeviitor.ro&label=peviitor.ro)](https://peviitor.ro)
[![API](https://img.shields.io/website?url=https%3A%2F%2Fapi.peviitor.ro%2F&label=api.peviitor.ro)](https://api.peviitor.ro/)
[![GitHub Pages](https://img.shields.io/github/deployments/peviitor-scrapers/setcorporation-srl-python-scraper/github-pages?label=GitHub%20Pages)](https://peviitor-scrapers.github.io/setcorporation-srl-python-scraper/)

# job_seeker_ro_spider — SET-CORPORATION SRL Scraper

**job_seeker_ro_spider** — a scraper for SET-CORPORATION SRL jobs in Romania
(brand **Mesopotamia**, CUI `29084042`). It reads the active vacancies from the
company's own careers site, [mesopotamia.ro](https://www.mesopotamia.ro/cariera/),
and publishes them to [peviitor.ro](https://peviitor.ro) through the Peviitor API.

During discovery, ANOFM had four postings in the 2026-11-16 snapshot but none
is active now; jobRapid, BeBee, Jobica, Emprego, Cauta.ro and eJobs likewise have
no active posting for this employer. The careers site is therefore the primary
source. Its footer carries the legal name and CIF, so each page is verified as
belonging to this company before publication. Every distinct URL is published
as a distinct job.

> **🌱 Derived scraper.** This repository is derived from
> [ozaltin-insaat-python-scraper](https://github.com/peviitor-scrapers/ozaltin-insaat-python-scraper).

## Overview

The project automates the daily collection of SET-CORPORATION SRL jobs in Romania,
keeping the peviitor.ro board up to date with the latest career opportunities.

## Features

- Reads the WordPress page sitemap and follows only the known career/Manager
  detail URLs on `mesopotamia.ro` (seven distinct job URLs in discovery)
- Verifies the company legal name and CIF in the page footer before accepting a URL
- Deduplicates by URL; distinct URLs remain distinct jobs
- Publishes only enriched non-personal fields: URL, title, company, CIF, date,
  status, location and tags
- Never stores job descriptions, contact names, emails or phone numbers (GDPR data minimization)
- Validates the company via CUIScan (legal name and address, by CIF) and CUIFirma (brand search)
- **Company cache** — does not hit the APIs on every scrape
- **Stale cache / config fallback** when CUIScan is unavailable
- Cross-validates against the Peviitor API
- Deletes stale jobs from peviitor when they are no longer live (scoped to this scraper's URL prefix)
- Stores to the Peviitor API (job core + company core)
- Generates `docs/jobs.md` automatically — accessible on GitHub Pages
- **Company identity in a single file** (`scraper/config/company.json`)
- GitHub Actions: daily scrape + automated testing (unit, integration, e2e, consistency)
- Identifies itself through the User-Agent: `job_seeker_ro_spider`

## Local setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests/unit tests/consistency   # offline checks
.venv/bin/python -m scraper.index                         # full scrape + publish
```

## License

Copyright (c) 2026 Alexandra Ifrim

Licensed under the [MIT License](LICENSE).

## Managed By

This project is managed by [ASOCIATIA OPORTUNITATI SI CARIERE](https://oportunitatisicariere.ro) and used as a web scraper for the [peviitor.ro](https://peviitor.ro) job board project.

## Disclaimer

This scraper is designed for educational purposes and legitimate job data aggregation for the Romanian job market.
