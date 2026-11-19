# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Careers-site scraper for SET-CORPORATION SRL (Mesopotamia): reads the page
  sitemap, verifies the CIF in each page footer and publishes the distinct
  vacancies (#1).
- Enriched non-personal fields only: title, company, CIF, date, status,
  location and tags (#1).

### Changed
- Company identity set to SET-CORPORATION SRL (CUI `29084042`); config, docs
  and test fixtures rebranded (#1).
- Source identifier is now `mesopotamia.ro`; stale-job scope covers this
  scraper's URL prefix (#1).
- ANOFM, jobRapid, BeBee, Jobica, Emprego, Cauta.ro and eJobs were checked
  during discovery and omitted because they have no active postings (#1).

## [1.0.0] - 2026-11-19

### Added
- Python scraper for **SET-CORPORATION SRL** (CUI `29084042`).
- Publisher to peviitor v1 API: company upsert, job upload, stale-job delete.
- ANAF company validation with CUIScan fallback and cache.
- Unit, integration, e2e, and consistency tests.
- GitHub Actions workflows and GitHub Pages (`docs/`) with generated `jobs.md`.
- AI documentation under `ai/`.
