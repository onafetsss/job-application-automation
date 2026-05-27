---
phase: 02-ingest-generate-and-email-apply
plan: "01"
subsystem: api
tags: [fastapi, api, ingest, dedup, eligibility, docker, schemas]
dependency_graph:
  requires: []
  provides:
    - src/api/app.py (FastAPI app with lifespan, session dependency, API key auth)
    - src/api/schemas.py (all Phase 2 Pydantic request/response schemas)
    - src/api/routes/ingest.py (POST /ingest-lead fully implemented)
    - src/queue/models.py (AgentConfig model, screening_questions column)
    - src/audit_log.py (APPLYING, SUBMITTED, FAILED, NOTIFIED events)
    - docker-compose.yml (n8n + api services on agent-network)
    - config/profile.yaml (AI prompt placeholder profile)
  affects:
    - All subsequent Phase 2 plans (02-02 through 02-06) depend on the FastAPI app
tech_stack:
  added:
    - fastapi>=0.100 (ASGI web framework)
    - uvicorn>=0.23 (ASGI server)
    - python-jobspy>=1.1.82 (job board scraping, used in plan 02-03)
    - google-api-python-client>=2.100 (Gmail API, used in plan 02-02)
    - google-auth-oauthlib>=1.0 (OAuth flow for Gmail)
    - google-auth>=2.20 (Google auth base)
    - python-docx>=1.0 (resume .docx reading, used in plan 02-04)
    - pymupdf>=1.23 (resume .pdf reading, used in plan 02-04)
    - anthropic>=0.20 (LLM for cover letter/matching, used in plans 02-04/02-05)
    - httpx>=0.25 (async HTTP for Kalibrr scraper, used in plan 02-03)
    - beautifulsoup4>=4.12 (HTML parsing for Kalibrr scraper)
  patterns:
    - FastAPI lifespan pattern (init_db + session factory + config loading at startup)
    - Request-scoped session dependency (request.app.state.session_factory)
    - API key header auth (X-API-Key, dev-mode bypass when API_KEY unset)
key_files:
  created:
    - src/api/__init__.py
    - src/api/app.py
    - src/api/schemas.py
    - src/api/routes/__init__.py
    - src/api/routes/ingest.py
    - src/api/routes/gmail.py (stub)
    - src/api/routes/scrape.py (stub)
    - src/api/routes/resume.py (stub)
    - src/api/routes/application.py (stub)
    - src/api/routes/profile.py (stub)
    - src/ingestion/__init__.py
    - src/preparation/__init__.py
    - docker-compose.yml
    - Dockerfile.api
    - config/profile.yaml
    - tests/integration/test_ingest_endpoint.py
  modified:
    - pyproject.toml (added 11 Phase 2 dependencies)
    - uv.lock (regenerated)
    - .env.example (added ANTHROPIC_API_KEY, N8N_ENCRYPTION_KEY, RESUMES_DIR, PROFILE_CONFIG_PATH)
    - src/queue/models.py (AgentConfig model, screening_questions column)
    - src/audit_log.py (APPLYING, SUBMITTED, FAILED, NOTIFIED AuditEvent values)
decisions:
  - "get_session uses request.app.state.session_factory instead of module-level global — avoids stale singleton in test isolation"
  - "LeadOut returns lowercase status (queued/rejected/duplicate) to match API contract; JobStatus enum values remain uppercase for DB storage"
  - "API key auth (T-02-01) uses dev-mode bypass when API_KEY env var unset — tests work without configuration"
  - "n8n port 5678 bound to 127.0.0.1 in docker-compose.yml (T-02-04: not exposed to public network)"
metrics:
  duration: "15 minutes"
  completed: "2026-05-27T17:52:48Z"
  tasks_completed: 3
  files_created: 16
  files_modified: 5
---

# Phase 2 Plan 01: FastAPI Foundation and /ingest-lead Endpoint Summary

**One-liner:** FastAPI app with request-scoped session dependency, all Phase 2 Pydantic schemas, `/ingest-lead` endpoint wiring Phase 1 dedup+eligibility+audit pipeline via HTTP, Docker Compose for n8n+API co-location, and 4 passing integration tests.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1a | Dependencies, Docker Compose, Dockerfile, env config, profile.yaml | a268dd0 | pyproject.toml, docker-compose.yml, Dockerfile.api, .env.example, config/profile.yaml |
| 1b | FastAPI app scaffold, schemas, models, audit events, stub routes | 623184c | src/api/app.py, src/api/schemas.py, src/queue/models.py, src/audit_log.py, all route stubs |
| 2 | Implement /ingest-lead with dedup + eligibility + audit | bbcd237 | src/api/routes/ingest.py, tests/integration/test_ingest_endpoint.py |

## What Was Built

### Task 1a
- Added 11 Phase 2 dependencies to `pyproject.toml` and ran `uv sync --python 3.11`
- Created `docker-compose.yml` with `n8n` and `api` services on `agent-network` bridge; n8n port 5678 bound to localhost only (T-02-04)
- Created `Dockerfile.api` with uvicorn CMD pointing to `src.api.app:app`
- Updated `.env.example` with `ANTHROPIC_API_KEY`, `N8N_ENCRYPTION_KEY` (with openssl note), `RESUMES_DIR`, `PROFILE_CONFIG_PATH`
- Created `config/profile.yaml` with realistic placeholder profile (summary, target_roles, key_projects, skills, location_preference, availability)

