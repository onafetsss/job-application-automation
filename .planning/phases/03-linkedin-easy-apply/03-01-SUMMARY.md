---
phase: 03-linkedin-easy-apply
plan: "01"
subsystem: browser-automation
tags: [camoufox, docker, job-status, test-scaffold, linkedin]
dependency_graph:
  requires: []
  provides:
    - camoufox dependency declared and lockfile updated
    - Dockerfile.api: xvfb + camoufox binary fetch
    - JobStatus.SKIPPED enum value
    - AuditEvent.SKIPPED enum value
    - LINKEDIN_* env vars in docker-compose and .env.example
    - tests/browser/test_linkedin_applier.py (RED scaffold)
    - tests/api/test_apply_routes.py (RED scaffold)
    - tests/unit/test_ingest_apply_type.py (RED scaffold)
  affects:
    - docker/Dockerfile.api (xvfb install + camoufox fetch)
    - src/queue/models.py (new enum member)
    - src/audit_log.py (new enum member)
tech_stack:
  added:
    - camoufox==0.4.11 (PyPI — stealth Firefox automation)
    - playwright==1.60.0 (transitive via camoufox)
    - xvfb (apt package, added to Dockerfile.api for headless="virtual")
  patterns:
    - pytest.mark.xfail for RED scaffold tests with missing dependencies
    - Module-level try/except import to avoid collection-time circular imports
key_files:
  created:
    - tests/browser/__init__.py
    - tests/browser/test_linkedin_applier.py
    - tests/api/__init__.py
    - tests/api/test_apply_routes.py
    - tests/unit/test_ingest_apply_type.py
  modified:
    - pyproject.toml (camoufox>=0.4.11 added to dependencies)
    - uv.lock (updated — 16 new packages)
    - docker/Dockerfile.api (xvfb install + camoufox fetch after uv sync)
    - docker-compose.yml (4 LINKEDIN_* env vars in api service environment block)
    - .env.example (LINKEDIN_* vars + SMARTPROXY_URL placeholder)
    - src/queue/models.py (JobStatus.SKIPPED added)
    - src/audit_log.py (AuditEvent.SKIPPED added)
decisions:
  - "camoufox dependency added as camoufox>=0.4.11 (verified legitimate on PyPI + github.com/daijro/camoufox per Task 1 gate)"
  - "LINKEDIN_PROFILE_DIR defaults to /data/linkedin_profile (user_data_dir approach, more reliable than storage_state JSON for __Host- cookies)"
  - "JobStatus.SKIPPED and AuditEvent.SKIPPED added as distinct values from FAILED — semantically different: SKIPPED is expected/non-erroneous, FAILED is a genuine error"
  - "Browser tests use try/except import + pytest.mark.xfail instead of pytest.importorskip to allow collection even when module is absent"
  - "tests/unit/test_ingest_apply_type.py uses lazy import inside test functions to avoid circular import from module-level src.api.routes.ingest import"
metrics:
  duration: "~25 minutes"
  completed_date: "2026-05-28"
  tasks_completed: 2
  tasks_skipped: 1
  files_created: 5
  files_modified: 7
---

# Phase 03 Plan 01: LinkedIn Easy Apply Foundation — Summary

**One-liner:** Camoufox declared as dependency with Docker xvfb+binary-fetch, JobStatus/AuditEvent extended with SKIPPED, LINKEDIN_* env vars wired, and five Nyquist test scaffold files created in RED state.

## What Was Built

### Task 1 (SKIPPED — pre-approved)
Package legitimacy gate for camoufox was cleared by the user before executor spawn. PyPI at pypi.org/project/camoufox/ (0.4.11, ~2 years history) and GitHub at github.com/daijro/camoufox confirmed legitimate.

### Task 2: camoufox dependency and Docker browser support

- `pyproject.toml`: `camoufox>=0.4.11` added to the `dependencies` array. `uv add camoufox` pulled in 16 packages including `playwright==1.60.0` as a transitive dependency.
- `docker/Dockerfile.api`: two RUN steps inserted after `uv sync --no-dev` and before `COPY src/`:
  1. `RUN apt-get update && apt-get install -y xvfb --no-install-recommends && rm -rf /var/lib/apt/lists/*`
  2. `RUN python -m camoufox fetch`
- `docker-compose.yml`: four env vars added to the `api` service `environment` block with shell-expansion defaults:
  - `LINKEDIN_PROFILE_DIR=/data/linkedin_profile`
  - `LINKEDIN_APPLY_WINDOW_START=${LINKEDIN_APPLY_WINDOW_START:-9}`
  - `LINKEDIN_APPLY_WINDOW_END=${LINKEDIN_APPLY_WINDOW_END:-17}`
  - `LINKEDIN_DAILY_CAP=${LINKEDIN_DAILY_CAP:-17}`
- `.env.example`: LINKEDIN_* section added with concrete defaults plus `# SMARTPROXY_URL=` placeholder (deferred per CONTEXT.md).

