---
phase: 01-foundation
verified: 2026-05-27T02:30:00Z
status: gaps_found
score: 8/11 must-haves verified
overrides_applied: 0
gaps:
  - truth: "python main.py --dry-run prints QUEUED or REJECTED: <category> for each sample lead — one scannable line per job (SC-3: dry-run processes without submitting)"
    status: partial
    reason: "The duplicate sample lead (6th item, same URL as lead 1) is printed as a third QUEUED line in dry-run mode rather than being caught by dedup. In dry-run mode no Job rows are inserted, so the url_hash is never stored in the DB — the subsequent is_duplicate() call on the same URL finds nothing and processes the duplicate. DEDUP_SKIP is never emitted in dry-run on a fresh DB. The terminal output shows 3 QUEUED lines instead of 2 QUEUED + 1 DEDUP_SKIP."
    artifacts:
      - path: "main.py"
        issue: "Dry-run mode does not write job rows to DB so dedup's fast path (url_hash lookup) cannot find the first occurrence. The duplicate passes through as a third QUEUED lead."
    missing:
      - "In dry-run mode, the dedup check must either (a) track url_hashes seen in the current run in an in-memory set, or (b) insert a 'ghost' record with a dry_run=True flag so the second pass finds it, or (c) check for duplicates within the current batch before the DB lookup."
  - truth: "A duplicate sample lead (same company + title + location) fed through the system appears once in the jobs table, not twice (SC-2)"
    status: partial
    reason: "SC-2 is satisfied in LIVE mode only. When python main.py (no --dry-run) is run, the duplicate is correctly caught (DEDUP_SKIP emitted, 5 unique jobs in DB). However, when --dry-run is run on a fresh DB, the duplicate is NOT caught — it appears as a third QUEUED terminal line with no DEDUP_SKIP event. The roadmap SC says 'fed through the system' without specifying live-only, and SC-3 implies dry-run is the validation mode — so dedup should also fire in dry-run."
    artifacts:
      - path: "main.py"
        issue: "is_duplicate() in the dry-run branch can only find url_hashes that were previously committed to the DB. In a fresh dry-run no such rows exist."
    missing:
      - "Track processed url_hashes in a local set within the run() function and check it before calling is_duplicate() to catch within-batch duplicates in dry-run mode."
  - truth: "check_eligibility() returns FilterResult(passed=False, reason='location_mismatch') when JD contains a blocked phrase AND location is None (CR-02 gap)"
    status: failed
    reason: "The entire location check block in eligibility.py is guarded by 'if location is not None:'. When a lead has location=None, blocked_phrases in the JD are never checked. A lead with location=None and 'must be authorized to work in the US' in the JD incorrectly passes the filter. This is CR-02 from the code review. The unit tests do not cover location=None with blocked phrases in JD."
    artifacts:
      - path: "src/filter/eligibility.py"
        issue: "Lines 56-68: blocked_phrases scan is inside 'if location is not None:' guard. Location=None leads bypass blocked_phrases entirely."
    missing:
      - "Move the blocked_phrases JD scan (rule 4a) outside the 'if location is not None:' guard so it fires regardless of whether the location field is present."
---

# Phase 1: Foundation Verification Report

**Phase Goal:** Establish the project skeleton and data layer — everything downstream code depends on: the package layout, the database engine, ORM models, eligibility filter engine, deduplication logic, and a dry-run CLI that proves the full pipeline end-to-end.
**Verified:** 2026-05-27T02:30:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

