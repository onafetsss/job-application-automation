---
phase: 02-ingest-generate-and-email-apply
plan: "04"
subsystem: api
tags: [fastapi, ai, resume-selection, profile, screening-answers, application-lifecycle, anthropic, pymupdf, python-docx]
dependency_graph:
  requires:
    - 02-01 (FastAPI app, schemas, stubs, queue models, audit log)
  provides:
    - src/preparation/resume_reader.py (PDF/DOCX text extraction + directory listing)
    - src/preparation/profile_loader.py (ProfileConfig Pydantic model + YAML loader)
    - src/api/routes/resume.py (POST /resume/select-resume — LLM resume selection)
    - src/api/routes/profile.py (GET /profile — profile config as JSON for n8n)
    - src/api/routes/application.py (POST /application/generate-screening-answers, /write-application, /mark-submitted)
    - tests/integration/test_resume_endpoint.py (3 resume tests)
    - tests/integration/test_profile_endpoint.py (2 profile tests)
    - tests/integration/test_screening_answers.py (4 screening tests)
    - tests/integration/test_application_endpoints.py (5 application lifecycle tests)
  affects:
    - 02-05 (email apply pipeline — uses /select-resume, /write-application, /mark-submitted)
    - 02-06 (cover letter generation — uses GET /profile for profile injection per D-19)
tech_stack:
  added:
    - anthropic (Claude Haiku LLM calls for resume selection and screening answer generation)
    - pymupdf/fitz (PDF resume text extraction)
    - python-docx/docx (DOCX resume text extraction)
  patterns:
    - Profile config loaded at lifespan startup — stored on app.state.profile_config
    - resumes_dir loaded from RESUMES_DIR env var at startup — stored on app.state.resumes_dir
    - response_model=None on endpoints with dict|JSONResponse return types (FastAPI compat)
    - ruff-clean imports: stdlib -> third-party -> local ordering enforced
key_files:
  created:
    - src/preparation/resume_reader.py
    - src/preparation/profile_loader.py
    - src/api/routes/resume.py (replaced stub)
    - src/api/routes/profile.py (replaced stub)
    - tests/integration/test_resume_endpoint.py
    - tests/integration/test_profile_endpoint.py
    - tests/integration/test_screening_answers.py
    - tests/integration/test_application_endpoints.py
  modified:
    - src/api/routes/application.py (replaced stub with 3 endpoints)
    - src/api/app.py (added profile_config + resumes_dir to lifespan startup)
decisions:
  - "response_model=None on /write-application and /mark-submitted — FastAPI cannot model dict|JSONResponse union types; using None avoids schema generation errors while retaining 200/404/409 HTTP responses"
  - "Profile config loaded at lifespan startup via load_profile_config() and stored on app.state.profile_config — same pattern as eligibility_config; avoids repeated YAML reads per request"
  - "Resume selection uses first-line-only parsing of Haiku response for filename extraction; falls back to case-insensitive match, then first resume — resilient to minor LLM formatting variations"
  - "Test isolation: each test function manages its own lifespan context + engine disposal — avoids shared app state across tests that set different RESUMES_DIR env vars"
  - "Ruff auto-format applied to new files to comply with project conventions (import ordering, line length)"
metrics:
  duration: "25 minutes"
  completed: "2026-05-28T00:00:00Z"
  tasks_completed: 3
  files_created: 8
  files_modified: 2
---

# Phase 2 Plan 04: AI Preparation and Application Lifecycle Summary

**One-liner:** Claude Haiku LLM-powered resume selection + screening answer generation, profile.yaml serialized as JSON for n8n cover letter prompts, and QUEUED→APPLYING→SUBMITTED state machine with audit trails — 14 integration tests all passing.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Resume reader, profile loader, GET /profile, /select-resume | f710c0b | src/preparation/resume_reader.py, src/preparation/profile_loader.py, src/api/routes/resume.py, src/api/routes/profile.py, src/api/app.py |
| 2 | Screening answer generation endpoint (AI-03, D-20) | 4a025d9 | src/api/routes/application.py, tests/integration/test_screening_answers.py |
| 3 | Application lifecycle endpoints + ruff fixes | ad7ee74 | src/api/routes/application.py, tests/integration/test_application_endpoints.py |

## What Was Built

### Task 1: Resume Reader, Profile Loader, GET /profile, /select-resume

- Created `src/preparation/resume_reader.py`:
  - `extract_resume_text(filepath)` — PDF via `fitz.open()` + `page.get_text()`, DOCX via `Document().paragraphs`, raises `ValueError` for unsupported types
  - `list_resumes(resumes_dir)` — iterates `.pdf`/`.docx` files, returns list of `{name, path, text}` dicts, logs count with structlog

- Created `src/preparation/profile_loader.py`:
  - `ProfileConfig` — Pydantic model with `summary`, `target_roles`, `key_projects` (list of `KeyProject(name, impact)`), `skills`, `location_preference`, `availability`
  - `load_profile_config(path)` — YAML safe_load + `ProfileConfig.model_validate()`, raises `FileNotFoundError` if missing

- Updated `src/api/app.py` lifespan:
  - Calls `load_profile_config(profile_path)` at startup, stores on `app.state.profile_config`
  - Reads `RESUMES_DIR` env var (default `"resumes"`), stores on `app.state.resumes_dir`

- Replaced stub `src/api/routes/profile.py`:
  - `GET /profile` (mounted at `/profile`) reads `app.state.profile_config`, returns `ProfileOut`
  - Returns HTTP 503 with `detail: "profile_not_loaded"` if startup failed

