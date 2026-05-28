# Phase 3: LinkedIn Easy Apply — Research

**Researched:** 2026-05-29
**Domain:** Camoufox browser automation, LinkedIn Easy Apply modal, n8n orchestration with daily cap, FastAPI integration
**Confidence:** MEDIUM-HIGH (Camoufox async API: HIGH via official docs; LinkedIn DOM selectors: MEDIUM via open-source bots; n8n cap patterns: HIGH via official n8n docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Optimistic tagging — all LinkedIn URLs tagged `apply_type='linkedin_easy_apply'`. Camoufox checks at runtime whether Easy Apply button is present; if not, log as SKIPPED.
- **D-02:** Phase 3 updates gmail ingest logic: if extracted job URL contains `linkedin.com`, set `apply_type='linkedin_easy_apply'` instead of `'email'`.
- **D-03:** No LinkedIn job board scraper added in this phase — job supply from Gmail alert digests only.
- **D-04:** Persist session cookies to disk via `data/linkedin_session.json`. Log in manually once, save Camoufox session. Each run loads saved session.
- **D-05:** On cookie expiry, stop run, fire Telegram alert: "LinkedIn session expired — manual re-login required." No auto-resume.
- **D-06:** Challenge detection (CAPTCHA, "unusual activity", 2FA): stop immediately, Telegram alert with challenge type, halt. No automatic retry. Stefano re-enables workflow in n8n after manual resolution.
- **D-07:** VPS IP only — no proxy in Phase 3. Proxy is operational fallback, not part of the build.
- **D-08:** n8n → FastAPI pattern identical to Phase 2. n8n calls `POST /apply/linkedin-easy-apply` with `job_id`. FastAPI runs Camoufox, returns result.
- **D-09:** Daily cap: n8n workflow tracks submission count for current day and stops triggering once cap (15-20) is reached. Timing randomized within configurable window (09:00–17:00 local).
- **D-10:** Standard fields: name, email, phone, resume upload, cover letter, work authorization (yes/no), LinkedIn profile URL, years of experience. Screening questions via existing `/application/generate-screening-answers`.
- **D-11:** Unknown/unrecognized fields: log the field label, skip job, write SKIPPED with reason `'unknown_form_field: {label}'`, fire Telegram alert.

### Claude's Discretion

No discretion areas specified — all decisions locked.

### Deferred Ideas (OUT OF SCOPE)

- Residential proxy (Smartproxy) — add placeholder to `.env.example`
- LinkedIn job board scraper — Phase 4 candidate
- Account warmup sequence — not automated
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| APPLY-01 | System submits applications via LinkedIn Easy Apply (max 15-20/day with randomized timing to avoid detection) | Camoufox 0.4.x async API confirmed on PyPI; DOM selectors sourced from active open-source bots; daily cap pattern documented via n8n Code+Wait nodes; challenge detection via URL pattern check |
</phase_requirements>

---

## Summary

Phase 3 adds a Camoufox-powered LinkedIn Easy Apply submission path to the existing n8n → FastAPI stack. The core technical components are: (1) a new `src/browser/linkedin_applier.py` module that owns all Camoufox interaction, (2) a new FastAPI route `POST /apply/linkedin-easy-apply` following the exact same pattern as the existing `/application/` endpoints, (3) a new n8n workflow `linkedin-easy-apply.json` with a daily cap counter + randomized Wait node timing, and (4) a session regeneration script `scripts/linkedin_session_save.py` that a human runs once to produce `data/linkedin_session.json`.

The main technical risks are: LinkedIn DOM selector drift (LinkedIn redesigns their job page UI with no notice — the selectors researched here are from active bots updated as recently as 2025 but must be validated against a live session before first production run), and Camoufox session persistence (the `persistent_context=True` + `user_data_dir` pattern is the most reliable approach; the Playwright `storage_state` JSON approach has known issues with `__Host-` prefixed cookies specific to LinkedIn).

Docker integration requires `headless="virtual"` (Camoufox's built-in Xvfb mode) and `apt-get install xvfb` in `Dockerfile.api`. No separate display service needed — Camoufox launches Xvfb internally when `headless="virtual"` is passed.

**Primary recommendation:** Use `AsyncCamoufox(headless="virtual", persistent_context=True, user_data_dir="/data/linkedin_profile")` for the automation session. Store the profile dir in the same `/data/` Docker volume that holds `jobs.db`. The `data/linkedin_session.json` reference in CONTEXT.md becomes the profile directory path rather than a single JSON file — this is more reliable for LinkedIn's `__Host-` cookies.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| LinkedIn Easy Apply form navigation | API / Backend (FastAPI service, Camoufox) | — | Browser automation runs inside the Docker container alongside FastAPI; n8n cannot run Camoufox directly |
| Daily cap enforcement | API / Backend (n8n Code node + AgentConfig counter) | — | n8n controls orchestration timing; FastAPI provides the counter endpoint |
| Session persistence | API / Backend (Docker volume `/data/`) | — | Cookie/profile dir lives in the same volume as jobs.db |
| Challenge detection + alerting | API / Backend (FastAPI → Telegram) | — | FastAPI detects the challenge condition and raises it; n8n triggers the Telegram node on error output |
| `apply_type` tagging (gmail ingest) | API / Backend (`src/api/routes/gmail.py` or `gmail_client.py`) | — | Small code change to existing ingest path |
| Screening question answers | API / Backend (`/application/generate-screening-answers`) | — | Already exists — Phase 3 calls it as an internal HTTP request |

---

## Standard Stack

### Core (new additions for Phase 3)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| camoufox | 0.4.11 [VERIFIED: PyPI registry] | Stealth Firefox browser automation | Only tool achieving 0% detection on major fingerprint test suites in 2025-2026; mandatory per CLAUDE.md |
| playwright | already in project via camoufox | Underlying automation API (Camoufox wraps it) | Camoufox exposes Playwright's async Firefox API |

Note: `camoufox` is not yet in `pyproject.toml` — it must be added. All other dependencies (fastapi, sqlalchemy, anthropic, structlog, tenacity) are already present.

**slopcheck status:** slopcheck was not available in this environment. `camoufox` confirmed on PyPI registry via `pip index versions camoufox` (0.4.11 latest, history back to 0.1.1). Package has an official GitHub at github.com/daijro/camoufox and documented homepage at camoufox.com. Treat as `[ASSUMED]` per protocol — planner should add a `checkpoint:human-verify` before install.

### Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| camoufox | PyPI | ~2 yrs | Not measured locally | github.com/daijro/camoufox | N/A (slopcheck unavailable) | [ASSUMED] — add checkpoint:human-verify before install |

*slopcheck was unavailable at research time. The package was confirmed via `pip index versions` (PyPI registry) and has an official GitHub and documentation site. Still tagged [ASSUMED] per the package name provenance rule — registry existence alone does not confer VERIFIED status.*

**Installation (additions to pyproject.toml):**
```bash
uv add camoufox
# Then install the Firefox binary (run inside Docker build or manually):
python -m camoufox fetch
# Or via the CLI:
camoufox fetch
```

**Dockerfile.api addition required:**
```dockerfile
RUN apt-get update && apt-get install -y xvfb --no-install-recommends && rm -rf /var/lib/apt/lists/*
```

---

## Architecture Patterns

### System Architecture Diagram

```
n8n Scheduler (daily cap check)
        |
        | POST /apply/linkedin-easy-apply {job_id}
        v
FastAPI route (apply/linkedin_apply.py)
        |
        |-- DB lookup: fetch Job by job_id
        |-- Check apply_type == 'linkedin_easy_apply'
        |-- Call write_application (status → APPLYING)
        |-- Instantiate LinkedInApplier (Camoufox session)
        |
        v
LinkedInApplier.apply(job)              [src/browser/linkedin_applier.py]
        |
        |-- Load session (user_data_dir or storage_state fallback)
        |-- page.goto(job.url)
        |-- Check URL for /checkpoint/, /login → raise ChallengeDetected
        |-- Find Easy Apply button (.jobs-apply-button--top-card)
        |-- If not found → raise NoEasyApplyButton (→ SKIPPED)
        |-- Click button → wait for modal (div.jobs-easy-apply-modal)
        |-- Loop: detect form fields, fill fields
        |     |-- Text inputs: .artdeco-text-input--input
        |     |-- Phone: input[type='tel'], input[name*='phone']
        |     |-- Dropdowns: select + option
        |     |-- Radios: input[type='radio'] in fieldset/div[role='radiogroup']
        |     |-- File upload (resume): input[type='file']
        |     |-- Screening Q&A: call /application/generate-screening-answers
        |     |-- Unknown field → raise UnknownFormField
        |-- Click Next (button[aria-label='Continue to next step'])
        |    or Review (button[aria-label='Review your application'])
        |    or Submit (button[aria-label='Submit application'])
        |-- Detect "application was sent" text → success
        |
        v
FastAPI route
        |-- mark_submitted (status → SUBMITTED)
        |-- Return {status: "submitted", application_id: ...}
        |
        v
n8n: Telegram notification node fires
     Daily counter incremented
```

### Recommended Project Structure

```
src/
├── api/
│   └── routes/
│       └── apply/
│           └── linkedin_apply.py     # new: POST /apply/linkedin-easy-apply
├── browser/
│   ├── __init__.py
│   └── linkedin_applier.py           # new: LinkedInApplier class
└── queue/
    └── models.py                     # existing: Job, Application, JobStatus

scripts/
└── linkedin_session_save.py          # new: one-time session persistence script

n8n/workflows/
└── linkedin-easy-apply.json          # new: n8n workflow with daily cap

data/
└── linkedin_profile/                 # new: Camoufox persistent profile dir
    └── (Camoufox/Firefox profile — managed by browser, not by code)
```

---

### Pattern 1: Camoufox Async Session with Persistent Context

**What:** Launch AsyncCamoufox with `persistent_context=True` and `user_data_dir` pointing to a directory inside the Docker-mounted `/data/` volume. Camoufox stores all cookies and localStorage in that directory across runs. After the human runs the session save script once (logging in manually), all subsequent automated runs reload the session automatically.

**When to use:** All automated LinkedIn apply runs after initial manual login.

**Source:** [CITED: camoufox.com/python/usage/]

```python
# src/browser/linkedin_applier.py
from camoufox.async_api import AsyncCamoufox

async def run_apply(job_url: str, user_data_dir: str) -> None:
    async with AsyncCamoufox(
        headless="virtual",          # Xvfb on Linux/Docker — not pure headless
        persistent_context=True,
        user_data_dir=user_data_dir, # e.g. /data/linkedin_profile
        humanize=True,               # human-like mouse movement
        os="windows",                # spoof Windows OS fingerprint
    ) as context:
        page = await context.new_page()
        await page.goto(job_url)
        # ... modal navigation
```

**Note on session file naming:** CONTEXT.md references `data/linkedin_session.json`. The Playwright `storage_state` JSON approach has known issues with LinkedIn's `__Host-` prefixed cookies (unanswered bug report: github.com/daijro/camoufox/discussions/408). The `persistent_context + user_data_dir` directory approach is more reliable. The planner should use `data/linkedin_profile/` as the actual path and note the discrepancy from CONTEXT.md D-04. [ASSUMED: the directory approach is preferred over a JSON file based on community findings — user confirmation recommended before finalizing]

**Alternative — Playwright storage_state fallback (if persistent_context causes issues):**
```python
# Save after manual login (scripts/linkedin_session_save.py):
await page.context.storage_state(path="data/linkedin_session.json")

# Load in automated run:
async with AsyncCamoufox(headless="virtual", os="windows") as browser:
    context = await browser.new_context(
        storage_state="data/linkedin_session.json"
    )
    page = await context.new_page()
```
[ASSUMED: storage_state may fail for __Host- cookies — treat as fallback only]

---

### Pattern 2: Challenge and Session Expiry Detection

**What:** After every `page.goto()`, check the current URL and page title before proceeding. Three distinct failure states to detect and handle differently.

**Source:** [ASSUMED — based on community bot analysis and LinkedIn automation guides; specific URL strings are well-documented across multiple open-source bots]

```python
CHALLENGE_URL_PATTERNS = [
    "/checkpoint/",          # CAPTCHA / unusual activity page
    "/authwall/",            # unauthenticated wall
]
LOGIN_URL_PATTERNS = [
    "/login",
    "/uas/login",
    "/signin",
]

async def check_for_challenge(page) -> str | None:
    """Returns challenge type string, or None if clean."""
    url = page.url
    title = await page.title()

    for pattern in CHALLENGE_URL_PATTERNS:
        if pattern in url:
            return f"checkpoint: {url}"

    for pattern in LOGIN_URL_PATTERNS:
        if pattern in url:
            return "session_expired"

    # Also check page title for "unusual activity" text
    lower_title = title.lower()
    if "unusual activity" in lower_title or "security verification" in lower_title:
        return f"challenge_page_title: {title}"

    return None
```

---

### Pattern 3: LinkedIn Easy Apply Modal Navigation

**What:** After navigating to a LinkedIn job URL, detect the Easy Apply button, click it, then loop through modal pages filling form fields, clicking Next until Submit is available.

**Source:** [CITED: github.com/nicolomantini/LinkedIn-Easy-Apply-Bot/blob/master/easyapplybot.py] and [CITED: github.com/AmmarAR97/linkedin-job-automation/blob/main/utils/apply.py]

**Easy Apply button detection:**
```python
# Selector 1 — button with jobs-apply-button class (works on job detail pages)
EASY_APPLY_BTN = '//button[contains(@class, "jobs-apply-button")]'
# Selector 2 — specific ID on top card
EASY_APPLY_BTN_ID = ".jobs-apply-button--top-card #jobs-apply-button-id"

# Runtime check — if Easy Apply button not found, skip (D-01)
easy_apply = page.locator(EASY_APPLY_BTN_ID)
if await easy_apply.count() == 0:
    # No Easy Apply button — not an Easy Apply job
    raise NoEasyApplyButton("Easy Apply button not found")
await easy_apply.click()

# Wait for modal
await page.wait_for_selector("div.jobs-easy-apply-modal", timeout=10000)
```

**Modal navigation loop:**
```python
async def navigate_modal(page, resume_path: str, answers: dict) -> None:
    while True:
        # Fill visible form fields on current page
        await fill_form_fields(page, answers)

        # Detect which button to click
        submit_btn = page.locator("button[aria-label='Submit application']")
        review_btn = page.locator("button[aria-label='Review your application']")
        next_btn = page.locator("button[aria-label='Continue to next step']")

        if await submit_btn.is_visible():
            # Optionally uncheck "follow company" before submit
            follow_cb = page.locator("label[for='follow-company-checkbox']")
            if await follow_cb.is_visible():
                if await page.locator("#follow-company-checkbox").is_checked():
                    await follow_cb.click()
            await submit_btn.click()
            break
        elif await review_btn.is_visible():
            await review_btn.click()
        elif await next_btn.is_visible():
            await next_btn.click()
        else:
            raise ModalNavigationError("No Next/Review/Submit button found")

        await page.wait_for_load_state("networkidle", timeout=5000)
```

---

### Pattern 4: Form Field Detection and Filling

**What:** On each modal page, detect all input types and fill them from the known profile fields or AI-generated screening answers. Unknown fields trigger the SKIPPED path (D-11).

**Source:** [CITED: github.com/AmmarAR97/linkedin-job-automation/blob/main/utils/apply.py] for selectors; profile data from existing `profile.yaml` / `profile_config`.

```python
async def fill_form_fields(page, profile: dict, screening_answers: list[dict]) -> None:
    # --- Resume file upload ---
    file_inputs = page.locator("input[type='file']")
    for i in range(await file_inputs.count()):
        fi = file_inputs.nth(i)
        if await fi.is_visible():
            await fi.set_input_files(profile["resume_path"])

    # --- Phone number ---
    phone_selectors = [
        "input[type='tel']",
        "input[name*='phone']",
        "input[id*='phone']",
        "input[aria-label*='phone' i]",
    ]
    for sel in phone_selectors:
        el = page.locator(sel).first
        if await el.is_visible():
            await el.fill(profile["phone"])
            break

    # --- Text inputs (name, email, years of experience, LinkedIn URL, etc.) ---
    text_inputs = page.locator(".artdeco-text-input--input")
    for i in range(await text_inputs.count()):
        el = text_inputs.nth(i)
        label = await get_label_for(page, el)
        value = resolve_profile_field(label, profile, screening_answers)
        if value is None:
            raise UnknownFormField(f"unknown_form_field: {label}")
        if await el.is_enabled():
            await el.fill(value)

    # --- Radio buttons (work authorization yes/no) ---
    radio_groups = page.locator("fieldset, div[role='radiogroup']")
    for i in range(await radio_groups.count()):
        group = radio_groups.nth(i)
        legend = await group.locator("legend").text_content() or ""
        answer = resolve_yes_no(legend.strip(), profile)
        if answer is not None:
            radio = group.locator(f"input[type='radio'][value='{answer}']")
            if await radio.count() > 0:
                await radio.first.click()

    # --- Dropdowns ---
    selects = page.locator("select")
    for i in range(await selects.count()):
        sel_el = selects.nth(i)
        label = await get_label_for(page, sel_el)
        value = resolve_profile_field(label, profile, screening_answers)
        if value is not None:
            await sel_el.select_option(label=value)


async def get_label_for(page, element) -> str:
    """Get label text for a form element via aria-label, placeholder, or associated label."""
    aria = await element.get_attribute("aria-label")
    if aria:
        return aria.strip()
    placeholder = await element.get_attribute("placeholder")
    if placeholder:
        return placeholder.strip()
    el_id = await element.get_attribute("id")
    if el_id:
        label_el = page.locator(f"label[for='{el_id}']")
        if await label_el.count() > 0:
            return (await label_el.first.text_content() or "").strip()
    return ""
```

---

### Pattern 5: n8n Workflow — Daily Cap with Randomized Timing

**What:** n8n workflow runs on a short schedule (every few minutes). A Code node checks whether the daily cap is reached and whether the current time is within the configured window. A Wait node with a Code-node-generated random delay produces the 6-8 hour spread.

**Source:** [CITED: n8n.io community — random wait pattern] [CITED: n8n official docs — Schedule Trigger, Code node]

**Daily cap pattern — track in AgentConfig DB table OR n8n static data:**
Option A (recommended): Add a new FastAPI endpoint `GET /apply/daily-linkedin-count` that reads Application rows submitted today with `apply_platform='linkedin'`. n8n Code node calls this endpoint and gates submission on `count < cap`.

Option B (simpler): n8n Code node uses a `$workflow.staticData` counter reset at midnight. Less reliable across n8n restarts.

**Recommendation: Option A** — durable across restarts, consistent with existing DB patterns.

```javascript
// n8n Code node: "Check Daily Cap and Window"
const now = new Date();
const hour = now.getHours();

// Time window check
const windowStart = parseInt($env.LINKEDIN_APPLY_WINDOW_START || "9");
const windowEnd = parseInt($env.LINKEDIN_APPLY_WINDOW_END || "17");
if (hour < windowStart || hour >= windowEnd) {
  return [{ json: { proceed: false, reason: "outside_window" } }];
}

// Daily count check (from previous HTTP node calling /apply/daily-linkedin-count)
const dailyCount = $('Get Daily Count').first().json.count;
const cap = parseInt($env.LINKEDIN_DAILY_CAP || "17");
if (dailyCount >= cap) {
  return [{ json: { proceed: false, reason: "cap_reached" } }];
}

// Random inter-submission delay (seconds)
const minDelay = 60 * 8;   // 8 minutes minimum
const maxDelay = 60 * 25;  // 25 minutes maximum
const randomDelay = Math.floor(Math.random() * (maxDelay - minDelay + 1)) + minDelay;

return [{ json: { proceed: true, waitSeconds: randomDelay } }];
```

```javascript
// n8n Wait node expression (after Code node):
// "Resume After" type → "Time Amount" expression: {{ $json.waitSeconds }}
// "Time Unit": seconds
```

**n8n workflow node sequence:**
```
Schedule Trigger (every 5 min)
  → Get Daily Count [HTTP GET /apply/daily-linkedin-count]
  → Check Cap + Window [Code node]
  → If proceed == true
      → Get Next LinkedIn Job [HTTP GET /apply/queued-linkedin-jobs]
      → If jobs exist
          → Wait (random delay from Code node)
          → POST /apply/linkedin-easy-apply {job_id}
          → If success → Telegram notification
          → If error → Telegram challenge alert + stop (n8n error output)
```

---

### Pattern 6: FastAPI Endpoint — linkedin_apply.py

**What:** New route `POST /apply/linkedin-easy-apply` follows exact same structure as existing routes in `application.py`. Uses `async with session.begin()`, returns `{"status": ..., "job_id": ...}`. Errors map to specific HTTP status codes.

**Source:** [CITED: src/api/routes/application.py] (read directly in this session)

```python
# src/api/routes/apply/linkedin_apply.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.app import get_session, verify_api_key
from src.queue.models import Job, JobStatus
from src.browser.linkedin_applier import LinkedInApplier, ChallengeDetected, NoEasyApplyButton, UnknownFormField
from src.audit_log import AuditEvent, write_audit
import structlog, os

log = structlog.get_logger()
router = APIRouter()

@router.post("/linkedin-easy-apply", dependencies=[Depends(verify_api_key)])
async def linkedin_easy_apply(
    payload: LinkedInApplyIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict | JSONResponse:
    async with session.begin():
        result = await session.execute(select(Job).where(Job.id == payload.job_id))
        job = result.scalar_one_or_none()
        if job is None:
            return JSONResponse(status_code=404, content={"detail": "job_not_found"})
        if job.status != JobStatus.QUEUED:
            return JSONResponse(status_code=409, content={"detail": "job_not_queued"})

    user_data_dir = os.environ.get("LINKEDIN_PROFILE_DIR", "/data/linkedin_profile")
    resume_path = ...  # resolved from profile + resume selection

    applier = LinkedInApplier(user_data_dir=user_data_dir)
    try:
        result = await applier.apply(job, resume_path)
    except ChallengeDetected as e:
        # Stop automation, fire Telegram (n8n error output handles Telegram)
        log.error("linkedin_challenge", job_id=payload.job_id, challenge=str(e))
        return JSONResponse(status_code=503, content={"status": "challenge_detected", "detail": str(e)})
    except NoEasyApplyButton:
        # Expected — not all LinkedIn URLs have Easy Apply
        async with session.begin():
            job.status = JobStatus.FAILED  # or a new SKIPPED status
            job.rejection_reason = "no_easy_apply_button"
        return JSONResponse(status_code=200, content={"status": "skipped", "reason": "no_easy_apply_button"})
    except UnknownFormField as e:
        async with session.begin():
            job.status = JobStatus.FAILED
            job.rejection_reason = str(e)
        return JSONResponse(status_code=200, content={"status": "skipped", "reason": str(e)})

    # Success — write SUBMITTED
    async with session.begin():
        # reuse existing mark_submitted logic
        ...

    return {"status": "submitted", "job_id": payload.job_id}
```

---

### Pattern 7: gmail_client.py — apply_type Detection (D-02)

**What:** Small change to the n8n gmail-ingest workflow's ingest payload OR to `src/api/routes/gmail.py` / the ingest call chain. When the job URL extracted from a LinkedIn alert contains `linkedin.com`, set `apply_type='linkedin_easy_apply'` instead of `'email'`.

**Existing code (src/api/routes/ingest.py line 91):**
```python
apply_type=payload.apply_type,  # comes from the n8n ingest workflow
```

**Fix option A (n8n-side, minimal code change):** In the gmail-ingest n8n workflow, add a Code node that checks if the extracted URL contains `linkedin.com` and sets `apply_type` accordingly before calling `/ingest-lead`.

**Fix option B (Python-side):** In the FastAPI `/ingest-lead` endpoint, auto-detect `apply_type` from URL if not provided:
```python
if payload.apply_type is None and payload.url and "linkedin.com" in payload.url:
    resolved_apply_type = "linkedin_easy_apply"
else:
    resolved_apply_type = payload.apply_type
```

**Recommendation: Option A (n8n Code node)** — keeps the existing Python ingest logic unchanged, minimal blast radius.

---

### Anti-Patterns to Avoid

- **Never use `headless=True` (pure headless) in production:** LinkedIn detects standard headless mode. Always use `headless="virtual"` on Linux/Docker. [CITED: camoufox.com/python/virtual-display/]
- **Never store session as a plain Playwright storage_state JSON if it has `__Host-` cookies:** LinkedIn's cookies use `__Host-` prefix requiring exact domain, secure=True, and path=/ — these break in Playwright's standard cookie injection. Use persistent_context + user_data_dir instead. [ASSUMED: based on camoufox discussion #408]
- **Never call `generate-screening-answers` as a synchronous HTTP request from inside Camoufox:** The Camoufox automation runs in the same FastAPI process — call the screening answers logic directly (import the function) or use httpx to call the local FastAPI endpoint (`http://localhost:8000/application/generate-screening-answers`). The Docker service name `http://job-app-api:8000` is for n8n→FastAPI calls only.
- **Never hard-code `http://localhost:8000` in n8n workflow JSON:** All n8n→FastAPI calls must use `http://job-app-api:8000` (Docker service name). [CITED: existing ai-apply-pipeline.json confirms this pattern]
- **Never attempt to fill unknown fields:** D-11 is a hard stop — log and SKIP.
- **Never retry automatically on challenge:** D-06 is explicit — no auto-resume.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stealth browser fingerprinting | Custom JS patches, navigator overrides | Camoufox (already decided) | LinkedIn's APFC engine checks 48 device characteristics; JS-level patches are insufficient |
| Human-like mouse movement | Custom Bézier curve mouse paths | Camoufox `humanize=True` | Built-in C++ implementation of HumanCursor algorithm |
| Random inter-submission delays | Python `asyncio.sleep(random.randint(...))` in the browser module | n8n Code node + Wait node | Timing must be controlled at the orchestration layer (n8n), not inside the browser session |
| Daily submission counting | In-memory counter in the FastAPI process | New DB endpoint reading Application table | In-memory counters reset on restart; DB is durable |
| Form field label extraction | Custom DOM traversal | Pattern established in this research (aria-label → placeholder → label[for=id]) | Standard three-level fallback is sufficient and used across all active LinkedIn bots |

---

## Common Pitfalls

### Pitfall 1: LinkedIn DOM Selector Drift

**What goes wrong:** LinkedIn updates their React component class names without warning. A selector that worked in March 2025 may return zero elements in May 2025. The automation silently fails to find the Easy Apply button.

**Why it happens:** LinkedIn's frontend uses generated class names that change on deploys. The relatively stable selectors are ARIA labels and structural attributes (`[aria-label='Submit application']`, `input[type='file']`) — not CSS class names.

**How to avoid:** Prioritize ARIA-label-based selectors over class-based selectors. Add a validation test that navigates to a known Easy Apply job URL and asserts each selector resolves at least one element. Run this test before every production run (or as a separate health-check endpoint).

**Warning signs:** `await page.locator(selector).count() == 0` in logs; jobs being incorrectly logged as SKIPPED with `no_easy_apply_button` when the job clearly has Easy Apply.

### Pitfall 2: Camoufox Binary Not Installed in Docker

**What goes wrong:** `camoufox` Python package installs, but the Firefox binary is not fetched. `AsyncCamoufox()` raises `FileNotFoundError` or `BrowserNotFound` at runtime.

**Why it happens:** Camoufox requires a separate binary download step (`python -m camoufox fetch`) distinct from `pip install camoufox`. The binary is ~100MB and not included in the PyPI package.

**How to avoid:** Add `RUN python -m camoufox fetch` to `Dockerfile.api` after `uv sync`. The binary is cached in the Docker layer. [ASSUMED: exact command — verify against camoufox docs at build time]

**Warning signs:** `BrowserNotFound` or `FileNotFoundError` in container logs on startup.

### Pitfall 3: Modal Stuck on Multi-Page Forms

**What goes wrong:** The Easy Apply modal has 3-5 pages on complex applications. After filling page 1 and clicking Next, the automation tries to click Next again but the new page's fields are not yet filled, causing LinkedIn to show validation errors and block progression.

**Why it happens:** `page.wait_for_load_state("networkidle")` is too broad — the modal uses partial DOM updates, not full page navigations.

**How to avoid:** After clicking Next, wait for the specific modal page indicator to change OR wait for a short fixed delay (1-2 seconds) before attempting field detection on the new page. Detect error messages using `.artdeco-inline-feedback__message` and surface them in logs.

**Warning signs:** Application logs showing "no Next/Review/Submit button found" after the first page; error messages visible on the page.

### Pitfall 4: Resume File Upload Path Not Accessible Inside Docker

**What goes wrong:** The resume PDF path resolved by the existing `/resume/select-resume` endpoint is a path on the host machine or a relative path that doesn't exist inside the Docker container.

**Why it happens:** Resume files are mounted at `/app/resumes` inside the container (per `docker-compose.yml` volume mapping `./resumes:/app/resumes`), but the path passed to `set_input_files()` may use a different base path.

**How to avoid:** Always resolve resume paths relative to `RESUMES_DIR` env var (`/app/resumes` in Docker). The `resume.py` route returns `resume_name` (filename only) — the browser module must construct the full path: `os.path.join(os.environ.get("RESUMES_DIR", "resumes"), resume_name)`.

**Warning signs:** `FileNotFoundError` on `set_input_files()`; resume upload step silently skipped.

### Pitfall 5: `__Host-` Cookie Loss with storage_state JSON

**What goes wrong:** Saving LinkedIn session via `await context.storage_state(path="data/linkedin_session.json")` and reloading via `browser.new_context(storage_state=...)` drops LinkedIn's `__Host-` prefixed cookies, causing the session to appear expired on first page load.

**Why it happens:** `__Host-` cookies require `Secure: True` and `path: /` and exact domain matching. Playwright's cookie serialization/deserialization has known edge cases with these. [ASSUMED: based on unanswered camoufox bug report #408]

**How to avoid:** Use `persistent_context=True` with `user_data_dir` pointing to a directory on the Docker volume. The browser natively manages cookie persistence in this mode — no serialization step.

**Warning signs:** Session expired Telegram alerts firing immediately after first run; URL redirecting to `/login` despite fresh manual login.

### Pitfall 6: n8n Daily Counter Not Resetting at Midnight

**What goes wrong:** If using n8n `$workflow.staticData` for the daily cap counter, the counter survives n8n restarts and deployments but does NOT reset at midnight automatically. The system stops accepting new applications after the first day reaches the cap.

**Why it happens:** `staticData` persists indefinitely; there is no built-in daily reset unless explicitly coded.

**How to avoid:** Use the DB-backed daily count approach (`GET /apply/daily-linkedin-count` returns today's Application count). The query filters by `submitted_at >= today_midnight` — it automatically resets each day.

**Warning signs:** No LinkedIn applications submitted after day 1; cap reached log in n8n workflow despite it being a new day.

---

## Code Examples

### Verified Pattern: AsyncCamoufox with Virtual Display

Source: [CITED: camoufox.com/python/virtual-display/]
```python
from camoufox.async_api import AsyncCamoufox

async with AsyncCamoufox(headless="virtual") as browser:
    page = await browser.new_page()
    await page.goto("https://www.linkedin.com/jobs/view/...")
```

### Verified Pattern: Persistent Context

Source: [CITED: camoufox.com/python/usage/]
```python
from camoufox.async_api import AsyncCamoufox

async with AsyncCamoufox(
    headless="virtual",
    persistent_context=True,
    user_data_dir="/data/linkedin_profile",
    humanize=True,
    os="windows",
) as context:
    page = await context.new_page()
```

### Verified Pattern: Playwright storage_state (fallback)

Source: [CITED: playwright.dev/python/docs/auth]
```python
# Save state after manual login:
await page.context.storage_state(path="data/linkedin_session.json")

# Load in new run:
context = await browser.new_context(storage_state="data/linkedin_session.json")
```

### Verified Pattern: Playwright form interactions (applies directly to Camoufox)

Source: [CITED: playwright.dev/python/docs/input]
```python
# Fill text input
await page.locator(".artdeco-text-input--input").first.fill("value")

# Select option in dropdown
await page.locator("select").select_option(label="Yes")

# Click radio button
await page.locator("input[type='radio'][value='Yes']").first.click()

# File upload (resume)
await page.locator("input[type='file']").set_input_files("/app/resumes/resume.pdf")
```

### Verified Pattern: n8n random delay with Code + Wait nodes

Source: [CITED: n8n.io community discussion on random delays]
```javascript
// Code node — generates random wait
const minDelay = 60 * 8;   // 8 min
const maxDelay = 60 * 25;  // 25 min
const randomDelay = Math.floor(Math.random() * (maxDelay - minDelay + 1)) + minDelay;
return [{ json: { waitSeconds: randomDelay } }];
```
Wait node: Time Amount = `{{ $json.waitSeconds }}`, Unit = `seconds`.

### Existing Pattern: Challenge detection — HTTP 503 response (follows OPS-01)

Source: [CITED: src/api/routes/gmail.py] (directly read)
```python
# Pattern from existing gmail.py — Phase 3 uses same approach:
raise HTTPException(
    status_code=503,
    detail={"status": "challenge_detected", "detail": "LinkedIn challenge: /checkpoint/"},
)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Selenium WebDriver for LinkedIn automation | Camoufox (Firefox stealth) + Playwright | 2024-2025 | Selenium is the most-detected; Camoufox achieves 0% detection on fingerprintjs/bot.sannysoft |
| playwright-stealth JS patches | Camoufox C++-level patching | Late 2024 (playwright-stealth abandoned) | JS patches don't cover Canvas, WebGL, AudioContext — the three primary LinkedIn detection vectors in 2025 |
| `headless=True` pure headless mode | `headless="virtual"` (Xvfb) | 2024 | Pure headless is increasingly fingerprinted; virtual display provides real rendering pipeline |
| Manual daily tracking / sleep timers | n8n Code+Wait+DB approach | Always best practice | No in-process state that resets on restart |

**Deprecated/outdated:**
- `playwright-stealth` (PyPI): Abandoned late 2024, do not use. [CITED: CLAUDE.md — "What NOT to Use" section]
- `Selenium`: Outdated WebDriver protocol is most-detected signal. [CITED: CLAUDE.md]
- n8n `$workflow.staticData` for daily cap: Functional but not restart-durable — prefer DB-backed counter.

---

## Runtime State Inventory

> Phase 3 is additive, not a rename/refactor. The only runtime state concern is the new session file/directory.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | No existing LinkedIn session data | Wave 0: create `data/linkedin_profile/` dir; human runs `scripts/linkedin_session_save.py` once before first production run |
| Live service config | n8n: new workflow `linkedin-easy-apply.json` must be imported and activated | Manual import step in n8n UI after deploy |
| OS-registered state | None | None |
| Secrets/env vars | New env vars needed: `LINKEDIN_PROFILE_DIR`, `LINKEDIN_APPLY_WINDOW_START`, `LINKEDIN_APPLY_WINDOW_END`, `LINKEDIN_DAILY_CAP` | Add to `.env.example` and `docker-compose.yml` |
| Build artifacts | Camoufox Firefox binary (~100MB) fetched at Docker build time | `RUN python -m camoufox fetch` in `Dockerfile.api` |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| camoufox Python package | Browser automation | Not installed (not in pyproject.toml) | 0.4.11 latest on PyPI | None — required |
| xvfb (apt package) | `headless="virtual"` in Docker | Not in Dockerfile.api | — | `headless=True` (reduced stealth) |
| Camoufox Firefox binary | `AsyncCamoufox()` launch | Not fetched | — | None — required |
| Docker `data/` volume | Session persistence | Yes (already mounted) | — | — |
| n8n | Orchestration | Yes (running in docker-compose) | latest | — |

**Missing dependencies with no fallback:**
- `camoufox` PyPI package — must be added to pyproject.toml and Docker build
- Camoufox Firefox binary — must be fetched at Docker build time
- `xvfb` apt package — must be added to Dockerfile.api (required for `headless="virtual"` in Linux container)

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23+ (already in pyproject.toml dev deps) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` — `asyncio_mode = "auto"` |
| Quick run command | `uv run pytest tests/browser/ -x -q` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| APPLY-01 | Easy Apply form submission end-to-end | integration (live LinkedIn) | manual-only (requires live LinkedIn session) | No — Wave 0 |
| APPLY-01 | Challenge detection fires on /checkpoint/ URL | unit (mock page URL) | `pytest tests/browser/test_linkedin_applier.py::test_challenge_detected -x` | No — Wave 0 |
| APPLY-01 | NoEasyApplyButton raises when button absent | unit (mock page) | `pytest tests/browser/test_linkedin_applier.py::test_no_easy_apply_button -x` | No — Wave 0 |
| APPLY-01 | Daily cap endpoint returns correct count | unit (DB fixture) | `pytest tests/api/test_apply_routes.py::test_daily_count -x` | No — Wave 0 |
| APPLY-01 | apply_type detection in ingest (D-02) | unit | `pytest tests/api/test_ingest.py::test_linkedin_url_apply_type -x` | No — Wave 0 |
| APPLY-01 | Bot fingerprint check passes | smoke (live) | manual: navigate to bot.sannysoft.com before first run | N/A |

**Note on end-to-end test:** Full apply submission requires a live LinkedIn session and a real job posting — this is a manual smoke test, not automated. The automated tests cover the detection logic and DB interactions using mocked Playwright pages.

### Sampling Rate

- **Per task commit:** `uv run pytest tests/browser/ tests/api/test_apply_routes.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/browser/__init__.py` — create package
- [ ] `tests/browser/test_linkedin_applier.py` — challenge detection, no-button, unknown field tests
- [ ] `tests/api/test_apply_routes.py` — daily count endpoint, linkedin-easy-apply route unit tests
- [ ] `tests/api/test_ingest.py::test_linkedin_url_apply_type` — D-02 detection logic

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes (LinkedIn session) | Session persisted in Docker volume with restricted file permissions; no credentials in code |
| V3 Session Management | Yes | `data/linkedin_profile/` dir must not be committed to git; add to `.gitignore` |
| V4 Access Control | Yes | FastAPI `verify_api_key` dependency already applied on all state-changing routes — apply to new `/apply/linkedin-easy-apply` route |
| V5 Input Validation | Yes | `job_id` validated against DB before Camoufox launch; all inputs are internal (n8n → FastAPI) |
| V6 Cryptography | No | No new crypto — session file is plaintext (browser-native) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Session file exposure | Information Disclosure | `data/linkedin_profile/` excluded from git, Docker volume not shared externally |
| SSRF via job URL | Tampering | Job URL comes from DB (already ingested + filtered) — not directly from n8n payload |
| LinkedIn account ban | Availability | Daily cap (D-09), challenge detection halt (D-06), VPS-only (D-07) |
| Credentials in n8n workflow JSON | Information Disclosure | LinkedIn credentials never appear in workflow JSON — session managed by Camoufox profile dir |

---

## Open Questions (RESOLVED)

1. **Persistent context vs. storage_state JSON for `data/linkedin_session.json`**
   - What we know: CONTEXT.md D-04 specifies a JSON file at `data/linkedin_session.json`. Community reports suggest `__Host-` cookies in LinkedIn sessions break with Playwright storage_state JSON serialization.
   - What's unclear: Whether the `persistent_context=True` + `user_data_dir` approach is sufficient or whether a JSON backup is also needed. The discussion is unresolved in the Camoufox GitHub issues.
   - Recommendation: Planner should default to `user_data_dir="/data/linkedin_profile"` and note the deviation from CONTEXT.md D-04. Add a task to test `storage_state` export after first manual login — if `__Host-` cookies survive, both approaches can coexist. Flag as `[ASSUMED]` risk.
   - **RESOLVED:** Use the `user_data_dir` directory approach (`persistent_context=True`, `user_data_dir="/data/linkedin_profile"`) as the primary session store — implemented in Plan 03-04 Task 1 (session save script) and consumed by Plan 03-03 (route resolves `LINKEDIN_PROFILE_DIR`) and Plan 03-02 (applier launch). LinkedIn's `__Host-` cookies have known serialization issues with the JSON `storage_state` approach, so the JSON export to `data/linkedin_session.json` is kept only as a best-effort, non-fatal fallback (try/except in the session save script). This satisfies CONTEXT.md D-04's intent (a persisted on-disk session under `data/`) while deviating on the exact format.

2. **SKIPPED status for jobs that lack Easy Apply button**
   - What we know: D-01 says "log as SKIPPED". The existing `JobStatus` enum has FAILED but not SKIPPED. D-11 also uses "SKIPPED" status.
   - What's unclear: Should Phase 3 add a new `SKIPPED` status to the `JobStatus` enum, or reuse `FAILED` with a specific `rejection_reason`?
   - Recommendation: Add `SKIPPED = "SKIPPED"` to `JobStatus` enum as part of Phase 3 — this is cleaner for Phase 4 dashboard filtering. Small migration: no schema change needed (string column).
   - **RESOLVED:** Add `JobStatus.SKIPPED = "SKIPPED"` as a new enum value (Plan 03-01 Task 2), plus a matching `AuditEvent.SKIPPED` (Plan 03-01). Do NOT reuse `FAILED` — SKIPPED (no Easy Apply button / unknown form field, expected and non-erroneous) and FAILED (genuine submission error) are semantically distinct and Phase 4 dashboard filtering depends on the distinction. No DB schema migration needed — the `status` column is a string. Consumed by Plan 03-03 (route writes `JobStatus.SKIPPED` + `AuditEvent.SKIPPED`).

3. **Internal screening answers call — HTTP or direct function import?**
   - What we know: The `/application/generate-screening-answers` endpoint is an async FastAPI route that uses a DB session. The Camoufox automation runs in the same FastAPI process.
   - What's unclear: Whether calling `http://localhost:8000/application/generate-screening-answers` from inside the FastAPI process introduces a potential deadlock (self-referential HTTP call on the same event loop thread).
   - Recommendation: Extract the core screening logic into a shared function in `src/preparation/screening.py` and call it directly from the browser module, bypassing HTTP. [ASSUMED: avoids self-HTTP call complexity]
   - **RESOLVED:** Extract the core screening logic into a shared `src/preparation/screening.py` module and import it directly from the browser module (Plan 03-02 Task 2). Do NOT issue a self-referential `http://localhost:8000/...` HTTP call from inside the FastAPI process — it risks event-loop contention. The existing `/application/generate-screening-answers` route is refactored to call the same shared function so both paths share one implementation.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `persistent_context=True` + `user_data_dir` is more reliable than `storage_state` JSON for LinkedIn `__Host-` cookies | Pattern 1, Pitfall 5 | Session expires on every run; manual re-login needed repeatedly |
| A2 | `python -m camoufox fetch` is the correct command to download the Firefox binary inside Docker | Pitfall 2, Environment Availability | Docker build fails; container cannot start Camoufox |
| A3 | LinkedIn Easy Apply button selector `.jobs-apply-button--top-card #jobs-apply-button-id` is current as of May 2026 | Pattern 3 | Button not found; all jobs logged as SKIPPED |
| A4 | LinkedIn modal ARIA labels `'Continue to next step'`, `'Review your application'`, `'Submit application'` are stable | Pattern 3 | Modal navigation fails; automation hangs on modal pages |
| A5 | Extracting screening logic into `src/preparation/screening.py` avoids self-HTTP call issues | Open Question 3 | If kept as HTTP call, potential event loop contention; risk is low on separate thread pool |
| A6 | `camoufox` PyPI package is legitimate and corresponds to github.com/daijro/camoufox | Package Legitimacy | Package could be spoofed; install proceeds but installs wrong software |

---

## Sources

### Primary (HIGH confidence)
- [camoufox.com/python/usage/](https://camoufox.com/python/usage/) — async API, persistent_context, headless options
- [camoufox.com/python/virtual-display/](https://camoufox.com/python/virtual-display/) — headless="virtual", xvfb requirement
- [playwright.dev/python/docs/auth](https://playwright.dev/python/docs/auth) — storage_state save/load patterns
- `src/api/routes/application.py` — FastAPI endpoint pattern (read directly)
- `src/api/routes/gmail.py` — challenge detection HTTP 503 pattern (read directly)
- `n8n/workflows/ai-apply-pipeline.json` — n8n workflow structure (read directly)
- `docker-compose.yml` + `Dockerfile.api` — Docker integration baseline (read directly)

### Secondary (MEDIUM confidence)
- [github.com/nicolomantini/LinkedIn-Easy-Apply-Bot/blob/master/easyapplybot.py](https://github.com/nicolomantini/LinkedIn-Easy-Apply-Bot) — DOM selectors (Easy Apply button XPath, Next/Review/Submit aria-labels, field container class)
- [github.com/AmmarAR97/linkedin-job-automation/blob/main/utils/apply.py](https://github.com/AmmarAR97/linkedin-job-automation) — form field selectors (phone, text, file, radio, dropdown patterns)
- [n8n.io community — random wait pattern](https://community.n8n.io/t/how-can-i-add-a-random-wait-time-between-loop-iterations-in-n8n/211048) — Code node + Wait node random delay implementation

### Tertiary (LOW confidence / ASSUMED)
- Community reports on `__Host-` cookie issues with Playwright storage_state in Camoufox context — unanswered GitHub discussion [github.com/daijro/camoufox/discussions/408]
- LinkedIn checkpoint URL patterns (`/checkpoint/`, `/authwall/`, `/login`) — derived from multiple LinkedIn automation community sources; not officially documented by LinkedIn

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — camoufox 0.4.11 confirmed on PyPI registry; all other deps already in project
- Camoufox async API: HIGH — official documentation read directly
- LinkedIn DOM selectors: MEDIUM — sourced from active open-source bots (nicolomantini, AmmarAR97); subject to LinkedIn UI changes
- n8n cap/timing patterns: HIGH — official n8n docs + community example directly read
- Session persistence approach: MEDIUM — official camoufox docs confirm persistent_context; JSON approach has known issues (LOW confidence)
- Challenge detection signals: MEDIUM — URL patterns consistent across multiple community sources

**Research date:** 2026-05-29
**Valid until:** 2026-06-29 for stack; 2026-06-12 for LinkedIn DOM selectors (fast-moving)
