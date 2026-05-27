---
phase: 02-ingest-generate-and-email-apply
plan: "03"
subsystem: ingestion
tags: [fastapi, scraping, jobspy, kalibrr, httpx, beautifulsoup4, endpoints, tests]
dependency_graph:
  requires:
    - src/api/app.py (FastAPI app, verify_api_key — from Plan 02-01)
    - src/api/schemas.py (ScrapeJobSpyIn, ScrapeKalibrrIn — from Plan 02-01)
    - src/ingestion/__init__.py (package — from Plan 02-01)
  provides:
    - src/ingestion/jobspy_runner.py (run_jobspy async function)
    - src/ingestion/kalibrr_scraper.py (scrape_kalibrr async function)
    - src/api/routes/scrape.py (POST /scrape/scrape-jobspy, POST /scrape/scrape-kalibrr)
    - tests/integration/test_scrape_endpoints.py (5 passing tests)
  affects:
    - n8n workflows that call /scrape-jobspy and /scrape-kalibrr on a 4-hour schedule
    - Plan 02-05 (ai-apply-pipeline) which receives leads from these scraper endpoints
tech_stack:
  added:
    - python-jobspy>=1.1.82 (already installed in Plan 02-01; run_jobspy wraps scrape_jobs())
    - httpx>=0.28 (already installed in Plan 02-01; used by kalibrr_scraper)
    - beautifulsoup4>=4.12 (already installed in Plan 02-01; used by kalibrr_scraper)
  patterns:
    - asyncio.get_event_loop().run_in_executor(None, partial(scrape_jobs, ...)) for sync-in-async
    - httpx.AsyncClient with User-Agent + follow_redirects for Kalibrr HTTP requests
    - Multi-strategy CSS selector parsing (3 fallback strategies for Kalibrr job cards)
    - OPS-01 zero-result warning field in API response
    - AsyncMock patch pattern for external HTTP calls in integration tests
key_files:
  created:
    - src/ingestion/jobspy_runner.py
    - src/ingestion/kalibrr_scraper.py
    - tests/integration/test_scrape_endpoints.py
  modified:
    - src/api/routes/scrape.py (replaced stub with full implementation)
decisions:
  - "run_jobspy uses asyncio.get_event_loop().run_in_executor instead of FastAPI run_in_threadpool — both are equivalent but run_in_executor matches PATTERNS.md spec exactly"
  - "kalibrr_scraper uses 3-strategy CSS selector fallback (data-testid, class names, href anchor patterns) because live selectors are unverified — checkpoint:human-verify will determine correct selector"
  - "scrape.py endpoints do not take a session dependency — scrapers are read-only from external sources and do not write to DB; n8n loops results through /ingest-lead separately"
  - "Pre-existing ruff errors in src/queue/db.py and src/queue/models.py are out of scope (deferred)"
metrics:
  duration: "4 minutes"
  completed: "2026-05-27T18:04:17Z"
  tasks_completed: 2
  files_created: 3
  files_modified: 1
---

# Phase 2 Plan 03: Scraper Endpoints Summary

**One-liner:** FastAPI scraper vertical slice — JobSpy async executor wrapper and best-effort Kalibrr httpx+BS4 scraper wired to POST /scrape-jobspy and POST /scrape-kalibrr with OPS-01 zero-result detection and 5 passing integration tests.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | JobSpy runner and Kalibrr scraper modules | e20d39d | src/ingestion/jobspy_runner.py, src/ingestion/kalibrr_scraper.py |
| 2 | Scrape route endpoints with tests | 49da9ec | src/api/routes/scrape.py, tests/integration/test_scrape_endpoints.py |

## What Was Built

### Task 1: jobspy_runner.py and kalibrr_scraper.py

**jobspy_runner.py:**
- `run_jobspy(search_term, location, results_wanted, hours_old, site_names)` — async function
- Calls synchronous `scrape_jobs()` via `asyncio.get_event_loop().run_in_executor(None, partial(...))` to avoid blocking the FastAPI event loop
- Defaults `site_names` to `["indeed"]` if None
- Returns empty list (no crash) when `scrape_jobs` returns None or empty DataFrame
- Selects only columns `[title, company, location, job_url, description]` from DataFrame; handles missing columns gracefully with `[col for col in keep if col in jobs_df.columns]`
- Replaces NaN with None via `.where(notna(), other=None)` before converting to `list[dict]`
- Uses `structlog.get_logger()` at module level; logs start, completion, and empty-result events

**kalibrr_scraper.py:**
- `scrape_kalibrr(search_term, max_pages)` — async function
- Uses `httpx.AsyncClient` with browser-like User-Agent, `follow_redirects=True`, and 30s timeout
- Paginates from page 1 to max_pages at URL `https://www.kalibrr.com/job-board/te/{search_term}/{page}`
- Stops pagination early when a page returns zero job cards
- CSS selector extraction uses 3 progressive fallback strategies (data-testid, class-based, href-anchor)
- Handles `httpx.HTTPStatusError` and `httpx.RequestError` gracefully — logs error, returns partial results
- Returns `list[dict]` with keys: `title`, `company`, `location`, `url`
- Absolutizes relative Kalibrr URLs via `urllib.parse.urljoin`

### Task 2: scrape.py endpoints and tests

**src/api/routes/scrape.py:**
- `POST /scrape/scrape-jobspy` (request body: `ScrapeJobSpyIn`): calls `run_jobspy()`, returns `{"jobs": [...], "count": N}` or adds `"warning": "zero_results_possible_block"` on empty result
- `POST /scrape/scrape-kalibrr` (request body: `ScrapeKalibrrIn`): calls `scrape_kalibrr()`, same response shape and zero-result warning pattern
- Both endpoints apply `verify_api_key` dependency (T-02-01)
- No session dependency — scrapers do not write to DB

