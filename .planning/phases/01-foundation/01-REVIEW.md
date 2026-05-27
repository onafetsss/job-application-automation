---
phase: 01-foundation
reviewed: 2026-05-27T00:00:00Z
depth: standard
files_reviewed: 22
files_reviewed_list:
  - .env.example
  - .gitignore
  - Dockerfile
  - config/eligibility.yaml
  - main.py
  - pyproject.toml
  - src/__init__.py
  - src/audit_log.py
  - src/filter/__init__.py
  - src/filter/config_loader.py
  - src/filter/dedup.py
  - src/filter/eligibility.py
  - src/queue/__init__.py
  - src/queue/db.py
  - src/queue/models.py
  - tests/__init__.py
  - tests/integration/__init__.py
  - tests/integration/test_cli.py
  - tests/integration/test_db_init.py
  - tests/integration/test_dedup.py
  - tests/integration/test_dry_run_pipeline.py
  - tests/unit/__init__.py
  - tests/unit/test_config_loader.py
  - tests/unit/test_eligibility.py
findings:
  critical: 3
  warning: 7
  info: 4
  total: 14
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-05-27T00:00:00Z
**Depth:** standard
**Files Reviewed:** 22
**Status:** issues_found

## Summary

This is a Python 3.11+ async greenfield foundation implementing a job dedup + eligibility pipeline backed by SQLite via SQLAlchemy async. The code is generally well-structured with clean separation of concerns. However, three blockers were found: the Dockerfile is non-functional as shipped (will crash on startup), the eligibility filter silently bypasses location-restriction phrases when a job has no location field, and the dedup slow-path matches against REJECTED jobs — permanently preventing re-evaluation of those jobs from alternate sources. Seven additional warnings cover per-connection SQLite PRAGMA scope, deprecated datetime APIs, broken in-memory test fixtures, and the ruff linting config being silently ignored.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Dockerfile Never Installs Project Dependencies — Container Crashes on Startup

**File:** `Dockerfile:4-5`
**Issue:** `pip install uv` installs the uv package manager but `uv sync` is never called. All project dependencies (`structlog`, `sqlalchemy`, `pydantic`, `aiosqlite`, `rapidfuzz`, etc.) are absent at runtime. `python main.py` crashes immediately with `ModuleNotFoundError` on the first import. The container is completely non-functional as shipped.
**Fix:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app

# Install uv for dependency management
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock* ./
# Install production deps into the system Python (no venv needed inside Docker)
RUN uv sync --no-dev --system

COPY . .

# Run as non-root for security
RUN useradd -r -s /bin/false agent
USER agent

# Persist the SQLite database across container restarts
VOLUME ["/app/data"]

CMD ["python", "main.py"]
```

---

### CR-02: Eligibility Filter Bypasses `blocked_phrases` Check When `location` Is `None`

**File:** `src/filter/eligibility.py:55-68`
**Issue:** The entire location check block — including the `blocked_phrases` scan of the JD — is guarded by `if location is not None:`. When a scraped lead omits the location field (a common occurrence with some boards), a JD containing `"must be authorized to work in the US"` or any other configured `blocked_phrases` value is **never checked**. The job passes the filter and gets queued for application. This directly defeats the primary protection against US-auth-required jobs for a Philippines-based user.

Concrete failing case:
```python
check_eligibility(
    title="Senior Product Manager",
    location=None,                                    # no location from scraper
    jd_text="Candidates must be authorized to work in the US",
    config=config,                                    # blocked_phrases configured
)
# Returns: FilterResult(passed=True)  <-- WRONG
```

**Fix:** Move the `blocked_phrases` check outside the `location is not None` guard. It operates on `jd_lower` which is available regardless of `location`:
```python
# 3. JD keyword blocklist
for phrase in config.keywords.blocklist:
    if _normalize(phrase) in jd_lower:
        return FilterResult(passed=False, reason="keyword_blocklist")

# 4a. Location blocked phrases in JD — check regardless of whether location field is present
for phrase in config.location.blocked_phrases:
    if _normalize(phrase) in jd_lower:
        return FilterResult(passed=False, reason="location_mismatch")

# 4b. Location allowlist check (only when location field is present)
if location is not None:
    location_lower = _normalize(location)
    if not config.location.allow_remote or "remote" not in location_lower:
        if not any(
            _normalize(loc) in location_lower
            for loc in config.location.allowed_locations
        ):
            return FilterResult(passed=False, reason="location_mismatch")