- Replaced stub `src/api/routes/resume.py`:
  - `POST /resume/select-resume` reads all resumes from `app.state.resumes_dir`
  - Builds selection prompt with job_title, company, job_description, resume previews (first 500 chars each)
  - Calls `anthropic.Anthropic().messages.create(model="claude-haiku-3-5", max_tokens=256)`
  - Parses first line of response as chosen filename; falls back to case-insensitive match, then first resume
  - Returns HTTP 404 (`no_resumes_found`) or 503 (`anthropic_api_unavailable`) on failure

### Task 2: Screening Answer Generation Endpoint (AI-03, D-20)

- `POST /application/generate-screening-answers` added to `src/api/routes/application.py`:
  - Validates job exists (404 if not)
  - Returns empty answers list immediately for empty `screening_questions` (no LLM call)
  - Builds prompt: job_title + job_description + profile summary/skills/projects + numbered question list
  - Calls Claude Haiku (`max_tokens=1024`), parses JSON `{"answers": [{question, answer}, ...]}`
  - Handles markdown code block extraction as fallback for malformed JSON
  - Stores `json.dumps(answers_list)` on `job.screening_answers`; updates `job.updated_at`
  - Returns `GenerateScreeningAnswersOut(job_id, answers)`

### Task 3: Application Lifecycle Endpoints + Tests

- `POST /application/write-application`:
  - Fetches Job by id (404 if not found)
  - Guards: job.status must be QUEUED (409 `job_not_queued` otherwise)
  - Sets `resume_template`, `cover_letter`, `status=APPLYING`, `updated_at=now()`
  - Calls `write_audit(session, source="api", event=AuditEvent.APPLYING)`
  - Returns `{"status": "ok", "job_id": job_id}`

- `POST /application/mark-submitted`:
  - Fetches Job by id (404 if not found)
  - Guards: job.status must be APPLYING (409 `job_not_applying` otherwise)
  - Sets `status=SUBMITTED`, `updated_at=now()`
  - Creates `Application(job_id, resume_template, cover_letter, screening_answers, submitted_at=now())`
  - Calls `write_audit(session, source="api", event=AuditEvent.SUBMITTED)`
  - Returns `{"status": "ok", "job_id": job_id}`

## Test Results

All 14 integration tests pass:

| File | Tests | Result |
|------|-------|--------|
| test_resume_endpoint.py | 3 (success, no_resumes, anthropic_failure) | PASSED |
| test_profile_endpoint.py | 2 (success, shape validation) | PASSED |
| test_screening_answers.py | 4 (success, empty_questions, not_found, anthropic_failure) | PASSED |
| test_application_endpoints.py | 5 (write success, not_found, 409, mark success, 409) | PASSED |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FastAPI response_model incompatibility with dict|JSONResponse**
- **Found during:** Task 2 first test run
- **Issue:** FastAPI raises `FastAPIError: Invalid args for response field` when route return annotation is `dict | JSONResponse` — cannot model this union type as a Pydantic schema
- **Fix:** Added `response_model=None` to `@router.post("/write-application")` and `@router.post("/mark-submitted")` decorators; return type annotation preserved for type-checking purposes
- **Files modified:** `src/api/routes/application.py`
- **Commit:** 4a025d9, ad7ee74

**2. [Rule 1 - Bug] Test isolation failure — AsyncClient has no .app attribute**
- **Found during:** Task 1 initial test structure
- **Issue:** Tests attempted to set `client.app.state.resumes_dir` after fixture creation, but `AsyncClient` has no `.app` attribute — `ASGITransport` wraps the app but doesn't expose it
- **Fix:** Restructured tests to set `RESUMES_DIR` env var before the lifespan context starts (each test function manages its own lifespan context), ensuring the app reads the correct `resumes_dir` at startup
- **Files modified:** `tests/integration/test_resume_endpoint.py`
- **Commit:** f710c0b

**3. [Rule 2 - Missing Critical Functionality] Ruff lint/format compliance**
- **Found during:** Task 3 verification (ruff check)
- **Issue:** New files had E501 line-too-long violations and I001 import ordering violations (anthropic import not sorted alphabetically relative to stdlib imports)
- **Fix:** Fixed docstring word-wrap for long lines, moved `import anthropic` before `import structlog`, ran `ruff format` on application.py and resume.py
- **Files modified:** `src/api/routes/resume.py`, `src/api/routes/application.py`
- **Commit:** ad7ee74

## Known Stubs

None — all stubs from Plan 01 resolved in this plan:

| File | Was Stub | Now |
|------|---------|-----|
| `src/api/routes/resume.py` | `GET /` returns not_implemented | `POST /resume/select-resume` fully implemented |
| `src/api/routes/profile.py` | `GET /` returns not_implemented | `GET /profile` fully implemented |
| `src/api/routes/application.py` | `GET /` returns not_implemented | 3 endpoints fully implemented |

## Threat Flags

No new threat surface beyond the plan's threat model. All T-02-1x mitigations applied:
- T-02-13: ANTHROPIC_API_KEY read from env via `anthropic.Anthropic()` default; never logged
- T-02-14: `list_resumes()` only reads from configured `resumes_dir`; no user-supplied paths
- T-02-15: `/write-application` status guard (must be QUEUED) prevents double-application; 409 on violation
- T-02-16: `write_audit()` called for APPLYING and SUBMITTED transitions

## Self-Check: PASSED
