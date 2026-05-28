---
phase: 03-linkedin-easy-apply
plan: "03"
subsystem: api
tags: [fastapi, linkedin, apply-routes, tdd, daily-cap]
dependency_graph:
  requires:
    - 03-01 (JobStatus.SKIPPED, AuditEvent.SKIPPED, test scaffold)
    - 03-02 (LinkedInApplier, ChallengeDetected, NoEasyApplyButton, UnknownFormField)
  provides:
    - POST /apply/linkedin-easy-apply — n8n→FastAPI contract (D-08), auth-guarded
    - GET /apply/daily-linkedin-count — durable DB-backed daily cap source (T-03-11)
    - GET /apply/queued-linkedin-jobs — QUEUED linkedin jobs feed for n8n scheduler
    - LinkedInApplyIn / LinkedInApplyOut schemas
    - src/api/routes/apply/ package
  affects:
    - src/api/app.py (new router registration)
    - src/api/schemas.py (two new schema classes)
    - tests/api/test_apply_routes.py (xfail scaffold → 4 GREEN tests)
tech_stack:
  added: []
  patterns:
    - TDD RED/GREEN cycle (test(03-03) commit before feat(03-03) commit)
    - JOIN-based daily count query: Application JOIN Job WHERE apply_type=linkedin_easy_apply AND submitted_at >= today_midnight
    - Exception→HTTP status mapping: ChallengeDetected→503, NoEasyApplyButton→200 SKIPPED, UnknownFormField→200 SKIPPED
    - QUEUED→APPLYING→SUBMITTED multi-step status transition across separate session.begin() blocks
    - Direct raw SQL inserts in test fixtures (bypass eligibility filter for controlled state setup)
key_files:
  created:
    - src/api/routes/apply/__init__.py
    - src/api/routes/apply/linkedin_apply.py
  modified:
    - src/api/schemas.py (LinkedInApplyIn, LinkedInApplyOut added)
    - src/api/app.py (linkedin_apply router registered)
    - tests/api/test_apply_routes.py (4 tests, all GREEN)
decisions:
  - "GET /daily-linkedin-count uses JOIN query (Application JOIN Job on apply_type) — not unfiltered Application count — to exclude email-platform applications from the LinkedIn daily cap"
  - "POST /linkedin-easy-apply uses three separate session.begin() blocks: one for 404/409 guard + APPLYING transition, one per SKIPPED exception handler, one for SUBMITTED + Application row"
  - "Test fixtures use raw SQL INSERT (with retry_count=0) instead of ingest API to bypass eligibility filter and control job status precisely"
  - "response_model=None on POST route to allow dict | JSONResponse return type (FastAPI constraint)"
metrics:
  duration: "~20 minutes"
  completed_date: "2026-05-28"
  tasks_completed: 1
  tasks_skipped: 0
  files_created: 2
  files_modified: 3
---

# Phase 03 Plan 03: LinkedIn Easy Apply API Routes — Summary

**One-liner:** FastAPI /apply router with POST linkedin-easy-apply (QUEUED→SUBMITTED/SKIPPED/503 flow), GET daily-linkedin-count (JOIN-based UTC midnight reset), and GET queued-linkedin-jobs — all registered on the app and covered by 4 GREEN TDD tests.

## What Was Built

### Task 1 (TDD): Add schemas and the linkedin_apply router

**RED phase** (`test(03-03)` commit `b79687e`):

Expanded `tests/api/test_apply_routes.py` from the Plan 03-01 scaffold (1 xfail test) to 4 normal tests:

