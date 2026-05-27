"""Gmail routes: POST /poll-gmail and POST /fetch-email-body.

/poll-gmail:
    Reads the current gmail_history_id from AgentConfig, calls the Gmail API
    for messages since that ID (filtered to jobalerts-noreply@linkedin.com),
    stores the new historyId in AgentConfig, and returns matching message IDs.

/fetch-email-body:
    Fetches and decodes the plain-text body of a Gmail message given its ID.

Both endpoints signal Gmail OAuth 401 errors as HTTP 503 with
{"status": "challenge_detected"} per OPS-01 pattern.
"""

import os
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.app import get_session, verify_api_key
from src.api.schemas import FetchEmailBodyIn, FetchEmailBodyOut, PollGmailOut
from src.ingestion.gmail_client import fetch_message_body, get_gmail_service, poll_gmail_since
from src.queue.models import AgentConfig

log = structlog.get_logger()

router = APIRouter()

# Sender filter per CONTEXT.md D-05
_LINKEDIN_SENDER = "jobalerts-noreply@linkedin.com"
# AgentConfig key for Gmail historyId checkpoint
_HISTORY_ID_KEY = "gmail_history_id"
# OPS-01: consistent detail message for auth challenge responses
_OAUTH_CHALLENGE_DETAIL = "Gmail OAuth token expired or revoked"


def _get_token_path() -> str:
    """Return the path to the Gmail OAuth token file from environment."""
    return os.environ.get("GOOGLE_TOKEN_PATH", ".google_token.json")


@router.post("/poll-gmail", dependencies=[Depends(verify_api_key)])
async def poll_gmail(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PollGmailOut:
    """Poll Gmail for new LinkedIn job alert message IDs since last historyId.

    Reads the current historyId from agent_config table, polls the Gmail API
    for messageAdded events since that ID, writes the new historyId back, and
    returns the list of matching message IDs.

    On first run (no historyId stored), establishes a baseline and returns
    an empty list. On Gmail OAuth 401, returns HTTP 503 challenge_detected.

    Returns:
        PollGmailOut with message_ids (list) and history_id (str).
    """
    token_path = _get_token_path()

    try:
        service = get_gmail_service(token_path)
    except HttpError as exc:
        if exc.resp.status == 401:
            log.warning("gmail_oauth_challenge", status=401, detail=str(exc))
            raise HTTPException(
                status_code=503,
                detail={"status": "challenge_detected", "detail": _OAUTH_CHALLENGE_DETAIL},
            ) from exc
        log.error("gmail_service_init_error", status=exc.resp.status, detail=str(exc))
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "detail": str(exc)},
        ) from exc
    except Exception as exc:
        log.warning("gmail_oauth_challenge", detail=str(exc))
        raise HTTPException(
            status_code=503,
            detail={"status": "challenge_detected", "detail": _OAUTH_CHALLENGE_DETAIL},
        ) from exc

    # Read current historyId from AgentConfig
    async with session.begin():
        result = await session.execute(
            select(AgentConfig).where(AgentConfig.key == _HISTORY_ID_KEY)
        )
        config_row = result.scalar_one_or_none()
        current_history_id: str | None = config_row.value if config_row else None

    log.info("gmail_poll_start", current_history_id=current_history_id)

    try:
        matching_ids, new_history_id = poll_gmail_since(
            service, current_history_id, _LINKEDIN_SENDER
        )
    except HttpError as exc:
        if exc.resp.status == 401:
            log.warning("gmail_oauth_challenge", status=401, detail=str(exc))
            raise HTTPException(
                status_code=503,
                detail={"status": "challenge_detected", "detail": _OAUTH_CHALLENGE_DETAIL},
            ) from exc
        log.error("gmail_poll_error", status=exc.resp.status, detail=str(exc))
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "detail": str(exc)},
        ) from exc

    # Persist the new historyId so the next poll only fetches deltas
    async with session.begin():
        await session.merge(AgentConfig(key=_HISTORY_ID_KEY, value=new_history_id))

    log.info(
        "gmail_poll_complete",
        message_count=len(matching_ids),
        new_history_id=new_history_id,
    )

    return PollGmailOut(message_ids=matching_ids, history_id=new_history_id)


@router.post("/fetch-email-body", dependencies=[Depends(verify_api_key)])
async def fetch_email_body(
    payload: FetchEmailBodyIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FetchEmailBodyOut:
    """Fetch the plain-text body of a Gmail message by ID.

    Args:
        payload: FetchEmailBodyIn with message_id field.

    Returns:
        FetchEmailBodyOut with body_text, subject, and sender.

    Raises:
        HTTP 404 if the message is not found.
        HTTP 503 challenge_detected if Gmail OAuth returns 401.
        HTTP 502 for other Gmail API errors.
    """
    token_path = _get_token_path()

    try:
        service = get_gmail_service(token_path)
    except HttpError as exc:
        if exc.resp.status == 401:
            log.warning("gmail_oauth_challenge", status=401, detail=str(exc))
            raise HTTPException(
                status_code=503,
                detail={"status": "challenge_detected", "detail": _OAUTH_CHALLENGE_DETAIL},
            ) from exc
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "detail": str(exc)},
        ) from exc
    except Exception as exc:
        log.warning("gmail_oauth_challenge", detail=str(exc))
        raise HTTPException(
            status_code=503,
            detail={"status": "challenge_detected", "detail": _OAUTH_CHALLENGE_DETAIL},
        ) from exc

    try:
        result = fetch_message_body(service, payload.message_id)
    except HttpError as exc:
        if exc.resp.status == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Message not found: {payload.message_id}",
            ) from exc
        if exc.resp.status == 401:
            log.warning("gmail_oauth_challenge", status=401, detail=str(exc))
            raise HTTPException(
                status_code=503,
                detail={"status": "challenge_detected", "detail": _OAUTH_CHALLENGE_DETAIL},
            ) from exc
        log.error(
            "gmail_fetch_error",
            message_id=payload.message_id,
            status=exc.resp.status,
            detail=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "detail": str(exc)},
        ) from exc

    return FetchEmailBodyOut(
        body_text=result["body_text"],
        subject=result.get("subject"),
        sender=result.get("sender"),
    )
