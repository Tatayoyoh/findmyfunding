from datetime import date, datetime

from pydantic import BaseModel


class SourceLink(BaseModel):
    url: str
    label: str = ""


class FundingProgram(BaseModel):
    id: int | None = None
    category: str
    name: str
    project_types: str = ""
    selection_criteria: str = ""
    submission_dates: str = ""
    pdp_axes: str = ""
    comments: str = ""
    source_urls: list[SourceLink] = []

    # Structured fields (AI-extracted)
    min_amount_eur: int | None = None
    max_amount_eur: int | None = None
    cofinancing_pct: int | None = None
    eligible_structures: list[str] = []
    eligible_themes: list[str] = []
    application_type: str | None = None
    next_deadline: date | None = None

    # Metadata
    last_scraped_at: datetime | None = None
    last_updated_at: datetime | None = None
    created_at: datetime | None = None


class FundingExtraction(BaseModel):
    """Schema returned by AI extraction from scraped pages."""
    min_amount_eur: int | None = None
    max_amount_eur: int | None = None
    cofinancing_pct: int | None = None
    eligible_structures: list[str] = []
    eligible_themes: list[str] = []
    application_type: str | None = None
    next_deadline: date | None = None
    summary: str = ""


class MonitoredSource(BaseModel):
    id: int | None = None
    url: str
    label: str = ""
    funding_program_id: int | None = None
    last_content_hash: str | None = None
    last_checked_at: datetime | None = None
    has_changed: bool = False
