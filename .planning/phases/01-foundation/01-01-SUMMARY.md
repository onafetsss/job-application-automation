---
phase: "01-foundation"
plan: "01"
subsystem: "foundation/db"
tags: ["scaffold", "sqlite", "sqlalchemy", "orm", "aiosqlite", "structlog", "pyproject"]
dependency_graph:
  requires: []
  provides:
    - "pyproject.toml — single-source dependency + tool config"
    - "src/queue/db.py — get_engine(), init_db(), get_session_factory()"
    - "src/queue/models.py — Job, Application, EligibilityConfigSnapshot ORM models"
    - "src/audit_log.py — AuditLogEntry ORM model + write_audit() + AuditEvent enum"
    - "config/eligibility.yaml — stub eligibility filter config"
    - "main.py — CLI entry point with --dry-run/--source/--limit flags"
  affects: []
tech_stack:
  added:
    - "aiosqlite 0.22.1 — async SQLite driver"
    - "sqlalchemy[asyncio] 2.0.50 — ORM with async engine"
    - "greenlet 3.5.1 — required for SQLAlchemy async on Python 3.14"
    - "pydantic 2.13.4 — config validation"
    - "pyyaml 6.0.3 — YAML config loading"
    - "rapidfuzz 3.14.5 — fuzzy dedup matching (Phase 2)"
    - "structlog 25.5.0 — structured JSON logging"
    - "python-dotenv 1.2.2 — env var loading"
    - "tenacity 9.1.4 — retry logic"
    - "pytest 9.0.3 + pytest-asyncio 1.4.0 — async test framework"
    - "ruff 0.15.14 — linting + formatting"
    - "mypy 2.1.0 — type checking"
  patterns:
    - "SQLAlchemy 2.0 async with create_async_engine + AsyncSession"
    - "Module-level engine singleton reset per init_db() call for test isolation"
    - "All ORM models share single Base from src.queue.models; db.py imports audit_log to register tables"
    - "structlog JSONRenderer configured once in main.py; modules use get_logger() only"
    - "argparse with --dry-run (bool), --source (str), --limit (int)"
key_files:
  created:
    - "pyproject.toml"
    - ".env.example"
    - ".gitignore"
    - "Dockerfile"
    - "src/__init__.py"
    - "src/queue/__init__.py"
    - "src/filter/__init__.py"
    - "tests/__init__.py"
    - "tests/unit/__init__.py"
    - "tests/integration/__init__.py"
    - "uv.lock"
    - "src/queue/db.py"
    - "src/queue/models.py"
    - "src/audit_log.py"
    - "config/eligibility.yaml"
    - "main.py"
    - "tests/integration/test_db_init.py"
  modified: []
decisions:
  - "sqlalchemy[asyncio] extra + greenlet>=3.0 added to deps — greenlet is not auto-installed on Python 3.14 as a transitive dep; SQLAlchemy async requires it explicitly"
  - "db.py imports src.audit_log at module level — ensures AuditLogEntry is registered with Base.metadata before create_all() runs; canonical pattern for all future ORM models"
  - "data/ directory chmod to 0700 after mkdir — umask prevents mkdir(mode=0o700) from enforcing restricted permissions; explicit chmod is the correct fix (T-01-01)"
  - "init_db() resets _engine singleton to None — enables test isolation with in-memory or temp-file databases without engine state leaking between calls"
metrics:
  duration: "~7 minutes"
  completed_at: "2026-05-27T01:25:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 17
  files_modified: 0
---

# Phase 1 Plan 01: Project Scaffold + DB Schema Summary

**One-liner:** SQLite WAL-mode DB with Job/Application/AuditLogEntry ORM models, aiosqlite async engine, and a bootable main.py CLI scaffold using uv + pyproject.toml.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Project scaffold — pyproject.toml, directories, .gitignore, .env.example | de7cb51 | pyproject.toml, .env.example, .gitignore, Dockerfile, 6x __init__.py, uv.lock |
| 2 | DB engine + ORM models — db.py, models.py, audit_log.py, eligibility.yaml, main.py | b46e3ba | src/queue/db.py, src/queue/models.py, src/audit_log.py, config/eligibility.yaml, main.py, tests/integration/test_db_init.py |

## Verification Evidence

All plan verification steps pass:

