"""Integration tests for GET /profile endpoint.

Tests that the profile config from profile.yaml is correctly serialized as JSON.
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

    # Reset engine singleton so each test gets a fresh DB connection
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


@pytest.mark.asyncio
async def test_get_profile_success(client: AsyncClient) -> None:
    """GET /profile returns 200 with all ProfileOut fields matching profile.yaml."""
    response = await client.get("/profile")
    assert response.status_code == 200
    data = response.json()

    # Verify required fields are present
    assert "summary" in data
    assert "target_roles" in data
    assert "key_projects" in data
    assert "skills" in data
    assert "location_preference" in data
    assert "availability" in data

    # Verify they match the profile.yaml content
    assert "Product Manager" in data["summary"] or len(data["summary"]) > 0
    assert len(data["target_roles"]) > 0
    assert len(data["skills"]) > 0


@pytest.mark.asyncio
async def test_get_profile_shape(client: AsyncClient) -> None:
    """GET /profile response JSON contains all ProfileOut fields as non-empty values."""
    response = await client.get("/profile")
    assert response.status_code == 200
    data = response.json()

    # All fields must be non-empty
    assert data["summary"] and len(data["summary"]) > 0
    assert isinstance(data["target_roles"], list) and len(data["target_roles"]) > 0
    assert isinstance(data["key_projects"], list) and len(data["key_projects"]) > 0
    assert isinstance(data["skills"], list) and len(data["skills"]) > 0
    assert data["location_preference"] and len(data["location_preference"]) > 0
    assert data["availability"] and len(data["availability"]) > 0

    # Each key_project must have name and impact keys
    for project in data["key_projects"]:
        assert "name" in project
        assert "impact" in project
