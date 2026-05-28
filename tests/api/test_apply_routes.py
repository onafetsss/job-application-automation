"""Tests for /apply/* routes (Plan 03-03).

Tests:
    test_daily_count        — GET /apply/daily-linkedin-count returns correct count for today's submissions
    test_apply_404          — POST /apply/linkedin-easy-apply returns 404 for unknown job_id
    test_apply_409          — POST /apply/linkedin-easy-apply returns 409 for non-QUEUED job
    test_queued_linkedin_jobs — GET /apply/queued-linkedin-jobs returns only QUEUED linkedin jobs
"""

import uuid
from datetime import datetime, timezone

import pytest

# ---------------------------------------------------------------------------
# Test 1: daily LinkedIn submission count
# ---------------------------------------------------------------------------


async def test_daily_count(tmp_path, monkeypatch) -> None:
    """DB fixture: insert Job+Application rows directly.

    Two linkedin applications submitted today; one email application today (excluded);
    GET /apply/daily-linkedin-count must return {"count": 2}.
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
    from sqlalchemy import text  # noqa: PLC0415

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Directly insert Job + Application rows into the DB (bypass eligibility filter)
            async with db_module._engine.connect() as conn:
                now_iso = datetime.now(timezone.utc).isoformat()
                li_job_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
                email_job_id = str(uuid.uuid4())

                # Insert two linkedin_easy_apply Job rows (SUBMITTED status)
                for i, job_id in enumerate(li_job_ids):
                    url_hash = f"hash-li-{i}"
                    await conn.execute(
                        text(
                            "INSERT INTO jobs "
                            "(id, url, url_hash, title, title_normalized, company, company_normalized, "
                            "location, location_normalized, source, apply_type, status, retry_count, created_at, updated_at) "
                            "VALUES (:id, :url, :url_hash, :title, :tn, :co, :cn, :loc, :ln, :src, :at, :st, 0, :ca, :ua)"
                        ),
                        {
                            "id": job_id,
                            "url": f"https://linkedin.com/jobs/view/li-job-{i}",
                            "url_hash": url_hash,
                            "title": f"Software Engineer {i}",
                            "tn": f"software engineer {i}",
                            "co": "LinkedIn Corp",
                            "cn": "linkedin corp",
                            "loc": "Remote",
                            "ln": "remote",
                            "src": "test",
                            "at": "linkedin_easy_apply",
                            "st": "SUBMITTED",
                            "ca": now_iso,
                            "ua": now_iso,
                        },
                    )
                    # Application row submitted today
                    await conn.execute(
                        text(
                            "INSERT INTO applications "
                            "(id, job_id, resume_template, cover_letter, submitted_at) "
                            "VALUES (:id, :job_id, :resume, :cl, :submitted_at)"
                        ),
                        {
                            "id": f"app-li-{job_id[:8]}",
                            "job_id": job_id,
                            "resume": "test.pdf",
                            "cl": "Test cover letter",
                            "submitted_at": now_iso,
                        },
                    )

                # Insert one email Job + Application (should be excluded by apply_type filter)
                await conn.execute(
                    text(
                        "INSERT INTO jobs "
                        "(id, url, url_hash, title, title_normalized, company, company_normalized, "
                        "location, location_normalized, source, apply_type, status, retry_count, created_at, updated_at) "
                        "VALUES (:id, :url, :url_hash, :title, :tn, :co, :cn, :loc, :ln, :src, :at, :st, 0, :ca, :ua)"
                    ),
                    {
                        "id": email_job_id,
                        "url": "https://careers.example.com/email-job",
                        "url_hash": "hash-email-1",
                        "title": "Email Job",
                        "tn": "email job",
                        "co": "Example Corp",
                        "cn": "example corp",
                        "loc": "Remote",
                        "ln": "remote",
                        "src": "test",
                        "at": "email",
                        "st": "SUBMITTED",
                        "ca": now_iso,
                        "ua": now_iso,
                    },
                )
                await conn.execute(
                    text(
                        "INSERT INTO applications "
                        "(id, job_id, resume_template, cover_letter, submitted_at) "
                        "VALUES (:id, :job_id, :resume, :cl, :submitted_at)"
                    ),
                    {
                        "id": f"app-em-{email_job_id[:8]}",
                        "job_id": email_job_id,
                        "resume": "test.pdf",
                        "cl": "Email cover letter",
                        "submitted_at": now_iso,
                    },
                )
                await conn.commit()

            # Call the daily count endpoint
            resp = await client.get("/apply/daily-linkedin-count")
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 2, f"Expected 2 submissions today, got {data['count']}"

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None


# ---------------------------------------------------------------------------
# Test 2: POST /apply/linkedin-easy-apply — 404 for unknown job_id
# ---------------------------------------------------------------------------


async def test_apply_404(tmp_path, monkeypatch) -> None:
    """POST /apply/linkedin-easy-apply with a non-existent job_id returns 404 {"detail":"job_not_found"}."""
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
            resp = await client.post(
                "/apply/linkedin-easy-apply",
                json={"job_id": str(uuid.uuid4())},
            )
            assert resp.status_code == 404
            assert resp.json()["detail"] == "job_not_found"

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None


# ---------------------------------------------------------------------------
# Test 3: POST /apply/linkedin-easy-apply — 409 for non-QUEUED job
# ---------------------------------------------------------------------------


async def test_apply_409(tmp_path, monkeypatch) -> None:
    """POST /apply/linkedin-easy-apply with a non-QUEUED job returns 409 {"detail":"job_not_queued"}."""
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
    from sqlalchemy import text  # noqa: PLC0415

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Insert a Job with APPLYING status directly (not QUEUED)
            job_id = str(uuid.uuid4())
            async with db_module._engine.connect() as conn:
                now_iso = datetime.now(timezone.utc).isoformat()
                await conn.execute(
                    text(
                        "INSERT INTO jobs "
                        "(id, url, url_hash, title, title_normalized, company, company_normalized, "
                        "location, location_normalized, source, apply_type, status, retry_count, created_at, updated_at) "
                        "VALUES (:id, :url, :url_hash, :title, :tn, :co, :cn, :loc, :ln, :src, :at, :st, 0, :ca, :ua)"
                    ),
                    {
                        "id": job_id,
                        "url": "https://linkedin.com/jobs/view/applying-job",
                        "url_hash": "hash-applying-1",
                        "title": "Applying Job",
                        "tn": "applying job",
                        "co": "Test Corp",
                        "cn": "test corp",
                        "loc": "Remote",
                        "ln": "remote",
                        "src": "test",
                        "at": "linkedin_easy_apply",
                        "st": "APPLYING",  # not QUEUED
                        "ca": now_iso,
                        "ua": now_iso,
                    },
                )
                await conn.commit()

            resp = await client.post(
                "/apply/linkedin-easy-apply",
                json={"job_id": job_id},
            )
            assert resp.status_code == 409
            assert resp.json()["detail"] == "job_not_queued"

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None


# ---------------------------------------------------------------------------
# Test 4: GET /apply/queued-linkedin-jobs — only QUEUED linkedin_easy_apply jobs
# ---------------------------------------------------------------------------


async def test_queued_linkedin_jobs(tmp_path, monkeypatch) -> None:
    """GET /apply/queued-linkedin-jobs returns only QUEUED jobs with apply_type='linkedin_easy_apply'."""
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
    from sqlalchemy import text  # noqa: PLC0415

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            li_job_id = str(uuid.uuid4())
            email_job_id = str(uuid.uuid4())

            async with db_module._engine.connect() as conn:
                now_iso = datetime.now(timezone.utc).isoformat()
                # LinkedIn QUEUED job — should appear
                await conn.execute(
                    text(
                        "INSERT INTO jobs "
                        "(id, url, url_hash, title, title_normalized, company, company_normalized, "
                        "location, location_normalized, source, apply_type, status, retry_count, created_at, updated_at) "
                        "VALUES (:id, :url, :url_hash, :title, :tn, :co, :cn, :loc, :ln, :src, :at, :st, 0, :ca, :ua)"
                    ),
                    {
                        "id": li_job_id,
                        "url": "https://linkedin.com/jobs/view/queued-li-job",
                        "url_hash": "hash-queued-li-1",
                        "title": "LinkedIn Job",
                        "tn": "linkedin job",
                        "co": "LinkedIn Corp",
                        "cn": "linkedin corp",
                        "loc": "Remote",
                        "ln": "remote",
                        "src": "test",
                        "at": "linkedin_easy_apply",
                        "st": "QUEUED",
                        "ca": now_iso,
                        "ua": now_iso,
                    },
                )
                # Email QUEUED job — should NOT appear
                await conn.execute(
                    text(
                        "INSERT INTO jobs "
                        "(id, url, url_hash, title, title_normalized, company, company_normalized, "
                        "location, location_normalized, source, apply_type, status, retry_count, created_at, updated_at) "
                        "VALUES (:id, :url, :url_hash, :title, :tn, :co, :cn, :loc, :ln, :src, :at, :st, 0, :ca, :ua)"
                    ),
                    {
                        "id": email_job_id,
                        "url": "https://careers.example.com/email-job-queued",
                        "url_hash": "hash-queued-email-1",
                        "title": "Email Job",
                        "tn": "email job",
                        "co": "Example Corp",
                        "cn": "example corp",
                        "loc": "Remote",
                        "ln": "remote",
                        "src": "test",
                        "at": "email",
                        "st": "QUEUED",
                        "ca": now_iso,
                        "ua": now_iso,
                    },
                )
                await conn.commit()

            resp = await client.get("/apply/queued-linkedin-jobs")
            assert resp.status_code == 200
            data = resp.json()
            assert "jobs" in data
            job_ids_returned = [j["id"] for j in data["jobs"]]
            # LinkedIn QUEUED job must be present
            assert li_job_id in job_ids_returned
            # Email job must NOT be present
            assert email_job_id not in job_ids_returned
            # All returned jobs must have the required fields
            for j in data["jobs"]:
                assert "id" in j
                assert "title" in j
                assert "company" in j
                assert "url" in j

    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None
