"""Integration tests for POST /gmail/poll-gmail and POST /gmail/fetch-email-body.

Tests use httpx.AsyncClient + ASGITransport + lifespan context (same pattern as
test_ingest_endpoint.py). The Gmail service layer is mocked — no real API calls.

Tests:
    1. test_poll_gmail_first_run — first run returns empty list and baseline historyId
    2. test_poll_gmail_with_existing_history — existing historyId passed through, results returned
    3. test_fetch_email_body_success — fetch returns body_text, subject, sender
    4. test_poll_gmail_auth_failure — get_gmail_service 401 returns HTTP 503 challenge_detected
"""

from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.queue.models import AgentConfig


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:  # type: ignore[type-arg]
    """Fixture: initialize the FastAPI app with a temp SQLite DB and yield an AsyncClient.

    Mirrors the pattern from test_ingest_endpoint.py for consistent test isolation.
    """
    db_file = tmp_path / "test_gmail.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("ELIGIBILITY_CONFIG_PATH", "config/eligibility.yaml")
    monkeypatch.setenv("PROFILE_CONFIG_PATH", "config/profile.yaml")
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", str(tmp_path / ".google_token.json"))
    # No API_KEY set — auth skipped in dev mode
    monkeypatch.delenv("API_KEY", raising=False)

    # Reset engine singleton so each test gets a fresh DB connection
    import src.queue.db as db_module  # noqa: PLC0415

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None

    # Import app AFTER env patches so lifespan reads correct DB path
    from src.api.app import app  # noqa: PLC0415

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


# ---------------------------------------------------------------------------
# Test 1: First-run poll
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_gmail_first_run(client: AsyncClient) -> None:
    """First run: no stored historyId — returns empty message_ids and baseline historyId."""
    mock_service = MagicMock()

    with (
        patch("src.api.routes.gmail.get_gmail_service", return_value=mock_service),
        patch(
            "src.api.routes.gmail.poll_gmail_since",
            return_value=([], "12345"),
        ) as mock_poll,
    ):
        response = await client.post("/gmail/poll-gmail")

    assert response.status_code == 200
    data = response.json()
    assert data["message_ids"] == []
    assert data["history_id"] == "12345"

    # Verify poll_gmail_since was called with None (no stored historyId yet)
    mock_poll.assert_called_once()
    call_args = mock_poll.call_args
    assert call_args[0][1] is None  # start_history_id = None on first run
    assert call_args[0][2] == "jobalerts-noreply@linkedin.com"


# ---------------------------------------------------------------------------
# Test 2: Poll with existing historyId
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_gmail_with_existing_history(client: AsyncClient, tmp_path) -> None:
    """When AgentConfig has a stored historyId, it is passed to poll_gmail_since."""
    # We need to seed AgentConfig — use the app's session factory
    # First, prime the DB by seeding via a helper that imports the session factory
    import src.queue.db as db_module  # noqa: PLC0415

    # Seed the AgentConfig row directly via the session factory
    async with db_module._engine.begin() as conn:
        # Use raw SQL to insert without ORM overhead in test setup
        from sqlalchemy import text  # noqa: PLC0415

        await conn.execute(
            text(
                "INSERT INTO agent_config (key, value, updated_at) VALUES (:key, :value, datetime('now'))"
            ),
            {"key": "gmail_history_id", "value": "10000"},
        )

    mock_service = MagicMock()

    with (
        patch("src.api.routes.gmail.get_gmail_service", return_value=mock_service),
        patch(
            "src.api.routes.gmail.poll_gmail_since",
            return_value=(["msg1", "msg2"], "10050"),
        ) as mock_poll,
    ):
        response = await client.post("/gmail/poll-gmail")

    assert response.status_code == 200
    data = response.json()
    assert len(data["message_ids"]) == 2
    assert data["history_id"] == "10050"

    # Verify poll_gmail_since received the seeded historyId
    mock_poll.assert_called_once()
    call_args = mock_poll.call_args
    assert call_args[0][1] == "10000"  # existing historyId passed through


# ---------------------------------------------------------------------------
# Test 3: fetch-email-body success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_email_body_success(client: AsyncClient) -> None:
    """fetch-email-body returns body_text, subject, and sender from mocked service."""
    mock_service = MagicMock()
    expected_result = {
        "body_text": "Job alert text — Senior Product Manager at Acme Corp",
        "subject": "Jobs for you",
        "sender": "LinkedIn <jobalerts-noreply@linkedin.com>",
    }

    with (
        patch("src.api.routes.gmail.get_gmail_service", return_value=mock_service),
        patch(
            "src.api.routes.gmail.fetch_message_body",
            return_value=expected_result,
        ),
    ):
        response = await client.post(
            "/gmail/fetch-email-body",
            json={"message_id": "test_msg_001"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["body_text"] == expected_result["body_text"]
    assert data["subject"] == expected_result["subject"]
    assert data["sender"] == expected_result["sender"]


# ---------------------------------------------------------------------------
# Test 4: Auth failure (OAuth 401) returns 503 challenge_detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_gmail_auth_failure(client: AsyncClient) -> None:
    """Gmail OAuth 401 from get_gmail_service returns HTTP 503 challenge_detected."""
    from googleapiclient.errors import HttpError  # noqa: PLC0415

    # Build a 401 HttpError
    resp = MagicMock()
    resp.status = 401
    resp.reason = "Unauthorized"
    http_error_401 = HttpError(resp=resp, content=b"Unauthorized")

    with patch(
        "src.api.routes.gmail.get_gmail_service",
        side_effect=http_error_401,
    ):
        response = await client.post("/gmail/poll-gmail")

    assert response.status_code == 503
    data = response.json()
    # FastAPI wraps the detail dict in a "detail" key
    detail = data["detail"]
    assert detail["status"] == "challenge_detected"
    assert "expired" in detail["detail"].lower() or "revoked" in detail["detail"].lower()
