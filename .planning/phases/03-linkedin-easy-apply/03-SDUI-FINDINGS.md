# Phase 03 — Live Checkpoint Findings: Easy Apply Flow Drifted to SDUI

**Date:** 2026-05-29
**Source:** Live validation against `https://www.linkedin.com/jobs/view/4418669306/` (Native Teams — Business Development Manager) using the saved Camoufox session in `data/linkedin_profile`.
**Verdict:** Selector + apply-flow assumptions in `src/browser/linkedin_applier.py` are STALE. Live apply must not run until reworked.

## Environment confirmed working
- Camoufox launches and navigates (after pinning `playwright==1.58.0` — 1.60.0 crashes on uncaught page errors, camoufox#617).
- Fingerprint clean on bot.sannysoft.com (only expected `window.chrome` absence, correct for Firefox UA).
- Saved session is authenticated (profile visible, notifications present).
- Account UI language is **Tagalog**, not English.

## What the code assumes vs. live reality (CORRECTED after modal capture)

### 1. Trigger element — DRIFTED
- **Code** (`linkedin_applier.py:56`): `EASY_APPLY_BTN_XPATH = '//button[contains(@class, "jobs-apply-button")]'`
- **Live**: the Easy Apply trigger is an `<a>` (not `<button>`) with obfuscated hashed classes.
  - Main job frame: `aria-label="Mag-easy Apply sa trabahong ito"` (Tagalog), inner `<span>` text `Easy Apply` (English).
  - Preload frame also exposes an **English** control: `aria-label="Easy Apply to {title} at {company}"`, text `"Easy Apply"`.
- `jobs-apply-button` class is gone. Class matching is dead (per-deploy hashes).
- **Robust selector**: match visible text `Easy Apply` OR `aria-label` containing `Easy Apply` (English form is stable). Do NOT match on class or href.

### 2. Apply architecture — STILL A MODAL (earlier "navigation" diagnosis was WRONG)
- Clicking Easy Apply opens an in-page **modal** titled "Apply to Native Teams" with a multi-step flow:
  - Step 1 "Contact info": Email address (select), Phone country code (select), Mobile phone number (text input). Progress bar starts at 0%. A blue **Next** button advances.
- The modal is rendered **dynamically inside a frame/overlay** — `querySelectorAll` on the main document body only sees page chrome, NOT the modal fields. The applier must operate against the correct frame, not assume the main frame.
- The click to open is **flaky/timing-sensitive** — opened on one attempt, not on a retry. Applier must `wait_for` a specific modal selector and retry, not use a fixed sleep.

### 3. Modal content is ENGLISH — locale is NOT the blocker
- Even with the surrounding UI in Tagalog, the modal renders English labels ("Contact info", "Email address", "Next"). The code's English aria-labels (`'Submit application'`, `'Review your application'`, `'Continue to next step'`) plausibly still match **inside the modal frame**. Confirm against the live modal, but locale is a minor concern, not a rewrite driver.

### 4. 🚩 reCAPTCHA Enterprise present in the apply flow — FEASIBILITY RISK
- The apply flow loads `google.com/recaptcha/enterprise/...` (frame[4]). LinkedIn's SDUI Easy Apply is gated by **reCAPTCHA Enterprise** (invisible/scored).
- This directly threatens the project's "zero human intervention, 24/7 autonomous apply" goal: automated submissions may be silently bot-scored, throttled, or challenged. This is an architecture/feasibility question, not a selector fix.

## Implications for re-plan
1. **Selectors**: match on visible text / English aria-label substring (`Easy Apply`). No class, no href, no Tagalog strings.
2. **Frame-aware**: locate and drive the modal inside its actual frame; current `page.locator(...)` on the main frame is wrong.
3. **Open reliability**: wait for an explicit modal selector + retry the open click; the open is racy.
4. **reCAPTCHA**: decide phase strategy — accept human-in-the-loop on challenge, detect+pause on reCAPTCHA, or reassess autonomy claim. Must be resolved before promising autonomous submission.
5. **Re-validation**: keep `scripts/capture_sdui_apply.py` + `scripts/validate_easy_apply_selector.py` in the loop; new selectors are MEDIUM-confidence until confirmed live.

## Residual risk after 03-05 (verified 2026-05-29 live checkpoint)
Task 3 confirmed: new selector resolves (text "Easy Apply", 1 match), the modal opens to the
Contact-info step, and reCAPTCHA Enterprise is reliably detected (frame url
google.com/recaptcha/enterprise/anchor). HOWEVER: the modal's form controls (Email / Phone
country / Mobile number) are NOT readable as plain input/select/textarea from any frame's DOM —
they are custom/shadow-DOM components. So `fill_form_fields` field-fill fidelity against the live
SDUI is UNVERIFIED. It can only be confirmed by a real supervised apply (which will pause at
reCAPTCHA on most jobs anyway). Worst case is a graceful UnknownFormField → job SKIPPED, not a
crash. Treat live field-fill as the next validation step (likely during the VPS phase with VNC).

## Artifacts
- Screenshots: `data/li_debug.png`, `data/sdui_apply_debug.png` (gitignored)
- Scripts: `scripts/validate_easy_apply_selector.py`, `scripts/capture_sdui_apply.py`
