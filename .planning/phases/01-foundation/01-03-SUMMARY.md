---
phase: "01-foundation"
plan: "03"
subsystem: "foundation/pipeline"
tags: ["cli", "pipeline", "audit-log", "dry-run", "dedup", "eligibility", "tdd", "structlog"]
dependency_graph:
  requires:
    - "01-01 — src/queue/db.py, src/queue/models.py, src/audit_log.py (stub write_audit)"
    - "01-02 — src/filter/eligibility.py, src/filter/dedup.py, src/filter/config_loader.py"
  provides:
    - "main.py — full CLI pipeline: dedup + eligibility + audit + dry-run output"
    - "src/audit_log.py — write_audit() fully implemented (StrEnum, structlog to stderr)"
    - "tests/integration/test_dry_run_pipeline.py — 4 pipeline integration tests"
    - "tests/integration/test_cli.py — 4 subprocess-based CLI tests"
  affects:
    - "Phase 2+ ingestion — replace SAMPLE_LEADS in main.py with real sources"
tech_stack:
  added: []
  patterns:
    - "structlog routed to stderr via PrintLoggerFactory(file=sys.stderr) — stdout reserved for dry-run terminal output only (D-02)"
    - "AuditEvent uses StrEnum (Python 3.11+) instead of (str, Enum) — ruff UP042 compliant"
    - "Per-lead atomic transactions: each lead processed in its own session.begin() context"
    - "DB isolation in CLI tests via tmp_path fixture — each test gets a fresh database"
    - "SAMPLE_LEADS typed as list[dict[str, Any]] — avoids mypy false positives on lead field access"
key_files:
  created:
    - "tests/integration/test_dry_run_pipeline.py"
    - "tests/integration/test_cli.py"
  modified:
    - "main.py"
    - "src/audit_log.py"
decisions:
  - "structlog configured with PrintLoggerFactory(file=sys.stderr) so JSON logs never contaminate stdout; print_dry_run_row() is the sole stdout writer in dry-run mode"
  - "AuditEvent converted from (str, Enum) to StrEnum — backward-compatible; .value still works; ruff UP042 compliant"
  - "Per-lead transactions (one session.begin() per lead) rather than a single transaction over all leads — dedup check reads committed rows from prior leads"
  - "CLI tests use tmp_path fixture with absolute DB path passed via DB_PATH env var — eliminates test-order-dependent state"
metrics:
  duration: "~15 minutes"
  completed_at: "2026-05-27T01:50:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 2
---

# Phase 1 Plan 03: Dry-Run CLI Pipeline Summary

**One-liner:** Full filter pipeline wired in main.py — dedup + eligibility + write_audit() — with scannable dry-run terminal output (QUEUED/REJECTED: reason) and live DB insertion, backed by 8 new integration tests in TDD RED/GREEN order.

## Tasks Completed

| Task | Name | Commit (RED) | Commit (GREEN) | Key Files |
|------|------|-------------|----------------|-----------|
| 1 | Complete write_audit() + integration test | 88fc3a1 | 6eb9b8e | src/audit_log.py, tests/integration/test_dry_run_pipeline.py |
| 2 | Complete main.py pipeline + CLI test | c476897 | 90e1fb0 | main.py, tests/integration/test_cli.py |

## Verification Evidence

All plan verification and success criteria verified:

1. `pytest tests/integration/test_dry_run_pipeline.py -v` — 4 passed
2. `pytest tests/integration/test_cli.py -v` — 4 passed
3. `pytest tests/ -v` — 26 passed (0 failures, 0 regressions)
4. `python main.py --dry-run` stdout contains QUEUED and REJECTED: lines (confirmed by test + manual run)
5. `python main.py --dry-run` jobs table has 0 rows after run (SC3 confirmed)
6. `python main.py` jobs table has QUEUED=2, REJECTED=3 after run (SC1 confirmed)
7. Duplicate sample lead: DEDUP_SKIP audit event present; jobs table has no duplicate (SC2 confirmed)
8. Audit trail: all rows have source, event, timestamp; REJECT events have non-null reason (SC5 confirmed)
9. REJECTED: output uses spaces: "REJECTED: title mismatch" not "REJECTED: title_mismatch" (D-03 confirmed)
10. `grep "session.commit" src/audit_log.py` — returns only docstring comment, no actual call
11. `ruff check src/audit_log.py main.py tests/integration/test_dry_run_pipeline.py tests/integration/test_cli.py` — All checks passed
12. `mypy src/ main.py` — 2 pre-existing errors in src/queue/db.py (Plan 01 sessionmaker typing); 0 new errors in plan-03 files

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] structlog `event` keyword conflict in write_audit()**
- **Found during:** Task 1 RED phase — first pytest run
- **Issue:** `log.info("audit", ..., event=event.value, ...)` raises `TypeError: got multiple values for argument 'event'`. structlog treats the first positional argument to `log.info()` as the reserved `event` key; passing `event=` as a keyword arg conflicts with this internal binding.
- **Fix:** Renamed the kwarg to `audit_event=event.value` in the `log.info()` call. The DB column still stores `event.value` (unchanged). Structlog JSON output field name changes from `"event"` to `"audit_event"` — no behavioral impact since only the terminal output is user-facing.
- **Files modified:** `src/audit_log.py`
- **Commit:** 6eb9b8e