All must-haves from the three PLAN frontmatters and the five ROADMAP success criteria are checked below.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | DB created with jobs, applications, audit_log tables | VERIFIED | pytest test_db_init.py PASSED; sqlite_master confirmed all three tables |
| 2 | WAL mode is active on the database | VERIFIED | PRAGMA journal_mode returns WAL; confirmed in test and db.py line 47 |
| 3 | All __init__.py files exist so imports resolve | VERIFIED | All 6 files confirmed present: src/, src/queue/, src/filter/, tests/, tests/unit/, tests/integration/ |
| 4 | pyproject.toml declares Phase 1 dependencies and tool config | VERIFIED | File exists; uv sync --group dev exits 0; 26 packages installed |
| 5 | check_eligibility() returns passed=True for matching title + valid location | VERIFIED | 7/7 unit tests pass; FilterResult logic traced in eligibility.py |
| 6 | check_eligibility() returns passed=False, reason='title_mismatch' for non-matching title | VERIFIED | test_reject_title_mismatch PASSED |
| 7 | check_eligibility() returns passed=False, reason='keyword_blocklist' when JD contains blocked phrase | VERIFIED | test_reject_jd_keyword_blocklist PASSED |
| 8 | check_eligibility() returns passed=False, reason='location_mismatch' when location blocked and allow_remote=False | VERIFIED | test_reject_location_mismatch PASSED |
| 9 | check_eligibility() returns passed=False when location=None and JD contains blocked_phrase | FAILED | blocked_phrases scan is inside 'if location is not None:' guard — bypassed when location is absent (CR-02) |
| 10 | is_duplicate() returns True for exact url_hash match in DB | VERIFIED | test_is_duplicate_exact_url_hash PASSED; fast path confirmed in dedup.py:57-59 |
| 11 | is_duplicate() returns True for fuzzy company+title+location match >=85 | VERIFIED | test_is_duplicate_fuzzy_cross_source PASSED; DEDUP_THRESHOLD=85 named constant |
| 12 | load_eligibility_config() raises FileNotFoundError on missing file | VERIFIED | test_raises_on_missing_file PASSED |
| 13 | load_eligibility_config() raises ValidationError on invalid YAML schema | VERIFIED | test_raises_on_missing_roles_key PASSED; yaml.safe_load confirmed |
| 14 | python main.py --dry-run prints QUEUED or REJECTED lines (SC-3) | PARTIAL | Terminal output shows QUEUED/REJECTED lines; but duplicate lead printed as 3rd QUEUED instead of DEDUP_SKIP — dedup does not fire in dry-run on fresh DB |
| 15 | python main.py --dry-run writes audit_log rows without jobs table rows (SC-3) | VERIFIED | After --dry-run: jobs=0, audit_log=6 rows (all DRY_RUN_WOULD_*); no submission rows created |
| 16 | Duplicate lead appears once in jobs table, not twice (SC-2) | PARTIAL | Satisfied in LIVE mode (DEDUP_SKIP fires, 5 unique jobs). NOT satisfied in dry-run on fresh DB — duplicate appears as third QUEUED line |
| 17 | Editing eligibility.yaml and rerunning reflects new rules (SC-4) | VERIFIED | Config loaded per-run via load_eligibility_config(config_path); no caching; file change takes effect immediately |
| 18 | Every processed job has audit log entry: job_id, source, event, reason, timestamp (SC-5) | VERIFIED | test_audit_log_has_required_fields PASSED; AuditLogEntry schema confirmed nullable=False for source, event, timestamp |
| 19 | write_audit() does not call session.commit() | VERIFIED | grep returns only docstring comment, not executable call |
| 20 | REJECTED display uses spaces not underscores (D-03) | VERIFIED | Terminal output confirms "REJECTED: title mismatch" not "title_mismatch"; print_dry_run_row() line 141 |
| 21 | Running LIVE mode produces QUEUED and REJECTED rows in jobs table (SC-1) | VERIFIED | python main.py: jobs table shows QUEUED=2, REJECTED=3 after run |

**Score:** 8/11 (truths 9, 14, 16 failed/partial)

Note: Truths 14 and 16 describe the same root cause (dry-run dedup gap) and are reported as a single gap group.

### Deferred Items

