"""Unit tests for the LinkedIn SDUI fixes (plan 03-05).

TDD contract for the live-SDUI rework of the Easy Apply applier:

Task 1 behaviors:
    test_needs_human_in_job_status        — JobStatus.NEEDS_HUMAN is a valid member
    test_needs_human_in_audit_event       — AuditEvent.NEEDS_HUMAN is a valid member
    test_recaptcha_detected_is_exception  — RecaptchaDetected subclasses Exception
    test_detect_recaptcha_true            — recaptcha-enterprise frame → True
    test_detect_recaptcha_false           — linkedin frame only → False
    test_send_telegram_missing_env        — missing env var → no raise

Task 2 behaviors:
    test_find_easy_apply_uses_text_selector   — text=Easy Apply selector resolves + clicks
    test_find_easy_apply_falls_back_to_aria   — aria fallback when text count=0
    test_find_easy_apply_raises_when_absent   — both selectors empty → NoEasyApplyButton
    test_navigate_modal_detects_recaptcha     — recaptcha present on iter 1 → RecaptchaDetected
    test_navigate_modal_detects_recaptcha_mid_flow — recaptcha appears on iter 2 → caught, no submit

All tests import without a live DB or browser.
"""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Task 1 — enums, exception, detection predicate, notify helper
# ---------------------------------------------------------------------------


def test_needs_human_in_job_status() -> None:
    """JobStatus.NEEDS_HUMAN is a valid enum member resolvable by value."""
    from src.queue.models import JobStatus

    assert JobStatus("NEEDS_HUMAN") == JobStatus.NEEDS_HUMAN


def test_needs_human_in_audit_event() -> None:
    """AuditEvent.NEEDS_HUMAN is a valid enum member resolvable by value."""
    from src.audit_log import AuditEvent

    assert AuditEvent("NEEDS_HUMAN") == AuditEvent.NEEDS_HUMAN


def test_recaptcha_detected_is_exception() -> None:
    """RecaptchaDetected is an Exception subclass importable from the applier."""
    from src.browser.linkedin_applier import RecaptchaDetected

    assert issubclass(RecaptchaDetected, Exception)


def test_detect_recaptcha_true() -> None:
    """detect_recaptcha returns True when a frame URL has both recaptcha + enterprise."""
    from src.browser.linkedin_applier import detect_recaptcha

    frame = MagicMock()
    frame.url = "https://www.google.com/recaptcha/enterprise/v3"
    page = MagicMock()
    page.frames = [frame]

    assert detect_recaptcha(page) is True


def test_detect_recaptcha_false() -> None:
    """detect_recaptcha returns False when no frame matches recaptcha+enterprise."""
    from src.browser.linkedin_applier import detect_recaptcha

    frame = MagicMock()
    frame.url = "https://www.linkedin.com/jobs/view/"
    page = MagicMock()
    page.frames = [frame]

    assert detect_recaptcha(page) is False


async def test_send_telegram_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """send_telegram returns without raising when TELEGRAM_BOT_TOKEN is unset."""
    from src.notify import send_telegram

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    # Must not raise even though env is missing.
    await send_telegram("hi")


# ---------------------------------------------------------------------------
# Task 2 — selector resolution + frame-aware reCAPTCHA pause
# ---------------------------------------------------------------------------


def _make_locator(count: int, visible: bool = True) -> MagicMock:
    """Build a mock Playwright locator with async count/is_visible/click and a .first."""
    locator = MagicMock()
    locator.count = AsyncMock(return_value=count)
    first = MagicMock()
    first.is_visible = AsyncMock(return_value=visible)
    first.click = AsyncMock()
    locator.first = first
    return locator


async def test_find_easy_apply_uses_text_selector() -> None:
    """The text selector resolves first; click is called once, no fallback needed."""
    from src.browser.linkedin_applier import (
        EASY_APPLY_TEXT_SELECTOR,
        LinkedInApplier,
    )

    text_locator = _make_locator(count=1, visible=True)
    page = MagicMock()
    page.locator = MagicMock(return_value=text_locator)
    page.wait_for_selector = AsyncMock()

    applier = LinkedInApplier(user_data_dir="/tmp/nope")
    await applier._find_and_click_easy_apply(page)

    page.locator.assert_any_call(EASY_APPLY_TEXT_SELECTOR)
    text_locator.first.click.assert_awaited()
    page.wait_for_selector.assert_awaited()


async def test_find_easy_apply_falls_back_to_aria() -> None:
    """When the text selector count=0, the aria selector resolves the trigger."""
    from src.browser.linkedin_applier import (
        EASY_APPLY_ARIA_SELECTOR,
        LinkedInApplier,
    )

    text_locator = _make_locator(count=0, visible=True)
    aria_locator = _make_locator(count=1, visible=True)

    def locator_router(selector: str) -> MagicMock:
        if selector == EASY_APPLY_ARIA_SELECTOR:
            return aria_locator
        return text_locator

    page = MagicMock()
    page.locator = MagicMock(side_effect=locator_router)
    page.wait_for_selector = AsyncMock()

    applier = LinkedInApplier(user_data_dir="/tmp/nope")
    await applier._find_and_click_easy_apply(page)

    aria_locator.first.click.assert_awaited()