**2. [Rule 1 - Bug] test_no_dry_run_no_terminal_output false failure due to structlog on stdout**
- **Found during:** Task 2 GREEN phase — first test run after implementing main.py
- **Issue:** The test asserts `"QUEUED" not in result.stdout`. structlog JSON output goes to stdout by default, and the JSON audit entries contain `"audit_event": "QUEUED"` — causing the assertion to fail even though no `print_dry_run_row()` output was emitted.
- **Fix:** Configured `structlog.configure()` with `logger_factory=structlog.PrintLoggerFactory(file=sys.stderr)`. Structured logs now go to stderr; stdout is exclusively for dry-run terminal output (print_dry_run_row calls). This aligns with D-02: "Output is terminal-only."
- **Files modified:** `main.py`
- **Commit:** 90e1fb0

**3. [Rule 1 - Bug] CLI tests not isolated — shared DB caused all leads to be deduped on second run**
- **Found during:** Task 2 GREEN phase — test_dry_run_prints_queued_line failing after test_no_dry_run_no_terminal_output populated `data/test_cli.db`
- **Issue:** `run_main()` used a fixed `DB_PATH=data/test_cli.db`. After the no-dry-run test inserted all leads, subsequent dry-run tests detected them all as duplicates (DEDUP_SKIP) and produced no QUEUED/REJECTED output.
- **Fix:** Added `tmp_path` fixture parameter to all DB-stateful tests. Each test gets a unique temp directory DB path passed via `DB_PATH` env var. `test_help_shows_dry_run_flag` needs no DB so it stays as-is.
- **Files modified:** `tests/integration/test_cli.py`
- **Commit:** 90e1fb0

**4. [Rule 2 - Quality] AuditEvent converted from (str, Enum) to StrEnum**
- **Found during:** Task 2 ruff check — UP042 violation
- **Issue:** `class AuditEvent(str, Enum)` triggers ruff UP042 (Python 3.11+ supports `StrEnum` directly). The `.value` attribute and string behavior are identical.
- **Fix:** Changed to `from enum import StrEnum` and `class AuditEvent(StrEnum)`. All callers using `event.value` continue to work; StrEnum values ARE their string value directly.
- **Files modified:** `src/audit_log.py`
- **Commit:** 90e1fb0

## Known Stubs

None. All plan goals fully implemented:
- `write_audit()` is complete and tested
- `main.py` processes sample leads through full pipeline
- SAMPLE_LEADS will be replaced in Phase 2 with real ingestion (documented with TODO comment in code)

## Threat Surface Scan

All threats from the plan's `<threat_model>` are mitigated:

| Threat | Mitigation Applied |
|--------|-------------------|
| T-03-01: dry-run info disclosure | `print_dry_run_row()` shows category label only ("title mismatch"); no config values or JD content in output — confirmed by grep and test |
| T-03-02: audit_log append-only | `write_audit()` only calls `session.add()` — no UPDATE/DELETE; append-only comment added to function body |
| T-03-03: Job row insertion via sample data | All Job fields set via SQLAlchemy ORM keyword args; no f-string SQL construction anywhere in main.py |
| T-03-04: sample_leads DoS (accepted) | 6-item hardcoded list; O(N) scan negligible |
| T-03-05: structlog PII (accepted) | Logs contain only job title and company (public); no credentials or personal data |
| T-03-SC: no new packages | pyproject.toml unchanged; Plan 03 adds no new dependencies |

## TDD Gate Compliance

Both tasks followed RED/GREEN TDD cycle:

| Task | RED commit | GREEN commit | Gate |
|------|-----------|--------------|------|
| 1 (write_audit + pipeline tests) | 88fc3a1 — `test(01-03): add failing integration tests` | 6eb9b8e — `feat(01-03): fix write_audit() structlog event kwarg conflict` | PASSED |
| 2 (main.py CLI + test_cli) | c476897 — `test(01-03): add failing CLI tests` | 90e1fb0 — `feat(01-03): complete main.py pipeline` | PASSED |

RED tests failed correctly (TypeError for Task 1; AssertionError for Task 2 — QUEUED not in empty stdout). GREEN implementations made all tests pass.

## Self-Check

All created and modified files verified to exist:
- `main.py` — FOUND
- `src/audit_log.py` — FOUND
- `tests/integration/test_dry_run_pipeline.py` — FOUND
- `tests/integration/test_cli.py` — FOUND
- `.planning/phases/01-foundation/01-03-SUMMARY.md` — FOUND

All commits verified in git log:
- `88fc3a1` — FOUND (test: RED pipeline integration tests)
- `6eb9b8e` — FOUND (feat: GREEN write_audit fix)
- `c476897` — FOUND (test: RED CLI tests)
- `90e1fb0` — FOUND (feat: GREEN main.py complete pipeline)

## Self-Check: PASSED
