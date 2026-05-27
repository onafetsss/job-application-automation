from datetime import datetime
from enum import Enum

import structlog
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession

from src.queue.models import Base

log = structlog.get_logger()


class AuditEvent(str, Enum):
    DISCOVERED = "DISCOVERED"
    FILTERED_PASS = "FILTERED_PASS"
    FILTERED_REJECT = "FILTERED_REJECT"
    DEDUP_SKIP = "DEDUP_SKIP"
    QUEUED = "QUEUED"
    DRY_RUN_WOULD_QUEUE = "DRY_RUN_WOULD_QUEUE"
    DRY_RUN_WOULD_REJECT = "DRY_RUN_WOULD_REJECT"


class AuditLogEntry(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String)                    # NULL for dedup-skipped entries (no row created)
    source = Column(String, nullable=False)    # ingestion source identifier
    event = Column(String, nullable=False)     # AuditEvent value
    reason = Column(String)                    # rejection reason or None
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    details = Column(Text)                     # optional JSON for extra context


async def write_audit(
    session: AsyncSession,
    *,
    source: str,
    event: AuditEvent,
    job_id: str | None = None,
    reason: str | None = None,
    details: str | None = None,
) -> None:
    """Write one audit log entry to DB and emit a structlog event.

    T-01-04: append-only — only calls session.add(); never UPDATE or DELETE.
    """
    entry = AuditLogEntry(
        job_id=job_id,
        source=source,
        event=event.value,
        reason=reason,
        details=details,
    )
    session.add(entry)
    # Also emit to structlog so stdout is a complete audit trail
    log.info(
        "audit",
        job_id=job_id,
        source=source,
        event=event.value,
        reason=reason,
    )
