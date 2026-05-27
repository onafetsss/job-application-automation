"""Integration tests for POST /resume/select-resume endpoint.

Tests resume text extraction, directory listing, and LLM-based resume selection.
Uses httpx.AsyncClient with ASGITransport + manual lifespan management.
Mocks anthropic.Anthropic().messages.create since it requires a real API key.
"""

import os
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from docx import Document
from httpx import ASGITransport, AsyncClient


def _make_docx(path: Path, content: str = "Senior Product Manager resume content") -> None:
    """Helper: create a minimal .docx file at the given path."""
    doc = Document()
    doc.add_paragraph(content)
    doc.save(str(path))


def _make_client_fixture(resumes_dir_path: str | None = None):
    """Factory: create a fixture that sets RESUMES_DIR before app starts."""

    @pytest_asyncio.fixture
    async def client_fixture(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:  # type: ignore[type-arg]
        db_file = tmp_path / "test.db"
        monkeypatch.setenv("DB_PATH", str(db_file))
        monkeypatch.setenv("ELIGIBILITY_CONFIG_PATH", "config/eligibility.yaml")
        monkeypatch.setenv("PROFILE_CONFIG_PATH", "config/profile.yaml")
        monkeypatch.delenv("API_KEY", raising=False)
        if resumes_dir_path is not None:
            monkeypatch.setenv("RESUMES_DIR", resumes_dir_path)

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

    return client_fixture


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:  # type: ignore[type-arg]
    """Default fixture: resumes_dir not set (will use app default)."""
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


@pytest.mark.asyncio
async def test_select_resume_success(tmp_path: Path, monkeypatch) -> None:
    """A request with a populated resumes dir returns 200 with resume_name and resume_text."""
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    resume_file = resumes_dir / "pm-growth.docx"
    _make_docx(resume_file, "Senior Product Manager resume content for growth focus")

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("ELIGIBILITY_CONFIG_PATH", "config/eligibility.yaml")
    monkeypatch.setenv("PROFILE_CONFIG_PATH", "config/profile.yaml")
    monkeypatch.setenv("RESUMES_DIR", str(resumes_dir))
    monkeypatch.delenv("API_KEY", raising=False)

    import src.queue.db as db_module  # noqa: PLC0415

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None

    from src.api.app import app  # noqa: PLC0415

    # Mock Anthropic response — return the filename as first line
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="pm-growth.docx\nBest match for PM growth role.")]

    with patch("src.api.routes.resume.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client_inst = MagicMock()
        mock_client_inst.messages.create.return_value = mock_message
        mock_anthropic_cls.return_value = mock_client_inst

        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                payload = {
                    "job_id": "test-job-001",
                    "job_description": "Lead product strategy for our growth team.",
                    "job_title": "Senior Product Manager",
                    "company": "Acme Corp",
                }
                response = await ac.post("/resume/select-resume", json=payload)

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None

    assert response.status_code == 200
    data = response.json()
    assert data["resume_name"] == "pm-growth.docx"
    assert len(data["resume_text"]) > 0


@pytest.mark.asyncio
async def test_select_resume_no_resumes(tmp_path: Path, monkeypatch) -> None:
    """An empty resumes directory returns HTTP 404."""
    empty_dir = tmp_path / "empty_resumes"
    empty_dir.mkdir()

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("ELIGIBILITY_CONFIG_PATH", "config/eligibility.yaml")
    monkeypatch.setenv("PROFILE_CONFIG_PATH", "config/profile.yaml")
    monkeypatch.setenv("RESUMES_DIR", str(empty_dir))
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
            payload = {
                "job_id": "test-job-002",
                "job_description": "Lead product strategy.",
                "job_title": "Product Manager",
                "company": "Beta Inc",
            }
            response = await ac.post("/resume/select-resume", json=payload)

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None

    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "no_resumes_found"


@pytest.mark.asyncio
async def test_select_resume_anthropic_failure(tmp_path: Path, monkeypatch) -> None:
    """Anthropic API failure returns HTTP 503."""
    resumes_dir = tmp_path / "resumes_fail"
    resumes_dir.mkdir()
    resume_file = resumes_dir / "pm-resume.docx"
    _make_docx(resume_file, "Product Manager resume content")

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("ELIGIBILITY_CONFIG_PATH", "config/eligibility.yaml")
    monkeypatch.setenv("PROFILE_CONFIG_PATH", "config/profile.yaml")
    monkeypatch.setenv("RESUMES_DIR", str(resumes_dir))
    monkeypatch.delenv("API_KEY", raising=False)

    import src.queue.db as db_module  # noqa: PLC0415

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None

    from src.api.app import app  # noqa: PLC0415

    with patch("src.api.routes.resume.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client_inst = MagicMock()
        mock_client_inst.messages.create.side_effect = Exception("API connection failed")
        mock_anthropic_cls.return_value = mock_client_inst

        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                payload = {
                    "job_id": "test-job-003",
                    "job_description": "Lead product strategy.",
                    "job_title": "Product Manager",
                    "company": "Gamma Corp",
                }
                response = await ac.post("/resume/select-resume", json=payload)

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None

    assert response.status_code == 503
    data = response.json()
    assert "anthropic" in data["detail"].lower() or "unavailable" in data["detail"].lower()
