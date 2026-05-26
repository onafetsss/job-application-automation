# Phase 1: Foundation - Pattern Map

**Mapped:** 2026-05-26
**Files analyzed:** 10 (new files to be created in this phase)
**Analogs found:** 0 / 10 — greenfield project; this phase establishes all base patterns

---

## Context

This is a greenfield Python 3.11 project. No existing source code exists. Phase 1 establishes the patterns that all subsequent phases must follow. This document defines the conventions the planner MUST encode into every plan — they replace analog excerpts for this first phase.

---

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `pyproject.toml` | config | — | none | no analog |
| `.env.example` | config | — | none | no analog |
| `config/eligibility.yaml` | config | — | none | no analog |
| `src/queue/db.py` | utility | CRUD | none | no analog |
| `src/queue/models.py` | model | CRUD | none | no analog |
| `src/filter/config_loader.py` | utility | request-response | none | no analog |
| `src/filter/eligibility.py` | service | request-response | none | no analog |
| `src/filter/dedup.py` | utility | CRUD | none | no analog |
| `src/audit_log.py` | utility | CRUD | none | no analog |
| `main.py` | controller | request-response | none | no analog |

---

## Pattern Assignments

### `pyproject.toml` (config)

**Purpose:** Single source of truth for dependencies, tool config (ruff, mypy, pytest), and project metadata. No `setup.py`. No `requirements.txt`.

**Pattern to follow:**

```toml
[project]
name = "job-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "aiosqlite>=0.20",
    "sqlalchemy>=2.0",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "rapidfuzz>=3.0",
    "structlog>=24.0",
    "python-dotenv>=1.0",
    "tenacity>=8.0",
]

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "UP"]

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.10",
]
```

**Key constraint:** All dependencies installed via `uv sync`, not `pip install`. Dev extras installed via `uv sync --group dev`.

---

### `.env.example` (config)

**Purpose:** Template for secrets. Committed to git. Actual `.env` is gitignored.

**Pattern to follow:**

```bash
# Database
DB_PATH=data/jobs.db

# Eligibility config
ELIGIBILITY_CONFIG_PATH=config/eligibility.yaml

# Telegram (Phase 2+)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Anthropic (Phase 2+)
ANTHROPIC_API_KEY=

# Gmail OAuth (Phase 2+)
GOOGLE_CREDENTIALS_PATH=
GOOGLE_TOKEN_PATH=
```

**Key constraint:** Never hardcode secrets. All personal data (salary expectations, etc.) must also be environment variables, not in config files.

---

### `config/eligibility.yaml` (config)

**Purpose:** Human-editable eligibility rules. Drives `src/filter/eligibility.py` entirely. Changes take effect on next run without code changes.

**Pattern to follow:**

```yaml
# Eligibility configuration for autonomous job application agent
# Edit freely — changes take effect on next run (no code changes needed)

roles:
  include:
    # Job title must contain at least one of these strings (case-insensitive)
    - "Product Manager"
    - "Senior Product Manager"
    - "Principal Product Manager"
    - "Head of Product"
  exclude:
    # Reject if title contains any of these (applied after include check)
    - "Internship"
    - "Graduate Program"
    - "Entry Level"
    - "Junior"
    - "0-2 years"

location:
  allow_remote: true
  allowed_locations:
    # Accept jobs in any of these locations (case-insensitive substring match)
    - "Philippines"
    - "Manila"
    - "Remote"
    - "Worldwide"
  blocked_phrases:
    # Reject if JD contains any of these phrases (catches "US only", "must be authorized")
    - "must be authorized to work in the US"
    - "US citizens only"
    - "requires US work authorization"
    - "must be located in"

salary:
  skip_if_no_data: false   # true = skip all jobs without salary info
  min_annual_usd: 0        # set to non-zero to filter by salary floor

keywords:
  blocklist:
    # Reject regardless of title match if any of these appear in the JD
    - "Clearance required"
    - "Security clearance"
```

**Key constraint:** Pydantic v2 model in `config_loader.py` validates this YAML on load. A malformed YAML or missing required key must raise a clear error with the field name, not silently use defaults.

---

### `src/queue/db.py` (utility, CRUD)

**Purpose:** SQLite engine setup with WAL mode, async session factory, and schema initialisation. All other modules import the session factory from here — never create their own engine.