**tests/integration/test_scrape_endpoints.py (5 tests):**

| Test | What it Tests | Result |
|------|---------------|--------|
| `test_scrape_jobspy_with_results` | Mock returns 3 jobs → count=3, no warning | PASS |
| `test_scrape_jobspy_zero_results` | Mock returns [] → warning="zero_results_possible_block" | PASS |
| `test_scrape_kalibrr_with_results` | Mock returns 2 jobs → count=2, no warning | PASS |
| `test_scrape_kalibrr_zero_results` | Mock returns [] → warning="zero_results_possible_block" | PASS |
| `test_scrape_jobspy_validation_missing_search_term` | No search_term → HTTP 422 | PASS |

## Human Verification Required

**Checkpoint: Kalibrr CSS Selector Verification**

This plan intentionally pauses here. The Kalibrr scraper uses best-effort CSS selectors that have NOT been verified against live HTML (per RESEARCH.md Open Question 1). The scraper may return zero results despite working code if the selectors do not match Kalibrr's actual HTML structure.

### What to Do

**Step 1: Start the FastAPI server**
```bash
cd /Users/stefano/Documents/Workspaces/Job\ Application\ Automation
uv run uvicorn src.api.app:app --port 8000
```

**Step 2: Test Kalibrr scraper with a live request**
```bash
curl -X POST http://localhost:8000/scrape/scrape-kalibrr \
  -H "Content-Type: application/json" \
  -d '{"search_term": "Product Manager", "max_pages": 1}'
```

**Step 3: Check the response**
- **Expected (success):** `{"jobs": [...], "count": N}` where `N > 0` and each job has `title`, `company`, `location`, `url`
- **If `count == 0`:** The CSS selectors need updating. Open `https://www.kalibrr.com/job-board/te/Product%20Manager/1` in a browser, inspect the job card HTML structure, and report the correct selectors for `title`, `company`, `location`, and URL elements

**Step 4: Verify at least one URL**
- Open one returned `url` value in browser to confirm it is a valid Kalibrr job page

**Step 5: (Optional) Also test JobSpy**
```bash
curl -X POST http://localhost:8000/scrape/scrape-jobspy \
  -H "Content-Type: application/json" \
  -d '{"search_term": "Product Manager", "location": "Remote", "results_wanted": 5}'
```

### Resume Signal

Type **"approved"** if `scrape_kalibrr` returns actual job listings with correct `title/company/location/url` fields.

If it returns 0 results, describe the actual HTML structure you see on the Kalibrr page so the selectors in `src/ingestion/kalibrr_scraper.py` (specifically the `_parse_job_cards` function) can be fixed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DataFrame column availability check in run_jobspy**
- **Found during:** Task 1 implementation
- **Issue:** `python-jobspy` may not always return all 5 expected columns in the DataFrame (different site scrapers return different column sets). Using `jobs_df[keep]` directly would raise `KeyError` if a column is absent.
- **Fix:** Added `available = [col for col in keep if col in jobs_df.columns]` to select only columns that exist, then apply the NaN replacement on only those columns.
- **Files modified:** `src/ingestion/jobspy_runner.py`
- **Commit:** e20d39d

**2. [Rule 1 - Bug] Kalibrr httpx.RequestError not handled**
- **Found during:** Task 1 implementation review
- **Issue:** Plan specified catching `httpx.HTTPStatusError` but network-level errors (timeout, DNS failure, connection refused) raise `httpx.RequestError` (the base class), not `HTTPStatusError`. Without catching both, network failures would propagate as unhandled exceptions.
- **Fix:** Added separate `except httpx.RequestError` clause after `HTTPStatusError` to catch all network-level errors gracefully.
- **Files modified:** `src/ingestion/kalibrr_scraper.py`
- **Commit:** e20d39d

### Out of Scope (Deferred)

Pre-existing ruff lint errors in files not touched by this plan:
- `src/queue/db.py` — `I001` unsorted imports (import block ordering)
- `src/queue/models.py` — `UP042` StrEnum inheritance, `E501` line too long (3 instances)

These exist in Phase 1 code. Not introduced by this plan, not fixed per scope boundary rule. Logged for a future chore task.

## Known Stubs

| File | Stub | Resolved by |
|------|------|-------------|
| `src/ingestion/kalibrr_scraper.py` | CSS selectors are best-effort, not verified against live HTML | checkpoint:human-verify (this plan) — user must confirm or fix selectors |

The stub does not prevent the plan's automated goals (endpoints are wired, tests pass), but the Kalibrr scraper's real-world correctness depends on the checkpoint result.

## Threat Flags

No new threat surface found beyond the plan's threat model. T-02-10 (IP block zero-result detection) and T-02-11 (BeautifulSoup text-only parsing, no eval/exec) mitigations are implemented. T-02-SC packages (python-jobspy, httpx, beautifulsoup4) were previously verified in RESEARCH.md.

## Self-Check

- `src/ingestion/jobspy_runner.py` exists: FOUND
- `src/ingestion/kalibrr_scraper.py` exists: FOUND
- `src/api/routes/scrape.py` (full implementation): FOUND
- `tests/integration/test_scrape_endpoints.py`: FOUND
- commit e20d39d (Task 1): FOUND
- commit 49da9ec (Task 2): FOUND
- 5/5 tests passing: CONFIRMED (pytest output above)
- ruff clean on new files: CONFIRMED

## Self-Check: PASSED
