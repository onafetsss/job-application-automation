# Project Research Summary

**Project:** Autonomous Job Application Agent
**Domain:** Agentic job application pipeline (email ingestion, multi-board scraping, AI generation, browser automation)
**Researched:** 2026-05-26
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a personal autonomous agent — not a SaaS product — designed to run 24/7 and submit job applications on Stefano's behalf without a human-in-the-loop approval step. The expert pattern for this type of system is a linear pipeline: ingest → normalize → filter → queue → prepare → apply → notify, with SQLite as the shared state store and a persistent browser session for anti-detection. The closest open-source analogue is AIHawk (Auto_Jobs_Applier_AI_Agent), which validates the YAML-config-driven eligibility filter and per-application AI generation approach. The key differentiators this agent can achieve over AIHawk and commercial tools are: multi-source ingestion (LinkedIn email + Kalibrr + others), multi-format dispatch (Easy Apply, email, full form, platform-native), multi-template resume selection, and genuinely safe LinkedIn rate limiting (15-20/day vs. the unsafe 50+ defaults in competitor tools).

The recommended stack centers on LangGraph (stateful graph orchestration with built-in SQLite checkpointing), Camoufox (Firefox stealth browser — the only 2025-2026 tool achieving 0% detection on major fingerprinting suites), Claude API (Haiku for filtering, Sonnet for generation), Gmail API with Pub/Sub push, APScheduler for polling ingestion, and Telegram for notifications. The entire system runs in a single Python process backed by a single SQLite file — no Redis, no Celery, no message broker. This is the correct scale for one user and ~15-40 applications/day.

The existential risk is LinkedIn account restriction or permanent ban. LinkedIn banned Apollo and Seamless.AI in 2025, increased its detection rate 340% between 2023-2025, and deployed updated session fingerprinting in Q1 2026. Camoufox with a persistent browser profile and residential IP (or home IP) is the technical mitigation. The behavioral mitigation is staying at 30-40% of LinkedIn's 50/day cap, randomizing timing across a 6-8 hour window, and including non-application browsing in every session. The second major risk is bad eligibility filtering: applying to wrong-fit roles at scale is the #1 failure mode of every competitor tool and produces ATS blacklisting at companies Stefano actually wants to work with. Eligibility filtering accuracy is the product quality — it must be validated in dry-run mode before autonomous operation begins.

## Key Findings

### Recommended Stack

The stack is Python 3.11+ throughout, with LangGraph as the workflow orchestration layer. LangGraph reached 1.0 stable in October 2025 and provides native stateful graphs with SQLite checkpointing — each job application is a persistent state object that survives process crashes without Redis or Celery. Camoufox replaces all other browser automation options for LinkedIn: playwright-stealth was abandoned in late 2024 and no longer patches Canvas/WebGL/AudioContext fingerprinting, which are the exact vectors LinkedIn's Q1 2026 update targets. Camoufox patches Firefox at the C++ level and achieves 0% detection on major fingerprinting test suites.

**Core technologies:**
- **Python 3.11+**: Runtime — asyncio maturity, first-class support across all required libraries
- **LangGraph 0.5.x (1.0 stable)**: Workflow orchestration — stateful graph with built-in SQLite checkpointing, crash recovery, interrupt/resume
- **Camoufox 0.4.x**: Browser automation — Firefox stealth at C++ level, 0% detection rate on fingerprinting suites, mandatory for LinkedIn
- **Claude API (Haiku-3.5 + Sonnet-4.5)**: AI generation — Haiku for cheap eligibility scoring, Sonnet for cover letters; under $0.05/application
- **Gmail API v1**: Email ingestion — Pub/Sub push eliminates polling, avoids MIME parsing with official library
- **SQLite + aiosqlite + SQLAlchemy 2.0**: State and queue — zero infrastructure, WAL mode for concurrent async writes, sufficient for 50 apps/day
- **APScheduler 3.10+**: Scheduling — in-process async scheduler backed by SQLite, no Redis or Celery required
- **JobSpy (python-jobspy)**: Multi-board scraping — normalizes Indeed/LinkedIn/Glassdoor to Pandas DataFrame; residential proxy required for LinkedIn
- **python-telegram-bot 21.x**: Notifications — free, instant, no Meta approval required
- **Sentence-Transformers (all-MiniLM-L6-v2)**: Resume selection — in-process cosine similarity, no vector DB needed at < 20 templates