### Task 3: SKIPPED job state, audit event, RED test scaffolds

- `src/queue/models.py`: `SKIPPED = "SKIPPED"` appended to `JobStatus` enum after `FAILED`. No DB migration needed (status column is `Column(String)`).
- `src/audit_log.py`: `SKIPPED = "SKIPPED"` inserted into `AuditEvent` StrEnum between `FAILED` and `NOTIFIED`.
- `tests/browser/__init__.py`: empty package marker.
- `tests/browser/test_linkedin_applier.py`: three async test functions (xfail when module absent):
  - `test_challenge_detected`: mocked page with `/checkpoint/` URL asserts `check_for_challenge()` returns non-None string
  - `test_no_easy_apply_button`: mocked locator with count==0 asserts `LinkedInApplier._find_and_click_easy_apply()` raises `NoEasyApplyButton`
  - `test_unknown_form_field`: unmappable label asserts `resolve_profile_field()` raises `UnknownFormField`
- `tests/api/__init__.py`: empty package marker.
- `tests/api/test_apply_routes.py`: `test_daily_count` — DB fixture inserts two Application rows submitted today then asserts `GET /apply/daily-linkedin-count` returns `{"count": 2}` (xfail until Plan 03-03).
- `tests/unit/test_ingest_apply_type.py`: two tests — `test_linkedin_url_apply_type` and `test_non_linkedin_url_apply_type` — asserting the `resolve_apply_type()` helper correctly routes URLs (xfail until Plan 03-04).

## Verification Results

```
$ uv run python -c "from src.queue.models import JobStatus; from src.audit_log import AuditEvent; print(JobStatus.SKIPPED, AuditEvent.SKIPPED)"
JobStatus.SKIPPED SKIPPED

$ uv run pytest tests/ --co -q | tail -5
...
67 tests collected in 0.52s
```

docker-compose.yml parsed clean via `docker compose config` (all four LINKEDIN_* vars present).

## Deviations from Plan

### Deviation 1: Module-level circular import in test_ingest_apply_type.py

**Found during:** Task 3 — initial collection run
**Issue:** Using `_try_import_resolve_apply_type()` at module level attempted to import `src.api.routes.ingest`, which triggered `src.api.app` initialization, causing `AttributeError: partially initialized module ... has no attribute 'router'` (circular import at collection time).
**Fix:** Moved import inside a `_load_resolve_apply_type()` helper called lazily inside each test function. Only safe modules (`src.ingestion.gmail_client`, `src.filter.eligibility`) are checked — `src.api.routes.ingest` removed from candidates to avoid the circular dependency path.
**Files modified:** `tests/unit/test_ingest_apply_type.py`
**Rule:** Rule 3 (auto-fix blocking issue — collection-time error prevented test discovery)

### Deviation 2: pytest.importorskip replaced by try/except + xfail in browser tests

**Found during:** Task 3 — first collection of tests/browser/
**Issue:** `pytest.importorskip` causes the entire file to be skipped (exit code 5, 0 tests collected) when the module is missing. The acceptance criteria requires the test functions to be collectable.
**Fix:** Replaced module-level `pytest.importorskip` with `try/except` import block setting `_MODULE_AVAILABLE = False`. Each test is decorated with `@pytest.mark.xfail(not _MODULE_AVAILABLE, ...)` so all three functions are collected and reported as xfail rather than skipped.
**Files modified:** `tests/browser/test_linkedin_applier.py`
**Rule:** Rule 2 (missing critical functionality — collectable scaffold required for Nyquist coverage tracking)

## Known Stubs

None. This plan creates scaffolding only — no data-rendering components.

## Threat Flags

No new threat surface introduced beyond what is documented in the plan's threat model (T-03-SC, T-03-01, T-03-02).

## Self-Check: PASSED

- `pyproject.toml` contains `camoufox>=0.4.11`: FOUND
- `docker/Dockerfile.api` contains `xvfb` and `camoufox fetch`: FOUND
- `docker-compose.yml` contains `LINKEDIN_PROFILE_DIR` and `LINKEDIN_DAILY_CAP`: FOUND
- `.env.example` contains `LINKEDIN_APPLY_WINDOW_START` and `SMARTPROXY_URL`: FOUND
- `src/queue/models.py` `JobStatus.SKIPPED == "SKIPPED"`: VERIFIED
- `src/audit_log.py` `AuditEvent.SKIPPED == "SKIPPED"`: VERIFIED
- `tests/browser/test_linkedin_applier.py` defines `test_challenge_detected`, `test_no_easy_apply_button`, `test_unknown_form_field`: FOUND
- `tests/api/test_apply_routes.py` defines `test_daily_count`: FOUND
- `tests/unit/test_ingest_apply_type.py` defines `test_linkedin_url_apply_type`: FOUND
- Task 2 commit `a06516e`: VERIFIED
- Task 3 commit `5096a86`: VERIFIED
- 67 tests collect without hard error: VERIFIED
