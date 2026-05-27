"""All Pydantic request/response schemas for Phase 2 API endpoints."""

from pydantic import BaseModel, Field


class LeadIn(BaseModel):
    """Payload for POST /ingest-lead — universal entry point for all lead sources."""

    url: str
    title: str
    company: str
    location: str | None = None
    source: str
    clean_jd: str | None = None
    apply_type: str | None = None


class LeadOut(BaseModel):
    """Response for POST /ingest-lead."""

    status: str  # "queued" | "rejected" | "duplicate"
    job_id: str | None = None


class ScrapeJobSpyIn(BaseModel):
    """Payload for POST /scrape-jobspy."""

    search_term: str
    location: str = "Remote"
    results_wanted: int = Field(default=25, ge=1, le=100)
    hours_old: int = Field(default=24, ge=1)
    site_names: list[str] = Field(default_factory=lambda: ["indeed"])


class ScrapeKalibrrIn(BaseModel):
    """Payload for POST /scrape-kalibrr."""

    search_term: str
    max_pages: int = Field(default=3, ge=1, le=10)


class SelectResumeIn(BaseModel):
    """Payload for POST /select-resume."""

    job_id: str
    job_description: str
    job_title: str
    company: str


class SelectResumeOut(BaseModel):
    """Response for POST /select-resume."""

    resume_name: str
    resume_text: str


class WriteApplicationIn(BaseModel):
    """Payload for POST /write-application."""

    job_id: str
    resume_name: str
    cover_letter: str


class MarkSubmittedIn(BaseModel):
    """Payload for POST /mark-submitted."""

    job_id: str


class PollGmailOut(BaseModel):
    """Response for GET /poll-gmail."""

    message_ids: list[str]
    history_id: str


class FetchEmailBodyIn(BaseModel):
    """Payload for POST /fetch-email-body."""

    message_id: str


class FetchEmailBodyOut(BaseModel):
    """Response for POST /fetch-email-body."""

    body_text: str
    subject: str | None = None
    sender: str | None = None


class GenerateScreeningAnswersIn(BaseModel):
    """Payload for POST /generate-screening-answers."""

    job_id: str
    screening_questions: list[str]
    job_description: str
    job_title: str


class GenerateScreeningAnswersOut(BaseModel):
    """Response for POST /generate-screening-answers."""

    job_id: str
    answers: list[dict]  # type: ignore[type-arg]


class ProfileOut(BaseModel):
    """Response for GET /profile."""

    summary: str
    target_roles: list[str]
    key_projects: list[dict]  # type: ignore[type-arg]
    skills: list[str]
    location_preference: str
    availability: str
