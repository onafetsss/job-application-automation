"""Application routes — screening answer generation and application lifecycle endpoints."""

import json
from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.app import get_session
from src.api.schemas import (
    GenerateScreeningAnswersIn,
    GenerateScreeningAnswersOut,
    MarkSubmittedIn,
    WriteApplicationIn,
)
from src.audit_log import AuditEvent, write_audit
from src.preparation.screening import generate_screening_answers
from src.queue.models import Application, Job, JobStatus

log = structlog.get_logger()

router = APIRouter()


@router.post("/generate-screening-answers", response_model=GenerateScreeningAnswersOut)
async def generate_screening_answers_route(
    payload: GenerateScreeningAnswersIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GenerateScreeningAnswersOut | JSONResponse:
    """Generate answers to screening questions using Claude Haiku (AI-03 per D-20).

    Delegates to the shared ``generate_screening_answers`` function in
    ``src.preparation.screening`` so the browser module can call the same logic
    directly without a self-referential HTTP round-trip.

    Args:
        payload: GenerateScreeningAnswersIn with job_id, screening_questions, job_description,
            job_title.
        request: FastAPI Request — used to access app.state.profile_config.
        session: AsyncSession — DB session for reading/updating the Job record.

    Returns:
        GenerateScreeningAnswersOut with job_id and answers list.

    Raises:
        HTTP 404: If the job_id is not found.
        HTTP 503: If the Anthropic API call fails.
    """
    # Validate job exists
    async with session.begin():
        result = await session.execute(select(Job).where(Job.id == payload.job_id))
        job = result.scalar_one_or_none()
        if job is None:
            return JSONResponse(status_code=404, content={"detail": "job_not_found"})

        profile_config = getattr(request.app.state, "profile_config", None)

        try:
            answers_list = generate_screening_answers(
                profile_config=profile_config,
                job_title=payload.job_title,
                job_description=payload.job_description,
                questions=payload.screening_questions,
            )
        except RuntimeError as exc:
            if str(exc) == "anthropic_api_unavailable":
                log.error("anthropic_api_failure", job_id=payload.job_id)
                return JSONResponse(
                    status_code=503, content={"detail": "anthropic_api_unavailable"}
                )
            raise

        # Store answers on the Job record
        job.screening_answers = json.dumps(answers_list)
        job.updated_at = datetime.utcnow()

        log.info(
            "screening_answers_generated",
            job_id=payload.job_id,
            question_count=len(payload.screening_questions),
            answer_count=len(answers_list),
        )

    return GenerateScreeningAnswersOut(job_id=payload.job_id, answers=answers_list)


@router.post("/write-application", response_model=None)
async def write_application(
    payload: WriteApplicationIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict | JSONResponse:
    """Transition a QUEUED job to APPLYING status and store resume_name + cover_letter.

    Args:
        payload: WriteApplicationIn with job_id, resume_name, cover_letter.
        session: AsyncSession — DB session.

    Returns:
        dict: {"status": "ok", "job_id": <job_id>}

    Raises:
        HTTP 404: If the job_id is not found.
        HTTP 409: If the job is not in QUEUED status.
    """
    async with session.begin():
        result = await session.execute(select(Job).where(Job.id == payload.job_id))
        job = result.scalar_one_or_none()

        if job is None:
            return JSONResponse(status_code=404, content={"detail": "job_not_found"})

        if job.status != JobStatus.QUEUED:
            return JSONResponse(status_code=409, content={"detail": "job_not_queued"})

        job.resume_template = payload.resume_name
        job.cover_letter = payload.cover_letter
        job.status = JobStatus.APPLYING
        job.updated_at = datetime.utcnow()

        await write_audit(
            session,
            source="api",
            event=AuditEvent.APPLYING,
            job_id=job.id,
        )

        log.info("write_application", job_id=job.id, resume_name=payload.resume_name)

    return {"status": "ok", "job_id": payload.job_id}


@router.post("/mark-submitted", response_model=None)
async def mark_submitted(
    payload: MarkSubmittedIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict | JSONResponse:
    """Transition an APPLYING job to SUBMITTED status and create an Application row.

    Args:
        payload: MarkSubmittedIn with job_id.
        session: AsyncSession — DB session.

    Returns:
        dict: {"status": "ok", "job_id": <job_id>}

    Raises:
        HTTP 404: If the job_id is not found.
        HTTP 409: If the job is not in APPLYING status.
    """
    async with session.begin():
        result = await session.execute(select(Job).where(Job.id == payload.job_id))
        job = result.scalar_one_or_none()

        if job is None:
            return JSONResponse(status_code=404, content={"detail": "job_not_found"})

        if job.status != JobStatus.APPLYING:
            return JSONResponse(status_code=409, content={"detail": "job_not_applying"})

        job.status = JobStatus.SUBMITTED
        job.updated_at = datetime.utcnow()

        application = Application(
            job_id=job.id,
            resume_template=job.resume_template,
            cover_letter=job.cover_letter,
            screening_answers=job.screening_answers,
            submitted_at=datetime.utcnow(),
        )
        session.add(application)

        await write_audit(
            session,
            source="api",
            event=AuditEvent.SUBMITTED,
            job_id=job.id,
        )

        log.info("mark_submitted", job_id=job.id)

    return {"status": "ok", "job_id": payload.job_id}


@router.get("/queued-email-jobs")
async def queued_email_jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """Return jobs with status=QUEUED and apply_type='email' for the n8n apply pipeline."""
    async with session.begin():
        result = await session.execute(
            select(Job).where(Job.status == JobStatus.QUEUED, Job.apply_type == "email")
        )
        jobs = result.scalars().all()
    return {
        "jobs": [
            {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "url": job.url,
                "clean_jd": job.clean_jd,
                "screening_questions": job.screening_questions,
                "apply_type": job.apply_type,
            }
            for job in jobs
        ]
    }
