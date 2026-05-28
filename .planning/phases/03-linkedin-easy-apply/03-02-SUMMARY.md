---
phase: 03-linkedin-easy-apply
plan: "02"
subsystem: browser-automation
tags: [camoufox, linkedin, screening, tdd, apply-engine]
dependency_graph:
  requires:
    - 03-01 (camoufox dependency, JobStatus.SKIPPED, test scaffolds)
  provides:
    - src/preparation/screening.py — generate_screening_answers shared function
    - src/browser/__init__.py — browser package marker
    - src/browser/linkedin_applier.py — LinkedInApplier class, custom exceptions, modal nav
    - application.py refactored to delegate to shared screening function
    - tests/unit/test_screening.py — 4 GREEN unit tests for screening function
  affects:
    - src/api/routes/application.py (generate_screening_answers_route now delegates)
    - tests/browser/test_linkedin_applier.py (3 xfail → 3 GREEN)
tech_stack:
  added: []
  patterns:
    - TDD RED/GREEN cycle for both tasks
    - Shared function pattern: extract route logic to importable module (no self-HTTP)
    - Camoufox persistent_context + user_data_dir session management
    - Bounded modal loop with explicit Submit/Review/Next ARIA detection
    - structlog keyword-arg logging convention throughout
key_files:
  created:
    - src/preparation/screening.py
    - src/browser/__init__.py
    - src/browser/linkedin_applier.py
    - tests/unit/test_screening.py
  modified:
    - src/api/routes/application.py
decisions:
  - "generate_screening_answers extracted to src/preparation/screening.py as synchronous function callable from both FastAPI route and browser module — avoids self-HTTP anti-pattern"
  - "application.py route renamed to generate_screening_answers_route internally to avoid name collision with imported shared function"
  - "LinkedInApplier._profile_dict convention: job object carries _profile_dict attribute resolved by caller (FastAPI route in Plan 03-03) — browser module is profile-agnostic"
  - "resolve_profile_field() is synchronous (no async page interaction) — clean testability without mocked page objects"
  - "ModalNavigationError added as 4th exception alongside the 3 specified — prevents silent infinite loops (T-03-03)"
metrics:
  duration: "~20 minutes"
  completed_date: "2026-05-28"
  tasks_completed: 2
  tasks_skipped: 0
  files_created: 4
  files_modified: 1
---

# Phase 03 Plan 02: LinkedIn Easy Apply Browser Module — Summary

**One-liner:** LinkedInApplier Camoufox module with challenge detection, bounded modal navigation, and field filling; screening logic extracted to shared function importable without HTTP.

## What Was Built

### Task 1 (TDD): Extract screening generation into shared function and refactor route

- `src/preparation/screening.py` created with `generate_screening_answers(profile_config, job_title, job_description, questions) -> list[dict]`:
  - Synchronous function (Anthropic client is sync) callable from both FastAPI and browser module
  - Identical prompt text, model (`claude-haiku-3-5`), and JSON + markdown-fallback parsing as the original route
  - Empty `questions` returns `[]` immediately without calling Anthropic
  - Anthropic exceptions re-raised as `RuntimeError("anthropic_api_unavailable")` for caller mapping
  - job_description truncated to 1500 chars (T-03-06 mitigation)
- `src/api/routes/application.py` refactored:
  - `generate_screening_answers` route renamed `generate_screening_answers_route` (avoids name collision with import)
  - Delegates to shared function; translates `RuntimeError("anthropic_api_unavailable")` → HTTP 503
  - External response shape (`GenerateScreeningAnswersOut`) unchanged
  - `from src.preparation.screening import generate_screening_answers` present at module top
- `tests/unit/test_screening.py` created with 4 GREEN tests:
  1. Valid Haiku response returns `[{question, answer}]` list
  2. Empty questions returns `[]` without calling Anthropic client
  3. Markdown-fenced `json` block is parsed (regression for existing fallback)
  4. `application.py` contains the import statement from `src.preparation.screening`

### Task 2 (TDD): Implement LinkedInApplier

- `src/browser/__init__.py` created (empty package marker)
- `src/browser/linkedin_applier.py` created with:
  - **Exceptions:** `ChallengeDetected`, `NoEasyApplyButton`, `UnknownFormField`, `ModalNavigationError`
  - **Constants:** `CHALLENGE_URL_PATTERNS = ["/checkpoint/", "/authwall/"]`, `LOGIN_URL_PATTERNS`
  - **`check_for_challenge(page)`:** URL inspection + page title check for "unusual activity" / "security verification"
  - **`get_label_for(page, element)`:** Three-level aria-label → placeholder → `label[for=id]` fallback
  - **`resolve_profile_field(label, profile, screening_answers)`:** Synchronous label→value resolver; raises `UnknownFormField` when unresolvable (D-11)
  - **`fill_form_fields()`:** File upload, phone, `.artdeco-text-input--input` text inputs, radio groups, dropdowns
  - **`LinkedInApplier`:** `__init__(user_data_dir)` + `_find_and_click_easy_apply(page)` + `_navigate_modal(...)` + `async def apply(job, resume_path) -> dict`
  - Camoufox session: `headless="virtual"` + `persistent_context=True` + `user_data_dir` + `humanize=True` + `os="windows"`
  - Direct `generate_screening_answers` import (no self-HTTP, no httpx localhost call)
  - Bounded modal loop (MAX_PAGES=20, raises `ModalNavigationError` on no-button — T-03-03)
  - structlog keyword-arg logging throughout; PII excluded from logs (T-03-04)
