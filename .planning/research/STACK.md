# Stack Research

**Domain:** Autonomous job application agent (email parsing, job scraping, AI generation, browser automation, notifications)
**Researched:** 2026-05-26
**Confidence:** MEDIUM-HIGH (browser automation anti-detection is fast-moving; LinkedIn risk is structural)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11+ | Runtime | asyncio maturity, all scraping/AI/automation libraries have first-class Python support; 3.11 gives significant async speed improvements over 3.10 |
| LangGraph | 0.5.x (1.0 stable) | Workflow orchestration / agentic state machine | Reached 1.0 stable in Oct 2025. Native stateful graphs — each job application is a persistent state object that survives crashes. Checkpointing via SQLite means no Redis/Celery needed. Code-first (no visual no-code lock-in). Direct support for interrupt/resume (human-in-the-loop optional). Better than n8n for this use case: n8n is wiring APIs; LangGraph is controlling an agent that makes decisions. |
| Camoufox | 0.4.x | Browser automation with stealth | Firefox fork patched at C++ level — removes headless signals at the binary level, not with JS patches. Only tool achieving 0% detection score on major fingerprinting test suites in 2025-2026. Drop-in Playwright-compatible async API (`camoufox.async_api`). Required for LinkedIn Easy Apply and platform-native flows. |
| Gmail API | v1 | Email ingestion (LinkedIn job alert digests) | REST-based, supports `users.watch` for push notifications (no polling loop). OAuth 2.0 with `gmail.readonly` scope. Avoids MIME parsing hell of raw IMAP. Official Google library: `google-api-python-client`. Setup takes 1-4 hours but is the right call for a 24/7 agent that must not miss messages. |
| Claude API (Anthropic) | claude-sonnet-4-5 or haiku-3.5 | Cover letter generation, screening Q&A, job-resume matching | Sonnet-class models are best at structured document generation with instruction-following. Use `claude-haiku-3-5` for cheap filtering/matching passes (job eligibility check), `claude-sonnet-4-5` for actual cover letter generation. Anthropic API is simpler than OpenAI for structured outputs. At ~$3/$15 per 1M tokens (Sonnet), cost per application is well under $0.05. |
| SQLite + aiosqlite | SQLite 3.47 (Python 3.13 bundled) / aiosqlite 0.20+ | Audit log, job state, resume library index | Zero infrastructure — single file database. WAL mode enables concurrent async writes without locking. Sufficient for solo-user agent tracking hundreds of applications. SQLAlchemy 2.0 async dialect (`sqlite+aiosqlite://`) for typed ORM access. Production-proven for AI agent state management at this scale. |
| APScheduler | 3.10+ | Scheduling (polling loops, retry queues) | In-process async scheduler — no Redis, no Celery, no separate worker process. Supports cron triggers, interval triggers, and job stores backed by SQLite. Right-sized for this workload: one user, ~10-50 applications/day. Celery is overkill and adds operational complexity. |
| python-telegram-bot | 21.x | Telegram notifications | Official community library, async (v20+), actively maintained, 3.28.x aiogram is equally valid but python-telegram-bot has cleaner docs for send-only notification use cases. Free API, zero per-message cost, instant delivery, no business verification. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| JobSpy (`python-jobspy`) | 1.1.82 | Scrape Indeed, LinkedIn, Glassdoor job listings | Phase 1 ingestion from supported boards. Built-in normalization to Pandas DataFrame. Rate-limited — use with residential proxies for LinkedIn. Does NOT cover Kalibrr (custom scraper needed). |
| BeautifulSoup4 + httpx | bs4 4.12+, httpx 0.27+ | Kalibrr scraper + any static HTML job boards | Kalibrr serves job listings as server-rendered HTML. httpx is async-native (unlike requests). Use for boards that don't need JavaScript execution. |
| google-auth + google-api-python-client | google-auth 2.x | Gmail API OAuth | Official Google auth flow. Store refresh token securely (not in git). |
| pydantic | 2.x | Eligibility profile config, job schema, application state | Config validation (`eligibility.yaml` parsed into Pydantic model). Type-safe state across the LangGraph graph nodes. |
| python-docx + PyMuPDF (fitz) | python-docx 1.1+, PyMuPDF 1.24+ | Resume template ingestion | Read `.docx` templates and extract structured content for AI matching. PyMuPDF for any PDF templates. |
| playwright | 1.44+ | Fallback browser automation (non-LinkedIn forms) | Used directly (without Camoufox stealth) for benign form-filling on low-risk company career pages. Camoufox wraps this library — keep as explicit dep. |
| tenacity | 8.x | Retry logic with exponential backoff | Wrap all external API calls (LLM, Gmail, Telegram, job boards). Prevents cascade failures on transient errors. |
| structlog | 24.x | Structured JSON logging | Machine-readable logs that integrate cleanly with the SQLite audit trail. Better than stdlib logging for agentic systems. |
| python-dotenv | 1.0+ | Environment variable management | API keys, OAuth tokens, Telegram bot token — never hardcoded. |
| Jinja2 | 3.1+ | Cover letter templating scaffold | Pre-structure the AI prompt with job-specific slots before sending to Claude. Keeps prompts consistent. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Dependency management + virtualenv | Faster than pip+venv, compatible with pyproject.toml. Use `uv sync` for reproducible installs. |
| pyproject.toml | Project config | Single file for deps, tool config (ruff, mypy). No setup.py. |
| ruff | Linting + formatting | Replaces black + flake8 + isort in one tool. |
| mypy | Type checking | Catch state schema mismatches before runtime. Critical for LangGraph typed state dicts. |
| pytest + pytest-asyncio | Testing | Async test support for all async graph nodes. |
| Docker | Container packaging for VPS deploy | Single `Dockerfile` wrapping the Python process. Use `--restart unless-stopped` for 24/7 uptime. |

