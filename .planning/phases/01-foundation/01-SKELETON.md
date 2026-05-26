# Walking Skeleton: Autonomous Job Application Agent — Phase 1

**Phase:** 01-foundation
**Created:** 2026-05-27
**Status:** Ready to execute

---

## What the Walking Skeleton Proves

After Phase 1 executes, the following end-to-end path is working:

```
python main.py --dry-run
  → loads eligibility.yaml (Pydantic-validated)
  → initialises SQLite DB (WAL mode, all tables created)
  → processes sample job leads through eligibility filter + dedup
  → prints one scannable line per job: QUEUED  Senior PM @ Acme Corp
                                    or REJECTED: title mismatch  Junior Dev @ Corp
  → writes audit_log rows to DB atomically
  → exits 0
```

This proves: config loads, DB initialises, filter decides, dedup skips duplicates, dry-run outputs results, audit trail is written. No submission path is touched.

---

## Architectural Decisions (locked for all downstream phases)

### Language + Runtime
| Decision | Value | Rationale |
|----------|-------|-----------|
| Language | Python 3.11 | asyncio maturity; all libraries have first-class support |
| Package manager | uv | Fast, pyproject.toml-native, reproducible installs |
| Config format | pyproject.toml only | No setup.py, no requirements.txt |

### Database
| Decision | Value | Rationale |
|----------|-------|-----------|
| Database | SQLite (WAL mode) | Zero infrastructure; survives crashes; sufficient for 50 jobs/day |
| Async driver | aiosqlite 0.20+ | Non-blocking async access |
| ORM | SQLAlchemy 2.0 async (`sqlite+aiosqlite://`) | Typed models, async sessions, migration path if needed |
| WAL mode | Enabled at startup via PRAGMA | Allows concurrent reads during writes |
| Primary keys | UUID strings (str(uuid.uuid4())) | No auto-increment conflicts across sources |

### State Machine
| Decision | Value | Rationale |
|----------|-------|-----------|
| Job states | DISCOVERED → QUEUED or REJECTED → APPLYING → SUBMITTED or FAILED | D-05 from CONTEXT.md; no intermediate PREPARING state |
| Status column | `jobs.status` text column | SQLite-as-queue pattern |
| Dedup key | url_hash (SHA-256) fast path + company+title+location fuzzy (85%) slow path | D-08; cross-source deduplication |

### Eligibility Config
| Decision | Value | Rationale |
|----------|-------|-----------|
| Config file | `config/eligibility.yaml` | D-07; human-editable, no code changes needed |
| Validation | Pydantic v2 `model_validate()` | Fails fast on misconfiguration with field names |
| Config path | `ELIGIBILITY_CONFIG_PATH` env var, default `config/eligibility.yaml` | Overridable without code changes |

### Logging
| Decision | Value | Rationale |
|----------|-------|-----------|
| Structured logging | structlog 24.x, JSON renderer | Machine-readable, integrates with audit table |
| Audit table | `audit_log` in SQLite | Every filter decision and state transition recorded |
| Dry-run events | DRY_RUN_WOULD_QUEUE / DRY_RUN_WOULD_REJECT | Separate from live events for query isolation |

### CLI Interface
| Decision | Value | Rationale |
|----------|-------|-----------|
| Entry point | `python main.py` | No installed script needed for Phase 1 |
| Dry-run flag | `--dry-run` (D-01) | Off by default; explicit per run |
| Future flags | `--source`, `--limit` slots defined now | Phase 2+ adds values without CLI changes |

---

## Directory Layout

```
Job Application Automation/
├── config/
│   └── eligibility.yaml          # Human-editable filter rules (D-07)
├── src/
│   ├── __init__.py
│   ├── audit_log.py              # Audit log table + write_audit()
│   ├── queue/
│   │   ├── __init__.py
│   │   ├── db.py                 # SQLite engine, WAL mode, init_db()
│   │   └── models.py             # Job, Application, EligibilityConfigSnapshot ORM models
│   └── filter/
│       ├── __init__.py
│       ├── config_loader.py      # load_eligibility_config() → EligibilityConfig
│       ├── eligibility.py        # check_eligibility() → FilterResult (pure function)
│       └── dedup.py              # is_duplicate() + hash_url() (async, uses DB session)
├── data/                         # gitignored; SQLite DB lives here at runtime
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   └── __init__.py           # eligibility.py and config_loader.py tests
│   └── integration/
│       └── __init__.py           # DB init and dedup integration tests
├── main.py                       # CLI entry point; --dry-run flag; runs filter pipeline
├── pyproject.toml                # All deps + ruff/mypy/pytest config
├── .env.example                  # Secret template (committed); .env is gitignored
├── .gitignore                    # data/, .env, __pycache__, *.db, browser_profiles/
└── Dockerfile                    # Stub only in Phase 1 (FROM python:3.11-slim)
```

---

## Dev Deployment Instructions

### Prerequisites
- Python 3.11+
- `uv` installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### First-time Setup

```bash
cd "Job Application Automation"

# Install all dependencies (core + dev)
uv sync --group dev

# Copy env template and set DB + config paths
cp .env.example .env
# Edit .env if needed — defaults work for local dev:
#   DB_PATH=data/jobs.db
#   ELIGIBILITY_CONFIG_PATH=config/eligibility.yaml
```

### Run the Walking Skeleton

```bash
# Dry-run: processes sample leads, prints QUEUED/REJECTED, writes audit log, no submissions
uv run python main.py --dry-run

# Expected output (one line per sample lead):
#   QUEUED                         Senior Product Manager @ Acme Corp
#   REJECTED: title mismatch       Junior Developer @ Tech Co
#   REJECTED: location mismatch    Product Manager @ US-Only Corp
#   DEDUP_SKIP                     Senior Product Manager @ Acme Corp  (duplicate)
```

### Run Tests

```bash
uv run pytest tests/ -v
```

### Verify DB Was Created

```bash
# DB file exists
ls data/jobs.db

# Audit log has entries
uv run python -c "
import asyncio, aiosqlite
async def check():
    async with aiosqlite.connect('data/jobs.db') as db:
        async with db.execute('SELECT COUNT(*) FROM audit_log') as cur:
            print('Audit log entries:', (await cur.fetchone())[0])
asyncio.run(check())
"
```

---

## What Phase 2 Inherits From This Skeleton

| Artifact | Phase 2 Usage |
|----------|---------------|
| `src/queue/models.py` Job model | Ingestion writes DISCOVERED rows here |
| `src/queue/db.py` get_session_factory() | All Phase 2 services use this factory |
| `src/filter/eligibility.py` check_eligibility() | Gmail/JobSpy leads flow through same filter |
| `src/filter/dedup.py` is_duplicate() | Prevents duplicate ingestion from all sources |
| `src/audit_log.py` write_audit() | Phase 2 adds APPLYING/SUBMITTED/FAILED events |
| `config/eligibility.yaml` | Phase 2 reads same config; Stefano tunes it before live run |
| `main.py` --source, --limit flags | Phase 2 populates --source with gmail, jobspy values |

---

*Walking Skeleton for Phase 1 — Autonomous Job Application Agent*
*Created: 2026-05-27*