- All 3 browser xfail tests now GREEN:
  - `test_challenge_detected` — `/checkpoint/` URL returns non-None string
  - `test_no_easy_apply_button` — locator count==0 raises `NoEasyApplyButton`
  - `test_unknown_form_field` — unmappable label raises `UnknownFormField`

## Verification Results

```
$ uv run python -c "from src.preparation.screening import generate_screening_answers; print('import-ok')"
import-ok

$ uv run python -c "from src.browser.linkedin_applier import LinkedInApplier, ChallengeDetected, NoEasyApplyButton, UnknownFormField; print('import-ok')"
import-ok

$ uv run pytest tests/browser/ tests/unit/test_screening.py -x -q
.......
7 passed in 0.39s

$ grep -n "headless" src/browser/linkedin_applier.py
14: T-03-05 — headless="virtual" + humanize=True + persistent_context (not headless-true).
488: headless="virtual",   # Xvfb on Linux/Docker — not headless-true (T-03-05)

$ grep -n "generate_screening_answers" src/browser/linkedin_applier.py | head -3
23:from src.preparation.screening import generate_screening_answers
170:            ``generate_screening_answers``.
475:                screening_answers = generate_screening_answers(
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added ModalNavigationError as 4th exception**
- **Found during:** Task 2 implementation of `_navigate_modal()`
- **Issue:** The plan specifies 3 custom exceptions but the modal navigation loop needs a distinct exception for "no button found" and "page limit exceeded" — without it the loop would silently hang or raise a generic exception with no diagnostic value
- **Fix:** Added `ModalNavigationError` at module top alongside the 3 specified exceptions. No behavior change to the specified exceptions. `_navigate_modal()` raises `ModalNavigationError` per T-03-03 (bounded loop requirement)
- **Files modified:** `src/browser/linkedin_applier.py`

**2. [Rule 2 - Missing Critical] Route function renamed to avoid name collision**
- **Found during:** Task 1 — refactoring `application.py` to import `generate_screening_answers` from `screening.py`
- **Issue:** The FastAPI route function was named `generate_screening_answers` — importing the shared function with the same name causes a name collision at module scope
- **Fix:** Renamed the route function to `generate_screening_answers_route`. The FastAPI endpoint URL (`/generate-screening-answers`) is unchanged. The `response_model` parameter unchanged. External contract identical.
- **Files modified:** `src/api/routes/application.py`

**3. [Rule 2 - Missing Critical] `resolve_profile_field` kept synchronous**
- **Found during:** Task 2 — test scaffold calls `resolve_profile_field(label, profile, screening_answers)` as a synchronous function
- **Issue:** Making `resolve_profile_field` async would require `await` in tests, but the scaffold and PLAN both show it as synchronous (the test calls it directly without `await`)
- **Fix:** Implemented as a synchronous function — consistent with plan's test scaffold and testability requirement (no page interaction needed, pure dict lookup)
- **Files modified:** `src/browser/linkedin_applier.py`

## Known Stubs

None. All functions are fully implemented. The `_profile_dict` convention on `job` objects is a documented interface contract (Plan 03-03 FastAPI route will set `job._profile_dict` before passing to `applier.apply()`), not a stub.

## Threat Flags

No new threat surface beyond what is documented in the plan's threat model (T-03-03 through T-03-07). The `src/preparation/screening.py` module calls the Anthropic API (already trusted path from Phase 2). The `src/browser/linkedin_applier.py` module makes outbound browser connections to LinkedIn (within T-03-05, T-03-07 mitigations). No new network endpoints exposed.

## Self-Check: PASSED

- `src/preparation/screening.py` exists and exports `generate_screening_answers`: VERIFIED
- `src/browser/__init__.py` exists: VERIFIED
- `src/browser/linkedin_applier.py` contains `class LinkedInApplier` with `async def apply`: VERIFIED
- `src/browser/linkedin_applier.py` exports `ChallengeDetected`, `NoEasyApplyButton`, `UnknownFormField`: VERIFIED
- `grep -c 'headless="virtual"'` >= 1: VERIFIED (count=2)
- `grep -c 'headless=True'` == 0: VERIFIED (count=0)
- `from src.preparation.screening import generate_screening_answers` in `linkedin_applier.py`: VERIFIED
- `from src.preparation.screening import generate_screening_answers` in `application.py`: VERIFIED
- `uv run pytest tests/browser/ tests/unit/test_screening.py -x -q` — 7 passed: VERIFIED
- Task 1 RED commit `cc651ee`: VERIFIED
- Task 1 GREEN commit `76ae111`: VERIFIED
- Task 2 GREEN commit `4c3f701`: VERIFIED