None — no later phases address these gaps.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | Dependency declarations and tool config | VERIFIED | Contains [project], [tool.ruff], [tool.mypy], [tool.pytest.ini_options] |
| `src/queue/db.py` | SQLite engine, WAL mode, init_db(), get_session_factory() | VERIFIED | All three functions present; WAL pragma in init_db; singleton pattern |
| `src/queue/models.py` | Job, Application, EligibilityConfigSnapshot ORM models + JobStatus enum | VERIFIED | All four classes confirmed; url_hash unique=True; all D-04/D-05/D-06 fields present |
| `src/audit_log.py` | AuditLogEntry ORM model + AuditEvent enum + write_audit() | VERIFIED | StrEnum with all 7 events; write_audit() implemented with session.add() + structlog; no session.commit() |
| `config/eligibility.yaml` | Eligibility config with roles, location, salary, keywords sections | VERIFIED | All four top-level keys present; valid YAML; PM titles + exclude keywords + blocked_phrases configured |
| `src/filter/config_loader.py` | load_eligibility_config() returning EligibilityConfig | VERIFIED | yaml.safe_load used; Pydantic model_validate(); FileNotFoundError on missing; ValidationError on invalid |
| `src/filter/eligibility.py` | check_eligibility() pure function returning FilterResult | PARTIAL | Function implemented; no I/O; 5-rule priority order; but blocked_phrases bypassed when location=None |
| `src/filter/dedup.py` | is_duplicate() async + hash_url() + DEDUP_THRESHOLD | VERIFIED | DEDUP_THRESHOLD=85; token_sort_ratio; fast path (url_hash) + slow path (fuzzy weighted); AsyncSession parameter |
| `main.py` | CLI with full filter pipeline | PARTIAL | print_dry_run_row present; pipeline wired; but duplicate not caught in dry-run on fresh DB |
| `tests/integration/test_dry_run_pipeline.py` | End-to-end pipeline tests | VERIFIED | 4 tests pass; covers DRY_RUN_WOULD_QUEUE, DRY_RUN_WOULD_REJECT, DEDUP_SKIP |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/queue/db.py` | `src/queue/models.py` | `from src.queue.models import Base` | WIRED | Line 7 of db.py; also imports src.audit_log at line 12 |
| `src/audit_log.py` | `src/queue/models.py` | `class AuditLogEntry(Base)` | WIRED | Line 8 of audit_log.py; Base imported from models |
| `src/filter/eligibility.py` | `src/filter/config_loader.py` | `from src.filter.config_loader import EligibilityConfig` | WIRED | Line 4 of eligibility.py |
| `src/filter/dedup.py` | `src/queue/models.py` | `from src.queue.models import Job` | WIRED | Line 9 of dedup.py |
| `src/filter/config_loader.py` | `config/eligibility.yaml` | `yaml.safe_load` | WIRED | Line 58 of config_loader.py |
| `main.py` | `src/filter/eligibility.py` | `from src.filter.eligibility import check_eligibility` | WIRED | Line 20 of main.py; called at line 196 |
| `main.py` | `src/filter/dedup.py` | `from src.filter.dedup import is_duplicate, hash_url` | WIRED | Line 20 of main.py; both called in run() |
| `main.py` | `src/audit_log.py` | `from src.audit_log import write_audit, AuditEvent` | WIRED | Line 18 of main.py; write_audit called 3 places in run() |
| `src/audit_log.py` | `src/queue/models.py` | `from src.queue.models import Base` | WIRED | Line 8 of audit_log.py |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `main.py` SAMPLE_LEADS | `SAMPLE_LEADS` list | Hardcoded Phase 1 fixture | Yes (intentional fixture) | FLOWING — Phase 1 intentionally uses hardcoded sample leads; real ingestion deferred to Phase 2 |
| `src/queue/db.py` | `_engine` | `create_async_engine` | Yes — real SQLite connection | FLOWING |
| `src/audit_log.py` write_audit | `AuditLogEntry` | session.add() → DB | Yes — real DB write confirmed by tests | FLOWING |
| `src/filter/dedup.py` is_duplicate | `url_hash` / fuzzy rows | SQLAlchemy select(Job) | Real DB query confirmed | FLOWING — but dry-run gap means no rows to find on first run |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| DB creates 3 tables in WAL mode | `pytest tests/integration/test_db_init.py -v` | 1 PASSED | PASS |
| Eligibility unit tests (7 cases) | `pytest tests/unit/test_eligibility.py -v` | 7 PASSED | PASS |
| Config loader unit tests (4 cases) | `pytest tests/unit/test_config_loader.py -v` | 4 PASSED | PASS |
| Dedup integration tests (6 cases) | `pytest tests/integration/test_dedup.py -v` | 6 PASSED | PASS |
| Pipeline integration tests (4 cases) | `pytest tests/integration/test_dry_run_pipeline.py -v` | 4 PASSED | PASS |
| CLI tests (4 cases) | `pytest tests/integration/test_cli.py -v` | 4 PASSED | PASS |
| Full test suite | `pytest tests/ -v` | 26 PASSED, 0 failed | PASS |
| `python main.py --dry-run` exits 0 | subprocess | exit 0 | PASS |
| `python main.py --dry-run` prints QUEUED line | stdout check | "QUEUED  Senior Product Manager @ Acme Corp" | PASS |
| `python main.py --dry-run` prints REJECTED line | stdout check | "REJECTED: title mismatch  Software Engineer @ Gamma Ltd" | PASS |
| Dedup in dry-run catches duplicate URL on fresh DB | stdout check | FAIL — 3 QUEUED lines, 0 DEDUP_SKIP events on fresh DB | FAIL |
| Live mode produces QUEUED=2, REJECTED=3 in DB | sqlite3 query | QUEUED=2, REJECTED=3 confirmed | PASS |
| Dedup in live mode catches duplicate URL | DEDUP_SKIP event | Confirmed — 6th lead DEDUP_SKIPped, 5 unique jobs | PASS |
| Spaces in rejected reason (not underscores) | stdout | "REJECTED: title mismatch" not "title_mismatch" | PASS |

### Probe Execution

No probe scripts defined for this phase.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INGEST-04 | 01-02-PLAN | Cross-source deduplication via company+title+location fuzzy match | PARTIAL | Dedup works in live mode (DEDUP_SKIP confirmed); broken in dry-run on fresh DB — duplicates not caught |
| FILTER-01 | 01-02-PLAN | Title keyword include/exclude filtering | SATISFIED | check_eligibility() passes 7/7 unit tests; case-insensitive matching confirmed |
| FILTER-02 | 01-02-PLAN | Location filtering — allow_remote, allowed_locations, blocked_phrases | PARTIAL | Location allowlist and allow_remote work; blocked_phrases bypassed when location=None (CR-02) |
| FILTER-03 | 01-03-PLAN | Dry-run mode — filter without submitting | PARTIAL | --dry-run flag works; no jobs table writes; QUEUED/REJECTED output correct; but dedup gap in dry-run means duplicate leads are re-processed |
| OPS-03 | 01-01-PLAN, 01-03-PLAN | Full audit trail per processed job | SATISFIED | Every lead produces audit_log row with source, event, reason, timestamp; nullable=False enforced on required fields |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/filter/eligibility.py` | 56-68 | `blocked_phrases` check inside `if location is not None:` guard | BLOCKER | Leads with no location field bypass JD phrase filtering; US-auth-required jobs pass filter when location is absent |
| `main.py` | 166-193 | No in-batch dedup tracking in dry-run | BLOCKER | Duplicate leads within the same batch are not caught in dry-run mode because no Job rows are written to DB |
| `Dockerfile` | 4-5 | `pip install uv` without `uv sync` — all project deps missing | WARNING | Container crashes on startup with ModuleNotFoundError (CR-01 from code review; Dockerfile is stub-only per Plan 01 intent) |
| `src/queue/db.py` | 47-49 | `PRAGMA foreign_keys=ON` set once in init_db, not per-connection | WARNING | Foreign key enforcement absent on all connections after init (WR-01) |
| `src/queue/models.py` | 47-48, 74 | `datetime.utcnow()` deprecated since Python 3.12 | WARNING | Deprecation warnings in test output; naive datetimes (WR-02) |
| `src/filter/dedup.py` | 63-65 | Slow-path query includes REJECTED jobs | WARNING | REJECTED jobs permanently block re-evaluation from alternate sources (CR-03) |
| `pyproject.toml` | 17-19 | `select` under `[tool.ruff]` instead of `[tool.ruff.lint]` | WARNING | Lint rules silently ignored since ruff 0.2.0; linter runs in default mode only (WR-06) |
| `main.py` | 35 | `__import__("sys").stderr` inline dynamic import | INFO | Non-idiomatic; bypasses linter import tracking (IN-02) |

