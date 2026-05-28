---
phase: 02-ingest-generate-and-email-apply
plan: 05
wave: 3
status: complete
commit: 0f8ea10
completed_at: "2026-05-28"
---

## What Was Built

Six n8n workflow JSON files and two supporting FastAPI endpoints that complete the autonomous job application loop.

### FastAPI Endpoints Added

**GET /application/queued-email-jobs**
Returns `{"jobs": [...]}` with all QUEUED jobs where `apply_type='email'`. Used by ai-apply-pipeline to poll for work.

**GET /resume/resume-file/{resume_name}**
Serves resume binaries (PDF/DOCX) with correct content-type. Includes path traversal protection. Used by ai-apply-pipeline to attach the resume to application emails.

### n8n Workflows

| File | Trigger | Purpose |
|---|---|---|
| `gmail-ingest.json` | 1h schedule | Polls Gmail, extracts jobs with Claude Haiku, ingests with `apply_type=email` |
| `jobspy-scrape.json` | 4h schedule | Scrapes Indeed via JobSpy, ingests leads, Telegram alert on zero-results |
| `kalibrr-scrape.json` | 4h schedule | Scrapes Kalibrr, ingests leads |
| `ai-apply-pipeline.json` | 15-min schedule | Full apply loop: profile fetch → queued job poll → resume selection → conditional screening answers → Claude Sonnet cover letter → Gmail send → mark submitted → Telegram notification |
| `error-handler.json` | Error Trigger | Catches any workflow error, sends Telegram alert |
| `heartbeat.json` | 30-min schedule | Sends Telegram ping confirming system is alive |

### Key Design Decisions

- **apply_type='email' set in gmail-ingest**: Claude Haiku extracts jobs from LinkedIn email digests; each lead is ingested with `apply_type=email` so the ai-apply-pipeline knows to process them.
- **GET /profile called once per pipeline run**: Profile data fetched from `/profile` (backed by `config/profile.yaml`) at the start of each ai-apply-pipeline run. Cover letter prompt uses dynamic profile fields — no static block to maintain.
- **Conditional screening answers**: IF node checks `screening_questions` non-empty before calling `/application/generate-screening-answers`. Merge node (append mode) reunifies both branches before cover letter generation.
- **503/error routing**: HTTP Request nodes use `onError: continueErrorOutput` to branch errors to Telegram alert node instead of silently failing.
- **Apply email MVP**: `APPLY_TO_EMAIL` env var controls where applications are sent. Default: Stefano's own email for manual review/forwarding. Documented in README.
- **Docker network**: All FastAPI URLs use `http://api:8000` (Docker service name), never `localhost`.

### Files Changed

- `n8n/workflows/gmail-ingest.json` (new)
- `n8n/workflows/jobspy-scrape.json` (new)
- `n8n/workflows/kalibrr-scrape.json` (new)
- `n8n/workflows/error-handler.json` (new)
- `n8n/workflows/heartbeat.json` (new)
- `n8n/workflows/ai-apply-pipeline.json` (new)
- `n8n/README.md` (new)
- `src/api/routes/application.py` (added GET /queued-email-jobs)
- `src/api/routes/resume.py` (added GET /resume-file/{resume_name})
- `.gitignore` (added n8n_storage/)

## Verification Results

- All 6 workflow JSONs parse as valid JSON ✓
- gmail-ingest.json sets `apply_type` in `/ingest/ingest-lead` body ✓
- ai-apply-pipeline.json has 18 nodes, includes profile fetch and conditional screening answers ✓
- All FastAPI calls use `http://api:8000` (not localhost) ✓
- `GET /application/queued-email-jobs` and `GET /resume/resume-file/{name}` registered in FastAPI ✓
- `n8n_storage/` added to .gitignore ✓

## Human Verification Pending

The checkpoint task requires:
1. `docker compose up -d` — both containers healthy
2. Import workflows in n8n UI (error-handler first)
3. Configure 4 credentials: FastAPI Key, anthropicApi, Telegram Bot, Gmail OAuth2
4. Activate heartbeat workflow → verify Telegram ping within 30 min
5. Manually trigger jobspy-scrape → verify /ingest-lead logs
6. `curl http://localhost:8000/profile` → verify profile JSON
