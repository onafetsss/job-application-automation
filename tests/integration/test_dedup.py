"""Integration tests for src/filter/dedup.py — uses in-memory SQLite DB."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.filter.dedup import DEDUP_THRESHOLD, hash_url, is_duplicate
from src.queue.db import get_session_factory, init_db
from src.queue.models import Job, JobStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def session() -> AsyncSession:
    """Provide an in-memory AsyncSession with all tables created."""
    await init_db(":memory:")
    factory = get_session_factory(":memory:")
    async with factory() as s:
        yield s


async def _insert_job(
    session: AsyncSession,
    *,
    url: str = "https://example.com/job/1",
    url_hash: str | None = None,
    title: str = "Senior Product Manager",
    title_normalized: str | None = None,
    company: str = "Acme Corp",
    company_normalized: str | None = None,
    location: str | None = "Manila",
    location_normalized: str | None = None,
    source: str = "linkedin",
) -> Job:
    """Insert a minimal Job row and flush (no commit — session-scoped)."""
    job = Job(
        url=url,
        url_hash=url_hash or hash_url(url),
        title=title,
        title_normalized=(title_normalized or title).lower().strip(),
        company=company,
        company_normalized=(company_normalized or company).lower().strip(),
        location=location,
        location_normalized=(location_normalized or location or "").lower().strip(),
        source=source,
        status=JobStatus.DISCOVERED,
    )
    session.add(job)
    await session.flush()
    return job


# ---------------------------------------------------------------------------
# hash_url tests (pure function — no DB needed)
# ---------------------------------------------------------------------------

def test_hash_url_strips_tracking_params() -> None:
    """Two URLs that differ only in tracking params must produce the same hash."""
    url_a = "https://example.com/job?id=123&utm_source=linkedin"
    url_b = "https://example.com/job?id=123&utm_campaign=spring"
    assert hash_url(url_a) == hash_url(url_b)


def test_hash_url_same_url_same_hash() -> None:
    """Calling hash_url twice with the same URL string must return the same result."""
    url = "https://example.com/job?id=999"
    assert hash_url(url) == hash_url(url)


# ---------------------------------------------------------------------------
# is_duplicate integration tests
# ---------------------------------------------------------------------------

async def test_is_duplicate_exact_url_hash(session: AsyncSession) -> None:
    """A job with the same url_hash already in the DB must return True."""
    job = await _insert_job(session, url="https://example.com/job/1")
    result = await is_duplicate(
        session,
        company="Acme Corp",
        title="Senior Product Manager",
        location="Manila",
        url_hash=job.url_hash,
    )
    assert result is True


async def test_is_duplicate_new_url(session: AsyncSession) -> None:
    """An empty DB must return False for any url_hash."""
    result = await is_duplicate(
        session,
        company="Acme Corp",
        title="Senior Product Manager",
        location="Manila",
        url_hash="newhash_abc123",
    )
    assert result is False


async def test_is_duplicate_fuzzy_cross_source(session: AsyncSession) -> None:
    """A near-identical job from a different source (different URL) must still be a duplicate."""
    await _insert_job(
        session,
        url="https://linkedin.com/jobs/1",
        company="Acme Corp",
        company_normalized="acme corp",
        title="Senior Product Manager",
        title_normalized="senior product manager",
        location="Manila",
        location_normalized="manila",
        source="linkedin",
    )
    # Different URL hash — simulates cross-source posting
    result = await is_duplicate(
        session,
        company="Acme Corp.",          # slight punctuation difference
        title="Senior Product Manager",
        location="Manila, Philippines", # slight location expansion
        url_hash="different_hash_xyz",
    )
    assert result is True


async def test_is_not_duplicate_different_company(session: AsyncSession) -> None:
    """A different company posting the same title must NOT be considered a duplicate."""
    await _insert_job(
        session,
        url="https://linkedin.com/jobs/2",
        company="Acme Corp",
        company_normalized="acme corp",
        title="Senior Product Manager",
        title_normalized="senior product manager",
        location="Manila",
        location_normalized="manila",
        source="linkedin",
    )
    result = await is_duplicate(
        session,
        company="Globex Corporation",   # completely different company
        title="Senior Product Manager",
        location="Manila",
        url_hash="different_hash_xyz2",
    )
    assert result is False