---

## Installation

```bash
# Core agent
uv add langgraph camoufox playwright aiosqlite sqlalchemy \
       google-api-python-client google-auth-httplib2 google-auth-oauthlib \
       anthropic python-jobspy httpx beautifulsoup4 \
       apscheduler python-telegram-bot pydantic \
       python-docx PyMuPDF tenacity structlog python-dotenv jinja2

# Install Camoufox browser binary (Firefox-based)
camoufox fetch

# Install Playwright browser binaries (fallback)
playwright install chromium

# Dev
uv add --dev pytest pytest-asyncio ruff mypy
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Camoufox (Firefox stealth) | Patchright (Chromium stealth) | If a target platform explicitly requires Chrome fingerprint; Patchright patches Chromium at a shallower level than Camoufox patches Firefox — lower stealth ceiling but easier debugging |
| Camoufox | playwright-stealth (JS patches) | Never: playwright-stealth was abandoned in late 2024, doesn't handle Canvas/WebGL/AudioContext fingerprinting — major detection vectors in 2025 |
| LangGraph | n8n | If Stefano wants a drag-and-drop visual workflow instead of code. n8n is better for integrating off-the-shelf APIs quickly. Worse for stateful agent logic with conditional branching per job type. |
| LangGraph | Plain Python + asyncio tasks | Acceptable for MVP if graph complexity feels premature. Loses built-in checkpointing and crash recovery. |
| Gmail API | IMAP (imaplib) | If Gmail access is ever unavailable or account switches to non-Google mail. IMAP is universally supported but requires raw MIME parsing and polling. |
| Claude API | OpenAI GPT-4o | GPT-4o is equally capable; choose based on existing API key / credits. Both support structured JSON outputs for eligibility scoring. |
| SQLite + aiosqlite | PostgreSQL | If the agent ever scales to multiple users or requires multi-process concurrent writes from separate machines. PostgreSQL adds infrastructure overhead not warranted for single-user. |
| APScheduler | Celery + Redis | If job volume exceeds ~500/day or retry queues require distributed workers. Celery adds Redis dependency + separate worker process — overkill for one user. |
| python-telegram-bot | Twilio WhatsApp | WhatsApp Business API requires BSP approval, per-conversation cost ($0.01-$0.09), and Meta business verification. Telegram Bot API is free, instant, no approval. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Selenium | Outdated WebDriver protocol is the most-detected automation signal; slower than Playwright; ecosystem has moved on | Camoufox (Firefox) or Playwright (Chromium) |
| playwright-stealth (PyPI) | Maintenance abandoned late 2024; does not patch Canvas, WebGL, or AudioContext fingerprinting — the exact vectors LinkedIn and Cloudflare check in 2025 | Camoufox or Patchright |
| Puppeteer | Node.js only; switching language adds operational friction for a Python-native stack | Camoufox (equivalent stealth, Python-native) |
| n8n for core agent logic | No-code tools lose when agent needs conditional branching per job type, per platform, per form structure — visual graphs become unmaintainable at that complexity | LangGraph |
| WhatsApp Business API (Twilio) | Requires Meta business verification (weeks), BSP monthly fees, per-conversation cost; overkill for personal notification use | Telegram Bot API (python-telegram-bot) |
| Scrapy | Great for breadth-first link crawling at scale; wrong abstraction for structured form-filling and per-job decision trees | httpx + BeautifulSoup4 for static scraping; Camoufox for JS-heavy |
| requests (synchronous) | Blocks the event loop in an async agent; all I/O must be async for APScheduler + LangGraph to work correctly | httpx (async-native, same API surface) |
| Celery | Requires Redis broker + worker processes; operational overhead not justified for single-user, moderate-volume agent | APScheduler (in-process, SQLite-backed job store) |

---

## Stack Patterns by Variant

**If LinkedIn Easy Apply is the primary submission channel:**
- Camoufox is mandatory — not optional. LinkedIn's 2025 enforcement increased detection rates 340% for standard Playwright. Budget for residential proxy rotation (Bright Data or Oxylabs). Accept a ~23% restriction risk on the LinkedIn account and design the agent to pause on detection signals (rate limit headers, login walls).

**If Kalibrr is the primary submission channel:**
- Kalibrr uses React + Flask (Python backend). Job listings are server-rendered. httpx + BeautifulSoup4 handles listing scraping. Application forms may require Camoufox for JS-rendered form flows. No API documented publicly — treat as scrape-only.

**If cost is the dominant constraint:**
- Replace `claude-sonnet-4-5` with `claude-haiku-3-5` for cover letter generation. Quality drops modestly. Eliminates ~80% of API cost. At 50 applications/day, Sonnet still costs under $5/day total.

**If 24/7 uptime is required without a managed server:**
- Deploy Docker container to a $6-12/month VPS (DigitalOcean Droplet, Hetzner CX22). Use `docker run --restart unless-stopped`. APScheduler runs inside the container — no separate scheduler service needed. SQLite database is a volume-mounted file for persistence across container restarts.

**If email monitoring needs real-time (not polled):**
- Use Gmail API `users.watch` + Google Pub/Sub push notifications instead of polling `users.messages.list` on a cron. Requires a public HTTPS endpoint on the VPS (Caddy reverse proxy recommended).

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| langgraph 0.5.x | Python 3.11-3.13 | 1.0 stable since Oct 2025; SQLite checkpointer built-in |
| camoufox 0.4.x | playwright 1.44+ | Camoufox wraps Playwright's async API; pin both together |
| aiosqlite 0.20+ | SQLAlchemy 2.0 | Use `create_async_engine("sqlite+aiosqlite://...")` dialect |
| APScheduler 3.10+ | Python 3.11+ asyncio | Use `AsyncIOScheduler` with `SQLAlchemyJobStore` backed by SQLite |
| google-api-python-client 2.x | google-auth 2.x | Must match; install together. OAuth tokens require periodic refresh — store in encrypted file or env var |
| python-telegram-bot 21.x | Python 3.8+ | v20+ is async-native; v21 adds webhook support if needed |

---

## Sources

- [Playwright vs Puppeteer vs Selenium 2026 — Apify Blog](https://use-apify.com/blog/playwright-vs-puppeteer-vs-selenium-2026) — browser automation comparison
- [Playwright Stealth: Bypass Bot Detection — Scrapfly Blog](https://scrapfly.io/blog/posts/playwright-stealth-bypass-bot-detection) — stealth library status and Camoufox recommendation (HIGH confidence)
- [Camoufox GitHub](https://github.com/daijro/camoufox) — anti-detect Firefox fork, PyPI available
- [Camoufox PyPI](https://pypi.org/project/camoufox/) — latest release Jan 2025
- [Patchright — ZenRows](https://www.zenrows.com/blog/patchright) — Chromium alternative to Camoufox
- [LinkedIn Automation Ban Risk 2026 — Growleads](https://growleads.io/blog/linkedin-automation-ban-risk-2026-safe-use/) — 23% restriction rate data (MEDIUM confidence; self-reported)
- [LinkedIn Automation Safety Guide 2026 — GetSales](https://getsales.io/blog/linkedin-automation-safety-guide-2026/) — enforcement escalation
- [JobSpy GitHub — speedyapply/JobSpy](https://github.com/speedyapply/JobSpy) — supported boards, v1.1.82 (HIGH confidence)
- [LangGraph vs n8n — ZenML Blog](https://www.zenml.io/blog/langgraph-vs-n8n) — framework comparison
- [LangGraph Agents in Production — Apify](https://use-apify.com/blog/langgraph-agents-production) — stateful agent patterns
- [Email APIs for AI Agents — Nylas CLI](https://cli.nylas.com/guides/email-apis-for-ai-agents-compared) — Gmail API vs IMAP tradeoffs
- [Gmail API Push Notifications — Google Developers](https://developers.google.com/workspace/gmail/api/guides/push) — watch method, scope requirements (HIGH confidence, official)
- [Telegram Bot API vs WhatsApp — WATI](https://www.wati.io/en/blog/telegram-vs-whatsapp/) — cost and setup comparison
- [aiogram PyPI](https://pypi.org/project/aiogram/) — aiogram 3.28.2 (May 2026) alternative Telegram library
- [SQLite Is the Best Database for AI Agents — DEV Community](https://dev.to/nathanhamlett/sqlite-is-the-best-database-for-ai-agents-and-youre-overcomplicating-it-1a5g) — single-user agent DB rationale (MEDIUM confidence)
- [aiosqlite GitHub — omnilib/aiosqlite](https://github.com/omnilib/aiosqlite) — async SQLite bridge
- [AI API Pricing Comparison 2026 — IntuitionLabs](https://intuitionlabs.ai/articles/ai-api-pricing-comparison-grok-gemini-openai-claude) — Claude vs GPT-4o cost
- [APScheduler vs Celery — CronJobPro](https://cronjobpro.com/blog/python-cron-jobs) — scheduling comparison
- [Deploy 24/7 AI Agent on AWS EC2 — DEV Community](https://dev.to/aws-builders/deploy-your-own-247-ai-agent-on-aws-ec2-with-docker-tailscale-the-secure-way-53aa) — VPS deployment pattern

---
*Stack research for: Autonomous Job Application Agent*
*Researched: 2026-05-26*