**Pattern to follow:**

```python
import asyncio
from pathlib import Path

import aiosqlite
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from src.queue.models import Base

_engine: AsyncEngine | None = None


def get_engine(db_path: str = "data/jobs.db") -> AsyncEngine:
    """Return the singleton async engine, creating it if needed."""
    global _engine
    if _engine is None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine


async def init_db(db_path: str = "data/jobs.db") -> None:
    """Create all tables and enable WAL mode. Call once at startup."""
    engine = get_engine(db_path)
    async with engine.begin() as conn:
        # WAL mode: allows concurrent reads during writes (required for multi-reader access)
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)


def get_session_factory(db_path: str = "data/jobs.db") -> sessionmaker:
    """Return an async session factory for use in services."""
    engine = get_engine(db_path)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

**Key constraints:**
- WAL mode MUST be set on every startup via `PRAGMA journal_mode=WAL`.
- `foreign_keys=ON` must be set to enforce referential integrity.
- The engine is a module-level singleton — never instantiate per-request.
- `expire_on_commit=False` prevents lazy-load errors after commit in async context.

---

### `src/queue/models.py` (model, CRUD)

**Purpose:** SQLAlchemy 2.0 ORM models for all Phase 1 tables. These models are the authoritative data contract — downstream phases must not add columns without updating this file.

**Pattern to follow:**

```python
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class JobStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    QUEUED = "QUEUED"
    REJECTED = "REJECTED"
    APPLYING = "APPLYING"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    url = Column(Text, unique=True, nullable=False)
    url_hash = Column(String(64), unique=True, nullable=False)  # SHA-256, fast dedup
    title = Column(Text, nullable=False)
    title_normalized = Column(Text, nullable=False)             # lowercase, stripped
    company = Column(Text, nullable=False)
    company_normalized = Column(Text, nullable=False)           # lowercase, stripped
    location = Column(Text)
    location_normalized = Column(Text)                          # lowercase, stripped
    source = Column(String, nullable=False)                     # 'linkedin_email'|'kalibrr'|'indeed'
    apply_type = Column(String)                                 # set during normalisation (Phase 2+)
    raw_jd = Column(Text)                                       # raw job description HTML
    clean_jd = Column(Text)                                     # stripped plain-text JD
    status = Column(String, nullable=False, default=JobStatus.DISCOVERED)
    rejection_reason = Column(String)                           # e.g. 'title_mismatch'|'location_mismatch'
    retry_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime)
    claimed_at = Column(DateTime)
    # Phase 2+ fields (nullable in Phase 1 — set when application is prepared)
    resume_template = Column(String)
    cover_letter = Column(Text)
    screening_answers = Column(Text)                            # JSON blob
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    applications = relationship("Application", back_populates="job")


class Application(Base):
    __tablename__ = "applications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    resume_template = Column(String, nullable=False)
    cover_letter = Column(Text, nullable=False)
    screening_answers = Column(Text)                            # JSON blob
    submitted_at = Column(DateTime)
    error_log = Column(Text)                                    # JSON blob on failure
    notified_at = Column(DateTime)

    job = relationship("Job", back_populates="applications")


class EligibilityConfigSnapshot(Base):
    """Audit trail of eligibility config changes."""
    __tablename__ = "eligibility_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_json = Column(Text, nullable=False)
    applied_at = Column(DateTime, nullable=False, default=datetime.utcnow)
```

**Key constraints:**
- Use `str(uuid.uuid4())` as primary key — not auto-increment integers.
- `url_hash` (SHA-256) is the fast dedup key — always indexed via UNIQUE constraint.
- `_normalized` columns store lowercased/stripped values for fuzzy match comparison.
- `JobStatus` enum values match D-05: `DISCOVERED → QUEUED | REJECTED → APPLYING → SUBMITTED | FAILED`.
- Phase 2+ fields (`resume_template`, `cover_letter`, `screening_answers`) are defined now (nullable) so the schema never needs migration to add them.

---

### `src/filter/config_loader.py` (utility, request-response)

**Purpose:** Load and validate `eligibility.yaml` into a typed Pydantic v2 model. Single function called at startup and when config changes.

**Pattern to follow:**

```python
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class RolesConfig(BaseModel):
    include: list[str] = Field(min_length=1)
    exclude: list[str] = Field(default_factory=list)


