"""Autonomous Job Application Agent — CLI entry point.

Usage:
    python main.py [--dry-run] [--source SOURCE] [--limit N]

Phase 1: processes hardcoded sample leads through dedup + eligibility + audit.
Phase 2+: replace sample_leads with real ingestion sources.
"""

import argparse
import asyncio
import os
import uuid
from typing import Any

import structlog
from dotenv import load_dotenv

from src.audit_log import AuditEvent, write_audit
from src.filter.config_loader import load_eligibility_config
from src.filter.dedup import hash_url, is_duplicate
from src.filter.eligibility import check_eligibility
from src.queue.db import get_session_factory, init_db
from src.queue.models import Job, JobStatus

# T-01-02: load_dotenv() before any os.environ access; no shell expansion of paths
load_dotenv()

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    # Route structured logs to stderr; stdout is reserved for dry-run terminal output only (D-02)
    wrapper_class=structlog.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(file=__import__("sys").stderr),
)

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Phase 1 sample leads — diverse set covering QUEUED, REJECTED, and DEDUP paths
# ---------------------------------------------------------------------------
# Shape: url, title, company, location, source, clean_jd
# Must include:
#   - At least one that passes the eligibility filter (QUEUED path)
#   - At least one that fails on title (REJECTED: title mismatch)
#   - At least one that fails on location/JD phrase (REJECTED: location mismatch)
#   - At least one duplicate URL (same as a passing lead — DEDUP_SKIP path)

SAMPLE_LEADS: list[dict[str, Any]] = [
    {
        "url": "https://example.com/job1",
        "title": "Senior Product Manager",
        "company": "Acme Corp",
        "location": "Remote",
        "source": "sample",
        "clean_jd": "Lead product strategy for our remote-first global team.",
    },
    {
        "url": "https://example.com/job2",
        "title": "Product Manager",
        "company": "Beta Inc",
        "location": "Manila, Philippines",
        "source": "sample",
        "clean_jd": "Own the roadmap for our core consumer product.",
    },
    {
        "url": "https://example.com/job3",
        "title": "Software Engineer",
        "company": "Gamma Ltd",
        "location": "Remote",
        "source": "sample",
        "clean_jd": "Build and scale our backend microservices.",
    },
    {
        "url": "https://example.com/job4",
        "title": "Senior Product Manager",
        "company": "Delta Co",
        "location": "San Francisco, CA",
        "source": "sample",
        "clean_jd": (
            "We are looking for a PM to lead our growth team. "
            "Candidates must be authorized to work in the US."
        ),
    },
    {
        "url": "https://example.com/job5",
        "title": "Junior Product Manager",
        "company": "Epsilon GmbH",
        "location": "Remote",
        "source": "sample",
        "clean_jd": "Great entry-level PM opportunity.",
    },
    # Duplicate of job1 — same URL, triggers DEDUP_SKIP
    {
        "url": "https://example.com/job1",
        "title": "Senior Product Manager",
        "company": "Acme Corp",
        "location": "Remote",
        "source": "sample",
        "clean_jd": "Lead product strategy for our remote-first global team.",
    },
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous Job Application Agent")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Filter jobs and log decisions without inserting into jobs table",
    )
    parser.add_argument(
        "--source",
        default="all",
        help="Ingestion source to run (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max leads to process (0 = unlimited)",
    )
    return parser


