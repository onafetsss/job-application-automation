import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class JobStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    QUEUED = "QUEUED"
    REJECTED = "REJECTED"
    APPLYING = "APPLYING"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    NEEDS_HUMAN = "NEEDS_HUMAN"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    url = Column(Text, unique=True, nullable=False)
    url_hash = Column(String(64), unique=True, nullable=False)  # SHA-256, fast dedup
    title = Column(Text, nullable=False)
    title_normalized = Column(Text, nullable=False)             # lowercase, stripped
    company = Column(Text, nullable=False)
    company_normalized = Column(Text, nullable=False)           # lowercase, stripped
    location = Column(Text)
    location_normalized = Column(Text)                          # lowercase, stripped
    source = Column(String, nullable=False)                     # 'linkedin_email'|'kalibrr'|'indeed'
    apply_type = Column(String)                                 # set during normalisation (Phase 2+)
    raw_jd = Column(Text)                                       # raw job description HTML
    clean_jd = Column(Text)                                     # stripped plain-text JD
    status = Column(String, nullable=False, default=JobStatus.DISCOVERED)
    rejection_reason = Column(String)                           # e.g. 'title_mismatch'|'location_mismatch'
    retry_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime)
    claimed_at = Column(DateTime)
    # Phase 2+ fields (nullable in Phase 1 — set when application is prepared)
    resume_template = Column(String)
    cover_letter = Column(Text)
    screening_answers = Column(Text)                            # JSON blob
    # screening_questions: raw text extracted during enrichment; nullable in Phase 2
    screening_questions = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    applications = relationship("Application", back_populates="job")


class Application(Base):
    __tablename__ = "applications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    resume_template = Column(String, nullable=False)
    cover_letter = Column(Text, nullable=False)
    screening_answers = Column(Text)                            # JSON blob
    submitted_at = Column(DateTime)
    error_log = Column(Text)                                    # JSON blob on failure
    notified_at = Column(DateTime)

    job = relationship("Job", back_populates="applications")


class EligibilityConfigSnapshot(Base):
    """Audit trail of eligibility config changes."""
    __tablename__ = "eligibility_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_json = Column(Text, nullable=False)
    applied_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AgentConfig(Base):
    """Key-value store for agent runtime state (e.g., gmail_history_id)."""
    __tablename__ = "agent_config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
