from datetime import date, datetime

from pydantic import BaseModel


class SourceLink(BaseModel):
    url: str
    label: str = ""
    last_hash: str | None = None
    last_checked_at: datetime | None = None
    has_changed: bool = False


class FundingProgram(BaseModel):
    id: int | None = None
    category: str
    name: str
    project_types: str = ""
    selection_criteria: str = ""
    permanent: bool = False
    start_submission_date: date | None = None
    end_submission_date: date | None = None
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
    permanent: bool = False
    start_submission_date: date | None = None
    end_submission_date: date | None = None
    summary: str = ""


