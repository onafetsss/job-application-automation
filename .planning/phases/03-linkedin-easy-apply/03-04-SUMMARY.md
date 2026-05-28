---
phase: 03-linkedin-easy-apply
plan: "04"
subsystem: api
tags: [n8n, linkedin, camoufox, telegram, daily-cap, session-save, apply_type]
dependency_graph:
  requires:
    - phase: 03-01 (JobStatus.SKIPPED, AuditEvent.SKIPPED, test scaffold)
    - phase: 03-02 (LinkedInApplier, ChallengeDetected, NoEasyApplyButton, UnknownFormField)
    - phase: 03-03 (POST /apply/linkedin-easy-apply, GET /apply/daily-linkedin-count, GET /apply/queued-linkedin-jobs)
  provides:
    - n8n/workflows/linkedin-easy-apply.json — scheduled daily-cap workflow with Telegram routing
    - scripts/linkedin_session_save.py — one-time manual session persistence via AsyncCamoufox
    - resolve_apply_type(url) in src/ingestion/gmail_client.py — D-02 apply_type detection helper
    - gmail-ingest.json gi-10 'Set Apply Type' node — linkedin.com URLs tagged linkedin_easy_apply
  affects:
    - n8n orchestration layer (new workflow to import/activate)
    - gmail ingest path (apply_type detection for all future LinkedIn alert digests)
    - Phase 04 dashboard (linkedin_easy_apply vs email apply_type filter)
tech_stack:
  added: []
  patterns:
    - n8n cross-node reference pattern for POST body: $('Get Next LinkedIn Job').first().json.jobs[0].id
    - n8n error output routing: onError continueErrorOutput -> success branch [0] + error branch [1]
    - n8n randomized timing: Code node generates waitSeconds -> Wait node Time Amount expression
    - AsyncCamoufox persistent_context session save with storage_state JSON as non-fatal fallback
    - resolve_apply_type pure helper function: url.lower().contains('linkedin.com') -> type string
key_files:
  created:
    - n8n/workflows/linkedin-easy-apply.json
    - scripts/linkedin_session_save.py
  modified:
    - n8n/workflows/gmail-ingest.json (gi-10 Set Apply Type node + Ingest Lead apply_type expression + connections rewire)
    - src/ingestion/gmail_client.py (resolve_apply_type function added)
key_decisions:
  - "resolve_apply_type placed in src/ingestion/gmail_client.py to match test_ingest_apply_type.py candidate list (module import candidates tried in order)"
  - "n8n Wait node references waitSeconds via $('Check Cap + Window').first().json.waitSeconds cross-node expression — not $json.waitSeconds — because If node does not modify the data"
  - "Telegram success message uses $('Get Next LinkedIn Job').first().json.jobs[0].* cross-node references because POST /apply/linkedin-easy-apply response only returns {status, job_id} (no company/title/url)"
  - "storage_state JSON export in session save script wrapped in try/except (non-fatal) — primary store is user_data_dir directory; __Host- cookies may not serialize correctly"
requirements-completed: [APPLY-01]
duration: ~25min
completed: "2026-05-29"
---

# Phase 03 Plan 04: LinkedIn Easy Apply Orchestration — Summary

**n8n daily-cap workflow (5-min schedule, 8-25min random wait, Telegram success/challenge routing), gmail-ingest apply_type detection (D-02), and one-time Camoufox session save script completing the APPLY-01 end-to-end channel — pending human checkpoint for fingerprint and live apply verification.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-29
- **Completed:** 2026-05-29 (auto tasks)
- **Tasks:** 2 of 3 completed (Task 3 is a blocking human checkpoint)
- **Files modified:** 4

## Accomplishments

- Built complete `linkedin-easy-apply.json` n8n workflow enforcing daily cap (LINKEDIN_DAILY_CAP env, default 17), time window (LINKEDIN_APPLY_WINDOW_START/END, default 9-17), randomized 8-25 min delay, and dual Telegram routing (success + challenge alert with no auto-retry per D-06)
- Patched `gmail-ingest.json` with gi-10 "Set Apply Type" Code node — all linkedin.com URLs tagged `linkedin_easy_apply`, others tagged `email` (D-02), Ingest Lead apply_type param is now expression-driven
- Added `resolve_apply_type(url)` helper to `src/ingestion/gmail_client.py` — `tests/unit/test_ingest_apply_type.py` both tests GREEN (xpassed)
- Created `scripts/linkedin_session_save.py` — AsyncCamoufox persistent_context session save with storage_state JSON as non-fatal fallback

## Task Commits

1. **Task 1: gmail-ingest apply_type detection and session save script** — `d8d5661` (feat)
2. **Task 2: Build linkedin-easy-apply n8n workflow** — `c03eb77` (feat)
3. **Task 3: Human checkpoint — session, fingerprint, live apply** — PAUSED (awaiting human action)