class LocationConfig(BaseModel):
    allow_remote: bool = True
    allowed_locations: list[str] = Field(default_factory=list)
    blocked_phrases: list[str] = Field(default_factory=list)


class SalaryConfig(BaseModel):
    skip_if_no_data: bool = False
    min_annual_usd: int = 0


class KeywordsConfig(BaseModel):
    blocklist: list[str] = Field(default_factory=list)


class EligibilityConfig(BaseModel):
    roles: RolesConfig
    location: LocationConfig = Field(default_factory=LocationConfig)
    salary: SalaryConfig = Field(default_factory=SalaryConfig)
    keywords: KeywordsConfig = Field(default_factory=KeywordsConfig)

    @model_validator(mode="after")
    def check_at_least_one_role(self) -> "EligibilityConfig":
        if not self.roles.include:
            raise ValueError("eligibility.yaml must define at least one role in roles.include")
        return self


def load_eligibility_config(path: str | Path) -> EligibilityConfig:
    """Load and validate eligibility.yaml. Raises on missing file or invalid schema."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Eligibility config not found: {config_path}")
    with config_path.open() as f:
        raw = yaml.safe_load(f)
    return EligibilityConfig.model_validate(raw)
```

**Key constraints:**
- Use `pydantic.BaseModel` with `model_validate()` (Pydantic v2 style — never `parse_obj`).
- Validation errors surface field names clearly — no `try/except` that swallows detail.
- Returns the typed model, never the raw dict.
- File path comes from `os.environ` in `main.py` — this function is pure (no env var reads).

---

### `src/filter/eligibility.py` (service, request-response)

**Purpose:** Apply hard eligibility rules from `EligibilityConfig` to a job lead. Returns `(passed: bool, reason: str | None)`. No I/O — pure function, fully testable without a database.

**Pattern to follow:**

```python
from dataclasses import dataclass

from src.filter.config_loader import EligibilityConfig


@dataclass
class FilterResult:
    passed: bool
    reason: str | None = None  # populated only when passed=False; matches CONTEXT.md D-03 format


def _normalize(text: str) -> str:
    """Lowercase and strip for consistent matching."""
    return text.lower().strip()


def check_eligibility(
    title: str,
    location: str | None,
    jd_text: str | None,
    config: EligibilityConfig,
) -> FilterResult:
    """
    Apply eligibility rules in order. First failing rule short-circuits.
    Returns FilterResult(passed=True) if all rules pass.
    """
    title_lower = _normalize(title)
    jd_lower = _normalize(jd_text or "")

    # 1. Title include check — must match at least one allowed pattern
    if not any(_normalize(kw) in title_lower for kw in config.roles.include):
        return FilterResult(passed=False, reason="title_mismatch")

    # 2. Title exclude check — reject if any excluded keyword present
    for kw in config.roles.exclude:
        if _normalize(kw) in title_lower:
            return FilterResult(passed=False, reason="title_mismatch")

    # 3. JD keyword blocklist — reject if any blocked phrase in job description
    for phrase in config.keywords.blocklist:
        if _normalize(phrase) in jd_lower:
            return FilterResult(passed=False, reason="keyword_blocklist")

    # 4. Location check
    if location is not None:
        location_lower = _normalize(location)
        # Blocked phrases in JD (e.g. "US work authorization required")
        for phrase in config.location.blocked_phrases:
            if _normalize(phrase) in jd_lower:
                return FilterResult(passed=False, reason="location_mismatch")
        # Must match at least one allowed location (or allow_remote covers it)
        if not config.location.allow_remote or "remote" not in location_lower:
            if not any(_normalize(loc) in location_lower for loc in config.location.allowed_locations):
                return FilterResult(passed=False, reason="location_mismatch")

    return FilterResult(passed=True)
```

**Key constraints:**
- Pure function — no database access, no file I/O, no global state.
- Reason strings use underscore format matching `rejection_reason` column values: `title_mismatch`, `location_mismatch`, `keyword_blocklist`.
- Dry-run output format (D-02, D-03): `REJECTED: title mismatch` — planner converts `reason` to display string in `main.py`.
- Rules apply in a fixed priority order; first failure short-circuits (do not report multiple reasons).

---

### `src/filter/dedup.py` (utility, CRUD)

**Purpose:** Cross-source deduplication using compound fuzzy match on `(company, title, location)`. Called before inserting a new job into the database. Also provides the URL hash function used as the primary fast-dedup key.

**Pattern to follow:**

```python
import hashlib
from urllib.parse import urlparse, urlencode, parse_qs

from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.queue.models import Job


DEDUP_THRESHOLD = 85  # Per CONTEXT.md D-08: ~85% similarity floor


def hash_url(url: str) -> str:
    """SHA-256 of the canonical URL. Used as the fast exact-dedup key."""
    canonical = _canonicalize_url(url)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _canonicalize_url(url: str) -> str:
    """Strip tracking params, normalize scheme and host to lowercase."""
    parsed = urlparse(url.lower().strip())
    # Strip known tracking query params
    tracking_params = {"utm_source", "utm_medium", "utm_campaign", "trk", "refId"}
    qs = {k: v for k, v in parse_qs(parsed.query).items() if k not in tracking_params}
    return parsed._replace(query=urlencode(qs, doseq=True)).geturl()


def _similarity_score(a: str, b: str) -> float:
    """Token sort ratio — handles word order differences ('Acme Corp' vs 'Corp Acme')."""
    return fuzz.token_sort_ratio(a.lower(), b.lower())


async def is_duplicate(
    session: AsyncSession,
    company: str,
    title: str,
    location: str | None,
    url_hash: str,
) -> bool:
    """
    Returns True if an identical or near-identical job already exists.

    Fast path: exact URL hash match (O(1) index lookup).
    Slow path: fuzzy compound match on company + title + location for cross-source dedup.
    """
    # Fast path: exact URL hash match
    result = await session.execute(select(Job).where(Job.url_hash == url_hash))
    if result.scalar_one_or_none():
        return True

    # Slow path: fuzzy compound match — only needed when URL differs across sources
    existing = await session.execute(
        select(Job.company_normalized, Job.title_normalized, Job.location_normalized)
    )
    for row in existing:
        company_sim = _similarity_score(company, row.company_normalized)
        title_sim = _similarity_score(title, row.title_normalized)
        location_sim = _similarity_score(location or "", row.location_normalized or "")
        # Weighted average: company + title weighted higher than location
        combined = (company_sim * 0.4 + title_sim * 0.4 + location_sim * 0.2)
        if combined >= DEDUP_THRESHOLD:
            return True

    return False
```

**Key constraints:**
- Use `rapidfuzz` (not `thefuzz`) — C extension, ~10x faster, same API surface.
- `DEDUP_THRESHOLD = 85` per D-08. Defined as a named constant, not a magic number.
- URL hash fast path always checked first to avoid the O(N) fuzzy scan when URL is identical.
- Async signature — must be called with `await` inside an `AsyncSession` context.

---

### `src/audit_log.py` (utility, CRUD)

**Purpose:** Write structured audit log entries to both structlog (stdout) and the `audit_log` table in SQLite. Every filter decision and job state transition is recorded here.

**Pattern to follow:**

```python
from datetime import datetime
from enum import Enum

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase

from src.queue.models import Base

log = structlog.get_logger()


class AuditEvent(str, Enum):
    DISCOVERED = "DISCOVERED"
    FILTERED_PASS = "FILTERED_PASS"
    FILTERED_REJECT = "FILTERED_REJECT"
    DEDUP_SKIP = "DEDUP_SKIP"
    QUEUED = "QUEUED"
    DRY_RUN_WOULD_QUEUE = "DRY_RUN_WOULD_QUEUE"
    DRY_RUN_WOULD_REJECT = "DRY_RUN_WOULD_REJECT"


class AuditLogEntry(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String)                    # NULL for dedup-skipped entries (no row created)
    source = Column(String, nullable=False)    # ingestion source identifier
    event = Column(String, nullable=False)     # AuditEvent value
    reason = Column(String)                    # rejection reason or None
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    details = Column(Text)                     # optional JSON for extra context


async def write_audit(
    session: AsyncSession,
    *,
    source: str,
    event: AuditEvent,
    job_id: str | None = None,
    reason: str | None = None,
    details: str | None = None,
) -> None:
    """Write one audit log entry to DB and emit a structlog event."""
    entry = AuditLogEntry(
        job_id=job_id,
        source=source,
        event=event.value,
        reason=reason,
        details=details,
    )
    session.add(entry)
    # Also emit to structlog so stdout is a complete audit trail
    log.info(
        "audit",
        job_id=job_id,
        source=source,
        event=event.value,
        reason=reason,
    )
```

**Key constraints:**
- All `write_audit` calls must be `await`ed inside the same session as the job insert/update — they are committed together atomically.
- `structlog` is configured at startup (in `main.py`) with JSON renderer for machine-readable stdout.
- `job_id` is nullable — dedup skips have no DB row to reference.
- The `AuditEvent` enum covers dry-run events explicitly (`DRY_RUN_WOULD_QUEUE`, `DRY_RUN_WOULD_REJECT`) to satisfy success criterion 3.

---

### `main.py` (controller, request-response)

**Purpose:** CLI entry point. Parses `--dry-run` flag and any future flags. Loads config. Initialises DB. Runs the filter pipeline against sample leads (in Phase 1) or live leads (Phase 2+). Prints dry-run output in scannable format per D-02/D-03.

**Pattern to follow:**

```python
import argparse
import asyncio
import os
from pathlib import Path

import structlog
from dotenv import load_dotenv

from src.queue.db import init_db, get_session_factory
from src.filter.config_loader import load_eligibility_config
from src.filter.eligibility import check_eligibility
from src.filter.dedup import hash_url, is_duplicate
from src.audit_log import write_audit, AuditEvent

load_dotenv()

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

log = structlog.get_logger()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous Job Application Agent")
    parser.add_argument("--dry-run", action="store_true", help="Filter jobs without submitting")
    parser.add_argument("--source", default="all", help="Ingestion source to run (default: all)")
    parser.add_argument("--limit", type=int, default=0, help="Max jobs to process (0 = unlimited)")
    return parser


def print_dry_run_row(title: str, company: str, status: str, reason: str | None) -> None:
    """Print one scannable dry-run line. Format: QUEUED  Senior PM @ Acme Corp (Remote)"""
    label = f"REJECTED: {reason.replace('_', ' ')}" if reason else "QUEUED"
    print(f"{label:<30} {title} @ {company}")


async def run(args: argparse.Namespace) -> None:
    db_path = os.environ.get("DB_PATH", "data/jobs.db")
    config_path = os.environ.get("ELIGIBILITY_CONFIG_PATH", "config/eligibility.yaml")

    await init_db(db_path)
    config = load_eligibility_config(config_path)
    session_factory = get_session_factory(db_path)

    log.info("startup", dry_run=args.dry_run, source=args.source)

    # Phase 1: iterate over sample leads; Phase 2+ replaces this with real ingestion
    async with session_factory() as session:
        async with session.begin():
            # TODO (Phase 2): replace sample_leads with real ingestion sources
            sample_leads: list[dict] = []
            for lead in sample_leads:
                result = check_eligibility(
                    title=lead["title"],
                    location=lead.get("location"),
                    jd_text=lead.get("clean_jd"),
                    config=config,
                )
                if args.dry_run:
                    print_dry_run_row(
                        lead["title"], lead["company"],
                        "QUEUED" if result.passed else "REJECTED",
                        result.reason,
                    )
                    event = AuditEvent.DRY_RUN_WOULD_QUEUE if result.passed else AuditEvent.DRY_RUN_WOULD_REJECT
                    await write_audit(
                        session, source=lead.get("source", "unknown"),
                        event=event, reason=result.reason,
                    )


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
```

**Key constraints:**
- `--dry-run` is the canonical flag name (D-01); accessed as `args.dry_run` (argparse converts hyphens to underscores).
- `--source` and `--limit` slots must be declared now so Phase 2+ can add values without changing the CLI interface.
- `load_dotenv()` called before any `os.environ` access.
- `structlog.configure()` called once at startup with JSON renderer — never called again inside modules.
- DB init and config load happen before any pipeline logic — fail fast on misconfiguration.
- Dry-run output (D-02, D-03): one line per job, left-aligned fixed-width status label, title and company.

---

## Shared Patterns

### Async Pattern
**Apply to:** `db.py`, `dedup.py`, `audit_log.py`, and all future service files.

```python
# Use SQLAlchemy async sessions — always as async context managers
async with session_factory() as session:
    async with session.begin():   # auto-commits or rolls back on exit
        # all DB operations here
        ...
```

Never use `session.commit()` explicitly — let `session.begin()` context manager handle it. Never use synchronous SQLAlchemy or `sqlite3` directly.

---

### Environment Variable Pattern
**Apply to:** `main.py` and any future entry point or scheduler.

```python
from dotenv import load_dotenv
import os

load_dotenv()  # must be called before any os.environ access

DB_PATH = os.environ.get("DB_PATH", "data/jobs.db")
```

All paths, tokens, and credentials come from environment variables. Defaults are safe local-dev values. Production values come from `.env` (gitignored).

---

### Structlog Pattern
**Apply to:** Every module that emits log events.

```python
import structlog

log = structlog.get_logger()

# At call sites — keyword arguments only, never positional after the event string
log.info("event_name", key=value, key2=value2)
log.error("error_name", error=str(exception), job_id=job_id)
```

Structlog is configured once in `main.py`. Modules only call `structlog.get_logger()` — they never call `structlog.configure()`.

---

### Error Handling Pattern
**Apply to:** All service and utility functions with external I/O.

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=5, max=45))
async def call_external_api(...):
    ...
```

- Wrap all external I/O (future: Gmail API, Anthropic API, Telegram) with `tenacity` retry.
- Phase 1 has no external I/O — establish the import convention now.
- Never `except Exception: pass` — catch specific exceptions and log with structlog before re-raising or returning a typed error result.

---

### Pydantic v2 Validation Pattern
**Apply to:** `config_loader.py` and all future config/schema models.

```python
# Pydantic v2 — use model_validate(), not parse_obj()
model = MyModel.model_validate(raw_dict)

# Field with default factory
field: list[str] = Field(default_factory=list)

# Model-level validator
@model_validator(mode="after")
def check_invariant(self) -> "MyModel":
    ...
    return self
```

---

## No Analog Found

All Phase 1 files have no codebase analog — this is a greenfield project.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `pyproject.toml` | config | — | Greenfield: no prior project config exists |
| `.env.example` | config | — | Greenfield: no prior env config exists |
| `config/eligibility.yaml` | config | — | Greenfield: first eligibility config |
| `src/queue/db.py` | utility | CRUD | Greenfield: no prior DB setup |
| `src/queue/models.py` | model | CRUD | Greenfield: no prior ORM models |
| `src/filter/config_loader.py` | utility | request-response | Greenfield: no prior YAML loader |
| `src/filter/eligibility.py` | service | request-response | Greenfield: no prior eligibility logic |
| `src/filter/dedup.py` | utility | CRUD | Greenfield: no prior dedup logic |
| `src/audit_log.py` | utility | CRUD | Greenfield: no prior audit logging |
| `main.py` | controller | request-response | Greenfield: no prior CLI entry point |

The patterns above are derived from the project's STACK.md, ARCHITECTURE.md, and PITFALLS.md research documents and establish the conventions all later phases inherit.

---

## Directory Structure to Create

The planner must include directory scaffolding in Phase 1:

```
Job Application Automation/
├── config/
│   └── eligibility.yaml
├── src/
│   ├── __init__.py
│   ├── queue/
│   │   ├── __init__.py
│   │   ├── db.py
│   │   └── models.py
│   └── filter/
│       ├── __init__.py
│       ├── config_loader.py
│       ├── eligibility.py
│       └── dedup.py
├── data/               # gitignored
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   └── __init__.py
│   └── integration/
│       └── __init__.py
├── main.py
├── src/audit_log.py
├── pyproject.toml
├── .env.example
├── .gitignore
└── Dockerfile          # stub only in Phase 1
```

`.gitignore` must include: `data/`, `.env`, `__pycache__/`, `*.db`, `.mypy_cache/`, `.ruff_cache/`, browser profile directories (`browser_profiles/`).

---

## Metadata

**Analog search scope:** N/A — greenfield project
**Files scanned:** 0 existing source files
**Pattern extraction date:** 2026-05-26
**Pattern source:** `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md`, `.planning/phases/01-foundation/01-CONTEXT.md`
