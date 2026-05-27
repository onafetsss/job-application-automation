"""Integration tests for POST /application/write-application and POST /application/mark-submitted.

Tests application lifecycle state transitions: QUEUED -> APPLYING -> SUBMITTED.
No external mocks needed — these are pure DB operations.
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:  # type: ignore[type-arg]
    """Fixture: initialize the FastAPI app with a temp SQLite DB and yield an AsyncClient."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("ELIGIBILITY_CONFIG_PATH", "config/eligibility.yaml")
    monkeypatch.setenv("PROFILE_CONFIG_PATH", "config/profile.yaml")
    monkeypatch.delenv("API_KEY", raising=False)

    import src.queue.db as db_module  # noqa: PLC0415

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None

    from src.api.app import app  # noqa: PLC0415

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None


async def _create_queued_job(client: AsyncClient, url_suffix: str = "001") -> str:
    """Helper: create a QUEUED job via /ingest-lead and return the job_id."""
    payload = {
        "url": f"https://example.com/jobs/app-test-{url_suffix}",
        "title": "Senior Product Manager",
        "company": "Test Corp",
        "location": "Remote",
        "source": "test",
        "clean_jd": "Lead product strategy for our growth team.",
    }
    response = await client.post("/ingest/ingest-lead", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    return data["job_id"]


@pytest.mark.asyncio
async def test_write_application_success(client: AsyncClient) -> None:
    """write-application transitions QUEUED job to APPLYING and stores resume + cover letter."""
    job_id = await _create_queued_job(client, "wa-001")

    payload = {
        "job_id": job_id,
        "resume_name": "pm-growth.pdf",
        "cover_letter": "Dear Hiring Manager, I am excited to apply for this role.",
    }
    response = await client.post("/application/write-application", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["job_id"] == job_id

    # Verify DB state via raw SQL
    import src.queue.db as db_module  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    async with db_module._engine.connect() as conn:
        result = await conn.execute(
            text("SELECT status, resume_template, cover_letter FROM jobs WHERE id = :id"),
            {"id": job_id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "APPLYING"
        assert row[1] == "pm-growth.pdf"
        assert row[2] == "Dear Hiring Manager, I am excited to apply for this role."


@pytest.mark.asyncio
async def test_write_application_job_not_found(client: AsyncClient) -> None:
    """write-application with fake job_id returns HTTP 404."""
    payload = {
        "job_id": "00000000-0000-0000-0000-000000000000",
        "resume_name": "pm-growth.pdf",
        "cover_letter": "Dear Hiring Manager...",
    }
    response = await client.post("/application/write-application", json=payload)

    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "job_not_found"


@pytest.mark.asyncio
async def test_write_application_not_queued(client: AsyncClient) -> None:
    """write-application on a non-QUEUED job returns HTTP 409."""
    job_id = await _create_queued_job(client, "wa-409")

    # First write-application — transitions to APPLYING
    first_payload = {
        "job_id": job_id,
        "resume_name": "pm-growth.pdf",
        "cover_letter": "Dear Hiring Manager...",
    }
    first_response = await client.post("/application/write-application", json=first_payload)
    assert first_response.status_code == 200

    # Second write-application — job is now APPLYING, should return 409
    second_response = await client.post("/application/write-application", json=first_payload)
    assert second_response.status_code == 409
    data = second_response.json()
    assert data["detail"] == "job_not_queued"


@pytest.mark.asyncio
async def test_mark_submitted_success(client: AsyncClient) -> None:
    """mark-submitted transitions APPLYING job to SUBMITTED and creates an Application row."""
    job_id = await _create_queued_job(client, "ms-001")

    # Transition to APPLYING first
    write_payload = {
        "job_id": job_id,
        "resume_name": "pm-growth.pdf",
        "cover_letter": "Dear Hiring Manager, I am excited to apply.",
    }
    write_response = await client.post("/application/write-application", json=write_payload)
    assert write_response.status_code == 200

    # Now mark as submitted
    submit_payload = {"job_id": job_id}
    response = await client.post("/application/mark-submitted", json=submit_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["job_id"] == job_id

    # Verify DB state — job should be SUBMITTED
    import src.queue.db as db_module  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    async with db_module._engine.connect() as conn:
        job_result = await conn.execute(
            text("SELECT status FROM jobs WHERE id = :id"),
            {"id": job_id},
        )
        job_row = job_result.fetchone()
        assert job_row is not None
        assert job_row[0] == "SUBMITTED"

        # Verify Application row was created with correct fields
        app_result = await conn.execute(
            text(
                "SELECT resume_template, cover_letter, submitted_at "
                "FROM applications WHERE job_id = :job_id"
            ),
            {"job_id": job_id},
        )
        app_row = app_result.fetchone()
        assert app_row is not None
        assert app_row[0] == "pm-growth.pdf"
        assert app_row[1] == "Dear Hiring Manager, I am excited to apply."
        assert app_row[2] is not None  # submitted_at is set


@pytest.mark.asyncio
async def test_mark_submitted_not_applying(client: AsyncClient) -> None:
    """mark-submitted on a QUEUED job (not APPLYING) returns HTTP 409."""
    job_id = await _create_queued_job(client, "ms-409")

    # Try to mark submitted without calling write-application first
    submit_payload = {"job_id": job_id}
    response = await client.post("/application/mark-submitted", json=submit_payload)

    assert response.status_code == 409
    data = response.json()
    assert data["detail"] == "job_not_applying"
