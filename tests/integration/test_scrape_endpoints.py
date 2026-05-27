"""Integration tests for POST /scrape/scrape-jobspy and POST /scrape/scrape-kalibrr.

Scraper functions are mocked since they make real HTTP/external calls.
A temporary DB is initialized via app lifespan (for app startup consistency),
but scrape endpoints do not use the session.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:  # type: ignore[type-arg]
    """Fixture: initialize the FastAPI app with a temp SQLite DB and yield an AsyncClient.

    Mirrors the test_ingest_endpoint.py fixture pattern — uses lifespan_context to
    trigger startup/shutdown hooks. DB is initialized so the app starts cleanly, but
    scrape endpoints do not interact with the DB.
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

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None


# ---------------------------------------------------------------------------
# /scrape/scrape-jobspy tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_jobspy_with_results(client: AsyncClient) -> None:
    """Mock run_jobspy to return 3 jobs. Assert /scrape-jobspy returns 200 with count=3."""
    mock_jobs = [
        {
            "title": "Senior Product Manager",
            "company": "Acme Corp",
            "location": "Remote",
            "job_url": "https://indeed.com/job/1",
            "description": "Lead product strategy.",
        },
        {
            "title": "Product Manager",
            "company": "Beta Inc",
            "location": "Metro Manila",
            "job_url": "https://indeed.com/job/2",
            "description": "Own the roadmap.",
        },
        {
            "title": "Head of Product",
            "company": "Gamma Ltd",
            "location": "Remote",
            "job_url": "https://indeed.com/job/3",
            "description": "Drive product vision.",
        },
    ]

    with patch(
        "src.api.routes.scrape.run_jobspy",
        new=AsyncMock(return_value=mock_jobs),
    ):
        response = await client.post(
            "/scrape/scrape-jobspy",
            json={"search_term": "Product Manager", "location": "Remote"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert len(data["jobs"]) == 3
    assert data["jobs"][0]["title"] == "Senior Product Manager"
    assert "warning" not in data


@pytest.mark.asyncio
async def test_scrape_jobspy_zero_results(client: AsyncClient) -> None:
    """Mock run_jobspy to return []. Assert response includes warning and count=0."""
    with patch(
        "src.api.routes.scrape.run_jobspy",
        new=AsyncMock(return_value=[]),
    ):
        response = await client.post(
            "/scrape/scrape-jobspy",
            json={"search_term": "Wizard", "location": "Remote"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["jobs"] == []
    assert data["warning"] == "zero_results_possible_block"


# ---------------------------------------------------------------------------
# /scrape/scrape-kalibrr tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_kalibrr_with_results(client: AsyncClient) -> None:
    """Mock scrape_kalibrr to return 2 jobs. Assert /scrape-kalibrr returns 200 with count=2."""
    mock_jobs = [
        {
            "title": "Product Manager",
            "company": "TechCo PH",
            "location": "Makati City",
            "url": "https://www.kalibrr.com/c/techco/product-manager",
        },
        {
            "title": "Senior PM",
            "company": "Startup PH",
            "location": "BGC, Taguig",
            "url": "https://www.kalibrr.com/c/startup/senior-pm",
        },
    ]

    with patch(
        "src.api.routes.scrape.scrape_kalibrr",
        new=AsyncMock(return_value=mock_jobs),
    ):
        response = await client.post(
            "/scrape/scrape-kalibrr",
            json={"search_term": "Product Manager", "max_pages": 1},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["jobs"]) == 2
    assert data["jobs"][0]["title"] == "Product Manager"
    assert "warning" not in data


@pytest.mark.asyncio
async def test_scrape_kalibrr_zero_results(client: AsyncClient) -> None:
    """Mock scrape_kalibrr to return []. Assert warning field is present."""
    with patch(
        "src.api.routes.scrape.scrape_kalibrr",
        new=AsyncMock(return_value=[]),
    ):
        response = await client.post(
            "/scrape/scrape-kalibrr",
            json={"search_term": "Unicorn Wrangler", "max_pages": 1},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["jobs"] == []
    assert data["warning"] == "zero_results_possible_block"


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_jobspy_validation_missing_search_term(client: AsyncClient) -> None:
    """POST /scrape-jobspy without required search_term returns HTTP 422."""
    response = await client.post(
        "/scrape/scrape-jobspy",
        json={"location": "Remote", "results_wanted": 5},
    )
    assert response.status_code == 422
