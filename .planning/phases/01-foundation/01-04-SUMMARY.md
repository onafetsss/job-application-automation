---
phase: 01-foundation
plan: "04"
subsystem: pipeline
tags: [dedup, dry-run, in-memory, audit-log, tdd, gap-closure]

# Dependency graph
requires:
  - phase: 01-03
    provides: main.run() dry-run pipeline with SAMPLE_LEADS fixture and audit_log writes

provides:
  - "in-memory seen_hashes: set[str] accumulator in main.run() — catches within-batch URL duplicates before DB lookup"
  - "Regression test test_dry_run_catches_within_batch_duplicate — subprocess-style, asserts QUEUED==2 and DEDUP_SKIP in stdout and audit_log"
  - "VERIFICATION truths 14 and 16 closed: dry-run on fresh DB now shows 2 QUEUED + 1 DEDUP_SKIP"

affects:
  - "01-VERIFICATION (truths 14 and 16 now satisfied)"
  - "Phase 2 ingestion (seen_hashes pattern applies to any lead source; within-batch dedup is source-agnostic)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "In-memory accumulator pattern: seen_hashes set initialized before processing loop; checked before DB call to handle state that DB cannot see in dry-run mode"
    - "Dual-layer dedup: in-memory (within-batch, both modes) + DB (cross-run, live only) — inner fast path, outer authoritative check"

key-files:
  created: []
  modified:
    - main.py
    - tests/integration/test_dry_run_pipeline.py

key-decisions:
  - "Use in-memory set (not a second DB query) for within-batch dedup — zero overhead, covers dry-run gap without changing DB schema"
  - "Emit DEDUP_SKIP audit row even for in-memory hits — OPS-03 audit trail must be complete regardless of which dedup layer fires"
  - "Print DEDUP_SKIP with :<30 alignment to match print_dry_run_row column format — consistent terminal UX"
  - "Test uses sqlite3 (stdlib) for post-subprocess DB assertion — avoids async machinery in a sync subprocess test"
  - "AuditEvent.DEDUP_SKIP stores 'DEDUP_SKIP' (uppercase StrEnum) — fixed SQL query in test to match case (SQLite = is case-sensitive)"

patterns-established:
  - "Subprocess regression test pattern: subprocess.run + DB query via sqlite3 to assert both stdout and audit trail"
  - "TDD RED/GREEN: failing test committed first, then implementation; verified at each gate"

requirements-completed: [INGEST-04, FILTER-03]

# Metrics
duration: 8min
completed: "2026-05-27"
---

# Phase 01 Plan 04: Dry-Run Within-Batch Dedup Gap Closure Summary

**In-memory `seen_hashes` set added to `main.run()` so dry-run on a fresh DB catches same-batch duplicate URLs and prints DEDUP_SKIP instead of a spurious third QUEUED line**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-27T~T
- **Completed:** 2026-05-27
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- Added `seen_hashes: set[str] = set()` accumulator to `main.run()` — checked before `is_duplicate()` DB call, covers the dry-run mode gap where no Job rows are written
- Dry-run on 6-lead SAMPLE_LEADS fixture now correctly shows 2 QUEUED + 3 REJECTED + 1 DEDUP_SKIP (was 3 QUEUED + 3 REJECTED before fix)
- Live mode unchanged: QUEUED=2, REJECTED=3 in jobs table, 1 DEDUP_SKIP audit row
- 29 tests pass (28 baseline + 1 new subprocess regression test)
- VERIFICATION truths 14 and 16 closed

## Task Commits

Each task was committed atomically (TDD):

1. **Task 1: RED — failing regression test** - `7bf48a7` (test)
2. **Deviation fix: audit event case correction in test** - `feba702` (fix)
3. **Task 2: GREEN — in-memory seen_hashes implementation** - `6661d4f` (fix)

**Plan metadata:** (SUMMARY + docs commit — see below)

_TDD tasks: test commit (RED) then implementation commit (GREEN)_

## Files Created/Modified

- `main.py` — Added `seen_hashes: set[str]` accumulator before the lead processing loop; inserted in-memory dedup check block with audit write, dry-run print, and log.info
- `tests/integration/test_dry_run_pipeline.py` — Added `test_dry_run_catches_within_batch_duplicate` (subprocess-style): asserts QUEUED count == 2, DEDUP_SKIP in stdout, and audit_log has 1 DEDUP_SKIP row

## Decisions Made

- Used an in-memory Python `set` (not a second DB query or a temporary table) — zero overhead, no schema change, correctly handles the dry-run gap
- The DB `is_duplicate()` call is kept as the cross-run authoritative check; the in-memory set is a fast-path prefix that also covers live mode duplicates (though they'd be caught by the DB too)
- Audit write opens its own `async with session_factory()` block (separate from the main loop's session) to keep transactions atomic and consistent with the existing dedup branch pattern

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed audit event case mismatch in regression test SQL query**
- **Found during:** Task 1 (RED test verification)
- **Issue:** The test SQL query used `WHERE event = 'dedup_skip'` (lowercase) but `AuditEvent.DEDUP_SKIP` is `"DEDUP_SKIP"` (uppercase StrEnum). SQLite `=` is case-sensitive, so the count would return 0 even after the fix was applied.
- **Fix:** Updated SQL query to `WHERE event = 'DEDUP_SKIP'`
- **Files modified:** `tests/integration/test_dry_run_pipeline.py`
- **Verification:** Confirmed test still FAILED at the correct assertion (QUEUED count, not DB count) after the fix
- **Committed in:** `feba702` (separate fix commit between RED and GREEN)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in test assertion)
**Impact on plan:** Fix was essential for test correctness. No scope creep. The RED test still failed correctly (at QUEUED count assertion) so the TDD gate was preserved.

## Issues Encountered

None — plan executed cleanly once the audit event case mismatch was identified and corrected.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Within-batch dedup is now correct in both dry-run and live mode
- 29 tests provide a solid regression baseline for Phase 2 ingestion work
- The `seen_hashes` pattern is source-agnostic and will apply to any future lead ingestion source
- Pre-existing mypy errors in `src/queue/db.py` (SQLAlchemy overload mismatch) are unrelated to this plan and remain as pre-existing technical debt

## Known Stubs

None — all data flows are wired end-to-end.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced.

## Self-Check: PASSED

- [x] `tests/integration/test_dry_run_pipeline.py::test_dry_run_catches_within_batch_duplicate` exists and passes
- [x] Full test suite: 29 passed
- [x] `python main.py --dry-run` prints 2 QUEUED + 1 DEDUP_SKIP on fresh DB
- [x] Live mode: QUEUED=2, REJECTED=3, 1 DEDUP_SKIP audit row
- [x] Commits `7bf48a7` (RED), `feba702` (case fix), `6661d4f` (GREEN) exist on branch
- [x] ruff check: passed; ruff format: applied; mypy errors are pre-existing in src/queue/db.py (not main.py)

---
*Phase: 01-foundation*
*Completed: 2026-05-27*