**Debt marker gate:** No TBD, FIXME, or XXX markers found in phase source files.

### Human Verification Required

None — all phase behaviors are programmatically verifiable.

### Gaps Summary

**Root cause 1 — Dry-run dedup gap (INGEST-04 / SC-2 / SC-3):**
`is_duplicate()` correctly detects duplicates by looking up `url_hash` in the `jobs` table. In dry-run mode, no Job rows are ever inserted, so when the same URL appears a second time in the same batch, the DB lookup finds nothing and the duplicate passes through as a fresh lead. The terminal output shows a third "QUEUED" line for a lead that should be DEDUP_SKIPped. This breaks SC-2 and SC-3 when verified end-to-end in dry-run mode.

Fix: Add an in-memory `seen_hashes: set[str]` in the `run()` function and check it before calling `is_duplicate()`.

**Root cause 2 — Location blocked_phrases bypass (FILTER-02 / CR-02):**
`check_eligibility()` wraps the entire location check (including `blocked_phrases` in JD) inside `if location is not None:`. A job scraped without a location field can contain `"must be authorized to work in the US"` in its JD and still pass the filter. This is a correctness bug that directly affects the user's protection against US-auth-required jobs when location is absent from the scraper output.

Fix: Move the blocked_phrases JD scan outside the `if location is not None:` guard. It operates on `jd_lower` which is independent of the location field.

---

_Verified: 2026-05-27T02:30:00Z_
_Verifier: Claude (gsd-verifier)_
