# Phase 2: Ingest, Generate, and Email Apply - Pattern Map

**Mapped:** 2026-05-28
**Files analyzed:** 15 new/modified files
**Analogs found:** 10 / 15 (5 have no close analog — new patterns with no Phase 1 predecessor)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/api/app.py` | config/entrypoint | request-response | `main.py` (startup + init_db pattern) | role-match |
| `src/api/schemas.py` | model | request-response | `src/filter/config_loader.py` (Pydantic models) | role-match |
| `src/api/routes/ingest.py` | controller | CRUD | `main.py` (dedup+eligibility+audit pipeline) | exact |
| `src/api/routes/scrape.py` | controller | request-response | `main.py` (structlog + session pattern) | role-match |
| `src/api/routes/gmail.py` | controller | event-driven | `main.py` (env config + session + audit pattern) | partial |
| `src/api/routes/resume.py` | controller | request-response | `main.py` (session + structlog pattern) | partial |
| `src/api/routes/application.py` | controller | CRUD | `main.py` (session.begin + Job update + audit pattern) | role-match |
| `src/ingestion/gmail_client.py` | service | event-driven | none — no Gmail/OAuth code exists in Phase 1 | none |
| `src/ingestion/kalibrr_scraper.py` | service | batch | none — no HTTP scraper exists in Phase 1 | none |
| `src/ingestion/jobspy_runner.py` | service | batch | none — no job board scraper exists in Phase 1 | none |
| `src/preparation/resume_reader.py` | utility | file-I/O | none — no file reader exists in Phase 1 | none |
| `src/queue/models.py` | model | CRUD | itself (add `AgentConfig` model) | exact |
| `src/audit_log.py` | model/utility | CRUD | itself (add new `AuditEvent` values) | exact |
| `config/profile.yaml` | config | — | `config/eligibility.yaml` (YAML config pattern) | role-match |
| `pyproject.toml` | config | — | itself (add Phase 2 dependencies) | exact |

---

## Pattern Assignments

### `src/api/app.py` (config/entrypoint, request-response)

**Analog:** `main.py`

**Imports pattern** (`main.py` lines 1–27):
```python
import os
import structlog
from dotenv import load_dotenv

# T-01-02: load_dotenv() before any os.environ access; no shell expansion of paths
load_dotenv()

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    # Route structured logs to stderr; stdout is reserved for human-readable output only
    wrapper_class=structlog.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(file=__import__("sys").stderr),
)

log = structlog.get_logger()
```

**FastAPI lifespan + session factory pattern** (from RESEARCH.md Pattern 2 — no analog in codebase yet):
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.queue.db import init_db, get_session_factory

_session_factory = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _session_factory
    db_path = os.environ.get("DB_PATH", "data/jobs.db")
    config_path = os.environ.get("ELIGIBILITY_CONFIG_PATH", "config/eligibility.yaml")
    profile_path = os.environ.get("PROFILE_CONFIG_PATH", "config/profile.yaml")
    await init_db(db_path)
    _session_factory = get_session_factory(db_path)
    # Load eligibility config + profile.yaml at startup — same pattern as main.py line 155-156
    yield

app = FastAPI(lifespan=lifespan)
```

**Session dependency pattern** (mirrors `main.py` lines 199–200 session usage):
```python
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

async def get_session() -> AsyncSession:
    async with _session_factory() as session:
        yield session
```

---

### `src/api/schemas.py` (model, request-response)

**Analog:** `src/filter/config_loader.py`

**Pydantic model pattern** (`src/filter/config_loader.py` lines 1–59):
```python
from pydantic import BaseModel, Field

class LeadIn(BaseModel):
    url: str
    title: str
    company: str
    location: str | None = None
    source: str
    clean_jd: str | None = None
    apply_type: str | None = None

class LeadOut(BaseModel):
    status: str          # "queued" | "rejected" | "duplicate"
    job_id: str | None = None

class ScrapeJobSpyIn(BaseModel):
    search_term: str
    location: str = "Remote"
    results_wanted: int = Field(default=25, ge=1, le=100)
    hours_old: int = Field(default=24, ge=1)
    site_names: list[str] = Field(default_factory=lambda: ["indeed"])

class SelectResumeIn(BaseModel):
    job_id: str
    job_description: str
    job_title: str
    company: str

class SelectResumeOut(BaseModel):
    resume_name: str
    resume_text: str

class WriteApplicationIn(BaseModel):
    job_id: str
    resume_name: str
    cover_letter: str

class MarkSubmittedIn(BaseModel):
    job_id: str
```

