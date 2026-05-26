# Architecture Research

**Domain:** Autonomous agentic job application pipeline
**Researched:** 2026-05-26
**Confidence:** HIGH (core patterns); MEDIUM (anti-detection specifics, browser-use internals)

---

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INGESTION LAYER                               │
├──────────────────┬───────────────────┬──────────────────────────────┤
│  Gmail Watcher   │  Kalibrr Scraper  │  Other Board Scrapers        │
│  (Pub/Sub push)  │  (APScheduler)    │  (APScheduler)               │
└────────┬─────────┴────────┬──────────┴────────────────┬─────────────┘
         │                  │                           │
         ▼                  ▼                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      NORMALISATION BUS                               │
│         Raw leads → canonical JobLead(url, title, company,           │
│                    salary, location, source, raw_html)               │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      ELIGIBILITY FILTER                              │
│  Config-driven: role_titles[], salary_min, location[], keywords[]   │
│  Hash-based dedup: skip if job_url already in jobs table            │
└──────────────┬──────────────────────────────────────────────────────┘
               │ eligible + not-seen
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    JOB QUEUE  (SQLite + queue table)                 │
│  status: QUEUED → PREPARING → APPLYING → SUBMITTED | FAILED         │
└──────────────┬──────────────────────────────────────────────────────┘
               │ worker picks next QUEUED row (SELECT ... FOR UPDATE)
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    APPLICATION PIPELINE                              │
│                                                                      │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐   │
│   │ Resume       │   │ AI Generator │   │ Apply Executor        │   │
│   │ Selector     │──▶│ Cover Letter │──▶│ (platform-specific    │   │
│   │ (embedding   │   │ + Answers    │   │  adapter)             │   │
│   │  similarity) │   │              │   │                        │   │
│   └──────────────┘   └──────────────┘   └──────────┬───────────┘   │
└──────────────────────────────────────────────────────┼──────────────┘
                                                       │
                    ┌──────────────────────────────────┤
                    │                                  │
                    ▼                                  ▼
         ┌──────────────────┐               ┌──────────────────┐
         │  Apply Adapters  │               │  Notification    │
         │  ─ LinkedIn EA   │               │  Dispatcher      │
         │  ─ Email SMTP    │               │  ─ Telegram      │
         │  ─ Kalibrr form  │               │  ─ WhatsApp      │
         │  ─ Generic form  │               └──────────────────┘
         └──────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      PERSISTENCE LAYER                               │
│  SQLite:  jobs | applications | resume_templates | eligibility_cfg  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

| Component | Owns | Typical Implementation |
|-----------|------|------------------------|
| **Gmail Watcher** | Detect new LinkedIn alert emails, parse job URLs and metadata from HTML digests | `google-api-python-client` + Gmail Pub/Sub push to local HTTP endpoint; fallback: IMAP polling with `imaplib` |
| **Board Scrapers** | Poll Kalibrr and other job boards on a schedule, extract job listings | APScheduler cron jobs; `httpx` + BeautifulSoup or Playwright for JS-heavy boards |
| **Normalisation Bus** | Convert every source's raw output into a canonical `JobLead` dataclass | Pure Python function called by each scraper before enqueuing |
| **Eligibility Filter** | Apply configurable hard rules; hash-deduplicate against `jobs` table | YAML/JSON config file; SHA-256 of job URL as stable dedup key |
| **Job Queue** | Serialise work; prevent duplicate applications; expose retry semantics | SQLite table with `status` column acting as a lightweight queue (WAL mode for concurrent reads) |
| **Resume Selector** | Rank Stefano's resume templates against a job description | Sentence-Transformers `all-MiniLM-L6-v2`; cosine similarity; top-1 selection |
| **AI Generator** | Produce tailored cover letter + screening question answers | LLM call (Claude API or local Ollama) with structured prompt including job description + selected resume content |
| **Apply Executor** | Dispatch to the correct platform adapter | Strategy pattern: inspects `job.source` or `job.apply_url` to pick adapter |
| **LinkedIn EA Adapter** | Fill Easy Apply modal (multi-step form, file upload) | `browser-use` (Python) over Playwright with stealth patches; persistent browser profile |
| **Email Adapter** | Send resume + cover letter to a recruiter address | `smtplib` / `boto3 SES`; PDF attachment generation from template |
| **Generic Form Adapter** | Fill arbitrary company career-site forms | `browser-use` agent with task prompt; fallback to structured Playwright script |
| **Kalibrr Adapter** | Submit via Kalibrr's platform native flow | Playwright or Kalibrr API if available |
| **Notification Dispatcher** | Send Telegram / WhatsApp message after submit | `python-telegram-bot`; Twilio WhatsApp API |
| **Persistence Layer** | Store all state durably | SQLite 3 with SQLAlchemy ORM; WAL journal mode |