**Do not use:** Selenium (most-detected), playwright-stealth PyPI (abandoned 2024), requests (sync blocks event loop), Celery (overkill for one user), WhatsApp Business API (Meta approval + per-message cost).

### Expected Features

The v1 MVP must deliver the complete LinkedIn Easy Apply loop end-to-end before any other source is added. Every competitor that is unreliable fails because it tried to cover too many sources before the core loop was solid.

**Must have (table stakes):**
- Job deduplication across all sources (URL hash + company+title fuzzy match) — without this, duplicate applications destroy credibility
- Configurable eligibility filters via YAML (role titles, location, remote flag, salary, keyword include/exclude, company blacklist)
- Application log with full audit trail (company, role, URL, date, resume version, cover letter, outcome)
- Telegram notification per submission (rich template: company, role, salary, resume used, job URL)
- Gmail ingestion of LinkedIn job alert emails → structured job records
- LinkedIn Easy Apply dispatch with anti-detection layer
- Resume library with per-job template selection (similarity matching)
- AI cover letter generation per job (JD + resume + user profile context)
- AI screening question answers (pre-anchored values for salary, start date, work authorization)

**Should have (competitive differentiators):**
- Kalibrr scraper + platform-native application dispatch (add after LinkedIn is proven stable)
- Email application dispatch for jobs that post a recruiter address
- Outcome tracking: parse Gmail for rejection/interview emails, update log entries
- Full form application dispatch for company career pages (highest complexity, add last)

**Defer (v2+):**
- ATS keyword enrichment of resume bullets per job (high value, high AI-drift risk — requires careful prompt engineering)
- Additional source adapters (Indeed alerts, Jobstreet)
- Web UI for log review and config editing
- Automated filter tuning from outcome data

**Firm anti-features — do not build in v1:**
- Unlimited high-volume applications (100+/day on LinkedIn) — triggers permanent account ban
- AI-generated resume rewrite per application — detectable by ATS and recruiters (62% rejection rate per Resume Now survey)
- CAPTCHA solving — ToS violation on all platforms, detect and skip instead
- Follow-up email automation — treated as spam at this volume
- Interview scheduling automation — too high-stakes for autonomous action

### Architecture Approach

The system uses a single-machine pipeline architecture: all components run in one Python process, coordinated by APScheduler (for ingestion cron jobs) and LangGraph (for the application state machine). SQLite serves as both the persistent queue and the audit log. The queue pattern is a `jobs` table with a `status` column — workers claim rows with `BEGIN IMMEDIATE` transactions. A persistent Camoufox browser context is shared across all browser-based adapters in a session, preserving cookies and fingerprint signals. Platform adapters follow the Strategy pattern: `executor.py` selects the correct adapter at runtime based on `job.apply_type`, making new platform support a matter of adding one adapter file.

**Major components:**
1. **Ingestion Layer** (gmail_watcher.py + board scrapers) — converts raw sources into canonical `JobLead` dataclass via normaliser.py
2. **Eligibility Filter** (eligibility.py + config_loader.py) — YAML-config-driven hard rules + SHA-256 deduplication against jobs table
3. **Job Queue** (SQLite jobs table, worker.py) — state machine: DISCOVERED → QUEUED → PREPARING → APPLYING → SUBMITTED | FAILED | DEAD_LETTER
4. **Preparation** (resume_selector.py + ai_generator.py) — cosine similarity resume selection + Claude API cover letter/answer generation
5. **Apply Executor + Adapters** (executor.py + adapters/) — Strategy pattern dispatcher; adapters: linkedin_ea, email_apply, kalibrr, generic_form
6. **Persistent Browser Session** (browser_session.py) — single Camoufox context shared across adapters, stored on disk between runs
7. **Notification Dispatcher** (telegram.py) — fire-and-forget after SUBMITTED write; failure is non-blocking to application status
8. **Persistence Layer** (SQLite via SQLAlchemy ORM) — tables: jobs, applications, resume_templates, eligibility_config