**Validation pattern** — copy the `model_validator` approach from `src/filter/config_loader.py` lines 34–38 for any schemas needing cross-field validation.

---

### `src/api/routes/ingest.py` (controller, CRUD)

**Analog:** `main.py` (the dedup → eligibility → audit → DB write pipeline)

**Core pipeline pattern** (`main.py` lines 174–274) — this is the primary analog. The FastAPI endpoint encapsulates exactly this logic:

**Imports pattern** (`main.py` lines 19–24):
```python
from src.audit_log import AuditEvent, write_audit
from src.filter.config_loader import load_eligibility_config
from src.filter.dedup import hash_url, is_duplicate
from src.filter.eligibility import check_eligibility
from src.queue.db import get_session_factory, init_db
from src.queue.models import Job, JobStatus
```

**Session + transaction pattern** (`main.py` lines 199–200):
```python
async with session_factory() as session:
    async with session.begin():
        # all reads and writes inside this block
```

**Dedup check pattern** (`main.py` lines 201–222):
```python
url_hash = hash_url(payload.url)
dup = await is_duplicate(
    session,
    company=payload.company,
    title=payload.title,
    location=payload.location,
    url_hash=url_hash,
)
if dup:
    await write_audit(session, source=payload.source, event=AuditEvent.DEDUP_SKIP)
    return {"status": "duplicate", "job_id": None}
```

**Eligibility + Job insert pattern** (`main.py` lines 224–274):
```python
result = check_eligibility(
    title=payload.title,
    location=payload.location,
    jd_text=payload.clean_jd,
    config=config,
)
status = JobStatus.QUEUED if result.passed else JobStatus.REJECTED
job = Job(
    id=str(uuid.uuid4()),
    url=payload.url,
    url_hash=url_hash,
    title=payload.title,
    title_normalized=payload.title.lower().strip(),
    company=payload.company,
    company_normalized=payload.company.lower().strip(),
    location=payload.location,
    location_normalized=(payload.location or "").lower().strip(),
    source=payload.source,
    clean_jd=payload.clean_jd,
    apply_type=payload.apply_type,
    status=status,
    rejection_reason=result.reason,
)
session.add(job)
audit_event = AuditEvent.QUEUED if result.passed else AuditEvent.FILTERED_REJECT
await write_audit(session, source=payload.source, event=audit_event,
                  job_id=job.id, reason=result.reason)
return {"status": status.value, "job_id": job.id}
```

**Error handling pattern** — wrap endpoint body in try/except; return HTTP 503 with `{"status": "challenge_detected", "detail": "..."}` for OPS-01 signals (see Shared Patterns below).

---

### `src/api/routes/scrape.py` (controller, request-response)

**Analog:** `main.py` (structlog + session dependency pattern)

**JobSpy async executor pattern** (RESEARCH.md Pattern 4 — no codebase analog):
```python
from fastapi.concurrency import run_in_threadpool
from functools import partial
from jobspy import scrape_jobs

@router.post("/scrape-jobspy")
async def scrape_jobspy(payload: ScrapeJobSpyIn, session: AsyncSession = Depends(get_session)):
    # CRITICAL: scrape_jobs() is synchronous (pandas-based).
    # Must use run_in_threadpool to avoid blocking the FastAPI event loop.
    jobs_df = await run_in_threadpool(
        partial(
            scrape_jobs,
            site_name=payload.site_names,
            search_term=payload.search_term,
            location=payload.location,
            results_wanted=payload.results_wanted,
            hours_old=payload.hours_old,
        )
    )
    if jobs_df is None or len(jobs_df) == 0:
        log.warning("scrape_jobspy_zero_results", search_term=payload.search_term)
        # OPS-01: zero results may indicate IP block
        return {"jobs": [], "warning": "zero_results"}
    return {"jobs": jobs_df[["title", "company", "location", "job_url", "description"]].to_dict(orient="records")}
```

**Structlog pattern** (`main.py` lines 39–39 + usage throughout):
```python
log = structlog.get_logger()
log.info("scrape_jobspy_complete", count=len(jobs_df), search_term=payload.search_term)
```

---

### `src/api/routes/gmail.py` (controller, event-driven)

**Analog:** `main.py` (env config + session factory pattern)