---

## Job Lifecycle State Machine

Every job moves through exactly one path. States are stored in the `jobs.status` column.

```
                 ┌─────────────┐
  (scraped)      │  DISCOVERED │
  ──────────────▶│             │
                 └──────┬──────┘
                        │ eligibility filter
                  pass  │         │ fail
                        ▼         ▼
                 ┌──────────┐  ┌──────────┐
                 │  QUEUED  │  │ REJECTED │ (terminal)
                 └────┬─────┘  └──────────┘
                      │ worker picks up
                      ▼
                 ┌──────────────┐
                 │  PREPARING   │  (resume select + AI generation)
                 └──────┬───────┘
                        │ success
                        ▼
                 ┌──────────────┐
                 │  APPLYING    │  (browser/email action in progress)
                 └──────┬───────┘
              success   │         │ failure
                        ▼         ▼
                 ┌──────────┐  ┌──────────────────┐
                 │SUBMITTED │  │  FAILED           │
                 │(terminal)│  │  retry_count += 1 │
                 └──────────┘  └────────┬──────────┘
                                        │ retry_count < MAX_RETRIES
                                        ▼
                                   back to QUEUED
                                        │ retry_count >= MAX_RETRIES
                                        ▼
                                   ┌─────────────┐
                                   │ DEAD_LETTER │ (terminal, alert sent)
                                   └─────────────┘
```

**State transition rules:**
- Only one worker may hold a job in `APPLYING` at a time (row-level lock via SQLite `BEGIN IMMEDIATE`).
- Transitions are written atomically with the action result — never "optimistic" updates before the action completes.
- `SUBMITTED` triggers notification dispatch before the transaction commits (notification failure is non-blocking: logged, not a rollback cause).

---

## Recommended Project Structure

```
job-agent/
├── config/
│   ├── eligibility.yaml          # role titles, salary, location, keywords
│   └── templates/                # resume template files (PDF + YAML metadata)
├── src/
│   ├── ingestion/
│   │   ├── gmail_watcher.py      # Gmail Pub/Sub listener + email parser
│   │   ├── kalibrr_scraper.py    # Kalibrr polling scraper
│   │   ├── board_scrapers.py     # Indeed / other board scrapers
│   │   └── normaliser.py         # raw → JobLead canonical form
│   ├── filter/
│   │   ├── eligibility.py        # hard-rule filter + dedup logic
│   │   └── config_loader.py      # loads eligibility.yaml into typed config
│   ├── queue/
│   │   ├── models.py             # SQLAlchemy models: Job, Application, etc.
│   │   ├── worker.py             # main loop: picks QUEUED jobs, runs pipeline
│   │   └── db.py                 # SQLite engine setup, WAL mode, migrations
│   ├── preparation/
│   │   ├── resume_selector.py    # embedding similarity → best template
│   │   └── ai_generator.py       # cover letter + screening answer generation
│   ├── application/
│   │   ├── executor.py           # strategy dispatcher
│   │   ├── adapters/
│   │   │   ├── linkedin_ea.py    # LinkedIn Easy Apply adapter
│   │   │   ├── email_apply.py    # email submission adapter
│   │   │   ├── kalibrr.py        # Kalibrr platform adapter
│   │   │   └── generic_form.py   # generic browser-use form adapter
│   │   └── browser_session.py    # shared persistent Playwright context
│   ├── notification/
│   │   ├── telegram.py           # python-telegram-bot send wrapper
│   │   └── whatsapp.py           # Twilio WhatsApp send wrapper
│   └── scheduler.py              # APScheduler entry point, wires all crons
├── data/
│   └── jobs.db                   # SQLite database (gitignored)
├── tests/
│   ├── unit/
│   └── integration/
├── pyproject.toml
└── .env                          # secrets: API keys, Gmail credentials (gitignored)
```

