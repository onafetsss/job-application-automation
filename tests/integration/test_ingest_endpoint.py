"""Integration tests for POST /ingest/ingest-lead endpoint.

Tests the full dedup + eligibility + audit pipeline via HTTP.
Uses httpx.AsyncClient with ASGITransport + manual lifespan management.
"""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:  # type: ignore[type-arg]
    """Fixture: initialize the FastAPI app with a temp SQLite DB and yield an AsyncClient.

    We create a fresh app instance per test to avoid singleton state leaking between tests.
    Env vars are patched before app import so lifespan reads the correct DB path.
    """
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("ELIGIBILITY_CONFIG_PATH", "config/eligibility.yaml")
    monkeypatch.setenv("PROFILE_CONFIG_PATH", "config/profile.yaml")
    # No API_KEY set — auth skipped in dev mode
    monkeypatch.delenv("API_KEY", raising=False)

    # Reset engine singleton so each test gets a fresh DB connection
    import src.queue.db as db_module  # noqa: PLC0415

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None

    # Import app AFTER env patches so os.environ reads the right values during lifespan
    from src.api.app import app  # noqa: PLC0415

    # Use lifespan context to run startup/shutdown
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    # Cleanup engine after test
    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None


@pytest.mark.asyncio
async def test_ingest_lead_queued(client: AsyncClient) -> None:
    """A lead matching eligibility (Senior Product Manager, Remote) returns queued."""
    payload = {
        "url": "https://example.com/jobs/spm-001",
        "title": "Senior Product Manager",
        "company": "Acme Corp",
        "location": "Remote",
        "source": "test",
        "clean_jd": "Lead product strategy for our remote-first global team.",
    }
    response = await client.post("/ingest/ingest-lead", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert data["job_id"] is not None
    assert len(data["job_id"]) == 36  # UUID format


@pytest.mark.asyncio
async def test_ingest_lead_rejected(client: AsyncClient) -> None:
    """A lead with a non-matching title (Software Engineer) returns rejected."""
    payload = {
        "url": "https://example.com/jobs/swe-002",
        "title": "Software Engineer",
        "company": "Beta Inc",
        "location": "Remote",
        "source": "test",
        "clean_jd": "Build and scale our backend microservices.",
    }
    response = await client.post("/ingest/ingest-lead", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    # job_id is returned for rejected jobs (they are inserted into DB)
    assert data["job_id"] is not None


@pytest.mark.asyncio
async def test_ingest_lead_duplicate(client: AsyncClient) -> None:
    """Posting the same lead twice returns queued first, then duplicate."""
    payload = {
        "url": "https://example.com/jobs/dup-003",
        "title": "Senior Product Manager",
        "company": "Delta Co",
        "location": "Remote",
        "source": "test",
        "clean_jd": "Own the roadmap for our growth team.",
    }

    # First POST — should be queued
    first = await client.post("/ingest/ingest-lead", json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "queued"

    # Second POST — same URL hash — should be duplicate
    second = await client.post("/ingest/ingest-lead", json=payload)
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert second.json()["job_id"] is None


@pytest.mark.asyncio
async def test_ingest_lead_missing_fields(client: AsyncClient) -> None:
    """Posting without the required 'url' field returns HTTP 422 validation error."""
    payload = {
        "title": "Senior Product Manager",
        "company": "Gamma Ltd",
        # Missing: url, source
    }
    response = await client.post("/ingest/ingest-lead", json=payload)
    assert response.status_code == 422