**historyId read/write pattern** (RESEARCH.md Code Examples — no codebase analog):
```python
from sqlalchemy import select
from src.queue.models import AgentConfig  # new model added in Phase 2

# Read current historyId
result = await session.execute(
    select(AgentConfig).where(AgentConfig.key == "gmail_history_id")
)
row = result.scalar_one_or_none()
history_id = row.value if row else None

# Write updated historyId (merge = upsert)
await session.merge(AgentConfig(key="gmail_history_id", value=new_history_id))
```

**Env config pattern** (`main.py` lines 154–156):
```python
# All file paths resolved via os.environ — same pattern as main.py
token_path = os.environ.get("GOOGLE_TOKEN_PATH", ".google_token.json")
credentials_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", ".google_credentials.json")
```

---

### `src/api/routes/resume.py` (controller, request-response)

**Analog:** `main.py` (env config + structlog + session dependency pattern)

**Resume directory pattern** (env config from `main.py` lines 154–156):
```python
resumes_dir = os.environ.get("RESUMES_DIR", "resumes")
```

**Anthropic SDK call pattern** (new for Phase 2 — no codebase analog):
```python
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env automatically

message = client.messages.create(
    model="claude-haiku-3-5",
    max_tokens=256,
    messages=[{"role": "user", "content": selection_prompt}],
)
resume_name = message.content[0].text.strip()
```

---

### `src/api/routes/application.py` (controller, CRUD)

**Analog:** `main.py` (session.begin + Job model update + audit)

**Job state transition pattern** (`main.py` lines 199–274, adapted for UPDATE not INSERT):
```python
from sqlalchemy import select, update
from src.queue.models import Job, JobStatus
from src.audit_log import AuditEvent, write_audit

@router.post("/write-application")
async def write_application(payload: WriteApplicationIn, session: AsyncSession = Depends(get_session)):
    async with session.begin():
        result = await session.execute(select(Job).where(Job.id == payload.job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        job.resume_template = payload.resume_name
        job.cover_letter = payload.cover_letter
        job.status = JobStatus.APPLYING
        job.updated_at = datetime.utcnow()
        await write_audit(session, source="api", event=AuditEvent.APPLYING, job_id=job.id)
    return {"status": "ok"}

@router.post("/mark-submitted")
async def mark_submitted(payload: MarkSubmittedIn, session: AsyncSession = Depends(get_session)):
    async with session.begin():
        result = await session.execute(select(Job).where(Job.id == payload.job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        job.status = JobStatus.SUBMITTED
        job.updated_at = datetime.utcnow()
        await write_audit(session, source="api", event=AuditEvent.SUBMITTED, job_id=job.id)
    return {"status": "ok"}
```

**Relationship INSERT pattern** (`src/queue/models.py` lines 53–65 — Application model):
```python
# When marking submitted, also create an Application row
application = Application(
    job_id=job.id,
    resume_template=payload.resume_name,
    cover_letter=payload.cover_letter,
    submitted_at=datetime.utcnow(),
)
session.add(application)
```

---

### `src/ingestion/gmail_client.py` (service, event-driven)

**Analog:** None in codebase. Use RESEARCH.md patterns exclusively.

**Token refresh pattern** (RESEARCH.md Code Examples):
```python
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

def get_gmail_service(token_path: str):
    creds = Credentials.from_authorized_user_file(token_path)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)
```

**historyId polling pattern** (RESEARCH.md Pattern 3):
```python
from googleapiclient.errors import HttpError

def poll_gmail_since(service, start_history_id: str | None, sender_filter: str) -> tuple[list[str], str]:
    """Returns (new_message_ids, new_history_id). Handles 404 fallback."""
    if start_history_id is None:
        # First run — get baseline historyId from most recent message
        msgs = service.users().messages().list(
            userId="me", q=f"from:{sender_filter}", maxResults=1
        ).execute()
        if not msgs.get("messages"):
            return [], ""
        msg = service.users().messages().get(
            userId="me", id=msgs["messages"][0]["id"], format="minimal"
        ).execute()
        return [], msg["historyId"]

    try:
        # Normal path
        changes = []
        page_token = None
        latest_history_id = start_history_id
        while True:
            response = service.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                pageToken=page_token,
            ).execute()
            latest_history_id = response.get("historyId", latest_history_id)
            for record in response.get("history", []):
                for msg in record.get("messagesAdded", []):
                    changes.append(msg["message"]["id"])
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        # Filter by sender
        matching_ids = []
        for msg_id in changes:
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="metadata",
                metadataHeaders=["From"]
            ).execute()
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            if sender_filter in headers.get("From", ""):
                matching_ids.append(msg_id)
        return matching_ids, latest_history_id

    except HttpError as e:
        if e.resp.status == 404:
            # historyId expired — fall back to baseline acquisition
            log.warning("gmail_history_id_expired", error=str(e))
            return poll_gmail_since(service, None, sender_filter)
        raise
```

