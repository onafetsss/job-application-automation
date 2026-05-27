"""Integration tests for the dry-run pipeline: write_audit, dedup, and eligibility flow."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.audit_log import AuditEvent, AuditLogEntry, write_audit
from src.filter.config_loader import EligibilityConfig, LocationConfig, RolesConfig
from src.filter.dedup import hash_url, is_duplicate
from src.filter.eligibility import check_eligibility
from src.queue.db import get_session_factory, init_db
from src.queue.models import Job, JobStatus

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def make_config(
    roles_include: list[str] | None = None,
    allow_remote: bool = True,
) -> EligibilityConfig:
    """Build a minimal EligibilityConfig for testing."""
    if roles_include is None:
        roles_include = ["Product Manager"]
    return EligibilityConfig(
        roles=RolesConfig(include=roles_include),
        location=LocationConfig(allow_remote=allow_remote),
    )


def make_lead(
    title: str = "Senior Product Manager",
    company: str = "Acme Corp",
    location: str = "Remote",
    source: str = "sample",
    clean_jd: str = "",
    url: str = "https://example.com/job1",
) -> dict:
    return {
        "url": url,
        "title": title,
        "company": company,
        "location": location,
        "source": source,
        "clean_jd": clean_jd,
    }


@pytest_asyncio.fixture
async def db_session_factory(tmp_path):
    """Create an isolated in-memory DB for each test."""
    db_path = str(tmp_path / "test_pipeline.db")
    await init_db(db_path)
    yield get_session_factory(db_path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_queues_eligible_lead(db_session_factory):
    """QUEUED path: audit row created; no jobs row created in dry-run mode."""
    config = make_config(roles_include=["Product Manager"], allow_remote=True)
    lead = make_lead(title="Senior Product Manager", company="Acme Corp", location="Remote")
    url_hash = hash_url(lead["url"])

    session_factory = db_session_factory
    async with session_factory() as session:
        async with session.begin():
            is_dup = await is_duplicate(
                session,
                company=lead["company"],
                title=lead["title"],
                location=lead["location"],
                url_hash=url_hash,
            )
            assert not is_dup

            result = check_eligibility(
                title=lead["title"],
                location=lead["location"],
                jd_text=lead["clean_jd"],
                config=config,
            )
            assert result.passed

            event = AuditEvent.DRY_RUN_WOULD_QUEUE
            await write_audit(
                session,
                source=lead["source"],
                event=event,
                reason=result.reason,
            )

    # Verify: one audit_log row with DRY_RUN_WOULD_QUEUE; no jobs row
    async with session_factory() as session:
        audit_rows = (await session.execute(select(AuditLogEntry))).scalars().all()
        assert len(audit_rows) == 1
        assert audit_rows[0].event == "DRY_RUN_WOULD_QUEUE"
        assert audit_rows[0].source == "sample"

        job_rows = (await session.execute(select(Job))).scalars().all()
        assert len(job_rows) == 0


@pytest.mark.asyncio
async def test_dry_run_rejects_ineligible_lead(db_session_factory):
    """REJECTED path: audit row has correct event and reason."""
    config = make_config(roles_include=["Product Manager"])
    lead = make_lead(title="Junior Developer", company="Acme Corp", location="Remote")

    session_factory = db_session_factory
    async with session_factory() as session:
        async with session.begin():
            result = check_eligibility(
                title=lead["title"],
                location=lead["location"],
                jd_text=lead["clean_jd"],
                config=config,
            )
            assert not result.passed
            assert result.reason == "title_mismatch"

            await write_audit(
                session,
                source=lead["source"],
                event=AuditEvent.DRY_RUN_WOULD_REJECT,
                reason=result.reason,
            )

    async with session_factory() as session:
        audit_rows = (await session.execute(select(AuditLogEntry))).scalars().all()
        assert len(audit_rows) == 1
        assert audit_rows[0].event == "DRY_RUN_WOULD_REJECT"
        assert audit_rows[0].reason == "title_mismatch"


@pytest.mark.asyncio
async def test_dedup_skip_logged(db_session_factory):
    """Duplicate path: DEDUP_SKIP audit row; jobs table count unchanged."""
    lead = make_lead(url="https://example.com/job99")
    url_hash = hash_url(lead["url"])

    session_factory = db_session_factory

    # Manually insert a Job row with the same url_hash
    async with session_factory() as session:
        async with session.begin():
            existing_job = Job(
                id=str(uuid.uuid4()),
                url=lead["url"],
                url_hash=url_hash,
                title=lead["title"],
                title_normalized=lead["title"].lower().strip(),
                company=lead["company"],
                company_normalized=lead["company"].lower().strip(),
                location=lead["location"],
                location_normalized=(lead["location"] or "").lower().strip(),
                source=lead["source"],
                status=JobStatus.QUEUED,
            )
            session.add(existing_job)

    # Now run pipeline — should detect duplicate
    async with session_factory() as session:
        async with session.begin():
            is_dup = await is_duplicate(
                session,
                company=lead["company"],
                title=lead["title"],
                location=lead["location"],
                url_hash=url_hash,
            )
            assert is_dup  # must be detected as duplicate

            # Write DEDUP_SKIP audit entry (no job inserted)
            await write_audit(
                session,
                source=lead["source"],
                event=AuditEvent.DEDUP_SKIP,
                job_id=None,
            )

    async with session_factory() as session:
        audit_rows = (await session.execute(select(AuditLogEntry))).scalars().all()
        assert len(audit_rows) == 1
        assert audit_rows[0].event == "DEDUP_SKIP"

        # Jobs table still has only one row — no duplicate inserted
        job_rows = (await session.execute(select(Job))).scalars().all()
        assert len(job_rows) == 1


@pytest.mark.asyncio
async def test_audit_log_has_required_fields(db_session_factory):
    """Every audit_log row must have source, event, timestamp populated."""
    config = make_config(roles_include=["Product Manager"])
    leads = [
        make_lead(title="Senior Product Manager", url="https://example.com/a"),
        make_lead(title="Junior Developer", url="https://example.com/b"),
    ]

    session_factory = db_session_factory
    async with session_factory() as session:
        async with session.begin():
            for lead in leads:
                result = check_eligibility(
                    title=lead["title"],
                    location=lead["location"],
                    jd_text=lead["clean_jd"],
                    config=config,
                )
                event = (
                    AuditEvent.DRY_RUN_WOULD_QUEUE
                    if result.passed
                    else AuditEvent.DRY_RUN_WOULD_REJECT
                )
                await write_audit(
                    session,
                    source=lead["source"],
                    event=event,
                    reason=result.reason,
                )

    async with session_factory() as session:
        rows = (await session.execute(select(AuditLogEntry))).scalars().all()
        assert len(rows) == 2

        for row in rows:
            # Required fields must always be populated
            assert row.source is not None
            assert row.event is not None
            assert row.timestamp is not None

            # Reason: must be non-null for REJECT events; may be null for QUEUE events
            if row.event == AuditEvent.DRY_RUN_WOULD_REJECT.value:
                assert row.reason is not None
            elif row.event in (
                AuditEvent.QUEUED.value,
                AuditEvent.DRY_RUN_WOULD_QUEUE.value,
            ):
                assert row.reason is None  # no reason for passing leads
