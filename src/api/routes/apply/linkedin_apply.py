"""LinkedIn Easy Apply routes — POST /linkedin-easy-apply, GET /daily-linkedin-count, GET /queued-linkedin-jobs.

Implements the n8n → FastAPI contract (D-08) for LinkedIn Easy Apply submissions.

Security:
    T-03-08 — POST /linkedin-easy-apply is guarded by Depends(verify_api_key); GET endpoints are read-only/unauthenticated.
    T-03-09 — job.url comes from the DB Job row (already ingested), never from the n8n payload.
    T-03-10 — write_audit records APPLYING/SUBMITTED/SKIPPED events for every transition.
    T-03-11 — daily-linkedin-count is the durable DB-backed cap source for the n8n gate.
"""

import os
from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.app import get_session, verify_api_key
from src.api.schemas import LinkedInApplyIn
from src.audit_log import AuditEvent, write_audit
from src.browser.linkedin_applier import (
    ChallengeDetected,
    LinkedInApplier,
    NoEasyApplyButton,
    UnknownFormField,
)
from src.queue.models import Application, Job, JobStatus

log = structlog.get_logger()

router = APIRouter()


@router.get("/daily-linkedin-count")
async def daily_linkedin_count(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """Return count of today's SUBMITTED LinkedIn applications.

    Uses a JOIN-based query so only applications whose parent Job has
    apply_type='linkedin_easy_apply' are counted (T-03-11 — durable cap source).
    Resets at midnight UTC.

    Returns:
        dict: {"count": N}
    """
    today_midnight = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    async with session.begin():
        result = await session.execute(
            select(func.count())
            .select_from(Application)
            .join(Job, Application.job_id == Job.id)
            .where(
                Job.apply_type == "linkedin_easy_apply",
                Application.submitted_at >= today_midnight,
            )
        )
        count = result.scalar_one()

    log.info("daily_linkedin_count", count=count, since=today_midnight.isoformat())
    return {"count": count}


@router.get("/queued-linkedin-jobs")
async def queued_linkedin_jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """Return QUEUED jobs with apply_type='linkedin_easy_apply' for the n8n scheduler.

    Returns:
        dict: {"jobs": [{"id", "title", "company", "url"}, ...]}
    """
    async with session.begin():
        result = await session.execute(
            select(Job).where(
                Job.status == JobStatus.QUEUED,
                Job.apply_type == "linkedin_easy_apply",
            )
        )
        jobs = result.scalars().all()

    log.info("queued_linkedin_jobs", count=len(jobs))
    return {
        "jobs": [
            {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "url": job.url,
            }
            for job in jobs
        ]
    }


@router.post("/linkedin-easy-apply", dependencies=[Depends(verify_api_key)], response_model=None)
async def linkedin_easy_apply(
    payload: LinkedInApplyIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict | JSONResponse:
    """Execute a LinkedIn Easy Apply submission for a QUEUED job.

    Flow:
        1. Look up job by job_id — 404 if missing.
        2. Verify job is QUEUED — 409 if not.
        3. Transition QUEUED → APPLYING and write APPLYING audit event.
        4. Instantiate LinkedInApplier and call await applier.apply(job, resume_path).
        5. On success: transition → SUBMITTED, create Application row, write SUBMITTED audit.
        6. On ChallengeDetected: log + raise HTTP 503.
        7. On NoEasyApplyButton/UnknownFormField: transition → SKIPPED, write SKIPPED audit, return 200.

    Args:
        payload: LinkedInApplyIn with job_id.
        request: FastAPI Request — used to access app.state.resumes_dir and profile_config.
        session: AsyncSession — DB session.

    Returns:
        {"status": "submitted", "job_id": ...} on success.
        JSONResponse 200 {"status": "skipped", "reason": ...} for expected skips.

    Raises:
        HTTP 404: job_not_found
        HTTP 409: job_not_queued
        HTTP 503: challenge_detected
    """
    # --- 1. DB lookup + 404/409 guard ---
    async with session.begin():
        result = await session.execute(select(Job).where(Job.id == payload.job_id))
        job = result.scalar_one_or_none()

        if job is None:
            return JSONResponse(status_code=404, content={"detail": "job_not_found"})

        if job.status != JobStatus.QUEUED:
            return JSONResponse(status_code=409, content={"detail": "job_not_queued"})

        # --- 2. QUEUED → APPLYING transition ---
        job.status = JobStatus.APPLYING
        job.updated_at = datetime.utcnow()

        await write_audit(
            session,
            source="api",
            event=AuditEvent.APPLYING,
            job_id=job.id,
        )

        log.info("linkedin_apply_start", job_id=job.id, title=job.title, company=job.company)

    # --- 3. Resolve resume path (T-03-09: from DB, not from payload) ---
    resumes_dir = getattr(request.app.state, "resumes_dir", os.environ.get("RESUMES_DIR", "resumes"))
    resume_template = job.resume_template or ""
    if resume_template:
        resume_path = os.path.join(resumes_dir, resume_template)
    else:
        # Fallback: use first available resume in resumes_dir
        try:
            available = [
                f for f in os.listdir(resumes_dir)
                if f.endswith((".pdf", ".docx"))
            ]
            resume_path = os.path.join(resumes_dir, available[0]) if available else ""
        except (OSError, FileNotFoundError):
            resume_path = ""

    # --- 4. Attach profile config for screening answers (T-03-04: no PII in logs) ---
    profile_config = getattr(request.app.state, "profile_config", None)
    job._profile_config = profile_config  # type: ignore[attr-defined]

    # --- 5. Run the applier ---
    user_data_dir = os.environ.get("LINKEDIN_PROFILE_DIR", "/data/linkedin_profile")
    applier = LinkedInApplier(user_data_dir=user_data_dir)

    try:
        await applier.apply(job, resume_path)

    except ChallengeDetected as exc:
        log.error("linkedin_challenge", job_id=payload.job_id, challenge=str(exc))
        raise HTTPException(
            status_code=503,
            detail={"status": "challenge_detected", "detail": str(exc)},
        )

    except NoEasyApplyButton:
        reason = "no_easy_apply_button"
        async with session.begin():
            result2 = await session.execute(select(Job).where(Job.id == payload.job_id))
            job2 = result2.scalar_one_or_none()
            if job2 is not None:
                job2.status = JobStatus.SKIPPED
                job2.rejection_reason = reason
                job2.updated_at = datetime.utcnow()
                await write_audit(
                    session,
                    source="api",
                    event=AuditEvent.SKIPPED,
                    job_id=payload.job_id,
                    reason=reason,
                )
        log.info("linkedin_skipped", job_id=payload.job_id, reason=reason)
        return JSONResponse(
            status_code=200,
            content={"status": "skipped", "job_id": payload.job_id, "reason": reason},
        )

    except UnknownFormField as exc:
        reason = str(exc) or "unknown_form_field"
        async with session.begin():
            result3 = await session.execute(select(Job).where(Job.id == payload.job_id))
            job3 = result3.scalar_one_or_none()
            if job3 is not None:
                job3.status = JobStatus.SKIPPED
                job3.rejection_reason = reason
                job3.updated_at = datetime.utcnow()
                await write_audit(
                    session,
                    source="api",
                    event=AuditEvent.SKIPPED,
                    job_id=payload.job_id,
                    reason=reason,
                )
        log.info("linkedin_skipped", job_id=payload.job_id, reason=reason)
        return JSONResponse(
            status_code=200,
            content={"status": "skipped", "job_id": payload.job_id, "reason": reason},
        )

    # --- 6. Success: APPLYING → SUBMITTED + Application row ---
    async with session.begin():
        result4 = await session.execute(select(Job).where(Job.id == payload.job_id))
        job4 = result4.scalar_one_or_none()
        if job4 is not None:
            job4.status = JobStatus.SUBMITTED
            job4.updated_at = datetime.utcnow()

            application = Application(
                job_id=job4.id,
                resume_template=job4.resume_template or "",
                cover_letter=job4.cover_letter or "",
                screening_answers=job4.screening_answers,
                submitted_at=datetime.utcnow(),
            )
            session.add(application)

            await write_audit(
                session,
                source="api",
                event=AuditEvent.SUBMITTED,
                job_id=job4.id,
            )

    log.info("linkedin_submitted", job_id=payload.job_id)
    return {"status": "submitted", "job_id": payload.job_id}