**Structlog pattern** — same as all other modules: `log = structlog.get_logger()` at module level.

---

### `src/ingestion/kalibrr_scraper.py` (service, batch)

**Analog:** None in codebase. httpx + BeautifulSoup4 is new for Phase 2.

**Async HTTP pattern** (new — no codebase analog):
```python
import httpx
from bs4 import BeautifulSoup

async def scrape_kalibrr(search_term: str, max_pages: int = 3) -> list[dict]:
    """Scrape Kalibrr job listings. CSS selectors must be verified against live HTML."""
    jobs = []
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True) as client:
        for page in range(1, max_pages + 1):
            resp = await client.get(
                "https://www.kalibrr.com/job-board",
                params={"search": search_term, "page": page},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            # TODO: CSS selectors must be verified by inspecting live Kalibrr HTML
            # (see RESEARCH.md Open Question 1 — do not hardcode without verification)
            cards = soup.select("div[data-testid='job-card']")  # PLACEHOLDER — verify
            if not cards:
                break
            for card in cards:
                jobs.append({
                    "title": card.select_one("h2").get_text(strip=True),
                    "company": card.select_one("[data-testid='company-name']").get_text(strip=True),
                    "location": card.select_one("[data-testid='job-location']").get_text(strip=True),
                    "url": card.select_one("a")["href"],
                })
    return jobs
```

---

### `src/ingestion/jobspy_runner.py` (service, batch)

**Analog:** None in codebase. python-jobspy is new for Phase 2.

**Sync-in-async executor pattern** (RESEARCH.md Pattern 4):
```python
import asyncio
from functools import partial
from jobspy import scrape_jobs

async def run_jobspy(
    search_term: str,
    location: str = "Remote",
    results_wanted: int = 25,
    hours_old: int = 24,
    site_names: list[str] | None = None,
) -> list[dict]:
    """Run synchronous scrape_jobs() in a thread executor to avoid blocking the event loop."""
    if site_names is None:
        site_names = ["indeed"]
    loop = asyncio.get_event_loop()
    jobs_df = await loop.run_in_executor(
        None,
        partial(
            scrape_jobs,
            site_name=site_names,
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
        ),
    )
    if jobs_df is None or jobs_df.empty:
        return []
    keep = ["title", "company", "location", "job_url", "description"]
    return jobs_df[keep].where(jobs_df[keep].notna(), other=None).to_dict(orient="records")
```

---

### `src/preparation/resume_reader.py` (utility, file-I/O)

**Analog:** None in codebase. python-docx and PyMuPDF are new for Phase 2.

**File extraction pattern** (RESEARCH.md Pattern 6):
```python
import fitz  # PyMuPDF — import name "fitz" is maintained as compatibility alias
from docx import Document
from pathlib import Path

def extract_resume_text(filepath: str | Path) -> str:
    """Extract plain text from a .pdf or .docx resume file."""
    path = str(filepath)
    if path.endswith(".pdf"):
        doc = fitz.open(path)
        return "\n".join(page.get_text() for page in doc)
    elif path.endswith(".docx"):
        doc = Document(path)
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
    raise ValueError(f"Unsupported file type: {path}")

def list_resumes(resumes_dir: str | Path) -> list[dict]:
    """Return list of {name, path, text} for all .pdf and .docx files in resumes_dir."""
    resumes_path = Path(resumes_dir)
    result = []
    for f in resumes_path.iterdir():
        if f.suffix in {".pdf", ".docx"}:
            result.append({
                "name": f.name,
                "path": str(f),
                "text": extract_resume_text(f),
            })
    return result
```

---

### `src/queue/models.py` (model, CRUD — modification)

**Analog:** Itself — add `AgentConfig` model following the existing `EligibilityConfigSnapshot` pattern.

