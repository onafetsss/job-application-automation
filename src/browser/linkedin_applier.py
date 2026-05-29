"""LinkedIn Easy Apply browser module — Camoufox-powered session, modal navigation, field fill.

Implements:
    ChallengeDetected       — CAPTCHA / authwall / 2FA / session expiry detected
    NoEasyApplyButton       — expected for non-Easy-Apply jobs (D-01)
    UnknownFormField        — label maps to no known profile field (D-11)
    check_for_challenge()   — URL + title inspection after page.goto()
    get_label_for()         — three-level aria-label → placeholder → label[for=id] fallback
    resolve_profile_field() — map label string to profile data or screening answer
    fill_form_fields()      — fill all field types on a modal page
    LinkedInApplier         — class owning the Camoufox session lifecycle and apply() method

Security: T-03-04 — logs job_id and event names only, never PII or resume bytes.
         T-03-05 — headless gated by CAMOUFOX_DISPLAY_MODE env (False on VPS with DISPLAY=:1, 'virtual' locally) + humanize=True + persistent_context (not headless-true).
         T-03-03 — bounded modal loop; raises on no navigation button found (no infinite loop).
"""

import os
from typing import Any

import structlog

from src.preparation.screening import generate_screening_answers

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class ChallengeDetected(Exception):
    """Raised when LinkedIn presents a CAPTCHA, authwall, or 2FA prompt."""


class NoEasyApplyButton(Exception):
    """Raised when the Easy Apply button is absent — expected for non-Easy-Apply jobs (D-01)."""


class UnknownFormField(Exception):
    """Raised when a form field label cannot be mapped to a known profile field (D-11)."""


class ModalNavigationError(Exception):
    """Raised when no Next/Review/Submit button is found during modal navigation (T-03-03)."""


class RecaptchaDetected(Exception):
    """Raised when reCAPTCHA Enterprise is detected in the apply flow — caller must pause the job."""


def detect_recaptcha(page: Any) -> bool:
    """Return True when any frame in the page is a reCAPTCHA Enterprise frame.

    Synchronous: ``page.frames`` is a property (not a coroutine) in Playwright.
    Checks every frame's URL for both ``recaptcha`` and ``enterprise`` substrings —
    the live signal (03-SDUI-FINDINGS.md §4) is a sibling frame loading
    ``google.com/recaptcha/enterprise/...``.

    Args:
        page: Playwright/Camoufox page object (top-level).

    Returns:
        True if a reCAPTCHA Enterprise frame is present, else False.
    """
    return any(
        "recaptcha" in f.url.lower() and "enterprise" in f.url.lower()
        for f in getattr(page, "frames", [])
    )


# ---------------------------------------------------------------------------
# URL/title patterns for challenge detection (RESEARCH.md Pattern 2)
# ---------------------------------------------------------------------------

CHALLENGE_URL_PATTERNS = ["/checkpoint/", "/authwall/"]
LOGIN_URL_PATTERNS = ["/login", "/uas/login", "/signin"]

# Easy Apply trigger selectors (03-SDUI-FINDINGS.md §1 — class selectors are dead).
# Locate by visible text first, then by aria-label (case-insensitive) — never by class/href.
EASY_APPLY_TEXT_SELECTOR = "text=Easy Apply"
EASY_APPLY_ARIA_SELECTOR = "[aria-label*='Easy Apply' i]"

# Confirmed-open modal selector — wait for this before declaring the trigger click a success.
MODAL_SELECTOR = "div[data-test-modal], div[role='dialog']"

# Field label → profile key mapping (case-insensitive substring match)
_LABEL_TO_PROFILE_KEY: list[tuple[str, str]] = [
    ("first name", "first_name"),
    ("last name", "last_name"),
    ("full name", "full_name"),
    ("name", "full_name"),
    ("email", "email"),
    ("phone", "phone"),
    ("mobile", "phone"),
    ("linkedin", "linkedin_url"),
    ("profile", "linkedin_url"),
    ("years of experience", "years_of_experience"),
    ("years experience", "years_of_experience"),
    ("experience", "years_of_experience"),
    ("city", "city"),
    ("location", "location"),
    ("website", "website"),
    ("portfolio", "portfolio"),
]


