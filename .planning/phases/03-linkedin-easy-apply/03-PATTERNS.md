# Phase 3: LinkedIn Easy Apply - Pattern Map

**Mapped:** 2026-05-29
**Files analyzed:** 7 (5 new, 2 modified)
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/browser/linkedin_applier.py` | service | event-driven | `src/api/routes/gmail.py` (challenge detection + 503 pattern) | partial-match |
| `src/api/routes/apply/linkedin_apply.py` | controller | request-response | `src/api/routes/application.py` | exact |
| `n8n/workflows/linkedin-easy-apply.json` | config | event-driven | `n8n/workflows/ai-apply-pipeline.json` | role-match |
| `src/queue/models.py` | model | CRUD | `src/queue/models.py` (existing JobStatus enum) | self (modification) |
| `n8n/workflows/gmail-ingest.json` | config | event-driven | `n8n/workflows/gmail-ingest.json` (existing) | self (modification) |
| `pyproject.toml` | config | — | `pyproject.toml` (existing) | self (modification) |
| `Dockerfile.api` | config | — | `Dockerfile.api` (existing) | self (modification) |

---

## Pattern Assignments

### `src/browser/linkedin_applier.py` (service, event-driven)

**Analog:** `src/api/routes/gmail.py` (challenge detection pattern) + RESEARCH.md code examples

**Imports pattern** — model after existing challenge-aware service modules:
```python
# No existing browser module exists — copy imports convention from gmail.py lines 1-29
import os
from typing import Annotated

import structlog
from camoufox.async_api import AsyncCamoufox

log = structlog.get_logger()
```

**Challenge detection pattern** — `src/api/routes/gmail.py` lines 67-83 (OPS-01 pattern):
```python
# gmail.py raises HTTPException(status_code=503) on auth failure.
# linkedin_applier.py raises a custom ChallengeDetected exception instead
# (the FastAPI route translates it to 503 — same wire format).
# Pattern: detect failure condition → raise named exception → caller handles.
raise HTTPException(
    status_code=503,
    detail={"status": "challenge_detected", "detail": _OAUTH_CHALLENGE_DETAIL},
)
```

**structlog usage pattern** — `src/api/routes/gmail.py` lines 68, 73, 79, 93 (all log calls in this project use keyword-only args):
```python
log.warning("gmail_oauth_challenge", status=401, detail=str(exc))
log.error("gmail_service_init_error", status=exc.resp.status, detail=str(exc))
log.info("gmail_poll_start", current_history_id=current_history_id)
log.info("gmail_poll_complete", message_count=len(matching_ids), new_history_id=new_history_id)
```

**Custom exception pattern** — no existing analog; define inline at top of module (consistent with how this codebase avoids a separate `exceptions.py`):
```python
class ChallengeDetected(Exception):
    """Raised when LinkedIn presents a CAPTCHA, authwall, or 2FA prompt."""

class NoEasyApplyButton(Exception):
    """Raised when the Easy Apply button is absent — expected for non-Easy-Apply jobs."""

class UnknownFormField(Exception):
    """Raised when a form field label cannot be mapped to a known profile field."""
```

**Async context manager pattern** — Camoufox session (RESEARCH.md Pattern 1, lines 193-209):
```python
async with AsyncCamoufox(
    headless="virtual",          # required on Linux/Docker — never headless=True
    persistent_context=True,
    user_data_dir=user_data_dir, # /data/linkedin_profile
    humanize=True,
    os="windows",
) as context:
    page = await context.new_page()
    await page.goto(job_url)
```

---

### `src/api/routes/apply/linkedin_apply.py` (controller, request-response)

**Analog:** `src/api/routes/application.py` — exact pattern match

**Imports pattern** — `src/api/routes/application.py` lines 1-24 + `src/api/routes/ingest.py` line 14 (auth dependency):
```python
import json
import os
from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.app import get_session, verify_api_key
from src.api.schemas import LinkedInApplyIn, LinkedInApplyOut   # new schemas
from src.audit_log import AuditEvent, write_audit
from src.queue.models import Application, Job, JobStatus
from src.browser.linkedin_applier import (
    LinkedInApplier,
    ChallengeDetected,
    NoEasyApplyButton,
    UnknownFormField,
)