**Existing model pattern** (`src/queue/models.py` lines 68–75):
```python
class EligibilityConfigSnapshot(Base):
    """Audit trail of eligibility config changes."""
    __tablename__ = "eligibility_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_json = Column(Text, nullable=False)
    applied_at = Column(DateTime, nullable=False, default=datetime.utcnow)
```

**New AgentConfig model to add** (RESEARCH.md Code Examples):
```python
class AgentConfig(Base):
    """Key-value store for agent runtime state (e.g., gmail_history_id)."""
    __tablename__ = "agent_config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**db.py import registration** — must also add `import src.queue.models` in `src/queue/db.py` line 12 comment block to ensure `AgentConfig` is registered with `Base.metadata` before `create_all()` runs. The existing comment says: _"Adding a new model? Import it here."_

---

### `src/audit_log.py` (model/utility — modification)

**Analog:** Itself — extend `AuditEvent` StrEnum with Phase 2 values.

**Existing enum pattern** (`src/audit_log.py` lines 13–19):
```python
class AuditEvent(StrEnum):
    DISCOVERED = "DISCOVERED"
    FILTERED_PASS = "FILTERED_PASS"
    FILTERED_REJECT = "FILTERED_REJECT"
    DEDUP_SKIP = "DEDUP_SKIP"
    QUEUED = "QUEUED"
    DRY_RUN_WOULD_QUEUE = "DRY_RUN_WOULD_QUEUE"
    DRY_RUN_WOULD_REJECT = "DRY_RUN_WOULD_REJECT"
```

**New values to append** (from CONTEXT.md `## Existing Code Insights`):
```python
    APPLYING = "APPLYING"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"
    NOTIFIED = "NOTIFIED"
```

No other changes to `audit_log.py` — `write_audit()` and `AuditLogEntry` are unchanged.

---

### `config/profile.yaml` (config — new file)

**Analog:** `config/eligibility.yaml` (YAML config loaded via Pydantic at startup)

**YAML structure pattern** (`config/eligibility.yaml` lines 1–43 — header comment + section structure):
```yaml
# Profile configuration for AI cover letter and resume selection prompts
# Edit freely — changes take effect on next run (no code changes needed)

summary: >
  Senior Product Manager with 7+ years driving 0-to-1 products at B2B SaaS and marketplace companies.
  Track record of shipping data-driven features that grow DAU and revenue.

target_roles:
  - "Product Manager"
  - "Senior Product Manager"
  - "Head of Product"

key_projects:
  - name: "Growth Flywheel — Marketplace Platform"
    impact: "Increased GMV 34% in 6 months by redesigning seller onboarding"
  - name: "ML Recommendations Engine"
    impact: "Reduced churn 18% by personalizing home feed for 2M users"

skills:
  - "Product strategy"
  - "Data analysis (SQL, Amplitude)"
  - "Stakeholder alignment"
  - "Agile / Sprint planning"

location_preference: "Remote — Philippines / Southeast Asia based"
availability: "Immediate"
```

**Config loader pattern** — create `src/preparation/profile_loader.py` following `src/filter/config_loader.py` lines 1–59 exactly: `yaml.safe_load()` → `EligibilityConfig.model_validate()` equivalent for `ProfileConfig` Pydantic model.

---

### `pyproject.toml` (config — modification)

**Analog:** Itself — add Phase 2 dependencies to `[project] dependencies`.

**Existing pattern** (`pyproject.toml` lines 1–15):
```toml
[project]
name = "job-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "aiosqlite>=0.20",
    "sqlalchemy[asyncio]>=2.0",
    ...
]
```

**New dependencies to add** (from RESEARCH.md Standard Stack):
```toml
    "fastapi>=0.136",
    "uvicorn>=0.48",
    "python-jobspy>=1.1.82",
    "google-api-python-client>=2.196",
    "google-auth-oauthlib>=1.4",
    "google-auth>=2.53",
    "python-docx>=1.2",
    "pymupdf>=1.27",
    "anthropic>=0.104",
    "httpx>=0.28",
    "beautifulsoup4>=4.14",
```

---

## Shared Patterns

### Session Handling (apply to all route files)
**Source:** `main.py` lines 199–200 and `src/queue/db.py` lines 53–56
**Apply to:** `src/api/routes/ingest.py`, `src/api/routes/application.py`, `src/api/routes/gmail.py`, `src/api/routes/scrape.py`, `src/api/routes/resume.py`
```python
# All DB writes follow this exact pattern — no exceptions
async with session_factory() as session:
    async with session.begin():
        # reads and writes here
        # session.begin() auto-commits on block exit, auto-rolls-back on exception
```

