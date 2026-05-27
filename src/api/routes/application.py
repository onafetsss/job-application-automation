"""Application routes — screening answer generation and application lifecycle endpoints."""

import json
from datetime import datetime
from typing import Annotated

import anthropic
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
from src.queue.models import Application, Job, JobStatus

log = structlog.get_logger()

router = APIRouter()


@router.post("/generate-screening-answers", response_model=GenerateScreeningAnswersOut)
async def generate_screening_answers(
    payload: GenerateScreeningAnswersIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GenerateScreeningAnswersOut | JSONResponse:
    """Generate answers to screening questions using Claude Haiku (AI-03 per D-20).

    Builds a prompt from the job context + profile + screening questions, calls Haiku,
    parses the JSON response, and stores the answers on the Job record.

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

        # If no screening questions, return empty answers without calling Anthropic
        if not payload.screening_questions:
            log.info("screening_answers_empty", job_id=payload.job_id)
            return GenerateScreeningAnswersOut(job_id=payload.job_id, answers=[])

        # Build prompt using profile + job context
        profile_config = getattr(request.app.state, "profile_config", None)
        profile_context = ""
        if profile_config is not None:
            skills_list = ", ".join(profile_config.skills[:6])
            projects_text = "\n".join(
                f"  - {p.name}: {p.impact}" for p in profile_config.key_projects
            )
            profile_context = (
                f"\nApplicant Profile:\n"
                f"Summary: {profile_config.summary}\n"
                f"Skills: {skills_list}\n"
                f"Key Projects:\n{projects_text}\n"
            )

        questions_text = "\n".join(
            f"{i + 1}. {q}" for i, q in enumerate(payload.screening_questions)
        )

        prompt = (
            f"You are helping a job applicant answer screening questions professionally.\n"
            f"{profile_context}\n"
            f"Job Title: {payload.job_title}\n"
            f"Job Description:\n{payload.job_description[:1500]}\n\n"
            f"Screening Questions:\n{questions_text}\n\n"
            f"Instructions: Answer each question concisely and professionally from the applicant's "
            f"perspective, using their profile data above. Return a JSON object with an 'answers' "
            f"array where each element has 'question' (the original question text) and 'answer' "
            f"(the generated response). Return ONLY the JSON object, no other text."
        )

        try:
            client = anthropic.Anthropic()
            message = client.messages.create(
                model="claude-haiku-3-5",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = message.content[0].text.strip()
        except Exception as exc:
            log.error("anthropic_api_failure", error=str(exc), job_id=payload.job_id)
            return JSONResponse(status_code=503, content={"detail": "anthropic_api_unavailable"})

        # Parse JSON response
        try:
            parsed = json.loads(response_text)
            answers_list = parsed.get("answers", [])
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract from markdown code block
            import re

            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(1))
                answers_list = parsed.get("answers", [])
            else:
                log.warning(
                    "screening_answers_parse_error",
                    job_id=payload.job_id,
                    response=response_text[:200],
                )
                answers_list = [
                    {"question": q, "answer": response_text} for q in payload.screening_questions
                ]

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
