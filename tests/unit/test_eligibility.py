"""Unit tests for src/filter/eligibility.py."""
import pytest

from src.filter.config_loader import (
    EligibilityConfig,
    KeywordsConfig,
    LocationConfig,
    RolesConfig,
    SalaryConfig,
)
from src.filter.eligibility import FilterResult, check_eligibility


def _make_config(
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    allow_remote: bool = True,
    allowed_locations: list[str] | None = None,
    blocked_phrases: list[str] | None = None,
    blocklist: list[str] | None = None,
) -> EligibilityConfig:
    """Convenience factory for building EligibilityConfig in tests."""
    return EligibilityConfig(
        roles=RolesConfig(
            include=include or ["Product Manager"],
            exclude=exclude or [],
        ),
        location=LocationConfig(
            allow_remote=allow_remote,
            allowed_locations=allowed_locations or [],
            blocked_phrases=blocked_phrases or [],
        ),
        salary=SalaryConfig(),
        keywords=KeywordsConfig(blocklist=blocklist or []),
    )


def test_pass_matching_title_remote() -> None:
    """A title that matches and a Remote location with allow_remote=True must pass."""
    config = _make_config(include=["Product Manager"], allow_remote=True)
    result = check_eligibility(
        title="Senior Product Manager",
        location="Remote",
        jd_text="",
        config=config,
    )
    assert result == FilterResult(passed=True, reason=None)


def test_reject_title_mismatch() -> None:
    """A title that does not match any include keyword must be rejected as title_mismatch."""
    config = _make_config(include=["Product Manager"])
    result = check_eligibility(
        title="Software Engineer",
        location="Remote",
        jd_text="",
        config=config,
    )
    assert result == FilterResult(passed=False, reason="title_mismatch")


def test_reject_excluded_keyword_in_title() -> None:
    """A title matching include but also containing an excluded keyword is title_mismatch."""
    config = _make_config(include=["Product Manager"], exclude=["Internship"])
    result = check_eligibility(
        title="Product Manager Internship",
        location="Remote",
        jd_text="",
        config=config,
    )
    assert result == FilterResult(passed=False, reason="title_mismatch")


def test_reject_jd_keyword_blocklist() -> None:
    """A JD containing a blocked phrase must be rejected as keyword_blocklist."""
    config = _make_config(
        include=["Product Manager"],
        blocklist=["Clearance required"],
    )
    result = check_eligibility(
        title="Senior Product Manager",
        location="Remote",
        jd_text="Clearance required for this role",
        config=config,
    )
    assert result == FilterResult(passed=False, reason="keyword_blocklist")


def test_reject_location_mismatch() -> None:
    """A non-remote location not in allowed_locations with allow_remote=False is rejected."""
    config = _make_config(
        allow_remote=False,
        allowed_locations=["Philippines"],
    )
    result = check_eligibility(
        title="Senior Product Manager",
        location="New York",
        jd_text="",
        config=config,
    )
    assert result == FilterResult(passed=False, reason="location_mismatch")


def test_reject_blocked_phrase_in_jd() -> None:
    """A JD containing a location blocked_phrase must be rejected as location_mismatch."""
    config = _make_config(
        include=["Product Manager"],
        allow_remote=True,
        blocked_phrases=["authorized to work in the US"],
    )
    result = check_eligibility(
        title="Senior Product Manager",
        location="Remote",
        jd_text="Must be authorized to work in the US",
        config=config,
    )
    assert result == FilterResult(passed=False, reason="location_mismatch")


def test_first_failing_rule_short_circuits() -> None:
    """When title_mismatch fires first, reason must be 'title_mismatch', not 'keyword_blocklist'."""
    config = _make_config(
        include=["Product Manager"],
        exclude=["Internship"],
        blocklist=["Clearance required"],
    )
    result = check_eligibility(
        title="Junior Developer Internship",
        location="Remote",
        jd_text="Clearance required",
        config=config,
    )
    # title fails first (no include match), so reason is title_mismatch
    assert result.passed is False
    assert result.reason == "title_mismatch"


def test_reject_blocked_phrase_in_jd_when_location_is_none() -> None:
    """CR-02 regression: blocked_phrases scan must run even when location is None.

    A lead scraped without a location field but with US work-auth language in the JD
    must be rejected as location_mismatch — not silently passed through.
    """
    config = _make_config(
        include=["Product Manager"],
        blocked_phrases=["authorized to work in the US"],
    )
    result = check_eligibility(
        title="Senior Product Manager",
        location=None,
        jd_text="Candidates must be authorized to work in the US",
        config=config,
    )
    assert result == FilterResult(passed=False, reason="location_mismatch")


def test_pass_when_location_is_none_and_no_blocked_phrase() -> None:
    """Defensive: fix must not over-correct and reject ALL location=None leads.

    A lead with location=None and a clean JD (no blocked phrase) must still pass.
    """
    config = _make_config(
        include=["Product Manager"],
        allow_remote=True,
        blocked_phrases=["authorized to work in the US"],
    )
    result = check_eligibility(
        title="Senior Product Manager",
        location=None,
        jd_text="Great PM role — fully remote, competitive pay",
        config=config,
    )
    assert result.passed is True
