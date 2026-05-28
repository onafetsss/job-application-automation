"""Shared screening answer generation — callable without HTTP.

Extracts the Claude Haiku prompt-build + API call + JSON-parse logic from the
FastAPI route so it can be imported directly by the browser module (Plan 03-02)
without triggering a self-referential HTTP call inside the FastAPI process.

The FastAPI route POST /application/generate-screening-answers now delegates to
this function while keeping an identical external response contract.
"""

import json
import re

import anthropic
import structlog

log = structlog.get_logger()


def generate_screening_answers(
    profile_config,
    job_title: str,
    job_description: str,
    questions: list[str],
) -> list[dict]:
    """Generate answers to screening questions using Claude Haiku.

    Builds a prompt from the job context + applicant profile, calls
    ``claude-haiku-3-5``, and returns a list of ``{question, answer}`` dicts.

    The function is synchronous (uses the synchronous Anthropic client) so that
    it can be called from both the async FastAPI route (in a thread pool) and
    from the Camoufox browser module without event-loop concerns.

    Args:
        profile_config: A ``ProfileConfig`` instance (or any object with
            ``summary``, ``skills``, and ``key_projects`` attributes). May be
            ``None`` — in that case the prompt omits the profile context section.
        job_title: Title of the job being applied for.
        job_description: Full or truncated job description (truncated to 1500 chars
            internally to bound prompt size — T-03-06 mitigation).
        questions: List of screening question strings. If empty, ``[]`` is returned
            immediately without calling the Anthropic API.

    Returns:
        A list of dicts, each with keys ``question`` (str) and ``answer`` (str).
        Returns ``[]`` for an empty ``questions`` argument.

    Raises:
        RuntimeError: With message ``"anthropic_api_unavailable"`` if the
            Anthropic API call fails for any reason. The caller should map this
            to the appropriate HTTP error response.
    """
    if not questions:
        return []

    # Build profile context section
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

    questions_text = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))

    prompt = (
        f"You are helping a job applicant answer screening questions professionally.\n"
        f"{profile_context}\n"
        f"Job Title: {job_title}\n"
        f"Job Description:\n{job_description[:1500]}\n\n"
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
        log.error("anthropic_api_failure", error=str(exc))
        raise RuntimeError("anthropic_api_unavailable") from exc

    # Parse JSON response with markdown code-block fallback
    try:
        parsed = json.loads(response_text)
        answers_list = parsed.get("answers", [])
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(1))
            answers_list = parsed.get("answers", [])
        else:
            log.warning(
                "screening_answers_parse_error",
                response=response_text[:200],
            )
            answers_list = [{"question": q, "answer": response_text} for q in questions]

    return answers_list
