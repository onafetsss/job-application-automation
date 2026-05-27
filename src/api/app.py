"""FastAPI application — lifespan startup, session dependency, and router registration."""

import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.filter.config_loader import load_eligibility_config
from src.preparation.profile_loader import load_profile_config
from src.queue.db import get_session_factory, init_db

# T-01-02: load_dotenv() before any os.environ access; no shell expansion of paths
load_dotenv()

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    # Route structured logs to stderr; stdout is reserved for human-readable output only
    wrapper_class=structlog.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize DB, session factory, and config at startup."""
    db_path = os.environ.get("DB_PATH", "data/jobs.db")
    config_path = os.environ.get("ELIGIBILITY_CONFIG_PATH", "config/eligibility.yaml")
    profile_path = os.environ.get("PROFILE_CONFIG_PATH", "config/profile.yaml")
    resumes_dir = os.environ.get("RESUMES_DIR", "resumes")

    await init_db(db_path)
    session_factory = get_session_factory(db_path)

    # Load eligibility config at startup — same pattern as main.py lines 155-156
    eligibility_config = load_eligibility_config(config_path)
    app.state.eligibility_config = eligibility_config
    app.state.session_factory = session_factory
    app.state.profile_config_path = profile_path
    app.state.resumes_dir = resumes_dir

    # Load profile config at startup — store on app.state for route handlers
    profile_config = load_profile_config(profile_path)
    app.state.profile_config = profile_config

    log.info(
        "api_startup",
        db_path=db_path,
        config_path=config_path,
        profile_path=profile_path,
        resumes_dir=resumes_dir,
    )

    yield

    log.info("api_shutdown")


app = FastAPI(
    title="Job Application Agent API",
    description="FastAPI service bridging n8n to Phase 1 Python logic.",
    version="2.0.0",
    lifespan=lifespan,
)


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an AsyncSession from app.state.session_factory.

    FastAPI injects Request automatically when it appears as a parameter in a dependency.
    All route handlers that need a DB session use: session: AsyncSession = Depends(get_session)
    """
    async with request.app.state.session_factory() as session:
        yield session


# T-02-01: API key header auth — checked by this dependency on all state-changing routes.
# Key is set via API_KEY env var. If unset, auth is skipped (development mode).
async def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Verify X-API-Key header against API_KEY env var (T-02-01)."""
    expected_key = os.environ.get("API_KEY")
    if not expected_key:
        # Dev mode: no key configured — skip auth
        return
    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# Re-export get_session and verify_api_key for route imports
__all__ = ["app", "get_session", "verify_api_key"]

# Register all six routers
from src.api.routes import (  # noqa: E402
    application,
    gmail,
    ingest,
    profile,
    resume,
    scrape,
)

app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
app.include_router(gmail.router, prefix="/gmail", tags=["gmail"])
app.include_router(scrape.router, prefix="/scrape", tags=["scrape"])
app.include_router(resume.router, prefix="/resume", tags=["resume"])
app.include_router(application.router, prefix="/application", tags=["application"])
app.include_router(profile.router, prefix="/profile", tags=["profile"])