1. `test_daily_count` — inserts 2 linkedin Job+Application rows (via raw SQL, today's `submitted_at`) plus 1 email application (same day) and 1 non-existent Job row; asserts `GET /apply/daily-linkedin-count` returns `{"count": 2}` — proving email-platform applications are excluded by the JOIN filter.
2. `test_apply_404` — POSTs with a random UUID `job_id`; asserts 404 `{"detail":"job_not_found"}`.
3. `test_apply_409` — inserts a Job with `status=APPLYING` directly; asserts 409 `{"detail":"job_not_queued"}`.
4. `test_queued_linkedin_jobs` — inserts one QUEUED linkedin job and one QUEUED email job; asserts only the linkedin job appears in the `GET /apply/queued-linkedin-jobs` response.

All 4 tests failed RED (404 from FastAPI because the routes didn't exist).

**GREEN phase** (`feat(03-03)` commit `d31bd7d`):

- `src/api/routes/apply/__init__.py` — empty package marker.
- `src/api/schemas.py` — `LinkedInApplyIn(job_id: str)` and `LinkedInApplyOut(status, job_id, reason)` added after existing schemas.
- `src/api/routes/apply/linkedin_apply.py` — three endpoints:
  - `GET /daily-linkedin-count`: JOIN query `Application JOIN Job ON apply_type='linkedin_easy_apply' AND submitted_at >= today_midnight_utc`. Returns `{"count": N}`.
  - `GET /queued-linkedin-jobs`: SELECT Jobs WHERE status=QUEUED AND apply_type=linkedin_easy_apply. Returns `{"jobs": [{id, title, company, url}]}`.
  - `POST /linkedin-easy-apply` (auth-guarded by `Depends(verify_api_key)`): 404/409 guard → APPLYING transition + audit → `LinkedInApplier.apply()` → exception mapping → SUBMITTED + Application row + audit, or SKIPPED + audit.
- `src/api/app.py` — `from src.api.routes.apply import linkedin_apply` added to import block; `app.include_router(linkedin_apply.router, prefix="/apply", tags=["apply"])` added after existing routers.

**Exception→status mapping:**
| Exception | HTTP Status | Job Status | Body |
|-----------|-------------|------------|------|
| `ChallengeDetected` | 503 | APPLYING (not changed) | `{"status":"challenge_detected","detail":...}` |
| `NoEasyApplyButton` | 200 | SKIPPED | `{"status":"skipped","reason":"no_easy_apply_button"}` |
| `UnknownFormField` | 200 | SKIPPED | `{"status":"skipped","reason":<field label>}` |
| Success | 200 | SUBMITTED | `{"status":"submitted","job_id":...}` |

## Verification Results

```
$ uv run python -c "from src.api.app import app; paths={r.path for r in app.routes}; assert '/apply/linkedin-easy-apply' in paths and '/apply/daily-linkedin-count' in paths and '/apply/queued-linkedin-jobs' in paths; print('routes-ok')"
routes-ok

$ uv run python -c "from src.api.app import app; print(sorted(r.path for r in app.routes if r.path.startswith('/apply')))"
['/apply/daily-linkedin-count', '/apply/linkedin-easy-apply', '/apply/queued-linkedin-jobs']

$ grep -n "Depends(verify_api_key)" src/api/routes/apply/linkedin_apply.py
101:@router.post("/linkedin-easy-apply", dependencies=[Depends(verify_api_key)], response_model=None)

$ uv run pytest tests/api/test_apply_routes.py -x -q
....
4 passed in 0.92s
PASS
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] response_model=None required on POST route**
- **Found during:** Task 1 GREEN — FastAPI router registration
- **Issue:** Return type annotation `dict | JSONResponse` is not a valid Pydantic field type; FastAPI raised `FastAPIError: Invalid args for response field!`
- **Fix:** Added `response_model=None` to the `@router.post` decorator — same pattern used on `write_application` and `mark_submitted` in `application.py`
- **Files modified:** `src/api/routes/apply/linkedin_apply.py`

**2. [Rule 1 - Bug] Test fixture raw SQL inserts required retry_count**
- **Found during:** Task 1 RED — test execution
- **Issue:** `jobs.retry_count` column has `NOT NULL` constraint (SQLAlchemy ORM sets `default=0` but raw SQL does not); first fixture INSERT raised `IntegrityError`
- **Fix:** All raw SQL INSERT statements include `retry_count=0` explicitly; column list updated to include `retry_count` with literal `0`
- **Files modified:** `tests/api/test_apply_routes.py`

**3. [Rule 2 - Missing] Test fixtures use raw SQL instead of ingest API**
- **Found during:** Task 1 RED — initial test design used `/ingest/ingest-lead` API calls
- **Issue:** The eligibility filter (config/eligibility.yaml) rejects "Test Role" and "Software Engineer" titles as `title_mismatch`, returning REJECTED status instead of QUEUED — making job_id unusable for the apply route tests
- **Fix:** Replaced ingest API calls with direct raw SQL INSERTs using `db_module._engine.connect()`, allowing precise control over `status`, `apply_type`, and `submitted_at` values in test fixtures
- **Files modified:** `tests/api/test_apply_routes.py`

### Pre-existing Out-of-Scope Issue (Not Fixed)

`tests/integration/test_application_endpoints.py::test_write_application_success` was failing before this plan and is still failing. The test ingests "Senior Product Manager" via `/ingest/ingest-lead` and expects QUEUED status, but the eligibility filter rejects it as `title_mismatch`. This is unrelated to Plan 03-03 changes — logged to deferred items.

## Known Stubs

None. All three endpoints are fully implemented and return live DB data.

## Threat Flags

No new threat surface introduced beyond the plan's threat model:
- T-03-08 (Spoofing): `Depends(verify_api_key)` on POST only — implemented.
- T-03-09 (SSRF): `job.url` read from DB Job row, never from n8n payload — implemented (payload carries only `job_id`).
- T-03-10 (Repudiation): `write_audit` called for APPLYING, SUBMITTED, and SKIPPED events — implemented.
- T-03-11 (DoS/cap): `daily-linkedin-count` is durable DB-backed source — implemented with JOIN filter.

## TDD Gate Compliance

- RED gate commit: `b79687e` — `test(03-03): RED — add failing tests for /apply/ routes`
- GREEN gate commit: `d31bd7d` — `feat(03-03): implement /apply router with linkedin-easy-apply, daily-count, queued-jobs endpoints`

## Self-Check: PASSED

- `src/api/routes/apply/__init__.py` exists: FOUND
- `src/api/routes/apply/linkedin_apply.py` defines `router` with POST and two GETs: FOUND
- `src/api/schemas.py` defines `class LinkedInApplyIn` and `class LinkedInApplyOut`: FOUND
- `src/api/app.py` includes `linkedin_apply.router` with prefix `/apply`: FOUND
- `/apply/linkedin-easy-apply`, `/apply/daily-linkedin-count`, `/apply/queued-linkedin-jobs` in app.routes: VERIFIED
- `Depends(verify_api_key)` on POST route only: VERIFIED (line 101)
- RED commit `b79687e`: VERIFIED
- GREEN commit `d31bd7d`: VERIFIED
- `uv run pytest tests/api/test_apply_routes.py -x -q` — 4 passed: VERIFIED
