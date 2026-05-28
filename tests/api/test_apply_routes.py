"""RED scaffold — API tests for /apply/* routes (Plan 03-03).

These tests are in RED state. The route module src.api.routes.apply.linkedin_apply
is created in Plan 03-03. The test is marked xfail until that plan completes.

Tests:
    test_daily_count    — daily-linkedin-count endpoint returns correct count for today's submissions
"""

from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Test 1: daily LinkedIn submission count
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="GET /apply/daily-linkedin-count route implemented in Plan 03-03",
    strict=False,
)
async def test_daily_count(tmp_path, monkeypatch) -> None:
    """DB fixture: insert two Application rows submitted today via the linkedin path.

    Asserts the daily-count helper/endpoint returns 2.
    The route GET /apply/daily-linkedin-count reads Application rows where
    submitted_at >= today midnight and apply_platform='linkedin' (or equivalent).
    """
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
    from httpx import ASGITransport, AsyncClient  # noqa: PLC0415

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Insert two QUEUED jobs to get job IDs
            job_ids = []
            for i in range(2):
                ingest_resp = await client.post(
                    "/ingest/ingest-lead",
                    json={
                        "url": f"https://linkedin.com/jobs/view/test-daily-{i}",
                        "title": f"Test Role {i}",
                        "company": "LinkedIn Corp",
                        "location": "Remote",
                        "source": "test",
                        "clean_jd": "Test job description",
                        "apply_type": "linkedin_easy_apply",
                    },
                )
                assert ingest_resp.status_code == 200
                job_ids.append(ingest_resp.json()["job_id"])

            # Directly insert Application rows (submitted today) via DB
            from sqlalchemy import text  # noqa: PLC0415
            from sqlalchemy.ext.asyncio import AsyncSession  # noqa: PLC0415

            async with db_module._engine.connect() as conn:
                for job_id in job_ids:
                    await conn.execute(
                        text(
                            "INSERT INTO applications "
                            "(id, job_id, resume_template, cover_letter, submitted_at) "
                            "VALUES (:id, :job_id, :resume, :cl, :submitted_at)"
                        ),
                        {
                            "id": f"app-test-{job_id[:8]}",
                            "job_id": job_id,
                            "resume": "test.pdf",
                            "cl": "Test cover letter",
                            "submitted_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                await conn.commit()

            # Call the daily count endpoint (implemented in Plan 03-03)
            resp = await client.get("/apply/daily-linkedin-count")
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 2, f"Expected 2 submissions today, got {data['count']}"

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None
