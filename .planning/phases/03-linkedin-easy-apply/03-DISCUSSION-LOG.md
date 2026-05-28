# Phase 3: LinkedIn Easy Apply - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-29
**Phase:** 3-LinkedIn Easy Apply
**Areas discussed:** Job sourcing for Easy Apply, Session & challenge handling, Proxy strategy

---

## Job sourcing for Easy Apply

| Option | Description | Selected |
|--------|-------------|----------|
| Optimistic — assume all LinkedIn URLs are Easy Apply | Tag all LinkedIn Gmail alert jobs as apply_type='linkedin_easy_apply'. Camoufox checks at runtime — if no Easy Apply button, skip and log as SKIPPED. | ✓ |
| Pre-check — visit each URL before queuing | After ingestion, a scraper visits the LinkedIn URL and checks for Easy Apply before setting apply_type. More accurate but adds latency and extra LinkedIn requests. | |

**User's choice:** Optimistic tagging
**Notes:** Simple, no extra scraping. Runtime skip on missing Easy Apply button is acceptable.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Update Gmail ingest to detect LinkedIn URLs | If extracted URL contains 'linkedin.com', set apply_type='linkedin_easy_apply'. Otherwise keep apply_type='email'. | ✓ |
| New ingest source — LinkedIn job board scraper | Separate scraper hitting LinkedIn job search directly. | |

**User's choice:** Update Gmail ingest
**Notes:** Minimal change to Phase 2 gmail_client.py. URL-based detection is sufficient.

---

## Session & challenge handling

| Option | Description | Selected |
|--------|-------------|----------|
| Persist session cookies | Log in once manually, save browser session/cookies to disk. Each run loads the saved session. | ✓ |
| Log in fresh each run | Camoufox enters credentials on every run. | |

**User's choice:** Persist session cookies
**Notes:** Standard approach for long-running automation. Manual re-login when cookies expire.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Pause + Telegram alert, wait for manual resolution | Stop run immediately, fire Telegram alert. Resume after Stefano resolves manually. | ✓ |
| Pause + Telegram alert, retry after cooldown | Auto-retry after N hours. | |

**User's choice:** Manual resolution only
**Notes:** Safest for account health. No auto-retry on LinkedIn challenges.

---

## Proxy strategy

| Option | Description | Selected |
|--------|-------------|----------|
| VPS IP, no proxy | Start on existing VPS IP. Add Smartproxy only if LinkedIn actually flags. | ✓ |
| Smartproxy residential from day one | $30/month residential proxy from the start. | |
| Home IP via WireGuard tunnel | Route VPS traffic through home internet. Free, residential IP. Adds WireGuard complexity. | |

**User's choice:** VPS IP, no proxy to start
**Notes:** User asked for research first. Research confirmed: at 15-20 applies/day with Camoufox fingerprinting, VPS IP is sufficient. Residential proxies become necessary at 50+/day or after actual flagging. Smartproxy (~$30/month) is the documented fallback.

---

## Claude's Discretion

- Form field coverage strategy (D-10, D-11) — standard fields list and unknown field handling defined by Claude based on LinkedIn Easy Apply common patterns
- Challenge detection signals (URL-based `/checkpoint/` or `/login` detection) — implementation detail
- Session file path (`data/linkedin_session.json`) — follows existing data directory convention

## Deferred Ideas

- Residential proxy (Smartproxy) — operational fallback, not Phase 3 build
- LinkedIn job board scraper — Phase 4 candidate
- Account warmup sequence — user judgment call, not automated