# ---------------------------------------------------------------------------
# Challenge detection
# ---------------------------------------------------------------------------


async def check_for_challenge(page: Any) -> str | None:
    """Inspect page URL and title for LinkedIn challenge / session-expiry signals.

    Returns a non-None string describing the challenge type when detected, or
    ``None`` when the page is clean.

    Args:
        page: Playwright/Camoufox page object.

    Returns:
        Challenge type string (e.g. ``"session_expired"``, ``"checkpoint: <url>"``,
        ``"challenge_page_title: <title>"``) or ``None``.
    """
    url = page.url

    for pattern in CHALLENGE_URL_PATTERNS:
        if pattern in url:
            return f"checkpoint: {url}"

    for pattern in LOGIN_URL_PATTERNS:
        if pattern in url:
            return "session_expired"

    title: str = await page.title()
    lower_title = title.lower()
    if "unusual activity" in lower_title or "security verification" in lower_title:
        return f"challenge_page_title: {title}"

    return None


# ---------------------------------------------------------------------------
# Label extraction
# ---------------------------------------------------------------------------


async def get_label_for(page: Any, element: Any) -> str:
    """Get the human-readable label for a form element.

    Three-level fallback: aria-label → placeholder → associated label[for=id].

    Args:
        page: Playwright/Camoufox page object.
        element: A Playwright locator or element handle.

    Returns:
        Label string (may be empty string if none found).
    """
    aria = await element.get_attribute("aria-label")
    if aria:
        return aria.strip()

    placeholder = await element.get_attribute("placeholder")
    if placeholder:
        return placeholder.strip()

    el_id = await element.get_attribute("id")
    if el_id:
        label_el = page.locator(f"label[for='{el_id}']")
        if await label_el.count() > 0:
            text = await label_el.first.text_content()
            return (text or "").strip()

    return ""


# ---------------------------------------------------------------------------
# Profile field resolution
# ---------------------------------------------------------------------------


def resolve_profile_field(
    label: str,
    profile: dict,
    screening_answers: list[dict],
) -> str | None:
    """Map a form field label to a value from the profile dict or screening answers.

    Performs case-insensitive substring matching against known label patterns.
    Falls back to screening answers when the label matches a known question.

    Args:
        label: The form field label string (from ``get_label_for``).
        profile: Dict of profile fields (keys: full_name, email, phone,
            linkedin_url, years_of_experience, etc.).
        screening_answers: List of ``{question, answer}`` dicts from
            ``generate_screening_answers``.

    Returns:
        The string value to fill, or ``None`` when no mapping exists.

    Raises:
        UnknownFormField: If no match is found in profile or screening answers.
    """
    lower_label = label.lower()

    # Direct profile key match
    for label_fragment, profile_key in _LABEL_TO_PROFILE_KEY:
        if label_fragment in lower_label:
            value = profile.get(profile_key)
            if value is not None:
                return str(value)

    # Screening answers fuzzy match (question substring)
    for answer_item in screening_answers:
        question = answer_item.get("question", "")
        if label.lower() in question.lower() or question.lower() in label.lower():
            return str(answer_item.get("answer", ""))

    raise UnknownFormField(f"unknown_form_field: {label}")


# ---------------------------------------------------------------------------
# Form field filling
# ---------------------------------------------------------------------------