## Files Created/Modified

- `n8n/workflows/linkedin-easy-apply.json` — Complete n8n workflow: Schedule (li-01) → GET daily-count (li-02) → Code cap+window (li-04) → If Proceed? (li-05) → GET queued-jobs (li-06) → If Any Jobs? (li-06a) → Wait random (li-06b) → POST apply (li-07, onError continueErrorOutput) → Telegram Success (li-08) / Challenge Alert (li-09)
- `scripts/linkedin_session_save.py` — AsyncCamoufox headless=False, persistent_context=True, LINKEDIN_PROFILE_DIR env var, storage_state fallback
- `n8n/workflows/gmail-ingest.json` — gi-10 Set Apply Type node inserted between gi-07 Parse Jobs and gi-08 Ingest Lead; connections updated; apply_type param changed from "email" literal to ={{ $json.apply_type }}
- `src/ingestion/gmail_client.py` — resolve_apply_type(url: str) -> str helper function added

## Decisions Made

- `resolve_apply_type` placed in `src/ingestion/gmail_client.py` to match the test file's candidate import list (tried in order: gmail_client, filter.eligibility)
- Telegram success node references `$('Get Next LinkedIn Job').first().json.jobs[0].*` because `POST /apply/linkedin-easy-apply` response body only returns `{status, job_id}` — company/title/url must come from the GET queued-jobs cross-node reference
- Wait node uses `$('Check Cap + Window').first().json.waitSeconds` cross-node reference — the data passes through If nodes unchanged so `$json.waitSeconds` would also work but the explicit cross-node ref is safer
- `storage_state` JSON export wrapped in `try/except` (non-fatal) to handle `__Host-` cookie serialization issues documented in RESEARCH.md Pitfall 5

## Deviations from Plan

None — plan executed exactly as written. The test file's candidate module list guided placing `resolve_apply_type` in `src/ingestion/gmail_client.py` (which was the first candidate listed).

## Known Stubs

None. All implemented logic is live:
- `resolve_apply_type` is a pure function with real logic (not placeholder)
- `linkedin-easy-apply.json` targets real FastAPI endpoints built in Plan 03-03
- `gmail-ingest.json` gi-10 node has real JS logic (not TODO)
- `scripts/linkedin_session_save.py` has real Camoufox session save logic

## Threat Flags

No new threat surface beyond the plan's threat model:
- T-03-12 (session disclosure): credentials entered manually only; profile dir is git-ignored; script does not print or log credentials
- T-03-13 (ban risk): daily cap + window + random delay enforced in li-04 Code node + li-06b Wait node
- T-03-14 (fingerprint): human checkpoint Task 3 step 2 validates bot.sannysoft.com before any autonomous run
- T-03-15 (URL tampering): workflow verification confirms no localhost and all URLs use job-app-api:8000
- T-03-16 (challenge hang): li-09 Challenge Alert on error output terminates the run (no retry edge from li-09)

## Self-Check: PASSED

- `n8n/workflows/linkedin-easy-apply.json` exists: FOUND
- `scripts/linkedin_session_save.py` exists: FOUND
- `n8n/workflows/gmail-ingest.json` contains gi-10 'Set Apply Type': VERIFIED
- `src/ingestion/gmail_client.py` contains `resolve_apply_type`: VERIFIED
- linkedin-easy-apply.json active=false, no localhost, fastApiKey + telegramBot credentials: VERIFIED
- gmail-ingest.json connections Parse Jobs -> Set Apply Type -> Ingest Lead: VERIFIED
- Ingest Lead apply_type = `={{ $json.apply_type }}` (not hardcoded 'email'): VERIFIED
- `tests/unit/test_ingest_apply_type.py` both tests GREEN (xpassed): VERIFIED
- Task 1 commit d8d5661: VERIFIED
- Task 2 commit c03eb77: VERIFIED

## Human Checkpoint Pending

Task 3 requires human verification before the plan is considered fully complete:

1. **SESSION**: Run `uv run python scripts/linkedin_session_save.py` and log in manually
2. **FINGERPRINT**: Navigate to bot.sannysoft.com — confirm no red/failed rows
3. **SELECTOR VALIDATION**: Open a LinkedIn Easy Apply job and confirm XPath `//button[contains(@class, "jobs-apply-button")]` resolves
4. **LIVE APPLY**: Trigger `POST /apply/linkedin-easy-apply` against a QUEUED linkedin job — confirm SUBMITTED status, Telegram notification
5. **CHALLENGE PATH** (optional): Confirm challenge alert fires and run halts
6. **WORKFLOW IMPORT**: Import `linkedin-easy-apply.json` into n8n UI and verify credentials resolve

Resume signal: type "approved" once fingerprint passes and a live Easy Apply submits successfully (or describe selector drift for correction).