log = structlog.get_logger()
router = APIRouter()
```

**Auth dependency pattern** — `src/api/routes/ingest.py` line 26 (all state-changing routes use `dependencies=[Depends(verify_api_key)]`):
```python
@router.post("/ingest-lead", dependencies=[Depends(verify_api_key)])
```

**DB lookup + 404/409 guard pattern** — `src/api/routes/application.py` lines 162-170 (`write_application` function, exact structure to copy):
```python
async with session.begin():
    result = await session.execute(select(Job).where(Job.id == payload.job_id))
    job = result.scalar_one_or_none()

    if job is None:
        return JSONResponse(status_code=404, content={"detail": "job_not_found"})

    if job.status != JobStatus.QUEUED:
        return JSONResponse(status_code=409, content={"detail": "job_not_queued"})
```

**Status transition + audit write pattern** — `src/api/routes/application.py` lines 172-184 (APPLYING transition) and lines 207-237 (SUBMITTED transition + Application row creation):
```python
# APPLYING transition (copy from write_application):
job.resume_template = payload.resume_name
job.cover_letter = payload.cover_letter
job.status = JobStatus.APPLYING
job.updated_at = datetime.utcnow()
await write_audit(session, source="api", event=AuditEvent.APPLYING, job_id=job.id)

# SUBMITTED transition + Application row (copy from mark_submitted lines 217-233):
job.status = JobStatus.SUBMITTED
job.updated_at = datetime.utcnow()
application = Application(
    job_id=job.id,
    resume_template=job.resume_template,
    cover_letter=job.cover_letter,
    screening_answers=job.screening_answers,
    submitted_at=datetime.utcnow(),
)
session.add(application)
await write_audit(session, source="api", event=AuditEvent.SUBMITTED, job_id=job.id)
```

**SKIPPED status transition** — copy the FAILED pattern from `application.py` but use `JobStatus.SKIPPED` (the new enum value) and write audit with `AuditEvent.SKIPPED` (the new audit event added in Plan 03-01):
```python
# For NoEasyApplyButton and UnknownFormField:
async with session.begin():
    result = await session.execute(select(Job).where(Job.id == payload.job_id))
    job = result.scalar_one_or_none()
    job.status = JobStatus.SKIPPED
    job.rejection_reason = reason_str
    job.updated_at = datetime.utcnow()
    await write_audit(session, source="api", event=AuditEvent.SKIPPED, job_id=job.id, reason=reason_str)
return JSONResponse(status_code=200, content={"status": "skipped", "reason": reason_str})
```

**Challenge 503 error pattern** — `src/api/routes/gmail.py` lines 67-83 (raise HTTPException, same wire format):
```python
except ChallengeDetected as exc:
    log.error("linkedin_challenge", job_id=payload.job_id, challenge=str(exc))
    raise HTTPException(
        status_code=503,
        detail={"status": "challenge_detected", "detail": str(exc)},
    )
```

**Pydantic schema pattern** — `src/api/schemas.py` lines 58-69 (copy `WriteApplicationIn` / `MarkSubmittedIn` structure):
```python
class LinkedInApplyIn(BaseModel):
    """Payload for POST /apply/linkedin-easy-apply."""
    job_id: str

class LinkedInApplyOut(BaseModel):
    """Response for POST /apply/linkedin-easy-apply."""
    status: str   # "submitted" | "skipped" | "challenge_detected"
    job_id: str
    reason: str | None = None
```

**Router registration pattern** — `src/api/app.py` lines 102-116 (add new router import + `app.include_router`):
```python
# Add to src/api/app.py imports block (lines 102-109):
from src.api.routes.apply import linkedin_apply

