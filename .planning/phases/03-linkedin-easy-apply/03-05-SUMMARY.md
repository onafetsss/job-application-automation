---
phase: 03-linkedin-easy-apply
plan: "05"
subsystem: browser
tags: [linkedin, camoufox, sdui, recaptcha, needs-human, telegram, frame-aware, selector-fix]
dependency_graph:
  requires:
    - phase: 03-01 (JobStatus.SKIPPED, AuditEvent.SKIPPED enums to extend)
    - phase: 03-02 (LinkedInApplier, ChallengeDetected/NoEasyApplyButton/UnknownFormField/ModalNavigationError, fill_form_fields, _navigate_modal)
    - phase: 03-03 (POST /apply/linkedin-easy-apply route + exception handling)
    - phase: 03-04 (linkedin-easy-apply.json n8n workflow, session save script — Task 3 SDUI recon that triggered this replan)
  provides:
    - src/notify.py — async send_telegram(text) best-effort Bot API helper (httpx, no new dep)
    - JobStatus.NEEDS_HUMAN + AuditEvent.NEEDS_HUMAN — paused-job state for challenge-gated applies
    - RecaptchaDetected exception + detect_recaptcha(page) predicate in linkedin_applier
    - frame-aware _resolve_modal_frame + per-iteration reCAPTCHA pause in _navigate_modal
    - text/aria Easy Apply selectors (EASY_APPLY_TEXT_SELECTOR / EASY_APPLY_ARIA_SELECTOR)
    - paused_human (HTTP 200) response branch on POST /apply/linkedin-easy-apply
  affects:
    - LinkedIn apply path (now pauses to NEEDS_HUMAN on reCAPTCHA instead of bot-scoring through)
    - queued-linkedin-jobs query (NEEDS_HUMAN jobs excluded from autonomous retry)
    - Phase 04 dashboard (NEEDS_HUMAN is a new terminal-until-human status to surface)
    - upcoming VPS phase (live field-fill against custom/shadow-DOM controls still to be verified there)
tech_stack:
  added: []
  patterns:
    - "Easy Apply trigger located by visible text / English aria-label substring — never class or href (per-deploy hashed classes are dead)"
    - "Click-then-wait_for_selector with one retry — the modal open is racy, fixed sleeps are unreliable"
    - "Frame-aware modal driving: _resolve_modal_frame probes page.frames, returns the modal frame or falls back to page (overlay-in-main is the normal live path)"
    - "Per-iteration reCAPTCHA re-check at top of _navigate_modal loop (against top-level page) — mid-flow challenges caught, not just on modal open"
    - "Best-effort Telegram notify: missing env -> warn+return, API failure -> swallow; never blocks the route or raises"
key_files:
  created:
    - src/notify.py
    - tests/unit/test_linkedin_sdui_fixes.py
  modified:
    - src/queue/models.py (JobStatus.NEEDS_HUMAN)
    - src/audit_log.py (AuditEvent.NEEDS_HUMAN)
    - src/browser/linkedin_applier.py (selector fix, frame-aware modal, RecaptchaDetected, detect_recaptcha, per-iteration pause)
    - src/api/routes/apply/linkedin_apply.py (RecaptchaDetected handler -> NEEDS_HUMAN + Telegram + paused_human)
    - scripts/validate_easy_apply_selector.py (import migrated off deleted EASY_APPLY_BTN_XPATH)
key_decisions:
  - "Easy Apply selector matches English visible text / aria-label substring (stable) — never the per-deploy hashed class or href; Tagalog UI strings are deliberately not matched"
  - "reCAPTCHA is re-checked at the TOP of every _navigate_modal iteration against the top-level page, not once before the first fill — Enterprise reCAPTCHA can appear mid-flow on a later step"
  - "reCAPTCHA -> NEEDS_HUMAN + paused_human (HTTP 200), NOT a failure: the job is audited, never auto-requeued, and a Telegram alert fires; no submission is attempted"
  - "send_telegram is best-effort and never raises — a Telegram outage must not block returning paused_human (T-03-05-05)"
  - "_resolve_modal_frame returning page (overlay-in-main) is the EXPECTED live path, not an error — the frame probe is defensive for a future LinkedIn iframe move"
  - "Live field-fill against the SDUI modal is left UNVERIFIED on purpose — the controls are custom/shadow-DOM and most jobs pause at reCAPTCHA anyway; deferred to the VPS+VNC phase"
requirements-completed: [APPLY-01]
duration: ~40min
completed: "2026-05-29"
---

# Phase 03 Plan 05: LinkedIn Easy Apply SDUI Rework — Summary

