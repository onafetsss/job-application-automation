# Phase 3: LinkedIn Easy Apply - Context

**Gathered:** 2026-05-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Add Camoufox-based LinkedIn Easy Apply submission on top of the existing n8n → FastAPI architecture. The phase delivers: session-persistent browser automation that navigates the Easy Apply modal, fills fields, uploads resume, answers screening questions via AI, submits, and writes SUBMITTED to the application log. Challenge detection (CAPTCHA, unusual activity) pauses automation immediately and fires a Telegram alert. Daily cap of 15-20 submissions with randomized timing across a 6-8 hour window.

This phase does NOT add a new job ingestion source — it routes jobs already in the queue (tagged `apply_type='linkedin_easy_apply'`) through the browser automation path.

</domain>

<decisions>
## Implementation Decisions

### Job Sourcing
- **D-01:** Optimistic tagging — all LinkedIn URLs from Gmail alert ingestion are tagged `apply_type='linkedin_easy_apply'`. Camoufox checks at runtime whether the Easy Apply button is present. If not found, skip the job and log as SKIPPED (no error, expected case).
- **D-02:** Phase 3 updates the Gmail ingest logic: if the extracted job URL contains `linkedin.com`, set `apply_type='linkedin_easy_apply'` instead of `'email'`. This is a small fix to the existing `gmail_client.py` ingest path — minimal Phase 2 code change.
- **D-03:** No LinkedIn job board scraper added in this phase. Job supply comes from Gmail alert digests already being processed by Phase 2.

### Session & Challenge Handling
- **D-04:** Persist session cookies to disk. Log in to LinkedIn manually once, save the Camoufox browser session/cookies to a file (e.g., `data/linkedin_session.json`). Each automated run loads the saved session — no re-login unless cookies expire.
- **D-05:** When cookies expire or LinkedIn rejects the session, Camoufox detects the redirect to login page, stops the run, and fires a Telegram alert: "LinkedIn session expired — manual re-login required." Manual recovery: Stefano logs in via the session file regeneration script.
- **D-06:** Challenge detection (CAPTCHA, "unusual activity" page, 2FA prompt): stop the run immediately, fire a Telegram alert with the challenge type, and halt. Do NOT retry automatically. Stefano resolves manually, then re-enables the workflow in n8n. No auto-resume after cooldown.

### Proxy Strategy
- **D-07:** Start with VPS IP — no proxy. Camoufox fingerprinting + randomized timing at 15-20/day is sufficient for this volume. If LinkedIn flags the account, add Smartproxy residential (~$30/month) as the fix. Proxy is not part of the Phase 3 implementation — it's an operational fallback.

### Orchestration
- **D-08:** Follows the same n8n → FastAPI pattern as Phase 2. n8n runs a scheduled workflow that calls `POST /apply/linkedin-easy-apply` with a `job_id`. FastAPI starts a Camoufox session, performs the apply, returns result. n8n handles the daily cap and timing via its own scheduler logic.
- **D-09:** Daily cap enforcement: n8n workflow tracks submission count for the current day and stops triggering once the cap (15-20) is reached. Timing is randomized within a configurable window (e.g., 09:00–17:00 local time).

### Form Field Coverage
- **D-10:** Standard fields handled: name, email, phone, resume upload, cover letter, work authorization (yes/no), LinkedIn profile URL, years of experience. Screening questions answered by Claude Haiku via existing `/application/generate-screening-answers` endpoint.
- **D-11:** Unknown/unrecognized fields: log the field label, skip the job, write status as SKIPPED with reason `'unknown_form_field: {label}'`, fire Telegram alert. Do not attempt to fill unknown fields.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Architecture
- `.planning/phases/02-ingest-generate-and-email-apply/02-CONTEXT.md` — locked architecture decisions: n8n → FastAPI pattern, Docker service names, credential IDs, Telegram notification pattern
- `.planning/phases/02-ingest-generate-and-email-apply/02-05-SUMMARY.md` — Phase 2 final state: all 6 n8n workflows, FastAPI endpoints, Docker setup
- `CLAUDE.md` — full tech stack, Camoufox 0.4.x usage, Docker conventions, uv/ruff/mypy/pytest conventions

### Existing Code (integration points)
- `src/queue/models.py` — Job model with `apply_type`, `status`, `retry_count` fields
- `src/api/routes/application.py` — existing `/application/queued-email-jobs` and `/application/generate-screening-answers` endpoints (pattern to follow)
- `src/api/routes/scrape.py` — existing scraper endpoint pattern
- `n8n/workflows/ai-apply-pipeline.json` — Phase 2 apply pipeline (pattern for Phase 3 n8n workflow)

### Phase 3 Scope
- `.planning/ROADMAP.md` §Phase 3 — goal, requirements (APPLY-01), success criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/api/routes/application.py` → `generate-screening-answers` endpoint: already calls Claude Haiku for screening Q&A — Phase 3 reuses this for LinkedIn screening questions
- `src/preparation/` — resume selection and cover letter prep logic already exists; Phase 3 reuses resume selection for the file upload step
- `n8n/workflows/error-handler.json` — existing error handler workflow catches n8n errors; Phase 3 LinkedIn workflow connects to it

### Established Patterns
- All FastAPI endpoints use `httpHeaderAuth` with `fastApiKey` credential ID — Phase 3 follows same pattern
- All Docker service URLs use `http://job-app-api:8000` — never localhost
- All Telegram alerts use `$env.TELEGRAM_CHAT_ID` — same in Phase 3
- `apply_type` field on Job model routes jobs to the right submission path — set during ingestion

### Integration Points
- `gmail_client.py` ingest path: add URL-based `apply_type` detection (linkedin.com → 'linkedin_easy_apply')
- New FastAPI route: `POST /apply/linkedin-easy-apply` — receives `job_id`, starts Camoufox session, returns `{status, application_id}`
- New n8n workflow: `linkedin-easy-apply.json` — scheduled trigger with daily cap logic, calls FastAPI endpoint, handles success/error routing
- Session file: `data/linkedin_session.json` — persisted Camoufox cookies, mounted as Docker volume

</code_context>

<specifics>
## Specific Ideas

- Session cookie file path: `data/linkedin_session.json` (same `data/` directory as SQLite DB — already volume-mounted in Docker)
- Challenge detection signal: check for URL containing `/checkpoint/` or `/login` after navigation, or for known challenge page titles
- Telegram challenge alert format: "⚠️ LinkedIn challenge detected: {type} — automation paused. Resolve manually, then reactivate the LinkedIn workflow in n8n."
- Daily cap window: configurable via env var `LINKEDIN_APPLY_WINDOW_START` / `LINKEDIN_APPLY_WINDOW_END` (default 09:00–17:00)

</specifics>

<deferred>
## Deferred Ideas

- Residential proxy (Smartproxy) — operational fallback if VPS IP gets flagged, not part of Phase 3 build. Add to `.env.example` as a placeholder.
- LinkedIn job board scraper (finding new Easy Apply jobs directly on LinkedIn) — Phase 4 candidate or standalone spike
- Account warmup sequence (manual-like browsing before first automated run) — user judgment call, not automated

</deferred>

---

*Phase: 3-LinkedIn Easy Apply*
*Context gathered: 2026-05-29*
