"""POST /ingest-lead — universal entry point for all lead sources (D-01, D-02).

n8n calls this endpoint for every lead regardless of source (Gmail, JobSpy, Kalibrr).
Pipeline: dedup → eligibility → audit → DB insert per main.py lines 174–274.
"""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.app import get_session, verify_api_key
from src.api.schemas import LeadIn, LeadOut
from src.audit_log import AuditEvent, write_audit
from src.filter.dedup import hash_url, is_duplicate
from src.filter.eligibility import check_eligibility
from src.queue.models import Job, JobStatus

log = structlog.get_logger()

router = APIRouter()


@router.post("/ingest-lead", dependencies=[Depends(verify_api_key)])
async def ingest_lead(
    payload: LeadIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LeadOut:
    """Ingest a job lead — dedup + eligibility + audit in one transaction.

    Returns:
        LeadOut with status "queued", "rejected", or "duplicate".
    """
    try:
        url_hash = hash_url(payload.url)
        eligibility_config = request.app.state.eligibility_config

        async with session.begin():
            # --- Dedup check (fast path: exact URL hash) ---
            dup = await is_duplicate(
                session,
                company=payload.company,
                title=payload.title,
                location=payload.location,
                url_hash=url_hash,
            )
            if dup:
                await write_audit(
                    session,
                    source=payload.source,
                    event=AuditEvent.DEDUP_SKIP,
                    job_id=None,
                    reason=None,
                )
                log.info(
                    "ingest_duplicate",
                    url=payload.url,
                    title=payload.title,
                    company=payload.company,
                )
                return LeadOut(status="duplicate", job_id=None)

            # --- Eligibility check ---
            result = check_eligibility(
                title=payload.title,
                location=payload.location,
                jd_text=payload.clean_jd,
                config=eligibility_config,
            )

            # --- Determine status ---
            status = JobStatus.QUEUED if result.passed else JobStatus.REJECTED

            # --- Create Job row (T-02-02: ORM parameterized queries — no raw SQL) ---
            job_id = str(uuid.uuid4())
            job = Job(
                id=job_id,
                url=payload.url,
                url_hash=url_hash,
                title=payload.title,
                title_normalized=payload.title.lower().strip(),
                company=payload.company,
                company_normalized=payload.company.lower().strip(),
                location=payload.location,
                location_normalized=(payload.location or "").lower().strip(),
                source=payload.source,
                clean_jd=payload.clean_jd,
                apply_type=payload.apply_type,
                status=status,
                rejection_reason=result.reason,
            )
            session.add(job)

            # --- Audit ---
            audit_event = AuditEvent.QUEUED if result.passed else AuditEvent.FILTERED_REJECT
            await write_audit(
                session,
                source=payload.source,
                event=audit_event,
                job_id=job_id,
                reason=result.reason,
            )

            log.info(
                "ingest_lead",
                status=status.value,
                job_id=job_id,
                title=payload.title,
                company=payload.company,
                source=payload.source,
            )
            # API contract: return lowercase status ("queued"|"rejected") per LeadOut schema
            return LeadOut(status=status.value.lower(), job_id=job_id)

    except HTTPException:
        raise
    except Exception as exc:
        log.error("ingest_lead_error", error=str(exc), url=payload.url)
        raise HTTPException(
            status_code=500,
            detail={"status": "error", "detail": str(exc)},
        ) from exc
