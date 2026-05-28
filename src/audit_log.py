from datetime import datetime
from enum import StrEnum

import structlog
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession

from src.queue.models import Base

log = structlog.get_logger()


class AuditEvent(StrEnum):
    DISCOVERED = "DISCOVERED"
    FILTERED_PASS = "FILTERED_PASS"
    FILTERED_REJECT = "FILTERED_REJECT"
    DEDUP_SKIP = "DEDUP_SKIP"
    QUEUED = "QUEUED"
    DRY_RUN_WOULD_QUEUE = "DRY_RUN_WOULD_QUEUE"
    DRY_RUN_WOULD_REJECT = "DRY_RUN_WOULD_REJECT"
    APPLYING = "APPLYING"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    NOTIFIED = "NOTIFIED"


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

    # audit_log is append-only — never update or delete rows (T-03-02, T-01-04).
    Caller manages the transaction — do NOT call session.commit() here.
    """
    entry = AuditLogEntry(
        job_id=job_id,
        source=source,
        event=event.value,
        reason=reason,
        details=details,
    )
    # audit_log is append-only — never update or delete rows
    session.add(entry)
    # Also emit to structlog so stdout is a complete audit trail.
    # Use audit_event kwarg to avoid conflict with structlog's reserved 'event' positional param.
    log.info(
        "audit",
        job_id=job_id,
        source=source,
        audit_event=event.value,
        reason=reason,
    )