# Add to app.include_router calls (after line 116):
app.include_router(linkedin_apply.router, prefix="/apply", tags=["apply"])
```

**GET queued-jobs endpoint pattern** — `src/api/routes/application.py` lines 241-264 (`queued_email_jobs`, copy for the new `queued-linkedin-jobs` endpoint):
```python
@router.get("/queued-linkedin-jobs")
async def queued_linkedin_jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    async with session.begin():
        result = await session.execute(
            select(Job).where(Job.status == JobStatus.QUEUED, Job.apply_type == "linkedin_easy_apply")
        )
        jobs = result.scalars().all()
    return {
        "jobs": [
            {"id": job.id, "title": job.title, "company": job.company, "url": job.url, ...}
            for job in jobs
        ]
    }
```

---

### `n8n/workflows/linkedin-easy-apply.json` (config, event-driven)

**Analog:** `n8n/workflows/ai-apply-pipeline.json` — closest structural match

**Node ID naming convention** — `ai-apply-pipeline.json` uses prefix `ap-` + sequential number (e.g., `ap-01`, `ap-02`). Use prefix `li-` for LinkedIn workflow nodes.

**Schedule trigger pattern** — `ai-apply-pipeline.json` node `ap-01` (lines 6-20), change interval to 5 minutes:
```json
{
  "parameters": {
    "rule": {
      "interval": [{"field": "minutes", "minutesInterval": 5}]
    }
  },
  "id": "li-01",
  "name": "Every 5 Minutes",
  "type": "n8n-nodes-base.scheduleTrigger",
  "typeVersion": 1.2,
  "position": [240, 400]
}
```

**HTTP GET node pattern** — `ai-apply-pipeline.json` node `ap-02` and `ap-03` (lines 22-45). Copy for `GET /apply/daily-linkedin-count` and `GET /apply/queued-linkedin-jobs`:
```json
{
  "parameters": {
    "method": "GET",
    "url": "http://job-app-api:8000/apply/daily-linkedin-count",
    "options": {}
  },
  "id": "li-02",
  "name": "Get Daily Count",
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 4.2,
  "position": [440, 400]
}
```

**Auth credential pattern** — `n8n/workflows/gmail-ingest.json` nodes `gi-02`, `gi-05`, `gi-08` (lines 28-38, 88-100, 163-175). All state-changing FastAPI calls use `httpHeaderAuth` with credential ID `fastApiKey`:
```json
"authentication": "genericCredentialType",
"genericAuthType": "httpHeaderAuth",
"credentials": {
  "httpHeaderAuth": {
    "id": "fastApiKey",
    "name": "FastAPI Key"
  }
}
```

**If/condition node pattern** — `ai-apply-pipeline.json` node `ap-04` (lines 46-73). Copy for "Any Jobs?" and "proceed == true" gate checks.

**Code node pattern** — `n8n/workflows/gmail-ingest.json` node `gi-07` (lines 150-158), `typeVersion: 2`. For the daily cap + window check Code node (RESEARCH.md Pattern 5):
```json
{
  "parameters": {
    "language": "javaScript",
    "jsCode": "const now = new Date();\nconst hour = now.getHours();\nconst windowStart = parseInt($env.LINKEDIN_APPLY_WINDOW_START || '9');\nconst windowEnd = parseInt($env.LINKEDIN_APPLY_WINDOW_END || '17');\nif (hour < windowStart || hour >= windowEnd) {\n  return [{ json: { proceed: false, reason: 'outside_window' } }];\n}\nconst dailyCount = $('Get Daily Count').first().json.count;\nconst cap = parseInt($env.LINKEDIN_DAILY_CAP || '17');\nif (dailyCount >= cap) {\n  return [{ json: { proceed: false, reason: 'cap_reached' } }];\n}\nconst minDelay = 60 * 8;\nconst maxDelay = 60 * 25;\nconst randomDelay = Math.floor(Math.random() * (maxDelay - minDelay + 1)) + minDelay;\nreturn [{ json: { proceed: true, waitSeconds: randomDelay } }];"
  },
  "id": "li-04",
  "name": "Check Cap + Window",
  "type": "n8n-nodes-base.code",
  "typeVersion": 2,
  "position": [840, 400]
}
```

**HTTP POST with auth + body pattern** — `n8n/workflows/gmail-ingest.json` node `gi-08` (lines 161-210). Copy for the `POST /apply/linkedin-easy-apply` call:
```json
{
  "parameters": {
    "method": "POST",
    "url": "http://job-app-api:8000/apply/linkedin-easy-apply",
    "authentication": "genericCredentialType",
    "genericAuthType": "httpHeaderAuth",
    "sendBody": true,
    "contentType": "json",
    "bodyParameters": {
      "parameters": [{"name": "job_id", "value": "={{ $json.id }}"}]
    },
    "options": {}
  },
  "credentials": {"httpHeaderAuth": {"id": "fastApiKey", "name": "FastAPI Key"}},
  "id": "li-07",
  "name": "Apply LinkedIn Easy Apply",
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 4.2,
  "position": [1440, 320],
  "onError": "continueErrorOutput"
}
```

**Telegram success notification pattern** — `ai-apply-pipeline.json` node `ap-17` (lines 416-431). Copy structure; credential ID is `telegramBot`, chat ID is `$env.TELEGRAM_CHAT_ID`:
```json
{
  "parameters": {
    "chatId": "={{ $env.TELEGRAM_CHAT_ID }}",
    "text": "={{ '✅ LinkedIn Easy Apply submitted!\\n\\n🏢 ' + $json.company + '\\n💼 ' + $json.title + '\\n🔗 ' + $json.url }}",
    "additionalFields": {}
  },
  "credentials": {"telegramApi": {"id": "telegramBot", "name": "Telegram Bot"}},
  "id": "li-08",
  "name": "Telegram Success",
  "type": "n8n-nodes-base.telegram",
  "typeVersion": 1.2
}
```

**Telegram error/challenge alert pattern** — `ai-apply-pipeline.json` node `ap-18` (lines 433-449). Copy for challenge_detected (503) error output:
```json
{
  "parameters": {
    "chatId": "={{ $env.TELEGRAM_CHAT_ID }}",
    "text": "={{ '⚠️ LinkedIn challenge detected!\\n\\n' + ($json.error?.message || JSON.stringify($json)) + '\\n\\nAutomation paused. Resolve manually, then reactivate the LinkedIn workflow in n8n.' }}",
    "additionalFields": {}
  },
  "credentials": {"telegramApi": {"id": "telegramBot", "name": "Telegram Bot"}},
  "id": "li-09",
  "name": "Challenge Alert",
  "type": "n8n-nodes-base.telegram",
  "typeVersion": 1.2
}
```

**Workflow metadata shell** — `ai-apply-pipeline.json` lines 538-548 (copy `active`, `settings`, `versionId`, `meta`, `id`, `tags` fields):
```json
"active": false,
"settings": {"executionOrder": "v1"},
"versionId": "linkedin-easy-apply-v1",
"meta": {"instanceId": ""},
"id": "linkedin-easy-apply-01",
"tags": []
```

---

### `src/queue/models.py` — MODIFY: add SKIPPED to JobStatus (model, CRUD)

**Analog:** `src/queue/models.py` itself (existing `JobStatus` enum, lines 13-19)

**Current enum** (lines 13-19):
```python
class JobStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    QUEUED = "QUEUED"
    REJECTED = "REJECTED"
    APPLYING = "APPLYING"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"
