from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.queue.models import Base

# Import all ORM models here so Base.metadata knows about every table
# before init_db() calls Base.metadata.create_all().
# Adding a new model? Import it here.
import src.audit_log  # noqa: F401, E402

_engine: AsyncEngine | None = None


def get_engine(db_path: str = "data/jobs.db") -> AsyncEngine:
    """Return the singleton async engine, creating it if needed."""
    global _engine
    if _engine is None:
        db_file = Path(db_path)
        # T-01-01: create data/ with restricted permissions (not world-readable).
        # mkdir mode is subject to umask; chmod enforces the intended permissions.
        # Only chmod directories we create (skip pre-existing system dirs like /tmp).
        parent = db_file.parent
        dir_existed = parent.exists()
        parent.mkdir(parents=True, exist_ok=True)
        if not dir_existed:
            parent.chmod(0o700)
        _engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine


async def init_db(db_path: str = "data/jobs.db") -> None:
    """Create all tables and enable WAL mode. Call once at startup."""
    # Reset singleton so tests can use different db_path values
    global _engine
    _engine = None

    engine = get_engine(db_path)
    async with engine.begin() as conn:
        # WAL mode: allows concurrent reads during writes (required for multi-reader access)
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        # T-01-03: foreign_keys=ON enforces referential integrity without shell exposure
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)


def get_session_factory(db_path: str = "data/jobs.db") -> sessionmaker:  # type: ignore[type-arg]
    """Return an async session factory for use in services."""
    engine = get_engine(db_path)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
