"""Integration tests for POST /application/generate-screening-answers endpoint (AI-03, D-20).

Tests screening answer generation via Claude Haiku with profile + JD context.
"""

import json
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


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


async def _create_queued_job(client: AsyncClient) -> str:
    """Helper: create a QUEUED job via /ingest-lead and return the job_id."""
    payload = {
        "url": f"https://example.com/jobs/screening-test-{id(client)}",
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
async def test_generate_screening_answers_success(client: AsyncClient) -> None:
    """Successful screening answer generation returns 200 with answers array."""
    job_id = await _create_queued_job(client)

    # Mock Anthropic to return structured JSON answers
    answers_json = json.dumps({
        "answers": [
            {
                "question": "What is your salary expectation?",
                "answer": "I am targeting $120,000-$140,000 annually based on market rates for senior PM roles.",
            },
            {
                "question": "Why are you interested in this role?",
                "answer": "I am excited about the opportunity to drive product strategy for a growing company.",
            },
        ]
    })
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=answers_json)]

    with patch("src.api.routes.application.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client_inst = MagicMock()
        mock_client_inst.messages.create.return_value = mock_message
        mock_anthropic_cls.return_value = mock_client_inst

        payload = {
            "job_id": job_id,
            "screening_questions": [
                "What is your salary expectation?",
                "Why are you interested in this role?",
            ],
            "job_description": "Lead product strategy for our growth team.",
            "job_title": "Senior Product Manager",
        }
        response = await client.post("/application/generate-screening-answers", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert isinstance(data["answers"], list)
    assert len(data["answers"]) == 2

    for answer_item in data["answers"]:
        assert "question" in answer_item
        assert "answer" in answer_item

    # Verify DB was updated
    import src.queue.db as db_module  # noqa: PLC0415
    from src.queue.models import Job  # noqa: PLC0415

    async with db_module._engine.connect() as conn:
        from sqlalchemy import text  # noqa: PLC0415

        result = await conn.execute(
            text("SELECT screening_answers FROM jobs WHERE id = :id"),
            {"id": job_id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] is not None
        stored_answers = json.loads(row[0])
        assert len(stored_answers) == 2


@pytest.mark.asyncio
async def test_generate_screening_answers_empty_questions(client: AsyncClient) -> None:
    """Empty screening_questions list returns 200 with empty answers, no Anthropic call."""
    job_id = await _create_queued_job(client)

    with patch("src.api.routes.application.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client_inst = MagicMock()
        mock_anthropic_cls.return_value = mock_client_inst

        payload = {
            "job_id": job_id,
            "screening_questions": [],
            "job_description": "Lead product strategy.",
            "job_title": "Product Manager",
        }
        response = await client.post("/application/generate-screening-answers", json=payload)

        # Anthropic should NOT have been called
        mock_client_inst.messages.create.assert_not_called()

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["answers"] == []


@pytest.mark.asyncio
async def test_generate_screening_answers_job_not_found(client: AsyncClient) -> None:
    """Non-existent job_id returns HTTP 404."""
    payload = {
        "job_id": "00000000-0000-0000-0000-000000000000",
        "screening_questions": ["What is your salary expectation?"],
        "job_description": "Lead product strategy.",
        "job_title": "Product Manager",
    }
    response = await client.post("/application/generate-screening-answers", json=payload)

    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "job_not_found"


@pytest.mark.asyncio
async def test_generate_screening_answers_anthropic_failure(client: AsyncClient) -> None:
    """Anthropic API failure returns HTTP 503."""
    job_id = await _create_queued_job(client)

    with patch("src.api.routes.application.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client_inst = MagicMock()
        mock_client_inst.messages.create.side_effect = Exception("API connection failed")
        mock_anthropic_cls.return_value = mock_client_inst

        payload = {
            "job_id": job_id,
            "screening_questions": ["What is your salary expectation?"],
            "job_description": "Lead product strategy.",
            "job_title": "Product Manager",
        }
        response = await client.post("/application/generate-screening-answers", json=payload)

    assert response.status_code == 503
    data = response.json()
    assert "anthropic" in data["detail"].lower() or "unavailable" in data["detail"].lower()