### Structlog Pattern (apply to all new Python files)
**Source:** `main.py` lines 29–39
**Apply to:** All new `src/` files
```python
import structlog

log = structlog.get_logger()

# All log calls use keyword arguments only — no positional message string
log.info("event_name", key1=value1, key2=value2)
log.warning("event_name", key1=value1)
log.error("event_name", error=str(e))
```

### Env Config Pattern (apply to all files that read paths)
**Source:** `main.py` lines 154–156
**Apply to:** `src/api/app.py`, `src/ingestion/gmail_client.py`, `src/preparation/resume_reader.py`
```python
# All path resolution uses os.environ.get() with safe defaults
# load_dotenv() must be called first (in app.py lifespan, not in individual modules)
db_path = os.environ.get("DB_PATH", "data/jobs.db")
config_path = os.environ.get("ELIGIBILITY_CONFIG_PATH", "config/eligibility.yaml")
resumes_dir = os.environ.get("RESUMES_DIR", "resumes")
token_path = os.environ.get("GOOGLE_TOKEN_PATH", ".google_token.json")
```

### Audit Write Pattern (apply to all state-changing routes)
**Source:** `src/audit_log.py` lines 35–66
**Apply to:** `src/api/routes/ingest.py`, `src/api/routes/application.py`
```python
# Always called inside session.begin() block — caller owns the transaction
await write_audit(
    session,
    source="api",            # use module/source identifier
    event=AuditEvent.QUEUED, # use typed enum, never raw string
    job_id=job.id,           # None is valid for dedup-skipped entries
    reason=result.reason,    # None for non-rejection events
)
```

### OPS-01 Challenge Signal Pattern (apply to scraper routes)
**Source:** RESEARCH.md Pattern 8 (no codebase analog)
**Apply to:** `src/api/routes/scrape.py`, `src/api/routes/gmail.py`
```python
# FastAPI returns HTTP 503 + structured body to signal challenge detection
# n8n IF node checks for this status to branch to Telegram alert
from fastapi import HTTPException

# On CAPTCHA / auth failure detection:
raise HTTPException(
    status_code=503,
    detail={"status": "challenge_detected", "detail": "CAPTCHA on Indeed search"}
)

# On zero-result scrape (possible IP block — Pitfall 3):
if len(jobs) == 0:
    log.warning("scrape_zero_results_possible_block", source="indeed")
    return {"jobs": [], "warning": "zero_results_possible_block"}
```

### Pydantic BaseModel Pattern (apply to all schema definitions)
**Source:** `src/filter/config_loader.py` lines 8–39
**Apply to:** `src/api/schemas.py`
```python
from pydantic import BaseModel, Field

# Use | None = None for optional fields (Python 3.10+ union syntax — matches existing codebase)
# Use Field(default_factory=list) for optional list fields
# Use Field(ge=1, le=100) for bounded integers
```

---

## No Analog Found

Files with no close match in the codebase — planner should use RESEARCH.md patterns instead:

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/ingestion/gmail_client.py` | service | event-driven | No OAuth2 or Gmail API code exists in Phase 1 |
| `src/ingestion/kalibrr_scraper.py` | service | batch | No HTTP scraping code exists in Phase 1 |
| `src/ingestion/jobspy_runner.py` | service | batch | No job board scraping code exists in Phase 1 |
| `src/preparation/resume_reader.py` | utility | file-I/O | No file I/O code exists in Phase 1 |
| `n8n/workflows/*.json` | config | event-driven | n8n workflow JSON has no Python code analog |

For `n8n/workflows/*.json` files, use RESEARCH.md Pattern 5 (Claude API HTTP Request body), Pattern 7 (workflow split), and Pattern 8 (OPS-01 IF node). These are JSON configuration exports, not Python code — no pattern extraction from this codebase applies.

---

## Metadata

**Analog search scope:** `/Users/stefano/Documents/Workspaces/Job Application Automation/src/`, `main.py`, `pyproject.toml`, `Dockerfile`, `config/`, `tests/`
**Files scanned:** 14 (9 src/*.py, main.py, pyproject.toml, Dockerfile, config/eligibility.yaml, 4 test files)
**Pattern extraction date:** 2026-05-28
