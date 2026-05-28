# Requirements: Autonomous Job Application Agent

**Defined:** 2026-05-26
**Core Value:** Apply to every eligible job faster than any human could — at scale, around the clock, without Stefano lifting a finger.

## v1 Requirements

### Ingestion

- [ ] **INGEST-01**: System monitors Gmail for LinkedIn job alert digest emails and extracts job leads (title, company, location, URL, JD)
- [ ] **INGEST-02**: System scrapes Kalibrr job listings on a schedule and extracts job leads
- [ ] **INGEST-03**: System scrapes additional job boards (Indeed, etc.) via JobSpy and extracts job leads
- [ ] **INGEST-04**: System deduplicates job leads across all sources using company + title + location fuzzy matching before queuing

### Filtering

- [ ] **FILTER-01**: System filters job leads against a YAML/JSON eligibility config with job title keywords (include/exclude lists)
- [ ] **FILTER-02**: System filters job leads by location (city, country, or remote-only flag) from the eligibility config
- [ ] **FILTER-03**: System runs in dry-run mode — filters and prepares applications but does not submit — for validation before autonomous operation begins

### AI Generation

- [ ] **AI-01**: System selects the best-fit resume template from Stefano's library by matching template content against the job description
- [ ] **AI-02**: System generates a tailored cover letter per application using the job description and Stefano's profile
- [ ] **AI-03**: System generates answers to custom screening questions using the job description and Stefano's profile

### Application Submission

- [x] **APPLY-01**: System submits applications via LinkedIn Easy Apply (max 15-20/day with randomized timing to avoid detection)
- [ ] **APPLY-02**: System submits applications via email (resume + AI cover letter as attachment)
- [ ] **APPLY-03**: System submits applications via Kalibrr's native apply flow using browser automation
- [ ] **APPLY-04**: System fills and submits generic web application forms using browser automation

### Safety & Operations

- [ ] **OPS-01**: System detects authentication challenges (CAPTCHAs, login walls) and pauses automation with an alert rather than failing silently
- [ ] **OPS-02**: System sends a heartbeat signal so Stefano can confirm it is running; alerts on extended silence
- [ ] **OPS-03**: System logs every application submission with full audit trail (job ID, platform, timestamp, resume used, cover letter, outcome)

### Notifications

- [ ] **NOTIF-01**: System sends a Telegram or WhatsApp notification after each successful application submission
- [ ] **NOTIF-02**: System sends a Telegram or WhatsApp alert on any critical failure (challenge detected, crash, auth expiry)

### Dashboard (CRM)

- [ ] **DASH-01**: Web dashboard displays full application list with current status (applied, interviewing, rejected, offer, ghosted)
- [ ] **DASH-02**: Dashboard shows stats and funnel view: total applied, response rate, interview rate, offer rate
- [ ] **DASH-03**: Dashboard shows job detail view per application: job description, resume template used, cover letter sent, timestamp
- [ ] **DASH-04**: User can manually update application status and add notes from the dashboard (e.g. "recruiter called", "interview scheduled")
- [ ] **DASH-05**: System retroactively imports job application history from Gmail (last 6 months) and populates the CRM on first run

## v2 Requirements

### Filtering

- **FILTER-V2-01**: Salary range filter (minimum salary or range) — deferred until salary data is reliably available from scrapers
- **FILTER-V2-02**: Company blocklist — skip specific companies by name
- **FILTER-V2-03**: AI scoring layer on top of hard filters — LLM scores filtered leads for fit quality

### Application Submission

- **APPLY-V2-01**: Support additional job boards beyond Indeed/Kalibrr (JobStreet, LinkedIn Jobs direct URL, etc.)

### Dashboard

- **DASH-V2-01**: Response rate trends over time (weekly/monthly chart)
- **DASH-V2-02**: Export application history to CSV

## Out of Scope

| Feature | Reason |
|---------|--------|
| Human approval queue before submission | Defeats the core value — fully autonomous by design |
| AI resume rewriting / tailoring content | Recruiter detection risk, authenticity concern; template selection is safer |
| Unlimited daily volume | LinkedIn enforces limits; exceeding 20/day risks permanent account ban |
| CAPTCHA solving | Terms of Service violation; brittle; legal exposure |
| Follow-up email automation | Domain spam risk; wrong tone at a critical moment |
| Interview scheduling automation | High-stakes interaction; wrong message = burned opportunity |
| Mobile app | Web dashboard is sufficient for single-user CRM |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INGEST-01 | Phase 2 | Pending |
| INGEST-02 | Phase 2 | Pending |
| INGEST-03 | Phase 2 | Pending |
| INGEST-04 | Phase 1 | Pending |
| FILTER-01 | Phase 1 | Pending |
| FILTER-02 | Phase 1 | Pending |
| FILTER-03 | Phase 1 | Pending |
| AI-01 | Phase 2 | Pending |
| AI-02 | Phase 2 | Pending |
| AI-03 | Phase 2 | Pending |
| APPLY-01 | Phase 3 | Complete |
| APPLY-02 | Phase 2 | Pending |
| APPLY-03 | Phase 4 | Pending |
| APPLY-04 | Phase 4 | Pending |
| OPS-01 | Phase 2 | Pending |
| OPS-02 | Phase 2 | Pending |
| OPS-03 | Phase 1 | Pending |
| NOTIF-01 | Phase 2 | Pending |
| NOTIF-02 | Phase 2 | Pending |
| DASH-01 | Phase 4 | Pending |
| DASH-02 | Phase 4 | Pending |
| DASH-03 | Phase 4 | Pending |
| DASH-04 | Phase 4 | Pending |
| DASH-05 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 24 total
- Mapped to phases: 24 ✓
- Unmapped: 0

---
*Requirements defined: 2026-05-26*
*Last updated: 2026-05-26 after roadmap creation*