async def fill_form_fields(
    frame: Any,
    profile: dict,
    screening_answers: list[dict],
    resume_path: str | None = None,
) -> None:
    """Detect and fill all form field types on the current modal page.

    Field types handled: resume file upload, phone, text inputs, radio groups,
    dropdowns. Unknown text input labels raise ``UnknownFormField`` (D-11).

    Args:
        frame: Playwright/Camoufox frame (or page) that owns the modal content.
            All locator calls are issued against this frame, not the top-level
            page — the live modal renders inside a resolved frame/overlay
            (03-SDUI-FINDINGS.md §2).
        profile: Profile dict (full_name, email, phone, linkedin_url, etc.).
        screening_answers: List of ``{question, answer}`` dicts.
        resume_path: Absolute path to the resume file for file upload inputs.
            If ``None`` or file not found, upload step is skipped with a warning.
    """
    # --- Resume file upload (T-03-04: path resolved from env, never logged) ---
    if resume_path and os.path.isfile(resume_path):
        file_inputs = frame.locator("input[type='file']")
        for i in range(await file_inputs.count()):
            fi = file_inputs.nth(i)
            if await fi.is_visible():
                await fi.set_input_files(resume_path)
                log.info("li_resume_uploaded")
    elif resume_path:
        log.warning("li_resume_not_found")

    # --- Phone number ---
    phone_selectors = [
        "input[type='tel']",
        "input[name*='phone']",
        "input[id*='phone']",
        "input[aria-label*='phone' i]",
    ]
    phone_value = profile.get("phone", "")
    if phone_value:
        for sel in phone_selectors:
            el = frame.locator(sel).first
            try:
                if await el.is_visible():
                    await el.fill(phone_value)
                    break
            except Exception:
                continue

    # --- Text inputs (name, email, years of experience, LinkedIn URL, etc.) ---
    text_inputs = frame.locator(".artdeco-text-input--input")
    for i in range(await text_inputs.count()):
        el = text_inputs.nth(i)
        label = await get_label_for(frame, el)
        # resolve_profile_field raises UnknownFormField if no match (D-11)
        value = resolve_profile_field(label, profile, screening_answers)
        if await el.is_enabled():
            await el.fill(value)

    # --- Radio buttons (work authorization yes/no, boolean questions) ---
    radio_groups = frame.locator("fieldset, div[role='radiogroup']")
    for i in range(await radio_groups.count()):
        group = radio_groups.nth(i)
        try:
            legend_el = group.locator("legend")
            legend_text = ""
            if await legend_el.count() > 0:
                legend_text = (await legend_el.text_content() or "").strip()
            if not legend_text:
                continue
            # Map legend to yes/no answer from profile or screening
            answer = _resolve_yes_no(legend_text, profile, screening_answers)
            if answer is not None:
                radio = group.locator(f"input[type='radio'][value='{answer}']")
                if await radio.count() > 0:
                    await radio.first.click()
        except Exception:
            continue

    # --- Dropdowns ---
    selects = frame.locator("select")
    for i in range(await selects.count()):
        sel_el = selects.nth(i)
        label = await get_label_for(frame, sel_el)
        try:
            value = resolve_profile_field(label, profile, screening_answers)
            if value is not None:
                await sel_el.select_option(label=value)
        except UnknownFormField:
            pass  # Unknown dropdowns are skipped (unlike text inputs which hard-stop)


def _resolve_yes_no(
    legend: str,
    profile: dict,
    screening_answers: list[dict],
) -> str | None:
    """Resolve a yes/no radio group from profile booleans or screening answers.

    Returns ``"Yes"`` or ``"No"`` (LinkedIn radio values), or ``None`` when not resolvable.
    """
    lower = legend.lower()

    # Work authorization
    if "authorized" in lower or "work authorization" in lower or "eligible to work" in lower:
        return "Yes" if profile.get("work_authorized", True) else "No"

    # Require sponsorship
    if "sponsor" in lower or "visa" in lower:
        return "No" if profile.get("no_sponsorship_needed", True) else "Yes"

    # Screening answers fuzzy match
    for answer_item in screening_answers:
        question = answer_item.get("question", "").lower()
        if legend.lower() in question or question in legend.lower():
            ans = str(answer_item.get("answer", "")).strip().lower()
            if ans in ("yes", "true", "1"):
                return "Yes"
            if ans in ("no", "false", "0"):
                return "No"

    return None