```

---

### CR-03: Dedup Slow-Path Matches Against `REJECTED` Jobs — Permanently Blocks Re-evaluation

**File:** `src/filter/dedup.py:63-73`
**Issue:** The fuzzy slow-path query fetches ALL rows from the `jobs` table with no status filter:
```python
existing = await session.execute(
    select(Job.company_normalized, Job.title_normalized, Job.location_normalized)
)
```
A job rejected due to `title_mismatch` or `location_mismatch` still occupies the table. When the same job appears from a second source (different URL), the slow-path fires first, returns `True`, and the pipeline emits `DEDUP_SKIP` — never reaching the eligibility check. Subsequent config changes that would now pass the job are also ineffective. The job is silently dropped forever.

**Fix:** Filter the slow-path query to only match non-rejected jobs:
```python
from src.queue.models import JobStatus

existing = await session.execute(
    select(Job.company_normalized, Job.title_normalized, Job.location_normalized)
    .where(Job.status.notin_([JobStatus.REJECTED]))
)
```

---

## Warnings

### WR-01: `PRAGMA foreign_keys=ON` Is Set Once and Does Not Apply to Subsequent Connections

**File:** `src/queue/db.py:47-49`
**Issue:** SQLite's `PRAGMA foreign_keys` is a **per-connection** setting, not a database-level setting. It is set only inside `init_db()` on the initial `engine.begin()` connection. All subsequent connections from the session factory (every application session) have foreign key enforcement disabled. Foreign key violations (e.g. an `AuditLogEntry` with a non-existent `job_id`, or an `Application` with a dangling `job_id`) will not be detected.

**Fix:** Use a SQLAlchemy `connect_args` event listener to set the pragma on every new connection:
```python
from sqlalchemy import event

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```
Remove the one-shot pragma from `init_db()`.

---

### WR-02: `datetime.utcnow()` Is Deprecated Since Python 3.12 — Produces Naive Datetimes

**File:** `src/audit_log.py:31`, `src/queue/models.py:47`, `src/queue/models.py:48`, `src/queue/models.py:74`
**Issue:** `datetime.utcnow()` is deprecated in Python 3.12 and will be removed in a future version. It also produces timezone-naive datetimes, making it impossible to distinguish UTC timestamps from local time when read back. With the target stack running Python 3.11+ and Docker images likely upgrading over time, this is a correctness and forward-compatibility risk.

**Fix:** Replace all four occurrences with `datetime.now(timezone.utc)` and add `timezone` to imports:
```python
from datetime import datetime, timezone

# In column defaults:
default=lambda: datetime.now(timezone.utc)
onupdate=lambda: datetime.now(timezone.utc)
```

---

### WR-03: `_engine` Singleton Does Not Validate `db_path` — Silently Uses Wrong Database

**File:** `src/queue/db.py:17-35`
**Issue:** `get_engine()` caches the engine in `_engine` and reuses it regardless of the `db_path` argument on subsequent calls. If `get_session_factory("data/other.db")` is called after `init_db("data/jobs.db")`, it silently returns the engine for `jobs.db`. There is no guard or error. This can cause tests or future multi-database scenarios to silently operate on the wrong database.

**Fix:** Store the path alongside the engine and raise on mismatch, or remove the singleton pattern and use dependency injection:
```python
_engine: AsyncEngine | None = None
_engine_path: str | None = None

def get_engine(db_path: str = "data/jobs.db") -> AsyncEngine:
    global _engine, _engine_path
    if _engine is not None and _engine_path != db_path:
        raise RuntimeError(
            f"Engine already initialized for '{_engine_path}'; "
            f"cannot reinitialize for '{db_path}' without calling reset."
        )
    if _engine is None:
        ...
```

---

### WR-04: In-Memory SQLite Test Fixture in `test_dedup.py` Is Broken Without `StaticPool`

**File:** `tests/integration/test_dedup.py:14-20`
**Issue:** The `session` fixture calls `init_db(":memory:")` then `get_session_factory(":memory:")`. For async SQLAlchemy with aiosqlite, SQLite `:memory:` databases are connection-scoped: each new connection produces a fresh empty database. Without `StaticPool`, the engine may acquire a different underlying connection for the session than the one `init_db` used to `CREATE TABLE`. The session would then see an empty schema and either raise `OperationalError` or return incorrect results. The fixture also lacks `@pytest_asyncio.fixture` and has an incorrect return-type annotation (`AsyncSession` instead of `AsyncGenerator[AsyncSession, None]`).

**Fix:**
```python
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine

@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s:
        yield s
```

---

### WR-05: `SalaryConfig` Fields Are Parsed but Silently Ignored by the Eligibility Filter

**File:** `src/filter/eligibility.py:18-70` / `src/filter/config_loader.py:19-22`
**Issue:** `EligibilityConfig` parses and validates `salary.skip_if_no_data` and `salary.min_annual_usd`, but `check_eligibility()` never reads `config.salary`. A user editing `eligibility.yaml` and setting `skip_if_no_data: true` or `min_annual_usd: 80000` will see no effect — jobs are accepted regardless. The comment `# set to non-zero to filter by salary floor` in the YAML implies these fields are active.

