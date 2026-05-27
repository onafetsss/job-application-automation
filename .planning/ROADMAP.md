# Roadmap: Autonomous Job Application Agent

## Overview

Four phases deliver the complete autonomous job application system. Phase 1 builds the data layer and filter logic that everything else depends on. Phase 2 adds all ingestion sources, AI generation, email submission, and notifications — producing the first real end-to-end run at zero LinkedIn account risk. Phase 3 adds LinkedIn Easy Apply with full anti-detection hardening. Phase 4 adds Kalibrr and generic form submissions plus the web dashboard CRM, completing the system.

## Phases

- [~] **Phase 1: Foundation** - DB schema, eligibility filter, dry-run mode, deduplication — the contract every later component depends on
- [ ] **Phase 2: Ingest, Generate, and Email Apply** - Gmail ingestion, JobSpy scraping, AI cover letter generation, email submission, notifications — first live end-to-end run with zero LinkedIn risk
- [ ] **Phase 3: LinkedIn Easy Apply** - Camoufox browser automation with anti-detection, challenge detection, conservative rate limiting
- [ ] **Phase 4: Dashboard CRM and Additional Sources** - Web CRM dashboard with Gmail history import, Kalibrr native apply, and generic form apply

## Phase Details

### Phase 1: Foundation
**Goal**: The data layer, eligibility filter, deduplication, and dry-run mode are fully operational — any job lead can be ingested, deduplicated, and filter-decided with a rejection reason, without touching any submission path
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: INGEST-04, FILTER-01, FILTER-02, FILTER-03, OPS-03
**Success Criteria** (what must be TRUE):
  1. Running the system against a batch of sample job leads produces a jobs table with QUEUED and REJECTED rows, each with a specific rejection reason logged
  2. A duplicate job lead (same company + title + location) fed through the system appears once in the jobs table, not twice
  3. Dry-run mode processes jobs through the full filter pipeline and writes rejection/approval decisions to the log without submitting anything
  4. The eligibility config (eligibility.yaml) can be edited to change title keywords, location, or exclusions and the system reflects the new rules immediately on next run without code changes
  5. Every processed job has a full audit log entry: job ID, source, timestamp, filter decision, and reason
**Plans**: 5 plans (2 gap closure)
Plans:

**Wave 1**
- [x] 01-PLAN-01-scaffold-db-schema.md — Project scaffold, pyproject.toml, SQLite engine, ORM models (Job/Application/AuditLogEntry), stub config and main.py boot

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 01-PLAN-02-filter-engine.md — Config loader (YAML→Pydantic), eligibility filter (pure function), cross-source deduplication with unit and integration tests

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 01-PLAN-03-dry-run-cli.md — Complete write_audit(), upgrade main.py to full dry-run pipeline, end-to-end CLI test

**Gap Closure** *(after verification — both plans wave 1, independent, parallel-safe)*
- [x] 01-04-PLAN.md — Add in-memory seen_hashes set to main.run() so dry-run catches within-batch URL duplicates (closes VERIFICATION truths 14 + 16)
- [x] 01-05-PLAN.md — Move blocked_phrases JD scan outside the location-is-not-None guard in eligibility.py (closes VERIFICATION truth 9 / REVIEW CR-02)

Cross-cutting constraints:
- `--dry-run` CLI flag (D-01) affects all three plans — must be wired through main.py in Wave 3
- SQLite WAL mode must be set at DB init (Wave 1) — all later phases depend on this

### Phase 2: Ingest, Generate, and Email Apply
**Goal**: The full pipeline runs end-to-end — Gmail job alerts and JobSpy scraped leads flow in, get filtered and deduplicated, AI selects the best resume and generates a tailored cover letter, applications submit via email, and Telegram notifications fire after each submission
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: INGEST-01, INGEST-02, INGEST-03, AI-01, AI-02, AI-03, APPLY-02, NOTIF-01, NOTIF-02, OPS-01, OPS-02
**Success Criteria** (what must be TRUE):
  1. A LinkedIn job alert email arriving in Gmail is parsed into a structured job lead and appears in the jobs table within minutes, without manual intervention
  2. JobSpy scrapes Indeed and other configured boards on schedule and adds new leads to the jobs table
  3. For each queued job, the system selects a resume template from the library and generates a cover letter that names the specific company and references a concrete detail from the job description
  4. A job with an email apply path receives a real email with the selected resume PDF and generated cover letter attached, and the application log entry is written as SUBMITTED
  5. A Telegram notification arrives after each submission containing company name, role, resume used, and job URL
  6. When the system detects a CAPTCHA or auth challenge it pauses automation and fires a Telegram alert rather than silently failing or crashing
  7. A heartbeat signal is emitted on schedule so an extended silence triggers an alert