**Key patterns:**
- Queue-first, apply-second: always write to queue before any application action — enables deduplication, retry, and crash recovery
- Confirmation-required success: a submission is SUBMITTED only on positive confirmation signal (URL pattern or page text), never on button click alone
- Config-in-YAML: eligibility rules live in `config/eligibility.yaml`, not in code — filter tuning requires no deployment

### Critical Pitfalls

1. **LinkedIn account permanent ban** — LinkedIn monitors 50+ fingerprint signals simultaneously; Q1 2026 update specifically targets Playwright/Puppeteer defaults. Mitigation: use Camoufox with persistent profile and home/residential IP; cap at 15-20 apps/day (not 50); randomize timing across 6-8 hour window; include non-application browsing in each session; implement challenge detection (CAPTCHA, "unusual activity" pages) with immediate Telegram alert and automation pause.

2. **Duplicate applications across sources** — The same job appears as a LinkedIn email alert, a Kalibrr listing, and an Indeed posting simultaneously with different IDs. Mitigation: deduplicate on SHA-256 of canonical job URL AND fuzzy-match composite fingerprint (normalized company + title + location) with >0.85 cosine similarity threshold; check dedup before any expensive AI generation or browser action (fail fast); mark as applied immediately on attempt, not on confirmation.

3. **Bad eligibility filtering — applying to irrelevant roles** — This is the #1 failure mode of every competitor tool. LoopCV applies to jobs in wrong languages and countries; LazyApply users report applying to 14,000 jobs including contract work and wrong cities. Mitigation: multi-signal filter (title allowlist + seniority keywords + location whitelist + keyword blocklist); mandatory dry-run mode validated by Stefano before autonomous operation; log every rejection with specific reason for rapid config tuning; start strict, expand coverage only after reviewing rejection log.