def print_dry_run_row(title: str, company: str, reason: str | None) -> None:
    """Print one scannable dry-run line per D-02 / D-03.

    Format: 'QUEUED                         Senior PM @ Acme Corp'
            'REJECTED: title mismatch       Software Engineer @ Gamma Ltd'

    T-03-01: shows category label only — no raw config values or JD content.
    """
    # reason contains underscore format (e.g. 'title_mismatch'); display with spaces
    label = f"REJECTED: {reason.replace('_', ' ')}" if reason else "QUEUED"
    print(f"{label:<30} {title} @ {company}")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> None:
    """Main pipeline: dedup → eligibility → audit → DB insert or dry-run output."""
    # T-01-03: resolve paths via os.environ; passed as str to pathlib in db.py
    db_path = os.environ.get("DB_PATH", "data/jobs.db")
    config_path = os.environ.get("ELIGIBILITY_CONFIG_PATH", "config/eligibility.yaml")

    await init_db(db_path)
    config = load_eligibility_config(config_path)
    session_factory = get_session_factory(db_path)

    log.info("startup", dry_run=args.dry_run, source=args.source, limit=args.limit)

    leads = SAMPLE_LEADS
    if args.limit > 0:
        leads = leads[: args.limit]

    # in-memory accumulator: catches within-batch duplicate URLs before the DB lookup.
    # In dry-run mode no Job rows are written, so is_duplicate() cannot detect same-batch
    # duplicates; this set covers that gap.  In live mode it serves as a fast-path first
    # check — the DB dedup remains the authoritative cross-run mechanism.
    seen_hashes: set[str] = set()

    # Process each lead atomically: dedup + eligibility + audit in one transaction
    for lead in leads:
        url_hash = hash_url(lead["url"])

        # --- In-memory within-batch dedup check (covers dry-run gap) ---
        if url_hash in seen_hashes:
            async with session_factory() as session:
                async with session.begin():
                    await write_audit(
                        session,
                        source=lead.get("source", "unknown"),
                        event=AuditEvent.DEDUP_SKIP,
                        job_id=None,
                        reason=None,
                    )
            if args.dry_run:
                print(f"{'DEDUP_SKIP':<30} {lead['title']} @ {lead['company']}")
            log.info(
                "dedup_skip",
                title=lead["title"],
                company=lead["company"],
                reason="within_batch",
            )
            continue
        seen_hashes.add(url_hash)

        async with session_factory() as session:
            async with session.begin():
                # --- Dedup check ---
                dup = await is_duplicate(
                    session,
                    company=lead["company"],
                    title=lead["title"],
                    location=lead.get("location"),
                    url_hash=url_hash,
                )
                if dup:
                    await write_audit(
                        session,
                        source=lead.get("source", "unknown"),
                        event=AuditEvent.DEDUP_SKIP,
                        job_id=None,
                        reason=None,
                    )
                    log.info(
                        "dedup_skip",
                        title=lead["title"],
                        company=lead["company"],
                    )
                    continue

                # --- Eligibility check ---
                result = check_eligibility(
                    title=lead["title"],
                    location=lead.get("location"),
                    jd_text=lead.get("clean_jd"),
                    config=config,
                )

                if args.dry_run:
                    # Dry-run: print terminal output + audit only (no jobs row)
                    print_dry_run_row(lead["title"], lead["company"], result.reason)
                    event = (
                        AuditEvent.DRY_RUN_WOULD_QUEUE
                        if result.passed
                        else AuditEvent.DRY_RUN_WOULD_REJECT
                    )
                    await write_audit(
                        session,
                        source=lead.get("source", "unknown"),
                        event=event,
                        reason=result.reason,
                    )
                else:
                    # Live mode: insert Job row + audit (T-03-03: ORM kwargs, no f-strings)
                    job_id = str(uuid.uuid4())
                    status = JobStatus.QUEUED if result.passed else JobStatus.REJECTED
                    job = Job(
                        id=job_id,
                        url=lead["url"],
                        url_hash=url_hash,
                        title=lead["title"],
                        title_normalized=lead["title"].lower().strip(),
                        company=lead["company"],
                        company_normalized=lead["company"].lower().strip(),
                        location=lead.get("location"),
                        location_normalized=(lead.get("location") or "").lower().strip(),
                        source=lead.get("source", "unknown"),
                        clean_jd=lead.get("clean_jd"),
                        status=status,
                        rejection_reason=result.reason,
                    )
                    session.add(job)

                    audit_event = AuditEvent.QUEUED if result.passed else AuditEvent.FILTERED_REJECT
                    await write_audit(
                        session,
                        source=lead.get("source", "unknown"),
                        event=audit_event,
                        job_id=job_id,
                        reason=result.reason,
                    )


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