**Fix:** Either implement the salary check or mark the config fields as `Phase2+` with a comment making it clear they have no effect in Phase 1:
```python
# Phase 1: salary filtering not yet implemented.
# config.salary.skip_if_no_data and config.salary.min_annual_usd are parsed
# but intentionally not evaluated until Phase 2 adds salary data to the Job schema.
```

---

### WR-06: Ruff Lint Rules Are Silently Ignored — Linter Is Effectively Disabled

**File:** `pyproject.toml:17-19`
**Issue:** The `select` key is placed under `[tool.ruff]` instead of `[tool.ruff.lint]`. Since ruff 0.2.0, lint rule configuration moved to the `[tool.ruff.lint]` section; keys at `[tool.ruff]` level are silently ignored. The project requires `ruff>=0.4`, meaning the `select = ["E", "F", "I", "UP"]` directive is never applied. The linter runs in default mode (no rule set enforced), defeating its purpose.

**Fix:**
```toml
[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]
```

---

### WR-07: No `.dockerignore` — Sensitive and Irrelevant Files Copied Into Image

**File:** `Dockerfile:3` (missing companion file)
**Issue:** `COPY . .` with no `.dockerignore` copies `.env` (if present), `.venv/`, `__pycache__/`, `browser_profiles/`, `.planning/`, test files, and any local `.db` files into the container image. If `.env` contains API keys (Anthropic, Telegram, Gmail OAuth tokens), they are baked into the image layer and visible to anyone with access to the image. Even without secrets, the image is unnecessarily large.

**Fix:** Create `.dockerignore`:
```
.env
.venv/
__pycache__/
*.pyc
*.db
data/
browser_profiles/
.planning/
.claude/
.mypy_cache/
.ruff_cache/
tests/
```

---

## Info

### IN-01: `model_validator` in `EligibilityConfig` Is Dead Code

**File:** `src/filter/config_loader.py:34-38`
**Issue:** The `check_at_least_one_role` model validator checks `self.roles.include` is non-empty. However, `RolesConfig.include` is already declared as `Field(min_length=1)`, which causes Pydantic to raise `ValidationError` before the model validator ever runs. The validator can never be reached and provides no additional protection.

**Fix:** Remove the redundant `model_validator`:
```python
class EligibilityConfig(BaseModel):
    roles: RolesConfig
    location: LocationConfig = Field(default_factory=LocationConfig)
    salary: SalaryConfig = Field(default_factory=SalaryConfig)
    keywords: KeywordsConfig = Field(default_factory=KeywordsConfig)
    # no model_validator needed — RolesConfig.include enforces min_length=1
```

---

### IN-02: Inline `__import__("sys")` Instead of Top-Level Import

**File:** `main.py:35`
**Issue:** `file=__import__("sys").stderr` uses a dynamic import inline instead of a standard top-level `import sys`. This is non-idiomatic, harder to read, and will not be caught by linters (import sorting tools like `isort` / ruff's `I` rules will not track it). With `mypy strict=true`, this also bypasses type-checking of `sys.stderr`.

**Fix:**
```python
import sys  # add to top-level imports

# In structlog.configure:
logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
```

---

### IN-03: `test_db_init.py` Contains Dead In-Memory Section That Never Asserts Anything

**File:** `tests/integration/test_db_init.py:13-18`
**Issue:** The test opens an `aiosqlite.connect(":memory:")` connection, does nothing (`pass`), and moves on. This section was presumably intended to validate the in-memory DB init but was never completed. The dead block creates false confidence that in-memory behavior is tested.

**Fix:** Either remove lines 13–18 entirely (the file-based assertions below are sufficient) or complete the in-memory check with proper assertions using `StaticPool` (see WR-04).

---

### IN-04: `pytest.mark.asyncio` Used Inconsistently Across Test Files

**File:** `tests/integration/test_dry_run_pipeline.py:66,112,144,200` vs `tests/integration/test_dedup.py:75-144`
**Issue:** `test_dry_run_pipeline.py` decorates async tests with `@pytest.mark.asyncio` while `test_dedup.py` omits the decorator entirely. Both work under `asyncio_mode = "auto"` in `pyproject.toml`, but the inconsistency is confusing. If `asyncio_mode` is ever changed, the undecorated tests in `test_dedup.py` will silently stop being async (they'll be collected as regular sync tests returning coroutine objects, which pytest marks as passed without executing).

**Fix:** Adopt one consistent style. Given `asyncio_mode = "auto"`, the idiomatic choice is to omit `@pytest.mark.asyncio` everywhere and rely on the `auto` mode. Remove the decorators from `test_dry_run_pipeline.py`.

---

_Reviewed: 2026-05-27T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
