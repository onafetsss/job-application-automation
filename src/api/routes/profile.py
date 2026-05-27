"""Profile routes — GET /profile returns serialized profile config as JSON for n8n (D-19)."""

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.api.schemas import ProfileOut

log = structlog.get_logger()

router = APIRouter()


@router.get("", response_model=ProfileOut)
async def get_profile(request: Request) -> ProfileOut | JSONResponse:
    """Return the profile config as JSON for n8n cover letter prompt construction (D-19).

    Reads profile_config from app.state (loaded at startup from config/profile.yaml).
    Enables n8n to call GET /profile and inject real profile data into the Claude Sonnet
    cover letter prompt — profile.yaml is the single source of truth.

    Returns:
        ProfileOut: Serialized profile config with all fields.

    Raises:
        HTTP 503: If profile_config is not loaded on app.state (startup failure).
    """
    profile_config = getattr(request.app.state, "profile_config", None)
    if profile_config is None:
        log.error("profile_not_loaded")
        return JSONResponse(status_code=503, content={"detail": "profile_not_loaded"})

    log.info("profile_fetched")
    return ProfileOut(
        summary=profile_config.summary,
        target_roles=profile_config.target_roles,
        key_projects=[p.model_dump() for p in profile_config.key_projects],
        skills=profile_config.skills,
        location_preference=profile_config.location_preference,
        availability=profile_config.availability,
    )