```

**Required change** — add one line after `FAILED`:
```python
    SKIPPED = "SKIPPED"
```

No schema migration required. The `status` column is `Column(String)` (line 38) — adding a new enum member does not alter the DB schema. SQLite stores strings; the new value is inserted by new code only.

Also add `SKIPPED` to `AuditEvent` in `src/audit_log.py` line 23, following the same `StrEnum` pattern (lines 13-24):
```python
class AuditEvent(StrEnum):
    ...
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"   # add here
    NOTIFIED = "NOTIFIED"
```

---

### `n8n/workflows/gmail-ingest.json` — MODIFY: add apply_type detection (config, event-driven)

**Analog:** `n8n/workflows/gmail-ingest.json` node `gi-07` (Parse Jobs Code node, lines 150-158)

**Current Parse Jobs Code node** (lines 151-157) outputs job objects with whatever was extracted from Claude. The `Ingest Lead` node `gi-08` (lines 162-210) hardcodes `apply_type: "email"` (line 191-193).

**Required change** — add a Code node between `gi-07` (Parse Jobs) and `gi-08` (Ingest Lead) that adds `apply_type` per URL. Follow `gi-07`'s `typeVersion: 2` / `language: javaScript` pattern:
```json
{
  "parameters": {
    "language": "javaScript",
    "jsCode": "return $input.all().map(item => {\n  const url = (item.json.url || '').toLowerCase();\n  const applyType = url.includes('linkedin.com') ? 'linkedin_easy_apply' : 'email';\n  return { json: { ...item.json, apply_type: applyType } };\n});"
  },
  "id": "gi-10",
  "name": "Set Apply Type",
  "type": "n8n-nodes-base.code",
  "typeVersion": 2,
  "position": [1540, 220]
}
```

Then update `gi-08` Ingest Lead's `apply_type` body parameter from the hardcoded `"email"` value to `"={{ $json.apply_type }}"`.

Connection change: `Parse Jobs → Set Apply Type → Ingest Lead` (insert `gi-10` between `gi-07` and `gi-08` in the `connections` block).

---

### `pyproject.toml` — MODIFY: add camoufox dependency (config)

**Analog:** `pyproject.toml` lines 1-26 (existing `dependencies` array)

**Pattern:** All deps follow `"package>=version"` format (lines 5-26). Add camoufox after the existing `httpx` line:
```toml
    "camoufox>=0.4.11",