# ---------------------------------------------------------------------------
# LinkedInApplier class
# ---------------------------------------------------------------------------


class LinkedInApplier:
    """Camoufox-powered LinkedIn Easy Apply browser automation.

    Loads a persistent Firefox session from ``user_data_dir``, navigates to a
    LinkedIn job URL, detects challenges/session-expiry, finds the Easy Apply
    button (skipping when absent), navigates the multi-page modal, fills known
    fields, answers screening questions via the directly-imported shared
    function, and submits.

    Args:
        user_data_dir: Path to the Camoufox persistent profile directory
            (e.g. ``/data/linkedin_profile``). Managed by Camoufox across runs.
    """

    def __init__(self, user_data_dir: str) -> None:
        self.user_data_dir = user_data_dir

    async def _find_and_click_easy_apply(self, page: Any) -> None:
        """Locate the Easy Apply trigger by text/aria, click it, and confirm the modal opens.

        Tries the visible-text selector first, then the aria-label selector. The
        first visible match is clicked; the method then waits for a confirmed modal
        selector to appear, retrying the click once on timeout before giving up.

        Args:
            page: Playwright/Camoufox page object already navigated to the job URL.

        Raises:
            NoEasyApplyButton: When neither selector matches a visible element
                (expected for non-Easy-Apply jobs — D-01).
            ModalNavigationError: When the trigger is clicked but the modal never
                opens within the timeout (after one retry).
        """
        # LinkedIn lazy-renders the Easy Apply button a few seconds after the job
        # page loads. Wait for it before checking, or we falsely conclude it's
        # absent. A genuine non-Easy-Apply job simply times out here and falls
        # through to NoEasyApplyButton below (correct skip).
        try:
            await page.wait_for_selector(EASY_APPLY_TEXT_SELECTOR, timeout=20000)
        except Exception:
            pass

        for selector in (EASY_APPLY_TEXT_SELECTOR, EASY_APPLY_ARIA_SELECTOR):
            locator = page.locator(selector)
            if await locator.count() > 0:
                first = locator.first
                if await first.is_visible():
                    await first.click()
                    log.info("li_easy_apply_clicked", selector=selector)
                    # Wait for the modal to confirm-open; retry the trigger click once.
                    for attempt in range(2):
                        try:
                            await page.wait_for_selector(MODAL_SELECTOR, timeout=8000)
                            return  # Modal confirmed open.
                        except Exception:
                            if attempt == 0:
                                log.warning("li_modal_open_retry", selector=selector)
                                await first.click()  # retry the trigger click
                            else:
                                raise ModalNavigationError("modal_open_timeout")
        raise NoEasyApplyButton(
            "Easy Apply trigger not found — neither text nor aria matched"
        )

    async def _resolve_modal_frame(self, page: Any) -> Any:
        """Locate the frame that owns the Easy Apply modal content, or return the page.

        Probes ``page.frames`` for a LinkedIn frame that exposes the modal's
        "Continue to next step" control or a "Contact"-titled step. If none
        qualifies, returns ``page`` itself.

        Per 03-SDUI-FINDINGS.md §2, ``return page`` is the EXPECTED outcome for the
        current live structure: the modal is an overlay div in the MAIN document,
        not a separate iframe. The frame probe is defensive in case LinkedIn moves
        the modal into a dedicated iframe later. "No frame resolved" is the normal
        path, not an error.

        Args:
            page: Playwright/Camoufox page object with the modal open.

        Returns:
            The resolved modal frame, or ``page`` when the modal is an overlay.
        """
        for frame in page.frames:
            if "linkedin.com" not in frame.url.lower():
                continue
            try:
                count = await frame.locator("[aria-label='Continue to next step']").count()
                if count > 0:
                    return frame
                title = await frame.title()
                if "contact" in title.lower():
                    return frame
            except Exception:
                continue
        return page  # overlay pattern — modal lives in the main document

    async def _navigate_modal(
        self,
        page: Any,
        profile: dict,
        screening_answers: list[dict],
        resume_path: str | None,
    ) -> None:
        """Loop through Easy Apply modal pages: fill fields, click Next/Review/Submit.

        Bounded loop — raises ``ModalNavigationError`` if no navigation button is
        found (T-03-03: no infinite loop). reCAPTCHA Enterprise is re-checked at the
        TOP OF EVERY iteration against the top-level page (challenges can appear
        mid-flow on a later step, not just at modal open — 03-SDUI-FINDINGS.md §4);
        on detection ``RecaptchaDetected`` is raised before any fill/click on that
        step so the job pauses instead of being bot-scored into rejection.

        Args:
            page: Playwright/Camoufox page object with the modal open. reCAPTCHA
                detection always runs against this top-level page.
            profile: Profile dict for field filling.
            screening_answers: Screening answers for field filling.
            resume_path: Resume file path for file upload inputs.

        Raises:
            RecaptchaDetected: When a reCAPTCHA Enterprise frame is present at the
                start of any iteration — caller pauses the job (NEEDS_HUMAN).
            ModalNavigationError: When no Submit/Review/Next button is visible.
            UnknownFormField: Propagated from ``fill_form_fields`` when an
                unresolvable text input is encountered (D-11).
        """
        # Resolve the frame/overlay that owns the modal content; drive locators on it.
        frame = await self._resolve_modal_frame(page)

        MAX_PAGES = 20  # Hard cap — LinkedIn Easy Apply never exceeds ~10 pages
        for _ in range(MAX_PAGES):
            # FIRST statement of every iteration: re-check reCAPTCHA on the TOP-LEVEL
            # page. A single pre-loop check would let a mid-flow challenge slip
            # through and submit, so this must run before each step's fill.
            if detect_recaptcha(page):
                log.warning("li_recaptcha_detected")
                raise RecaptchaDetected("recaptcha_enterprise")

            await fill_form_fields(frame, profile, screening_answers, resume_path)

            submit_btn = frame.locator("button[aria-label='Submit application']")
            review_btn = frame.locator("button[aria-label='Review your application']")
            next_btn = frame.locator("button[aria-label='Continue to next step']")

            if await submit_btn.is_visible():
                # Optionally uncheck "follow company" before submit
                follow_cb = frame.locator("label[for='follow-company-checkbox']")
                if await follow_cb.is_visible():
                    checkbox = frame.locator("#follow-company-checkbox")
                    if await checkbox.count() > 0 and await checkbox.is_checked():
                        await follow_cb.click()
                await submit_btn.click()
                log.info("li_submit_clicked")
                return  # Success — modal submitted

            elif await review_btn.is_visible():
                await review_btn.click()
                log.info("li_review_clicked")
            elif await next_btn.is_visible():
                await next_btn.click()
                log.info("li_next_clicked")
            else:
                raise ModalNavigationError(
                    "No Next/Review/Submit button found on modal page"
                )

            # Wait briefly for modal page to re-render after navigation click
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass  # timeout is acceptable — modal uses partial DOM updates

        raise ModalNavigationError("Modal page limit exceeded without reaching Submit")

    async def apply(self, job: Any, resume_path: str) -> dict:
        """Execute a full LinkedIn Easy Apply submission for a single job.

        Opens a Camoufox session using the persistent profile directory, navigates
        to the job URL, detects challenges, finds and clicks Easy Apply, navigates
        the modal, and returns ``{"status": "submitted"}`` on success.

        Args:
            job: ORM Job object with attributes ``url``, ``title``, ``company``,
                ``clean_jd``, ``screening_questions`` (JSON string or None), and
                ``id``.
            resume_path: Absolute path to the resume PDF to upload. Must be
                accessible inside the Docker container (``/app/resumes/<name>``).

        Returns:
            ``{"status": "submitted"}`` on successful submission.

        Raises:
            ChallengeDetected: When LinkedIn presents a CAPTCHA, authwall, or
                login redirect — stop immediately, caller fires Telegram alert (D-06).
            NoEasyApplyButton: When the Easy Apply button is absent — caller marks
                job as SKIPPED (D-01).
            UnknownFormField: When an unrecognised form field is encountered —
                caller marks job as SKIPPED with reason (D-11).
            ModalNavigationError: When the modal navigation loop hits a dead end.
        """
        import json as _json

        from camoufox.async_api import AsyncCamoufox

        log.info("li_apply_start", job_id=getattr(job, "id", None))

        # Build profile dict from job.app_state profile (resolved by caller if available,
        # or minimal fallback — the browser module is profile-agnostic)
        profile = getattr(job, "_profile_dict", {}) or {}

        # Resolve screening answers via direct import (no self-HTTP — RESEARCH Anti-Pattern 3)
        questions: list[str] = []
        raw_sq = getattr(job, "screening_questions", None)
        if raw_sq:
            try:
                questions = _json.loads(raw_sq) if isinstance(raw_sq, str) else list(raw_sq)
            except Exception:
                questions = []

        profile_config = getattr(job, "_profile_config", None)
        job_title = getattr(job, "title", "")
        job_description = getattr(job, "clean_jd", "") or ""

        screening_answers: list[dict] = []
        if questions:
            try:
                screening_answers = generate_screening_answers(
                    profile_config=profile_config,
                    job_title=job_title,
                    job_description=job_description,
                    questions=questions,
                )
                log.info("li_screening_answers_ready", count=len(screening_answers))
            except RuntimeError:
                log.warning("li_screening_answers_failed")
                # Continue without screening answers — fields will raise UnknownFormField
                # if they cannot be resolved from profile

        # Env-gated headless mode (T-03-05): on the VPS, supervisord sets
        # CAMOUFOX_DISPLAY_MODE=xvfb so Camoufox runs with a real window on
        # DISPLAY=:1 (headless=False). Locally (unset), keep "virtual".
        _display_mode = os.environ.get("CAMOUFOX_DISPLAY_MODE", "")
        _headless: bool | str = False if _display_mode == "xvfb" else "virtual"

        async with AsyncCamoufox(
            headless=_headless,           # xvfb→False on VPS, else "virtual" (T-03-05)
            persistent_context=True,
            user_data_dir=self.user_data_dir,
            humanize=True,               # Human-like mouse movement (anti-detection)
            os="windows",               # Spoof Windows OS fingerprint
        ) as context:
            page = await context.new_page()
            job_url = getattr(job, "url", "")
            await page.goto(job_url)

            # Challenge detection — halt immediately on any challenge (D-06)
            challenge = await check_for_challenge(page)
            if challenge is not None:
                log.error("li_challenge_detected", challenge=challenge, job_id=getattr(job, "id", None))
                raise ChallengeDetected(challenge)

            # Locate and click Easy Apply trigger; this confirms the modal opens
            # via MODAL_SELECTOR (raises NoEasyApplyButton if absent — D-01,
            # ModalNavigationError if the trigger clicks but the modal never opens).
            await self._find_and_click_easy_apply(page)

            # Navigate modal pages: fill fields, click Next/Review/Submit (T-03-03).
            # reCAPTCHA is re-checked at the top of every step inside _navigate_modal.
            await self._navigate_modal(page, profile, screening_answers, resume_path)

        log.info("li_apply_complete", job_id=getattr(job, "id", None))
        return {"status": "submitted"}
