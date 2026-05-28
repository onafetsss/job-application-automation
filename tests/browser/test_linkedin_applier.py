"""RED scaffold — browser tests for src.browser.linkedin_applier.

These tests are in RED state. The module src.browser.linkedin_applier is created
in Plan 03-02. Tests use pytest.mark.xfail so the suite collects without a hard
error when the module is missing.

Tests:
    test_challenge_detected        — /checkpoint/ URL causes challenge check to return a non-None string
    test_no_easy_apply_button      — locator count==0 raises NoEasyApplyButton
    test_unknown_form_field        — unmappable field label raises UnknownFormField
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    import src.browser.linkedin_applier as linkedin_applier  # type: ignore[import]

    ChallengeDetected = linkedin_applier.ChallengeDetected
    NoEasyApplyButton = linkedin_applier.NoEasyApplyButton
    UnknownFormField = linkedin_applier.UnknownFormField
    check_for_challenge = linkedin_applier.check_for_challenge
    _MODULE_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    _MODULE_AVAILABLE = False
    # Sentinel stubs so type-checker and collection succeed
    ChallengeDetected = Exception  # type: ignore[assignment,misc]
    NoEasyApplyButton = Exception  # type: ignore[assignment,misc]
    UnknownFormField = Exception   # type: ignore[assignment,misc]
    check_for_challenge = None     # type: ignore[assignment]
    linkedin_applier = None        # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Test 1: challenge detection fires on /checkpoint/ URL
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    not _MODULE_AVAILABLE,
    reason="src.browser.linkedin_applier implemented in Plan 03-02",
    strict=False,
)
async def test_challenge_detected() -> None:
    """A page whose URL contains /checkpoint/ must return a non-None challenge string.

    check_for_challenge() is the function that inspects the page URL and title.
    When /checkpoint/ is in the URL, it must return a non-None, non-empty string
    describing the challenge type.
    """
    if not _MODULE_AVAILABLE:
        pytest.xfail("src.browser.linkedin_applier not yet available — implemented in Plan 03-02")

    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/checkpoint/challenge/verify"
    mock_page.title = AsyncMock(return_value="LinkedIn Security Verification")

    result = await check_for_challenge(mock_page)

    assert result is not None, (
        "check_for_challenge must return a non-None string for /checkpoint/ URLs"
    )
    assert isinstance(result, str), "check_for_challenge must return a string"
    assert len(result) > 0, "challenge result string must not be empty"


# ---------------------------------------------------------------------------
# Test 2: NoEasyApplyButton raised when Easy Apply button absent
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    not _MODULE_AVAILABLE,
    reason="src.browser.linkedin_applier implemented in Plan 03-02",
    strict=False,
)
async def test_no_easy_apply_button() -> None:
    """When the Easy Apply locator count() returns 0, NoEasyApplyButton must be raised.

    LinkedInApplier._find_and_click_easy_apply uses page.locator(...).count()
    to detect presence. Count==0 means no Easy Apply button.
    """
    if not _MODULE_AVAILABLE:
        pytest.xfail("src.browser.linkedin_applier not yet available — implemented in Plan 03-02")

    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/jobs/view/123456789/"
    mock_page.title = AsyncMock(return_value="Senior Engineer at Test Corp - LinkedIn")

    # Simulate: locator(...).count() returns 0 — button not present
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=0)
    mock_page.locator = MagicMock(return_value=mock_locator)

    applier = linkedin_applier.LinkedInApplier(user_data_dir="/data/linkedin_profile")

    with pytest.raises(NoEasyApplyButton):
        await applier._find_and_click_easy_apply(mock_page)


# ---------------------------------------------------------------------------
# Test 3: UnknownFormField raised for unmappable field label
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    not _MODULE_AVAILABLE,
    reason="src.browser.linkedin_applier implemented in Plan 03-02",
    strict=False,
)
async def test_unknown_form_field() -> None:
    """An unmappable form field label must raise UnknownFormField.

    When the form field resolver encounters a label it cannot map to a known
    profile field, it must raise UnknownFormField with the field label.
    """
    if not _MODULE_AVAILABLE:
        pytest.xfail("src.browser.linkedin_applier not yet available — implemented in Plan 03-02")

    resolve_profile_field = getattr(linkedin_applier, "resolve_profile_field", None)
    if resolve_profile_field is None:
        pytest.xfail("resolve_profile_field not yet implemented in Plan 03-02")

    with pytest.raises(UnknownFormField):
        resolve_profile_field(
            label="some_completely_unknown_custom_field_xyz",
            profile={},
            screening_answers=[],
        )
