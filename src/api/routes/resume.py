"""Resume routes — POST /select-resume uses Claude Haiku for LLM-based resume matching (D-17, D-18)."""

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import anthropic

from src.api.schemas import SelectResumeIn, SelectResumeOut
from src.preparation.resume_reader import list_resumes

log = structlog.get_logger()

router = APIRouter()


@router.post("/select-resume", response_model=SelectResumeOut)
async def select_resume(
    payload: SelectResumeIn, request: Request
) -> SelectResumeOut | JSONResponse:
    """Select the best-fit resume for a job using Claude Haiku.

    Reads all resumes from app.state.resumes_dir, builds a selection prompt with
    job context, calls Claude Haiku to pick the best match, and returns the chosen
    resume name + full text.

    Args:
        payload: SelectResumeIn with job_id, job_description, job_title, company.
        request: FastAPI Request — used to access app.state.resumes_dir.

    Returns:
        SelectResumeOut: Chosen resume name and full text.

    Raises:
        HTTP 404: If no resumes found in the resumes directory.
        HTTP 503: If the Anthropic API call fails.
    """
    resumes_dir = getattr(request.app.state, "resumes_dir", "resumes")
    resumes = list_resumes(resumes_dir)

    if not resumes:
        log.warning("no_resumes_found", resumes_dir=resumes_dir)
        return JSONResponse(status_code=404, content={"detail": "no_resumes_found"})

    # Build selection prompt with job context and resume summaries
    resume_summaries = []
    for r in resumes:
        # Use first 500 chars as a condensed preview
        preview = r["text"][:500].replace("\n", " ").strip()
        resume_summaries.append(f'- Filename: {r["name"]}\n  Preview: {preview}')

    resume_list_text = "\n".join(resume_summaries)

    prompt = (
        f"You are a resume selection assistant. Given a job posting and a list of candidate resumes, "
        f"select the single best-fit resume.\n\n"
        f"Job Title: {payload.job_title}\n"
        f"Company: {payload.company}\n"
        f"Job Description:\n{payload.job_description[:2000]}\n\n"
        f"Available Resumes:\n{resume_list_text}\n\n"
        f"Instructions: Respond with ONLY the exact filename of the best-fit resume on the first line, "
        f"followed by a brief one-sentence explanation on the second line. "
        f"Do not include any other text before the filename."
    )

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-haiku-3-5",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text.strip()
    except Exception as exc:
        log.error("anthropic_api_failure", error=str(exc))
        return JSONResponse(status_code=503, content={"detail": "anthropic_api_unavailable"})

    # Extract the chosen filename from the first line of the response
    chosen_name = response_text.splitlines()[0].strip()

    # Find the matching resume in the list (case-insensitive match as fallback)
    matched_resume = None
    for r in resumes:
        if r["name"] == chosen_name:
            matched_resume = r
            break

    # Fallback: case-insensitive match
    if matched_resume is None:
        for r in resumes:
            if r["name"].lower() == chosen_name.lower():
                matched_resume = r
                break

    # Final fallback: pick the first resume if LLM response didn't match
    if matched_resume is None:
        log.warning(
            "resume_name_mismatch",
            chosen=chosen_name,
            available=[r["name"] for r in resumes],
        )
        matched_resume = resumes[0]

    log.info(
        "resume_selected",
        job_id=payload.job_id,
        resume_name=matched_resume["name"],
    )

    return SelectResumeOut(
        resume_name=matched_resume["name"],
        resume_text=matched_resume["text"],
    )