1. `uv sync --group dev` — exits 0, 24 packages installed cleanly
2. All 6 package `__init__.py` files exist — imports resolve
3. `pytest tests/integration/test_db_init.py -v` — 1 passed (jobs, applications, audit_log tables + WAL mode)
4. `python main.py --dry-run` — exits 0, prints "DB initialised."
5. `python main.py --help` — shows `--dry-run`, `--source`, `--limit` flags
6. `data/` directory created with `drwx------` (700) permissions — not world-readable (T-01-01)
7. `config/eligibility.yaml` valid YAML — `yaml.safe_load()` exits 0

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] greenlet missing from dependencies on Python 3.14**
- **Found during:** Task 2 — first pytest run
- **Issue:** SQLAlchemy async engine requires `greenlet` for concurrency primitives. On Python 3.14, greenlet is NOT automatically installed as a transitive dependency (unlike older Python versions where SQLAlchemy bundled it). The test failed with `ValueError: the greenlet library is required to use this function`.
- **Fix:** Added `sqlalchemy[asyncio]>=2.0` and `greenlet>=3.0` to `pyproject.toml` dependencies. Re-ran `uv sync --group dev`.
- **Files modified:** `pyproject.toml`, `uv.lock`
- **Commit:** b46e3ba

**2. [Rule 1 - Bug] AuditLogEntry not registered with Base.metadata at create_all time**
- **Found during:** Task 2 — first test run after greenlet fix
- **Issue:** `AuditLogEntry` is defined in `src/audit_log.py` using `Base` from `src/queue/models.py`. Since `db.py` never imported `audit_log`, the `AuditLogEntry` class was never instantiated, so `Base.metadata` had no record of the `audit_log` table. `init_db()` called `Base.metadata.create_all()` and silently omitted the table.
- **Fix:** Added `import src.audit_log  # noqa: F401` at the top of `src/queue/db.py`. This import side-effect registers `AuditLogEntry` with `Base.metadata` before `create_all()` runs. This is the canonical SQLAlchemy pattern for multi-module model registrations.
- **Files modified:** `src/queue/db.py`
- **Commit:** b46e3ba

**3. [Rule 2 - Security/T-01-01] data/ directory permissions not enforced due to umask**
- **Found during:** Task 2 — manual inspection post main.py run
- **Issue:** `Path.mkdir(mode=0o700)` does not guarantee 700 permissions — the process `umask` is applied on top, resulting in 755. This violates T-01-01 (DB file must not be world-readable).
- **Fix:** Added `parent.chmod(0o700)` after `mkdir()`, conditioned on whether the directory was newly created (to avoid attempting to chmod pre-existing system directories like `/tmp` which would raise `PermissionError` in tests).
- **Files modified:** `src/queue/db.py`
- **Commit:** b46e3ba

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `sample_leads: list[dict] = []` empty list | main.py:45 | Intentional Phase 1 stub — real ingestion sources added in Plan 02; `--dry-run` works but processes zero leads |
| `src/filter/config_loader.py` does not exist | main.py comments | Plan 02 creates this module; main.py has TODO comments for Phase 2 imports |

These stubs are intentional and documented. The plan goal ("main.py --dry-run exits 0") is fully achieved — the stub leads list is the expected Phase 1 state.

## Threat Surface Scan

All threats from the plan's `<threat_model>` are mitigated:

| Threat | Mitigation Applied |
|--------|-------------------|
| T-01-01: DB file world-readable | data/ created with chmod 0700 (deviation #3 above) |
| T-01-02: YAML injection | `yaml.safe_load()` used in config path; Pydantic model_validate() rejects unexpected fields |
| T-01-03: DB_PATH path traversal | pathlib.Path resolves path; never passed to shell; mkdir is pure Python |
| T-01-04: audit_log mutability | write_audit() only calls session.add() — never UPDATE/DELETE; append-only by code convention |
| T-01-05: CLI --dry-run spoofing | argparse boolean flag; no string-as-code execution |
| T-01-SC: package slopcheck | greenlet 3.5.1, sqlalchemy 2.0.50, aiosqlite 0.22.1 are well-established packages |

No new threat surface was introduced beyond the plan's threat model.

## Self-Check

All created files verified to exist:
- `pyproject.toml` — FOUND
- `src/queue/db.py` — FOUND
- `src/queue/models.py` — FOUND
- `src/audit_log.py` — FOUND
- `config/eligibility.yaml` — FOUND
- `main.py` — FOUND
- `tests/integration/test_db_init.py` — FOUND

All commits verified in git log:
- `de7cb51` — FOUND (chore: project scaffold)
- `b46e3ba` — FOUND (feat: DB engine + ORM models)

## Self-Check: PASSED