**Plans**: 5 plans
Plans:

**Wave 1**
- [x] 02-01-PLAN.md — FastAPI scaffold, Pydantic schemas, /ingest-lead endpoint, AgentConfig model, AuditEvent additions, Docker Compose, Dockerfile.api

**Wave 2** *(blocked on Wave 1 completion — all three plans run in parallel)*
- [x] 02-02-PLAN.md — Gmail API client with OAuth2, historyId polling, /poll-gmail and /fetch-email-body endpoints
- [x] 02-03-PLAN.md — JobSpy runner, Kalibrr scraper, /scrape-jobspy and /scrape-kalibrr endpoints
- [x] 02-04-PLAN.md — Resume reader, profile loader, /select-resume endpoint, /write-application and /mark-submitted endpoints

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 02-05-PLAN.md — Six n8n workflow JSON files (gmail-ingest, jobspy-scrape, kalibrr-scrape, ai-apply-pipeline, error-handler, heartbeat), supporting GET endpoints, README

Cross-cutting constraints:
- n8n uses Docker service name `http://api:8000` for all FastAPI calls (never localhost)
- All Claude API calls from n8n use Header Auth credential "anthropicApi" with x-api-key header
- Gmail OAuth token must be obtained via scripts/gmail_oauth.py before deployment
- N8N_ENCRYPTION_KEY must be generated and set before first n8n launch (never regenerated)

### Phase 3: LinkedIn Easy Apply
**Goal**: LinkedIn Easy Apply submissions run autonomously at 15-20 per day with no account restriction — Camoufox is active, challenge detection pauses the run with an alert, and timing is randomized across a 6-8 hour window
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: APPLY-01
**Success Criteria** (what must be TRUE):
  1. The system completes a LinkedIn Easy Apply submission end-to-end — modal navigation, field fill, file upload, screening question answers, and final submit — and writes SUBMITTED to the application log
  2. The browser session passes a bot-detection fingerprinting test (bot.sannysoft.com or equivalent) before any live LinkedIn run begins
  3. When a CAPTCHA or "unusual activity" page is detected during a LinkedIn session, automation stops immediately and a Telegram alert fires (no silent hang, no crash)
  4. Daily LinkedIn submissions are capped at 15-20 with randomized timing; the system does not submit more than the cap even if more jobs are queued
**Plans**: TBD

### Phase 4: Dashboard CRM and Additional Sources
**Goal**: The web dashboard shows every application with status, stats, and job detail; Stefano can update statuses and add notes; Gmail history for the last 6 months is imported on first run; Kalibrr and generic web forms are active submission channels
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: APPLY-03, APPLY-04, DASH-01, DASH-02, DASH-03, DASH-04, DASH-05
**Success Criteria** (what must be TRUE):
  1. The dashboard displays all submitted applications with current status (applied, interviewing, rejected, offer, ghosted) and Stefano can update the status and add a note from the UI
  2. The dashboard funnel view shows total applied, response rate, interview rate, and offer rate computed from the application log
  3. Clicking any application row shows the job description, resume template used, cover letter sent, and submission timestamp
  4. On first run, the system imports the last 6 months of Gmail application history and populates the CRM so the dashboard is not empty on day one
  5. A Kalibrr job lead flows through the pipeline and submits via Kalibrr's native application flow, with a SUBMITTED entry in the log
  6. A job requiring a generic web form is filled and submitted via browser automation, with a SUBMITTED entry confirming positive completion
**UI hint**: yes
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 5/5 | Complete   | 2026-05-27 |
| 2. Ingest, Generate, and Email Apply | 4/5 | In Progress|  |
| 3. LinkedIn Easy Apply | 0/TBD | Not started | - |
| 4. Dashboard CRM and Additional Sources | 0/TBD | Not started | - |
