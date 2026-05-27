"""Integration test: DB initialisation creates all required tables with WAL mode."""

import pytest
import aiosqlite

from src.queue.db import init_db


@pytest.mark.asyncio
async def test_init_db_creates_tables() -> None:
    """init_db() must create jobs, applications, and audit_log tables in WAL mode."""
    # Use in-memory SQLite for full test isolation — no files created on disk
    await init_db(":memory:")

    async with aiosqlite.connect(":memory:") as db:
        # Verify WAL mode on a fresh connection (init_db uses its own engine)
        # We test WAL on the engine's connection by reopening a file DB
        pass

    # Re-initialise against a temp file to check WAL mode and table creation together
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name

    try:
        await init_db(tmp_path)

        async with aiosqlite.connect(tmp_path) as db:
            # Assert all three tables exist
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ) as cursor:
                rows = await cursor.fetchall()
                table_names = {row[0] for row in rows}

            assert "jobs" in table_names, f"Table 'jobs' missing — got: {table_names}"
            assert "applications" in table_names, (
                f"Table 'applications' missing — got: {table_names}"
            )
            assert "audit_log" in table_names, (
                f"Table 'audit_log' missing — got: {table_names}"
            )

            # Assert WAL mode is active
            async with db.execute("PRAGMA journal_mode") as cursor:
                row = await cursor.fetchone()
                journal_mode = row[0] if row else None

            assert journal_mode == "wal", (
                f"Expected WAL mode but got: {journal_mode!r}"
            )
    finally:
        os.unlink(tmp_path)