4. **Generic AI cover letters** — 74% of hiring managers can detect AI-generated applications; 57% are far less likely to hire. Mitigation: force prompt structure (one non-obvious JD observation + one specific past project/metric from Stefano's profile + one company-specific detail); implement quality gate blocking generic phrases; run secondary model check confirming company name and named past project appear before acceptance.

5. **Silent form submission failures** — System logs SUBMITTED but employer receives nothing (required field not filled, file upload failed silently, JS form step skipped). Mitigation: require positive confirmation signal before writing SUBMITTED status; classify as FAILED and alert if no confirmation within 10 seconds; verify resume PDFs are text-layer only, under 4MB.

6. **24/7 unattended operation failures** — CAPTCHA hang, expired session, stuck browser process. Mitigation: challenge detection layer before every automated action; dead-man's switch (Telegram alert if no heartbeat in 30 minutes during active window); max runtime per cycle with force-kill; all network operations have explicit 15-30 second timeouts with exponential backoff.

## Implications for Roadmap

Based on the architecture's explicit dependency ordering and pitfall severity mapping, a 7-phase build order is recommended. The architecture research explicitly documents this as the "build order implications" — this ordering reflects real dependency constraints, not arbitrary preference.

### Phase 1: Foundation — Data Layer and Config
**Rationale:** The database schema is the contract every other component depends on. The eligibility config validation system must exist before any job is processed. Nothing can be built or tested without this.
**Delivers:** SQLite schema (jobs, applications, resume_templates, eligibility_config tables), SQLAlchemy ORM models, config/eligibility.yaml with Pydantic validation, WAL mode setup, db initialization script.
**Addresses:** Deduplication schema (URL hash from day one), audit trail structure, YAML eligibility config (prevents hardcoded filter anti-pattern).
**Avoids:** Pitfall 2 (dedup key in schema before any submission path), Pitfall 3 (config schema hard-fails on invalid config at load time).
**Research flag:** Standard patterns — skip research-phase. SQLite queue, SQLAlchemy 2.0 async, Pydantic config validation are all textbook implementations.

### Phase 2: Gmail Ingestion and Job Normalization
**Rationale:** Email parsing is the primary ingestion source and must be validated before any filtering, AI generation, or browser work. Email parsing failures are silent — audit logging that catches them must be built here, not retrofitted.
**Delivers:** Gmail API OAuth setup, Pub/Sub push handler (IMAP polling fallback), LinkedIn alert email parser (DOM-based with multiple CSS selector fallbacks), normaliser.py producing canonical `JobLead` dataclass, per-email audit log (email ID, timestamp, jobs extracted count, parse errors).
**Addresses:** Gmail ingestion (P1 feature), multi-source normalization foundation.
**Avoids:** Pitfall 8 (email parsing failures — audit logging and 0-result alerting built into parser; query by Gmail label ID not sender address).
**Research flag:** Needs research-phase. Gmail Pub/Sub setup has multiple GCP integration steps. LinkedIn email HTML structure should be spot-checked against a live current alert before finalizing parser design.

### Phase 3: Eligibility Filter and Queue Worker
**Rationale:** End-to-end flow becomes visible when filter + queue + worker connect to ingestion. Must include dry-run mode — Stefano must validate filter decisions before any application action exists.
**Delivers:** eligibility.py multi-signal filter (title allowlist, seniority keywords, location, salary, keyword include/exclude, company blacklist), hash-based and fuzzy-match deduplication, QUEUED/REJECTED status writes, worker.py skeleton (claims QUEUED rows, logs, releases), dry-run mode with full rejection reason logging.
**Addresses:** Configurable eligibility filters (P1), deduplication (P1), application log foundation (P1).
**Avoids:** Pitfall 3 (dry-run validation by Stefano required before Phase 4 begins), Pitfall 2 (dedup fully implemented before any submission path exists).
**Research flag:** Standard patterns — skip research-phase. Pure Python business logic, no external integrations.

### Phase 4: AI Generation — Resume Selection and Cover Letters
**Rationale:** AI generation is CPU/LLM-bound work completely independent of browser automation. Building and validating it here means it can be tested without any LinkedIn account risk. The quality gate must be proven before live submission.
**Delivers:** Resume library ingestion (YAML metadata + structured content), resume_selector.py using Sentence-Transformers cosine similarity, ai_generator.py (Claude Haiku for eligibility scoring, Sonnet for cover letter + screening answers), Jinja2 prompt templates with forced specificity structure, quality gate (phrase blocklist + secondary model check for company name and named project), pre-anchored config values for salary/start date/work authorization.
**Addresses:** Resume library + per-job selection (P1), AI cover letter generation (P1), AI screening question answers (P1).
**Avoids:** Pitfall 4 (generic AI cover letters — quality gate blocks non-specific output), Pitfall 9 (resume template mismatch — structured metadata tags drive deterministic selection).
**Research flag:** Needs research-phase. Sentence-Transformers integration and Claude prompt engineering for specificity-forcing pattern require design iteration. Quality gate secondary model design needs validation.

### Phase 5: Email Application Dispatch and Notifications
**Rationale:** The email adapter is the simplest and lowest-risk submission channel — no browser automation, no anti-detection complexity, no LinkedIn account risk. A real end-to-end run here (ingest → filter → queue → prepare → submit → log → notify) proves the full pipeline before browser work begins.
**Delivers:** email_apply.py adapter (smtplib with PDF attachment), PDF generation from resume template, Telegram notification dispatcher (python-telegram-bot), full application log entry on submission, positive confirmation pattern (sent receipt). First live end-to-end run with Stefano reviewing results.
**Addresses:** Email application dispatch (P2), Telegram notification (P1), application log (P1).
**Avoids:** Pitfall 5 (confirmation-required pattern established before browser work), Pitfall 6 (notification system validated before unsupervised runs).
**Research flag:** Standard patterns — skip research-phase. smtplib and python-telegram-bot have extensive official documentation.

### Phase 6: LinkedIn Easy Apply with Anti-Detection
**Rationale:** The highest-complexity, highest-risk phase. Must come after all upstream components are proven. Camoufox, persistent browser context, challenge detection, and rate limiting must all be validated before any live LinkedIn run. A botched LinkedIn session means restriction of Stefano's real professional account.
**Delivers:** browser_session.py (persistent Camoufox context, stored user data directory on disk), linkedin_ea.py adapter (multi-step Easy Apply modal filling, file upload, screening question completion), challenge detection layer (CAPTCHA presence, "unusual activity" pattern, logged-out page detection with Telegram alert and automation pause), rate limiter (15-20/day hard cap, log-normal distributed timing across 6-8 hour window, weekend breaks), non-application browsing mixed into sessions, bot-detection clean result required on bot.sannysoft.com before live run.
**Addresses:** LinkedIn Easy Apply dispatch (P1), anti-detection layer (P1 dependency).
**Avoids:** Pitfall 1 (LinkedIn account ban — Camoufox + persistent profile + conservative rate limits + challenge detection), Pitfall 7 (rate limit triggering — 15-20/day cap with non-uniform timing), Pitfall 6 (challenge detection + heartbeat + max runtime enforcement).
**Research flag:** Needs research-phase. This is the highest-uncertainty phase. Anti-detection specifics are fast-moving (LinkedIn updated fingerprinting Q1 2026 — verify Camoufox 0.4.x is still the recommended approach at planning time). Residential proxy decision must be made before implementation begins.

### Phase 7: Kalibrr, Additional Sources, and Outcome Tracking
**Rationale:** Add additional sources only after the LinkedIn loop is proven stable. Kalibrr is the second-highest priority source; additional board scrapers and outcome tracking complete the system.
**Delivers:** kalibrr_scraper.py (httpx + BeautifulSoup4, APScheduler cron), kalibrr.py adapter (platform-native application), generic_form.py adapter (browser-use agent for company career pages), outcome tracking (Gmail inbox parsing for rejections and interview invites, log entry updates), 30-day re-application lookback for company+role combinations.
**Addresses:** Kalibrr scraper + native dispatch (P2), full form application dispatch (P2), outcome tracking (P2).
**Avoids:** Pitfall 8 cross-referencing (Kalibrr scraper and Gmail parser dedup cross-validate each other), Pitfall 5 extended to generic form confirmation verification.
**Research flag:** Needs research-phase. Kalibrr's current application form structure must be inspected (no public API documented; may require Playwright for JS-rendered form flows). Generic form adapter complexity depends on which ATS vendors (Greenhouse, Lever, Workday) are encountered in target markets.

### Phase Ordering Rationale

- **Data layer first:** The schema is the contract. Every downstream component depends on it. Building any ingestion or application component before the schema is fixed guarantees migration pain.
- **Ingestion before filter, filter before queue, queue before application:** This is the explicit dependency chain documented in ARCHITECTURE.md. Each layer can only be tested once its upstream is operational.
- **Email dispatch before browser dispatch:** The email adapter proves the full pipeline at zero LinkedIn account risk. Bugs in eligibility filtering, AI generation, or logging surface here where they are cheap to fix.
- **LinkedIn last among submission channels:** The highest-risk component goes last, after all upstream logic is proven. A bad eligibility filter caught in Phase 3 is a config edit; the same bug caught during live LinkedIn automation is potential ATS blacklisting and account restriction.
- **One source before many sources:** Kalibrr and additional sources in Phase 7 only after the LinkedIn loop is stable. Every competitor tool that failed did so because it tried to cover too many sources before the core was solid.

### Research Flags

Phases needing deeper research during planning:
- **Phase 2:** Gmail Pub/Sub GCP setup; LinkedIn email HTML structure currency check
- **Phase 4:** Claude prompt engineering for specificity-forcing structure; quality gate design
- **Phase 6:** Camoufox 0.4.x persistent context configuration; residential proxy decision; LinkedIn fingerprinting status as of planning date — this is the most time-sensitive research flag
- **Phase 7:** Kalibrr current application form structure; ATS vendor quirks (Greenhouse, Lever, Workday) in target job markets

Phases with standard patterns (skip research-phase):
- **Phase 1:** SQLite + SQLAlchemy 2.0 + Pydantic — textbook implementation
- **Phase 3:** Pure Python eligibility filter business logic — no external integrations
- **Phase 5:** smtplib + python-telegram-bot — extensive official documentation

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Core stack (Python, LangGraph, SQLite, Gmail API, Claude API, Telegram) is HIGH from official docs and production validation. Camoufox is HIGH for current anti-detection capability but MEDIUM for long-term maintenance (single-developer project). Anti-detection specifics are fast-moving — any research finding here can become stale within months. |
| Features | HIGH | Grounded in direct competitor analysis (LazyApply TrustPilot reviews, AIHawk GitHub source inspection, LoopCV/JobCopilot documentation), survey data (Resume Now 62% AI rejection, Jobscan 3x rejection rate, TopResume 600 hiring managers), and LinkedIn official documentation. Feature gaps and anti-features are well-evidenced. |
| Architecture | HIGH (core) / MEDIUM (browser specifics) | SQLite queue pattern, Strategy adapter pattern, persistent browser context are production-validated with multiple confirming sources. Browser automation anti-detection specifics are MEDIUM — configurations can become stale within months as platforms update. |
| Pitfalls | HIGH (LinkedIn, duplicates, filtering) / MEDIUM (Kalibrr) | LinkedIn pitfalls grounded in official ToS, LinkedIn Help documentation, and multiple behavioral analysis sources. Kalibrr rate limits and detection behavior have no documented sources — treat as empirically unknown until observed in production. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Kalibrr rate limits and bot detection:** No public documentation found. Approach empirically: start at 10 applications/day, observe for 2 weeks, adjust based on response patterns. Log all HTTP responses from Kalibrr for anomaly detection.
- **Camoufox maintenance trajectory:** Single-developer project (daijro). If it stalls, the fallback is Patchright (Chromium-based stealth). Confirm active maintenance at planning time for Phase 6 — check commit recency and open issues.
- **LinkedIn email HTML structure currency:** The email parser design depends on LinkedIn's current alert email structure, which changes without notice. Spot-check a live LinkedIn alert email before finalizing Phase 2 design.
- **Home IP vs. residential proxy decision:** Whether Stefano's home IP is sufficient or a residential proxy (Bright Data, Oxylabs) is required depends on whether automation tools have previously run from that IP address. Decide this before Phase 6 begins.
- **LangGraph vs. plain Python tradeoff:** Plain Python + asyncio is an acceptable MVP alternative if graph complexity feels premature. The recommendation is LangGraph for crash recovery via checkpointing. Re-evaluate this trade-off at Phase 3 if the pipeline is simpler than expected.

## Sources

### Primary (HIGH confidence)
- LinkedIn Help Official Documentation — ToS Section 8.2, Easy Apply daily limits, prohibited software list
- Google Developers — Gmail API push notifications (Pub/Sub), official watch method and scope requirements
- Camoufox GitHub (daijro/camoufox) — anti-detection Firefox fork, PyPI releases, capability claims
- JobSpy GitHub (speedyapply/JobSpy) — supported boards, v1.1.82, normalization behavior
- LangGraph documentation — 1.0 stable release Oct 2025, SQLite checkpointer built-in

### Secondary (MEDIUM confidence)
- Scrapfly Blog — playwright-stealth abandonment late 2024, Camoufox recommendation as replacement
- Growleads / GetSales — LinkedIn 23% restriction rate (self-reported by automation vendors)
- DEV Community — SQLite as AI agent database, production pattern validation
- AIHawk (AGPL OSS, github.com/AIHawk-FOSS) — GitHub README and config YAML inspection for competitor feature analysis
- Apify Blog — LangGraph agents in production; LinkedIn Easy Apply bot persistent context approach

### Tertiary (MEDIUM-LOW confidence)
- TrustPilot LazyApply reviews (2.4/5, 56% 1-star) — competitor failure mode evidence
- Resume Now survey (62% employer rejection of AI resumes without personalization) — AI cover letter risk quantification
- Jobscan survey (3x higher rejection rates for automated-tool users) — volume vs. quality trade-off evidence
- LinkedIn 340% detection rate increase 2023-2025 (Dux-Soup research via ScaliQ) — unverified third-party claim, directionally consistent with other sources
- Kalibrr Terms of Use — reviewed; no automation prohibition found, but no rate limit documentation either

---
*Research completed: 2026-05-26*
*Ready for roadmap: yes*
