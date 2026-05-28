"""RED scaffold — unit test for linkedin URL apply_type detection (D-02).

The resolution logic (linkedin.com URL → apply_type='linkedin_easy_apply') is added
in Plan 03-04 to the gmail ingest path (n8n Code node or Python side).

This test uses a small pure helper function `resolve_apply_type(url: str) -> str`
that will be extracted into src.api.routes.ingest or a shared utility in Plan 03-04.
Tests are marked xfail until that helper is implemented.

Tests:
    test_linkedin_url_apply_type     — URL containing linkedin.com resolves to 'linkedin_easy_apply'
    test_non_linkedin_url_apply_type — URL without linkedin.com resolves to 'email' (default)
"""

import pytest


def _load_resolve_apply_type():
    """Try to import the apply_type resolver from the expected module location.

    Candidates are tried in order; the first successful import wins.
    Returns the function or None if not yet implemented.
    Called lazily inside tests to avoid module-level circular-import errors.
    """
    import importlib  # noqa: PLC0415

    candidates = [
        ("src.ingestion.gmail_client", "resolve_apply_type"),
        ("src.filter.eligibility", "resolve_apply_type"),
    ]
    for module_path, attr in candidates:
        try:
            mod = importlib.import_module(module_path)
            fn = getattr(mod, attr, None)
            if fn is not None:
                return fn
        except ImportError:
            continue
    return None


@pytest.mark.xfail(
    reason="resolve_apply_type implemented in Plan 03-04",
    strict=False,
)
def test_linkedin_url_apply_type() -> None:
    """A URL containing linkedin.com must resolve to apply_type='linkedin_easy_apply' (D-02)."""
    resolve_apply_type = _load_resolve_apply_type()
    if resolve_apply_type is None:
        pytest.xfail("resolve_apply_type not yet available — implemented in Plan 03-04")

    url = "https://www.linkedin.com/jobs/view/senior-engineer-at-acme-123456789/"
    result = resolve_apply_type(url)
    assert result == "linkedin_easy_apply", (
        f"Expected 'linkedin_easy_apply' for LinkedIn URL, got '{result}'"
    )


@pytest.mark.xfail(
    reason="resolve_apply_type implemented in Plan 03-04",
    strict=False,
)
def test_non_linkedin_url_apply_type() -> None:
    """A URL not containing linkedin.com must resolve to apply_type='email' (the default)."""
    resolve_apply_type = _load_resolve_apply_type()
    if resolve_apply_type is None:
        pytest.xfail("resolve_apply_type not yet available — implemented in Plan 03-04")

    url = "https://careers.example.com/apply/senior-engineer"
    result = resolve_apply_type(url)
    assert result == "email", (
        f"Expected 'email' for non-LinkedIn URL, got '{result}'"
    )