async def test_find_easy_apply_raises_when_absent() -> None:
    """When both selectors return count=0, NoEasyApplyButton is raised."""
    from src.browser.linkedin_applier import (
        LinkedInApplier,
        NoEasyApplyButton,
    )

    empty = _make_locator(count=0)
    page = MagicMock()
    page.locator = MagicMock(return_value=empty)
    page.wait_for_selector = AsyncMock()

    applier = LinkedInApplier(user_data_dir="/tmp/nope")
    with pytest.raises(NoEasyApplyButton):
        await applier._find_and_click_easy_apply(page)


def _recaptcha_frame() -> MagicMock:
    frame = MagicMock()
    frame.url = "https://www.google.com/recaptcha/enterprise/anchor"
    return frame


def _linkedin_frame() -> MagicMock:
    frame = MagicMock()
    frame.url = "https://www.linkedin.com/jobs/view/"
    # _resolve_modal_frame probes; make it return page (overlay pattern)
    frame.locator = MagicMock(return_value=MagicMock(count=AsyncMock(return_value=0)))
    frame.title = AsyncMock(return_value="LinkedIn")
    return frame


async def test_navigate_modal_detects_recaptcha(monkeypatch: pytest.MonkeyPatch) -> None:
    """reCAPTCHA present on the FIRST iteration → RecaptchaDetected before any fill."""
    from src.browser import linkedin_applier as mod
    from src.browser.linkedin_applier import LinkedInApplier, RecaptchaDetected

    page = MagicMock()
    page.frames = [_linkedin_frame(), _recaptcha_frame()]
    page.wait_for_load_state = AsyncMock()

    fill_spy = AsyncMock()
    monkeypatch.setattr(mod, "fill_form_fields", fill_spy)

    applier = LinkedInApplier(user_data_dir="/tmp/nope")
    with pytest.raises(RecaptchaDetected):
        await applier._navigate_modal(page, {}, [], None)

    # No fill should have happened — detection runs before the first fill.
    fill_spy.assert_not_awaited()


async def test_navigate_modal_detects_recaptcha_mid_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reCAPTCHA absent on iter 1 (fill + Next), present on iter 2 → caught, no submit."""
    from src.browser import linkedin_applier as mod
    from src.browser.linkedin_applier import LinkedInApplier, RecaptchaDetected

    li_frame = _linkedin_frame()
    recaptcha = _recaptcha_frame()

    page = MagicMock()
    # frames is a property in Playwright — emulate a changing list across iterations.
    frames_sequence = [
        [li_frame],              # iteration 1: no recaptcha
        [li_frame, recaptcha],   # iteration 2: recaptcha appears
    ]
    frames_calls = {"n": 0}

    def frames_getter() -> list:
        # detect_recaptcha + _resolve_modal_frame both read .frames; return current state.
        idx = min(frames_calls["n"], len(frames_sequence) - 1)
        return frames_sequence[idx]

    type(page).frames = property(lambda self: frames_getter())
    page.wait_for_load_state = AsyncMock()

    # Modal-frame locators: Next visible on iter 1, Submit never reached.
    submit_btn = MagicMock(is_visible=AsyncMock(return_value=False), click=AsyncMock())
    review_btn = MagicMock(is_visible=AsyncMock(return_value=False), click=AsyncMock())
    next_btn = MagicMock(is_visible=AsyncMock(return_value=True), click=AsyncMock())

    def modal_locator(selector: str) -> MagicMock:
        if "Submit" in selector:
            return submit_btn
        if "Review" in selector:
            return review_btn
        if "Continue" in selector or "next" in selector.lower():
            return next_btn
        return MagicMock(count=AsyncMock(return_value=0))

    # Resolve to the linkedin frame as the modal frame, drive locators against it.
    li_frame.locator = MagicMock(side_effect=modal_locator)
    li_frame.title = AsyncMock(return_value="Contact info")

    fill_spy = AsyncMock()
    monkeypatch.setattr(mod, "fill_form_fields", fill_spy)

    async def fake_resolve(self, p):  # noqa: ANN001
        return li_frame

    monkeypatch.setattr(LinkedInApplier, "_resolve_modal_frame", fake_resolve)

    # Advance the frames sequence each time Next is clicked (simulates step transition).
    async def advance_on_next() -> None:
        frames_calls["n"] += 1

    next_btn.click = AsyncMock(side_effect=advance_on_next)

    applier = LinkedInApplier(user_data_dir="/tmp/nope")
    with pytest.raises(RecaptchaDetected):
        await applier._navigate_modal(page, {}, [], None)

    # Iteration 1 filled once; iteration 2 raised before filling again.
    assert fill_spy.await_count == 1
    submit_btn.click.assert_not_awaited()
