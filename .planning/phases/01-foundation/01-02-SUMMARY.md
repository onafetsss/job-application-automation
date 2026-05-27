---
phase: "01-foundation"
plan: "02"
subsystem: "foundation/filter"
tags: ["filter", "eligibility", "dedup", "pydantic", "rapidfuzz", "yaml", "tdd"]
dependency_graph:
  requires:
    - "01-01 — src/queue/models.py (Job model), src/queue/db.py (get_session_factory, init_db)"
  provides:
    - "src/filter/config_loader.py — load_eligibility_config() returning EligibilityConfig Pydantic model"
    - "src/filter/eligibility.py — check_eligibility() pure function returning FilterResult"
    - "src/filter/dedup.py — is_duplicate() async function + hash_url() + DEDUP_THRESHOLD"
    - "tests/unit/test_config_loader.py — 4 unit tests"
    - "tests/unit/test_eligibility.py — 7 unit tests"
    - "tests/integration/test_dedup.py — 6 integration tests"
  affects:
    - "main.py — Plan 03 wires these modules into the dry-run pipeline"
tech_stack:
  added:
    - "rapidfuzz — already in pyproject.toml from Plan 01; first active use here"
    - "pyyaml — already in pyproject.toml from Plan 01; first active use here"
    - "pydantic v2 model_validate() + model_validator(mode='after') pattern established"
  patterns:
    - "EligibilityConfig Pydantic v2 model with nested sub-models (RolesConfig, LocationConfig, SalaryConfig, KeywordsConfig)"
    - "FilterResult dataclass — passed: bool + reason: str | None — canonical rejection reason format"
    - "check_eligibility() pure function — 5-rule priority order, first-failure short-circuit"
    - "hash_url() + _canonicalize_url() — tracking-param stripping via parse_qs/urlencode"
    - "is_duplicate() async — fast path (url_hash), slow path (weighted fuzzy: 0.4 company + 0.4 title + 0.2 location)"
    - "TDD: test(01-02) RED commits precede feat(01-02) GREEN commits for both tasks"
key_files:
  created:
    - "src/filter/config_loader.py"
    - "src/filter/eligibility.py"
    - "src/filter/dedup.py"
    - "tests/unit/test_config_loader.py"
    - "tests/unit/test_eligibility.py"
    - "tests/integration/test_dedup.py"
  modified: []
decisions:
  - "DEDUP_THRESHOLD = 85 named constant (not inline magic number) per D-08 — makes threshold auditable and overridable in tests"
  - "is_duplicate() uses AsyncSession parameter — never creates its own engine; caller owns the session lifecycle"
  - "check_eligibility() blocked_phrases check fires before allowed_locations check — location_mismatch reason covers both JD-phrase rejection and location list rejection"
  - "hash_url() canonicalization lowercases scheme+host and strips: utm_source, utm_medium, utm_campaign, trk, refId (case-insensitive via url.lower())"
metrics:
  duration: "~3 minutes"
  completed_at: "2026-05-27T01:33:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 6
  files_modified: 0
---

# Phase 1 Plan 02: Eligibility Filter + Deduplication Summary

**One-liner:** Pydantic v2 YAML config loader, pure eligibility filter with 5-rule priority order, and async fuzzy deduplication (SHA-256 fast path + rapidfuzz slow path at 85% threshold) — all fully TDD-tested.

## Tasks Completed

| Task | Name | Commit (RED) | Commit (GREEN) | Key Files |
|------|------|-------------|----------------|-----------|
| 1 | Config loader + eligibility filter with unit tests | e32704b | 3e9e281 | src/filter/config_loader.py, src/filter/eligibility.py, tests/unit/test_config_loader.py, tests/unit/test_eligibility.py |
| 2 | Deduplication module with integration test | 0f2b7cd | 76e8555 | src/filter/dedup.py, tests/integration/test_dedup.py |

## Verification Evidence

All 7 plan verification steps pass:

1. `pytest tests/unit/test_eligibility.py -v` — 7 passed
2. `pytest tests/unit/test_config_loader.py -v` — 4 passed
3. `pytest tests/integration/test_dedup.py -v` — 6 passed
4. `pytest tests/ -v` — 18 passed (0 failures, 0 regressions)
5. `grep "yaml.safe_load" src/filter/config_loader.py` — matches line 58
6. `grep "DEDUP_THRESHOLD" src/filter/dedup.py` — `DEDUP_THRESHOLD = 85`
7. `grep "token_sort_ratio" src/filter/dedup.py` — matches line in `_similarity_score()`

Additional acceptance criteria verified:
- `grep -n "aiosqlite\|sqlalchemy" src/filter/eligibility.py` — no match (pure function, no DB imports)
- FilterResult reason strings: `"title_mismatch"`, `"location_mismatch"`, `"keyword_blocklist"` — underscore format only
- `is_duplicate()` signature: `async def is_duplicate(session: AsyncSession, company: str, title: str, location: str | None, url_hash: str) -> bool`

## Deviations from Plan

None — plan executed exactly as written. All must_haves and acceptance criteria met without deviation.

## Known Stubs

None. All three modules are fully implemented and tested. No placeholder logic or hardcoded empty values.

## Threat Surface Scan

All threats from the plan's `<threat_model>` are mitigated:

| Threat | Mitigation Applied |
|--------|-------------------|
| T-02-01: YAML injection via yaml.load | `yaml.safe_load()` used exclusively — verified by grep |
| T-02-02: Rejection reason PII leak | Reason strings are category labels only (`"title_mismatch"` etc.) — no failing values or config contents exposed |
| T-02-03: Dedup O(N) scan DoS | Accepted — Phase 1 has at most hundreds of jobs; noted for Phase 2+ index |
| T-02-04: SQL injection via job field values | All queries use SQLAlchemy ORM `select(Job.company_normalized, ...)` — no f-strings in query construction |
| T-02-SC: rapidfuzz package legitimacy | rapidfuzz 3.14.5 already installed in Plan 01; well-established C-extension package (2M+ weekly downloads) |

No new threat surface introduced beyond the plan's threat model.

## TDD Gate Compliance

Both tasks followed RED/GREEN TDD cycle:

| Task | RED commit | GREEN commit | Gate |
|------|-----------|--------------|------|
| 1 (config_loader + eligibility) | e32704b — `test(01-02): add failing tests` | 3e9e281 — `feat(01-02): implement config_loader and eligibility filter` | PASSED |
| 2 (dedup) | 0f2b7cd — `test(01-02): add failing integration tests` | 76e8555 — `feat(01-02): implement dedup module` | PASSED |

RED tests failed with `ModuleNotFoundError` (modules not yet created), confirming proper RED state before implementation.

## Self-Check

All created files verified to exist:
- `src/filter/config_loader.py` — FOUND
- `src/filter/eligibility.py` — FOUND
- `src/filter/dedup.py` — FOUND
- `tests/unit/test_config_loader.py` — FOUND
- `tests/unit/test_eligibility.py` — FOUND
- `tests/integration/test_dedup.py` — FOUND

All commits verified in git log:
- `e32704b` — FOUND (test: RED phase config_loader + eligibility)
- `3e9e281` — FOUND (feat: GREEN phase config_loader + eligibility)
- `0f2b7cd` — FOUND (test: RED phase dedup)
- `76e8555` — FOUND (feat: GREEN phase dedup)

## Self-Check: PASSED