**Reworked the dead LinkedIn Easy Apply flow against live SDUI reality: text/aria selector replacing the dead class XPath, frame-aware modal navigation, a per-iteration reCAPTCHA-Enterprise pause that transitions the job to NEEDS_HUMAN with a Telegram alert instead of bot-scoring through — 11 unit tests GREEN, all three live validation steps PASS. Live field-fill against the modal's custom/shadow-DOM controls remains unverified and is deferred to the VPS phase.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-05-29
- **Completed:** 2026-05-29
- **Tasks:** 3 of 3 completed (Task 3 = blocking human checkpoint, now VALIDATED)
- **Files created:** 2 — **Files modified:** 5

## Why This Plan Existed

Plan 03-04's Task 3 live checkpoint discovered that the shipped 03-01..03-04 applier could
not open the Easy Apply modal at all (recorded in `03-SDUI-FINDINGS.md`). Three concrete
breakages: (1) the trigger selector `//button[contains(@class,"jobs-apply-button")]` was dead
(the trigger is an `<a>` with per-deploy hashed classes), (2) modal navigation ran against the
wrong frame, and (3) reCAPTCHA Enterprise gates the flow, threatening the "zero human
intervention" goal if applies silently bot-score through. 03-05 fixes all three and adds a
safe human-pause path.

## Accomplishments

- **NEEDS_HUMAN state** added to `JobStatus` and `AuditEvent` — a paused-job status that is
  audited and excluded from autonomous retry (the existing queued-linkedin-jobs query filters
  on `QUEUED`, so `NEEDS_HUMAN != QUEUED` already excludes it; confirmed by comment, no query change).
- **Telegram notify helper** (`src/notify.py`) — async `send_telegram(text)` over `httpx` (already
  pinned, no new dep). Missing `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` -> logs `telegram_env_missing`
  and returns; API failure is swallowed. Best-effort by design; never raises, never logs the token.
- **Selector fix** — `EASY_APPLY_BTN_XPATH` deleted; replaced by `EASY_APPLY_TEXT_SELECTOR =
  "text=Easy Apply"` and `EASY_APPLY_ARIA_SELECTOR = "[aria-label*='Easy Apply' i]"`.
  `_find_and_click_easy_apply` tries text first, then aria, then click-and-`wait_for_selector`
  on the modal with one retry, raising `ModalNavigationError("modal_open_timeout")` only after the
  second failure and `NoEasyApplyButton` if neither selector matches.
- **Frame-aware modal** — `_resolve_modal_frame(page)` probes `page.frames` for the LinkedIn modal
  frame (Continue-to-next-step control or "Contact" title) and falls back to `page` for the
  overlay-in-main-document case (the normal live path). `fill_form_fields` now takes `frame` as its
  first positional parameter; all `_navigate_modal` locator calls run against the resolved frame.
- **Per-iteration reCAPTCHA pause** — `detect_recaptcha(page)` returns True when any frame URL
  contains both "recaptcha" and "enterprise". It runs at the TOP of every `_navigate_modal`
  iteration (against the top-level page, where reCAPTCHA loads as a sibling frame) so a challenge
  appearing on a later step is caught before any fill/click — raising `RecaptchaDetected` before
  submission.
- **Route pause branch** — `linkedin_apply.py` catches `RecaptchaDetected`: sets the job to
  `JobStatus.NEEDS_HUMAN` with reason `recaptcha_enterprise`, writes `AuditEvent.NEEDS_HUMAN`,
  awaits `send_telegram(...)`, and returns HTTP 200 `{"status": "paused_human", "job_id": ...}`.
  No `HTTPException`, no submission attempt.
- **Script repair** — `scripts/validate_easy_apply_selector.py` import migrated off the deleted
  `EASY_APPLY_BTN_XPATH` to `EASY_APPLY_TEXT_SELECTOR` (same commit that removed the constant, so
  module import and pytest collection do not break).

## Task Commits

1. **Task 1 (RED): failing tests for SDUI fixes** — `6324a82` (test) — NEEDS_HUMAN, reCAPTCHA detection, selector predicates
2. **Task 1 (GREEN): NEEDS_HUMAN state, Telegram notify, RecaptchaDetected** — `b2073bb` (feat)
3. **Task 2: frame-aware Easy Apply modal + reCAPTCHA pause path** — `7188c2b` (feat)
4. **Task 3: live browser re-validation** — human checkpoint, now VALIDATED (see below)

## Tests

`tests/unit/test_linkedin_sdui_fixes.py` — **11 tests, all GREEN** (`11 passed in 0.55s`):

- `test_needs_human_in_job_status`, `test_needs_human_in_audit_event`
- `test_recaptcha_detected_is_exception`
- `test_detect_recaptcha_true`, `test_detect_recaptcha_false`
- `test_send_telegram_missing_env`
- `test_find_easy_apply_uses_text_selector`, `test_find_easy_apply_falls_back_to_aria`,
  `test_find_easy_apply_raises_when_absent`