### Task 1b
- Created `src/api/app.py`: FastAPI app with `asynccontextmanager` lifespan that calls `init_db()`, creates `get_session_factory()`, loads `eligibility_config` and `profile_config_path` onto `app.state`; `get_session` dependency uses `request.app.state.session_factory` for proper test isolation; `verify_api_key` dependency implements T-02-01 with dev-mode bypass
- Created `src/api/schemas.py`: All 14 Phase 2 schemas (LeadIn, LeadOut, ScrapeJobSpyIn, ScrapeKalibrrIn, SelectResumeIn/Out, WriteApplicationIn, MarkSubmittedIn, PollGmailOut, FetchEmailBodyIn/Out, GenerateScreeningAnswersIn/Out, ProfileOut)
- Added `AgentConfig` model to `src/queue/models.py` (`agent_config` table with key/value/updated_at)
- Added nullable `screening_questions` column to `Job` model (structural preparation for AI-03 enrichment)
- Added 4 new `AuditEvent` values: APPLYING, SUBMITTED, FAILED, NOTIFIED
- Created stub routes for gmail, scrape, resume, application, profile (all return `{"status": "not_implemented"}`)

### Task 2
- Implemented full `POST /ingest/ingest-lead` endpoint following `main.py` lines 174-274 pattern
- Pipeline: `hash_url` → `is_duplicate` (dedup) → `check_eligibility` → `Job` insert → `write_audit` in a single `session.begin()` transaction
- Returns lowercase status (`"queued"` / `"rejected"` / `"duplicate"`) per `LeadOut` API contract; `JobStatus` enum values stored uppercase in DB
- Error handling: unexpected exceptions re-raised as HTTP 500 with structured detail body

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Lowercased status in LeadOut response**
- **Found during:** Task 2 test run
- **Issue:** `JobStatus.QUEUED.value` returns `"QUEUED"` (uppercase), but the plan specifies LeadOut status as `"queued" | "rejected" | "duplicate"` (lowercase) and test assertions checked lowercase
- **Fix:** Added `.lower()` on `status.value` in the `LeadOut` return; DB storage unchanged (enum values remain uppercase in the `status` column)
- **Files modified:** `src/api/routes/ingest.py`
- **Commit:** bbcd237

**2. [Rule 2 - Missing Critical Functionality] API key auth (T-02-01)**
- **Found during:** Task 1b — threat model specifies T-02-01 as `mitigate`
- **Issue:** Plan listed T-02-01 but did not specify implementation location; app needed an auth dependency
- **Fix:** Added `verify_api_key` dependency to `src/api/app.py`; applied as `dependencies=[Depends(verify_api_key)]` on `/ingest-lead`; dev-mode bypass when `API_KEY` env var unset
- **Files modified:** `src/api/app.py`, `src/api/routes/ingest.py`
- **Commit:** 623184c, bbcd237

**3. [Rule 1 - Bug] get_session redesigned to avoid module-level singleton**
- **Found during:** Task 2 test fixture development
- **Issue:** Original plan pattern used a `_session_factory` module-level global set during lifespan; httpx `ASGITransport` doesn't run the ASGI lifespan by default, causing `AssertionError` in tests
- **Fix:** Changed `get_session` to accept `Request` parameter and access `request.app.state.session_factory`; used `app.router.lifespan_context(app)` in test fixture to manually trigger lifespan
- **Files modified:** `src/api/app.py`
- **Commit:** bbcd237

**4. [Rule 1 - Bug] uv sync Python version**
- **Found during:** Task 1a
- **Issue:** Default `uv sync` used system Python 3.9.6 which couldn't build `numpy 1.26.3` (a transitive dependency of `python-jobspy`)
- **Fix:** Added `--python 3.11` flag to `uv sync`; Python 3.11.15 is available via uv's managed Python distribution
- **Impact:** uv.lock now pins Python 3.11.15; developers need uv >= 0.4 to reproduce

## Known Stubs

The following route files are intentional stubs — they will be replaced in subsequent plans:

| File | Stub | Resolved by |
|------|------|-------------|
| `src/api/routes/gmail.py` | `GET /` returns `{"status": "not_implemented"}` | Plan 02-02 |
| `src/api/routes/scrape.py` | `GET /` returns `{"status": "not_implemented"}` | Plan 02-03 |
| `src/api/routes/resume.py` | `GET /` returns `{"status": "not_implemented"}` | Plan 02-04 |
| `src/api/routes/application.py` | `GET /` returns `{"status": "not_implemented"}` | Plan 02-05 |
| `src/api/routes/profile.py` | `GET /` returns `{"status": "not_implemented"}` | Plan 02-06 |
| `config/profile.yaml` | Placeholder values — not Stefano's real profile | Manual edit before deployment |

These stubs do not affect the plan's goal (the `/ingest-lead` endpoint is fully functional).

## Threat Flags

No new threat surface found beyond what is covered in the plan's threat model. All T-02-0x mitigations were applied during execution.

## Self-Check: PASSED

- `src/api/app.py` exists: FOUND
- `src/api/schemas.py` exists: FOUND
- `src/api/routes/ingest.py` exists: FOUND
- `src/queue/models.py` (AgentConfig): FOUND
- `docker-compose.yml` exists: FOUND
- `Dockerfile.api` exists: FOUND
- `config/profile.yaml` exists: FOUND
- `tests/integration/test_ingest_endpoint.py` exists: FOUND
- commit a268dd0: FOUND
- commit 623184c: FOUND
- commit bbcd237: FOUND
- 4/4 tests passing: CONFIRMED
- All 8 plan verifications passing: CONFIRMED