### Structure Rationale

- **ingestion/**: All source adapters are isolated behind the same normaliser — adding a new board means adding one file and registering it in `scheduler.py`, nothing else changes.
- **filter/**: Eligibility logic is pure Python with no I/O dependencies. Config is YAML so Stefano can tune thresholds without touching code.
- **queue/**: The SQLite queue is the only shared mutable state in the system. Centralising it here enforces that all state transitions go through one place.
- **preparation/**: CPU/AI-bound work is clearly separated from I/O-bound browser work. Easy to parallelize or move to a separate process later.
- **application/adapters/**: The Strategy pattern — `executor.py` picks the right adapter at runtime. Adding a new platform = new adapter file, no changes to the pipeline.
- **browser_session.py**: A single persistent Playwright browser context is shared across all browser-based adapters in a single worker run. This preserves cookies, fingerprints, and session state across multiple applications without re-launching.

---

## Architectural Patterns

### Pattern 1: SQLite as Lightweight Queue + State Store

**What:** Use a single SQLite database for both job/application storage and as the work queue. The `jobs.status` column IS the queue. Workers use `SELECT ... WHERE status = 'QUEUED' LIMIT 1` inside a `BEGIN IMMEDIATE` transaction to claim work atomically.

**When to use:** Single-machine deployments, low concurrency (1-3 workers), when inspectability and zero infrastructure overhead matter more than throughput. This system applies ~50 jobs/day — SQLite handles this effortlessly with WAL mode.

**Trade-offs:** No distributed fanout (fine here — one machine), requires WAL mode to allow concurrent reads during writes, row-level locking is advisory (enforce via `BEGIN IMMEDIATE`). Massive simplification vs. Redis/BullMQ: no separate broker process, full SQL queries for observability.

```python
# Atomic job claim — prevents double-processing
with engine.begin() as conn:  # BEGIN IMMEDIATE in WAL mode
    row = conn.execute(
        text("SELECT id FROM jobs WHERE status='QUEUED' ORDER BY created_at LIMIT 1")
    ).fetchone()
    if row:
        conn.execute(
            text("UPDATE jobs SET status='PREPARING', claimed_at=:now WHERE id=:id"),
            {"now": datetime.utcnow(), "id": row.id}
        )
```

**Confidence:** HIGH — pattern validated by production agentic systems handling 400+ item pipelines.

---

### Pattern 2: Platform-Agnostic Adapter Strategy

**What:** The `ApplyExecutor` selects an adapter at runtime based on the job's `apply_type` field (set during normalisation). Each adapter implements a common `apply(job, materials) -> ApplyResult` interface.

**When to use:** Whenever you have multiple submission paths (Easy Apply, email, form, platform-native). Avoids a monolithic `if/elif` chain that becomes unmaintainable.

**Trade-offs:** Requires a clean interface contract upfront. Adapters can't share browser state implicitly — must be passed explicitly via `browser_session`. Worth the overhead: adding Seek, Glassdoor, or any new platform means one new adapter file.

```python
class ApplyAdapter(Protocol):
    def apply(self, job: Job, materials: ApplicationMaterials) -> ApplyResult: ...

ADAPTERS: dict[str, ApplyAdapter] = {
    "linkedin_easy_apply": LinkedInEasyApplyAdapter,
    "email":               EmailApplyAdapter,
    "kalibrr":             KalibrrAdapter,
    "generic_form":        GenericFormAdapter,
}

def execute(job: Job, materials: ApplicationMaterials) -> ApplyResult:
    adapter = ADAPTERS[job.apply_type]
    return adapter().apply(job, materials)
```

**Confidence:** HIGH — standard GoF Strategy pattern; well-suited to this use case.

---

### Pattern 3: Persistent Browser Context for Anti-Detection

**What:** Launch a single Playwright `browser.new_persistent_context(user_data_dir=...)` at startup. All browser-based adapters share this context across multiple applications in a session. The context is stored between runs (persistent user data directory on disk).

**When to use:** Any scenario where the target platform (LinkedIn) tracks fingerprints and session continuity. A fresh browser context on every application is a strong bot signal.

**Trade-offs:** Context corruption on crash requires clearing the user data dir and re-authenticating manually. Use `playwright-stealth` / `patchright` to patch the remaining detectable signals (navigator.webdriver, Canvas, WebGL). Headless mode may still trigger LinkedIn detection — non-headless with a virtual display (Xvfb on Linux) is safer.

**Confidence:** MEDIUM — Apify's LinkedIn Easy Apply bot validated this approach (replaced headless with Browserbase persistent context to eliminate detection). DIY equivalent is persistent context + residential proxy.

---

### Pattern 4: Polling Ingestion with Gmail Pub/Sub for Email

**What:** Two ingestion patterns run in parallel:
1. **Gmail** — "watch" the inbox via Gmail API + Google Cloud Pub/Sub. Gmail pushes a notification to a local HTTP endpoint when a new message arrives. The handler fetches and parses the email, then normalises it into a `JobLead`.
2. **Web scrapers** — APScheduler cron jobs poll Kalibrr and other boards every N minutes. No webhook available from these sources; polling is the only option.

**When to use:** Gmail's push approach cuts latency from minutes (IMAP polling) to seconds and avoids Gmail API quota exhaustion from constant polling. Web scrapers have no push alternative, so polling is correct.

**Trade-offs:** Gmail Pub/Sub requires a publicly reachable endpoint (ngrok in dev, a cloud VM or VPS in prod) for push delivery. Alternative: fall back to IMAP polling with `imaplib` — simpler but adds latency and quota risk.

**Confidence:** HIGH (Gmail Pub/Sub is the officially documented pattern from Google).

---

## Data Flow

### End-to-End Application Flow

```
[Scraper / Gmail Watcher fires]
         │
         ▼
   Normaliser → JobLead(url, title, company, salary, location, source, raw_html)
         │
         ▼
   Eligibility Filter
   ├── FAIL: write REJECTED row, stop
   └── PASS + not-seen: write QUEUED row to jobs table
         │
         ▼
   Worker loop (polls jobs WHERE status=QUEUED every 30s)
   ├── Claim row → status=PREPARING
   │
   ├── Resume Selector
   │     └── embed job description, cosine-rank resume templates, pick top-1
   │
   ├── AI Generator
   │     └── LLM call → cover_letter.md + answers.json
   │
   ├── Claim row → status=APPLYING
   │
   ├── Apply Executor → pick adapter by job.apply_type
   │     ├── LinkedIn EA: browser-use agent fills modal
   │     ├── Email: SMTP send with PDF attachments
   │     ├── Kalibrr: platform adapter
   │     └── Generic form: browser-use agent with form-fill task
   │
   ├── SUCCESS → write SUBMITTED row + application log
   │     └── Notification Dispatcher → Telegram / WhatsApp push
   │
   └── FAILURE → increment retry_count
         ├── retry_count < 3: set status=QUEUED (exponential backoff delay)
         └── retry_count >= 3: set status=DEAD_LETTER + alert
```

### Key Data Flows

1. **Deduplication:** SHA-256 hash of the canonical job URL is stored on first write. Subsequent scrapes of the same URL hit a unique index violation — caught and silently skipped.
2. **Resume selection:** Resume templates are pre-embedded on startup (or on template change). Job description is embedded at runtime. Cosine similarity is computed in-process with `sentence-transformers`. No vector DB needed at this scale (< 20 templates).
3. **Failure propagation:** Adapter failures set status=FAILED with a `last_error` JSON blob. The worker re-queues with a `next_attempt_at` timestamp (exponential backoff: 5min, 15min, 45min). Dead-letter jobs trigger a Telegram alert distinct from the submission success message.

---

## Data Model

### Core Tables

```sql
-- Every job lead seen from any source
CREATE TABLE jobs (
    id            TEXT PRIMARY KEY,          -- UUID
    url           TEXT UNIQUE NOT NULL,      -- canonical apply URL
    url_hash      TEXT UNIQUE NOT NULL,      -- SHA-256 of url (fast dedup)
    title         TEXT NOT NULL,
    company       TEXT NOT NULL,
    salary_min    INTEGER,                   -- NULL if unknown
    salary_max    INTEGER,
    location      TEXT,
    source        TEXT NOT NULL,             -- 'linkedin_email'|'kalibrr'|'indeed'
    apply_type    TEXT NOT NULL,             -- 'linkedin_easy_apply'|'email'|'kalibrr'|'generic_form'
    raw_html      TEXT,                      -- original scrape for debugging
    status        TEXT NOT NULL DEFAULT 'QUEUED',
    retry_count   INTEGER NOT NULL DEFAULT 0,
    next_attempt_at DATETIME,
    claimed_at    DATETIME,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One row per completed (or attempted) application
CREATE TABLE applications (
    id              TEXT PRIMARY KEY,        -- UUID
    job_id          TEXT NOT NULL REFERENCES jobs(id),
    resume_template TEXT NOT NULL,           -- filename of selected template
    cover_letter    TEXT NOT NULL,           -- generated cover letter text
    screening_answers TEXT,                  -- JSON blob of Q&A pairs
    submitted_at    DATETIME,
    error_log       TEXT,                    -- JSON blob on failure
    notified_at     DATETIME
);

-- Stefano's resume templates (metadata only; files live in config/templates/)
CREATE TABLE resume_templates (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    label       TEXT NOT NULL,              -- e.g. 'product-manager', 'tech-lead'
    embedding   BLOB,                       -- serialised float32 numpy array
    updated_at  DATETIME NOT NULL
);

-- Eligibility config snapshot (audit trail of config changes)
CREATE TABLE eligibility_config (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    config_json TEXT NOT NULL,              -- full YAML->JSON snapshot
    applied_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Gmail API | OAuth2 + `google-api-python-client`; Pub/Sub push for new-mail events | Requires GCP project + Pub/Sub topic. Fallback: IMAP polling |
| LinkedIn | Playwright (browser-use) with persistent context + stealth | No official API. Anti-bot detection is the primary risk. Residential proxy recommended |
| Kalibrr | `httpx` scraper or platform API if publicly available | Check for API before scraping; scrape as fallback |
| Claude / OpenAI API | HTTP client (`anthropic` or `openai` SDK) for cover letter + answer generation | Async calls recommended to not block the worker during generation |
| Telegram | `python-telegram-bot` v20+ async send | Bot token + chat ID stored in `.env`. Fire-and-forget after SUBMITTED |
| WhatsApp | Twilio WhatsApp API or WhatsApp Business API | Twilio is easiest for personal use; needs approved message template |
| Google Cloud Pub/Sub | `google-cloud-pubsub` subscriber for Gmail push notifications | Local dev: `ngrok` tunnel; prod: static endpoint on VPS |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Ingestion → Queue | Direct function call → `db.insert_job_if_new()` | Scrapers run in-process; no inter-process messaging needed at this scale |
| Queue → Pipeline | SQLite row claim in worker loop | Synchronous within single process; can be moved to subprocess if browser automation needs isolation |
| Pipeline → Adapters | Synchronous function call with shared `BrowserSession` object | Browser session is NOT thread-safe; single-threaded worker or process-per-worker required |
| Pipeline → Notification | Async fire-and-forget after SUBMITTED write | Notification failure must not roll back application status |
| Config → Filter | YAML file loaded at startup; hot-reload via file watch optional | First version: restart to reload config |

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1–50 apps/day (MVP) | Single process, SQLite, one browser session, APScheduler in-process. Zero infrastructure overhead. |
| 50–200 apps/day | Separate scraper process from worker process. WAL mode SQLite handles concurrent readers fine. Add a second worker process for non-browser adapters (email). |
| 200–500 apps/day | Move job queue to Redis + Celery. Split browser workers (LinkedIn) from non-browser workers (email). Rate limit per platform becomes the constraint, not the queue. |
| 500+ apps/day | Not a real-world target for a personal job agent. If repurposed commercially: full Redis + Celery + Kubernetes, multiple residential proxy pools, per-user browser contexts. |

### Scaling Priorities

1. **First bottleneck: anti-bot rate limits.** LinkedIn will throttle or shadow-ban repeated Easy Apply submissions from the same account/IP. Solve with pacing (min 2–5 min between applications per platform) and residential proxy rotation before worrying about throughput.
2. **Second bottleneck: LLM API latency.** Cover letter generation is the slowest step (~3–8s per call). If queue depth grows, batch or parallelize AI generation separately from browser application.

---

## Anti-Patterns

### Anti-Pattern 1: Applying Immediately on Discovery

**What people do:** Scrape a job, generate a cover letter, and attempt to apply all in one synchronous call within the scraper.

**Why it's wrong:** Any failure (network blip, LLM timeout, bot detection) loses the job entirely. No retry path. No deduplication. Duplicate applications if the scraper runs twice.

**Do this instead:** Always write to the queue first, apply second. The queue is the source of truth. Discovery and application are separate concerns on separate clocks.

---

### Anti-Pattern 2: Fresh Browser Context Per Application

**What people do:** Launch a new headless browser instance for every application to "start clean."

**Why it's wrong:** Platforms like LinkedIn treat a fresh fingerprint on every request as a strong bot signal. Real users have consistent cookies, session history, and browser fingerprints over days and weeks.

**Do this instead:** Maintain a persistent browser context across an entire session. Reuse it for all applications in a run. Store the user data directory between runs. Manually log in once; the session persists.

---

### Anti-Pattern 3: Blocking the Worker on Notification

**What people do:** Call the Telegram/WhatsApp API synchronously and make SUBMITTED status conditional on notification success.

**Why it's wrong:** Notification APIs fail transiently. A failed notification should not mark a real application as un-submitted.

**Do this instead:** Write `status=SUBMITTED` first (committed). Then send the notification. If it fails, log the failure and optionally retry the notification separately. The application row is never rolled back due to a notification failure.

---

### Anti-Pattern 4: Hardcoding Eligibility Rules in Code

**What people do:** Write `if "Senior" in title and salary > 80000` directly in application code.

**Why it's wrong:** Stefano needs to tune these constantly. Code changes require deploys and risk regressions in unrelated code.

**Do this instead:** Eligibility config lives in `config/eligibility.yaml` — a structured file with typed fields. The filter reads from this file at startup. Changing criteria = editing YAML + restart. No code changes.

---

## Build Order Implications

The architecture has clear dependency layers that dictate implementation order:

```
Phase 1 (Foundation):
  db.py + models.py + eligibility.yaml loader
  → Nothing else can be built without the schema and config

Phase 2 (Ingestion):
  normaliser.py + one scraper (Gmail or Kalibrr)
  → Can now populate the jobs table and verify dedup

Phase 3 (Filter + Queue):
  eligibility.py + worker.py (skeleton — just claims and logs)
  → End-to-end flow visible: discover → filter → queue → claimed

Phase 4 (Preparation):
  resume_selector.py + ai_generator.py
  → Cover letter generation works; can be tested without browser

Phase 5 (Application — Email first):
  email_apply.py adapter
  → First real applications submitted; no browser risk yet

Phase 6 (Application — Browser):
  browser_session.py + linkedin_ea.py + generic_form.py
  → Browser automation added incrementally; anti-detection tuning happens here

Phase 7 (Notification + Remaining scrapers):
  telegram.py + whatsapp.py + remaining board scrapers
  → Full system operational

Dependency rule: Never build a downstream component before its upstream is tested.
The queue is the interface between ingestion and application — it is Phase 1, not Phase 3.
```

---

## Sources

- [Event-Driven Architecture for AI Agents — Confluent](https://www.confluent.io/blog/autonomous-agentic-event-driven-systems-architecture/)
- [SQLite Is the Best Database for AI Agents — DEV Community](https://dev.to/nathanhamlett/sqlite-is-the-best-database-for-ai-agents-and-youre-overcomplicating-it-1a5g)
- [Building a Durable Execution Engine With SQLite — Gunnar Morling](https://www.morling.dev/blog/building-durable-execution-engine-with-sqlite/)
- [Why I Built a Job Queue With SQLite Instead of Redis — DEV Community](https://dev.to/d_security/why-i-built-a-job-queue-with-sqlite-instead-of-redis-and-what-i-learned-4f05)
- [BullMQ Job Deduplication — OneUptime](https://oneuptime.com/blog/post/2026-01-21-bullmq-job-deduplication/view)
- [Deduplication in Distributed Systems — Architecture Weekly](https://www.architecture-weekly.com/p/deduplication-in-distributed-systems)
- [LinkedIn Easy Apply Bot — Apify (Browserbase persistent context approach)](https://apify.com/sunny_spade/linkedin-easy-apply-bot)
- [Playwright Stealth Mode 2026 — DEV Community](https://dev.to/vhub_systems_ed5641f65d59/playwright-stealth-mode-in-2026-the-7-patches-that-actually-matter-46bp)
- [browser-use GitHub](https://github.com/browser-use/browser-use)
- [AI Agent-Driven Browser Automation — AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/ai-agent-driven-browser-automation-for-enterprise-workflow-management/)
- [Gmail API Push Notifications — Google for Developers](https://developers.google.com/workspace/gmail/api/guides/push)
- [Building a Real-Time Gmail Processing Pipeline with Pub/Sub — SmythOS](https://smythos.com/developers/agent-integrations/building-a-real-time-gmail-processing-pipeline-with-pub-sub-webhooks/)
- [python-telegram-bot Architecture — GitHub Wiki](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Architecture)
- [Scaling Agentic Workflows with Redis and Celery — Medium](https://medium.com/@nimetha.21/scaling-agentic-workflows-with-redis-and-celery-efficiently-managing-complexity-in-modern-450b3493fc23)
- [Web Scraping Error Handling: Retries, Backoff — Rayobyte](https://rayobyte.com/blog/retries-backoff-failure-handling-web-scraping)
- [Sentence Transformers for Resume–Job Matching — Milvus](https://milvus.io/ai-quick-reference/how-can-sentence-transformers-support-an-ai-system-that-matches-resumes-to-job-descriptions-by-measuring-semantic-similarity)
- [APScheduler vs Celery Beat — Leapcell](https://leapcell.io/blog/scheduling-tasks-in-python-apscheduler-vs-celery-beat)

---

*Architecture research for: Autonomous Job Application Agent*
*Researched: 2026-05-26*
