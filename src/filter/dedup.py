"""Cross-source deduplication using exact URL hash and fuzzy compound match."""
import hashlib
from urllib.parse import parse_qs, urlencode, urlparse

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.queue.models import Job

DEDUP_THRESHOLD = 85  # Per CONTEXT.md D-08: ~85% similarity floor


def hash_url(url: str) -> str:
    """SHA-256 of the canonical URL. Used as the fast exact-dedup key."""
    canonical = _canonicalize_url(url)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _canonicalize_url(url: str) -> str:
    """Strip tracking params and normalize scheme+host to lowercase."""
    parsed = urlparse(url.lower().strip())
    # Strip known tracking query params
    tracking_params = {"utm_source", "utm_medium", "utm_campaign", "trk", "refid"}
    qs = {k: v for k, v in parse_qs(parsed.query).items() if k not in tracking_params}
    return parsed._replace(query=urlencode(qs, doseq=True)).geturl()


def _similarity_score(a: str, b: str) -> float:
    """Token sort ratio — handles word order differences ('Acme Corp' vs 'Corp Acme')."""
    return fuzz.token_sort_ratio(a.lower(), b.lower())


async def is_duplicate(
    session: AsyncSession,
    company: str,
    title: str,
    location: str | None,
    url_hash: str,
) -> bool:
    """Return True if an identical or near-identical job already exists in the DB.

    Fast path: exact URL hash match (O(1) index lookup).
    Slow path: fuzzy compound match on company + title + location for cross-source dedup.

    Args:
        session: An active AsyncSession — caller owns the session lifecycle.
        company: Raw company name to check.
        title: Raw job title to check.
        location: Raw location string (may be None).
        url_hash: Pre-computed SHA-256 hash of the canonical URL.

    Returns:
        True if a matching job exists; False otherwise.
    """
    # Fast path: exact URL hash match
    result = await session.execute(select(Job).where(Job.url_hash == url_hash))
    if result.scalar_one_or_none() is not None:
        return True

    # Slow path: fuzzy compound match — handles cross-source postings with different URLs.
    # T-02-04: parameterized ORM query — no raw SQL string interpolation.
    existing = await session.execute(
        select(Job.company_normalized, Job.title_normalized, Job.location_normalized)
    )
    for row in existing:
        company_sim = _similarity_score(company, row.company_normalized or "")
        title_sim = _similarity_score(title, row.title_normalized or "")
        location_sim = _similarity_score(location or "", row.location_normalized or "")
        # Weighted average: company + title weighted higher than location (D-08)
        combined = company_sim * 0.4 + title_sim * 0.4 + location_sim * 0.2
        if combined >= DEDUP_THRESHOLD:
            return True

    return False
