"""HTTP-layer request and response models for FastAPI routes."""

from pydantic import BaseModel, Field

from compressor.schemas import JobStatus, PageType


class JobCreateResponse(BaseModel):
    """Response body for job creation."""

    job_id: str
    status: JobStatus


class PageClassificationSummary(BaseModel):
    """Review-friendly page classification summary returned over HTTP."""

    page_num: int
    page_type: PageType
    confidence: float


class JobStatusResponse(BaseModel):
    """Polymorphic job status response keyed by status field."""

    job_id: str
    status: JobStatus
    classifications: list[PageClassificationSummary] | None = None
    thumbnails: list[str] | None = None
    download_url: str | None = None
    final_size_mb: float | None = None
    error: str | None = None


class ClassificationSelection(BaseModel):
    """User override for one page classification."""

    page_num: int
    page_type: PageType


class JobConfirmRequest(BaseModel):
    """Request body for confirming reviewed classifications."""

    classifications: list[ClassificationSelection] = Field(default_factory=list)


class JobConfirmResponse(BaseModel):
    """Response body for classification confirmation."""

    job_id: str
    status: JobStatus