- `test_navigate_modal_detects_recaptcha` (challenge present on iteration 1)
- `test_navigate_modal_detects_recaptcha_mid_flow` (challenge absent on iteration 1, present on
  iteration 2 -> `RecaptchaDetected` raised before the second fill, submit never clicked)

## Task 3 — Live Validation Results (all PASS)

Run against `https://www.linkedin.com/jobs/view/4418669306/` using the saved Camoufox session.

1. **Selector** — `scripts/validate_easy_apply_selector.py` -> `Matched elements: 1`, button text
   "Easy Apply", `RESULT: PASS — selector resolves.` The new text selector resolves the trigger
   that the old dead class XPath could not.
2. **Modal opens** — `scripts/capture_sdui_apply.py` + screenshot confirmed the "Apply to Native
   Teams" modal opened to the Contact-info step (Email / Phone / Mobile fields, Next button,
   progress bar at 0%) and the script exited WITHOUT submitting.
3. **reCAPTCHA detection** — the apply flow loads frame
   `google.com/recaptcha/enterprise/anchor?...`, which `detect_recaptcha()` keys on -> the
   NEEDS_HUMAN pause path will fire correctly on live jobs.

The run never reached the Submit button. Resume signal "validated" received.

## Deviations from Plan

None — plan executed exactly as written. TDD RED/GREEN gates honored (`6324a82` test commit
precedes the `b2073bb` feat commit). The `scripts/validate_easy_apply_selector.py` import fix was
performed inside Task 2 (same commit that removed the constant) exactly as the plan's step 6b
required.

## Known Caveat — Live Field-Fill UNVERIFIED (honest assessment)

This is the one thing 03-05 does **not** prove, and it is recorded in
`03-SDUI-FINDINGS.md §"Residual risk after 03-05"`:

- The modal's form controls (Email address / Phone country code / Mobile number) are **custom /
  shadow-DOM components** — they are NOT readable as plain `input`/`select`/`textarea` from any
  frame's DOM. So `fill_form_fields`' field-fill fidelity against the live SDUI is **UNVERIFIED**.
- It can only be confirmed by a real **supervised** apply — which pauses at reCAPTCHA on most jobs
  anyway, so a fully autonomous end-to-end submit was not (and on most jobs cannot be) demonstrated.
- **Worst case is graceful, not catastrophic:** an unmappable control raises `UnknownFormField`
  -> the job is SKIPPED, not crashed.
- **Deferred** to the upcoming VPS phase (with VNC for remote challenge-solving / supervised
  field-fill verification). LinkedIn applies are therefore **human-in-the-loop on reCAPTCHA by
  design**, not unattended.

Because of this caveat, Phase 03 is marked DONE for the SDUI-rework and pause-path scope, with an
explicit note that live field-fill remains to be verified.

## Known Stubs

None. All implemented logic is live — `send_telegram` posts to the real Bot API, the selectors
and frame probe run against the real page, and the reCAPTCHA pause writes a real DB transition +
audit event. The only unproven element is live field-fill against shadow-DOM controls (above),
which is a verification gap, not a stub.

## Threat Flags

No new threat surface beyond the plan's threat model. Mitigations applied as planned:

- **T-03-05-03** (Elevation): reCAPTCHA -> NEEDS_HUMAN transition is audited via
  `write_audit(NEEDS_HUMAN)`; the job cannot be auto-requeued.
- **T-03-05-04** (Info Disclosure): `send_telegram` logs only event names; the bot token and the
  message body are never logged to structlog.
- **T-03-05-05** (DoS): `send_telegram` swallows all exceptions; HTTP 200 `paused_human` is returned
  regardless of Telegram success.
- **T-03-05-SC**: no new pip installs — `httpx` was already pinned.

## Self-Check: PASSED

- `src/notify.py` exists: FOUND
- `tests/unit/test_linkedin_sdui_fixes.py` exists: FOUND
- `scripts/validate_easy_apply_selector.py` exists (import migrated): FOUND
- `NEEDS_HUMAN` in `src/queue/models.py` (1) and `src/audit_log.py` (1): VERIFIED
- `EASY_APPLY_BTN_XPATH` / `jobs-apply-button` absent from `src/`: ZERO matches (VERIFIED)
- `RecaptchaDetected` / `paused_human` in `linkedin_apply.py`: 5 matches (VERIFIED)
- `tests/unit/test_linkedin_sdui_fixes.py`: 11 passed in 0.55s (VERIFIED)
- Commit `6324a82` (RED test): FOUND
- Commit `b2073bb` (GREEN feat): FOUND
- Commit `7188c2b` (frame-aware + pause): FOUND
