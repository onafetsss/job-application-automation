"""Pure eligibility filter function — no I/O, no database access."""
from dataclasses import dataclass

from src.filter.config_loader import EligibilityConfig


@dataclass
class FilterResult:
    passed: bool
    reason: str | None = None  # populated only when passed=False; matches CONTEXT.md D-03 format


def _normalize(text: str) -> str:
    """Lowercase and strip for consistent matching."""
    return text.lower().strip()


def check_eligibility(
    title: str,
    location: str | None,
    jd_text: str | None,
    config: EligibilityConfig,
) -> FilterResult:
    """Apply eligibility rules in order. First failing rule short-circuits.

    Rules applied in priority order:
      1. Title include check — must match at least one allowed pattern
      2. Title exclude check — reject if any excluded keyword is present
      3. JD keyword blocklist — reject if any blocked phrase in job description
      4. Location blocked phrases in JD — reject if location-restricting language found
      5. Location allowed list — reject if not remote-eligible and location not in allowed list

    Returns:
        FilterResult(passed=True) if all rules pass.
        FilterResult(passed=False, reason=<underscore_code>) for first failing rule.
        Reason strings: "title_mismatch" | "location_mismatch" | "keyword_blocklist"
    """
    title_lower = _normalize(title)
    jd_lower = _normalize(jd_text or "")

    # 1. Title include check — must match at least one allowed pattern
    if not any(_normalize(kw) in title_lower for kw in config.roles.include):
        return FilterResult(passed=False, reason="title_mismatch")

    # 2. Title exclude check — reject if any excluded keyword is present
    for kw in config.roles.exclude:
        if _normalize(kw) in title_lower:
            return FilterResult(passed=False, reason="title_mismatch")

    # 3. JD keyword blocklist — reject if any blocked phrase in job description
    for phrase in config.keywords.blocklist:
        if _normalize(phrase) in jd_lower:
            return FilterResult(passed=False, reason="keyword_blocklist")

    # 4. Location check (only if location is provided)
    if location is not None:
        location_lower = _normalize(location)
        # 4a. Blocked phrases in JD (e.g. "US work authorization required")
        for phrase in config.location.blocked_phrases:
            if _normalize(phrase) in jd_lower:
                return FilterResult(passed=False, reason="location_mismatch")
        # 4b. Must match at least one allowed location (or allow_remote covers it)
        if not config.location.allow_remote or "remote" not in location_lower:
            if not any(
                _normalize(loc) in location_lower
                for loc in config.location.allowed_locations
            ):
                return FilterResult(passed=False, reason="location_mismatch")

    return FilterResult(passed=True)