```

No other pyproject.toml changes needed. `playwright` is already brought in transitively by camoufox but can be pinned explicitly if needed: `"playwright>=1.44"`.

---

### `Dockerfile.api` — MODIFY: add xvfb + camoufox binary (config)

**Analog:** `Dockerfile.api` lines 1-8 (existing 8-line file)

**Current file** (lines 1-8):
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --no-dev
COPY src/ src/
COPY main.py .
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Required additions** — insert two RUN commands after `uv sync`, before `COPY src/`:
```dockerfile
# Install Xvfb for Camoufox headless="virtual" mode (required on Linux)
RUN apt-get update && apt-get install -y xvfb --no-install-recommends && rm -rf /var/lib/apt/lists/*
# Fetch Camoufox Firefox binary (~100MB, cached in Docker layer)
RUN python -m camoufox fetch
```

**docker-compose.yml additions** — `docker-compose.yml` lines 16-36 (`api` service `environment` block). Add new env vars following the existing `KEY=${VAR}` or `KEY=value` pattern (lines 24-30):
```yaml
      - LINKEDIN_PROFILE_DIR=/data/linkedin_profile
      - LINKEDIN_APPLY_WINDOW_START=${LINKEDIN_APPLY_WINDOW_START:-9}
      - LINKEDIN_APPLY_WINDOW_END=${LINKEDIN_APPLY_WINDOW_END:-17}
      - LINKEDIN_DAILY_CAP=${LINKEDIN_DAILY_CAP:-17}
      - API_KEY=${API_KEY}
```

The `data/` volume is already mounted at `./data:/data` (line 33) — `linkedin_profile/` subdirectory inside that mount requires no additional volume entry.

---

## Shared Patterns

### Authentication (API key on all state-changing routes)
**Source:** `src/api/routes/ingest.py` line 26; `src/api/routes/gmail.py` lines 46, 125
**Apply to:** `src/api/routes/apply/linkedin_apply.py` — all POST endpoints
```python
@router.post("/linkedin-easy-apply", dependencies=[Depends(verify_api_key)])
@router.get("/queued-linkedin-jobs")         # GET endpoints: no auth required (matches existing pattern)
@router.get("/daily-linkedin-count")         # GET endpoints: no auth required
```

### n8n credential ID for FastAPI calls
**Source:** `n8n/workflows/gmail-ingest.json` nodes `gi-02`, `gi-05`, `gi-08`
**Apply to:** All HTTP nodes in `linkedin-easy-apply.json` that call `http://job-app-api:8000`
```json
"authentication": "genericCredentialType",
"genericAuthType": "httpHeaderAuth",
"credentials": {"httpHeaderAuth": {"id": "fastApiKey", "name": "FastAPI Key"}}
```

### n8n FastAPI service URL
**Source:** `n8n/workflows/ai-apply-pipeline.json` nodes `ap-02`, `ap-03`, `ap-06`, `ap-09`, `ap-13`, `ap-14`, `ap-16`
**Apply to:** All n8n HTTP nodes — NEVER use `localhost`
```
http://job-app-api:8000
```

### n8n Telegram alert
**Source:** `n8n/workflows/ai-apply-pipeline.json` node `ap-18` (lines 433-449); `n8n/workflows/gmail-ingest.json` node `gi-09` (lines 212-228)
**Apply to:** Error output node in `linkedin-easy-apply.json`
```json
"credentials": {"telegramApi": {"id": "telegramBot", "name": "Telegram Bot"}},
"parameters": {"chatId": "={{ $env.TELEGRAM_CHAT_ID }}", ...}
```

### structlog call convention
**Source:** `src/api/routes/gmail.py` lines 68, 73, 79, 93, 101, 116; `src/api/routes/application.py` lines 105, 121, 134, 184, 236
**Apply to:** All log calls in `linkedin_applier.py` and `linkedin_apply.py`
```python
log.info("event_name", key1=value1, key2=value2)   # always keyword args
log.error("event_name", error=str(exc), job_id=...)
log.warning("event_name", detail=str(exc))
```

### DB session transaction pattern
**Source:** `src/api/routes/application.py` lines 54-58, 162-176, 207-237
**Apply to:** All DB operations in `linkedin_apply.py`
```python
async with session.begin():
    result = await session.execute(select(Job).where(Job.id == payload.job_id))
    job = result.scalar_one_or_none()
    # mutations inside the same begin() block
    job.status = JobStatus.APPLYING
    job.updated_at = datetime.utcnow()
    await write_audit(session, source="api", event=AuditEvent.APPLYING, job_id=job.id)
# separate begin() block for each logical transaction
```

### Audit log write
**Source:** `src/audit_log.py` lines 39-70; called in `application.py` lines 177-182, 229-233
**Apply to:** All status transitions in `linkedin_apply.py`
```python
await write_audit(
    session,
    source="api",
    event=AuditEvent.APPLYING,   # or SUBMITTED, FAILED, SKIPPED
    job_id=job.id,
    reason=reason_str_or_None,
)
```

---

## No Analog Found

No files are completely without analog. The browser module (`linkedin_applier.py`) is the most novel — no existing Camoufox or Playwright code exists in the codebase. Its patterns come from RESEARCH.md (Camoufox official docs and open-source bot analysis) rather than existing project code.

| File | Novel Aspect | Fall Back To |
|---|---|---|
| `src/browser/linkedin_applier.py` | Camoufox session management, modal navigation, form field detection | RESEARCH.md Patterns 1–4 (all cited in research) |
| `scripts/linkedin_session_save.py` | One-time manual session persistence script | RESEARCH.md Pattern 1 alternative (storage_state fallback) |
| `tests/browser/test_linkedin_applier.py` | Mocked Playwright page fixture | `pytest-asyncio` pattern already in pyproject.toml; no existing browser tests to copy from |

---

## Metadata

**Analog search scope:** `src/`, `n8n/workflows/`, project root config files
**Files read:** 13 source files read directly
**Pattern extraction date:** 2026-05-29
