"""Pydantic models shared by the compressor pipeline and service layer."""

from datetime import datetime
from enum import Enum
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field


class PageType(str, Enum):
    """Supported heuristic page categories for portfolio pages."""

    HERO = "hero"
    PROCESS = "process"


class PageFeatures(BaseModel):
    """Visual features extracted from a rendered portfolio page."""

    color_entropy: float
    edge_density: float
    image_area_ratio: float
    text_area_ratio: float


class PageClassification(BaseModel):
    """Classification result for one rendered portfolio page."""

    page_num: int
    page_type: PageType
    confidence: float
    features: PageFeatures
    user_override: bool = False


class CompressionConfig(BaseModel):
    """Configuration values for binary-search PDF compression."""

    target_size_mb: float
    tolerance_mb: float = 0.5
    max_iterations: int = 8
    hero_base_quality: int = 90
    process_base_quality: int = 55
    hero_min_quality: int = 60
    process_min_quality: int = 25
    render_dpi: int = 200


class PageData(BaseModel):
    """Rendered page image paired with its classification."""

    image: np.ndarray
    classification: PageClassification

    model_config = ConfigDict(arbitrary_types_allowed=True)


class CompressionStats(BaseModel):
    """Summary information for one binary-search compression run."""

    iterations_used: int
    final_multiplier: float
    final_size_mb: float
    converged: bool


class JobStatus(str, Enum):
    """Lifecycle states for in-memory compression jobs."""

    RECEIVED = "received"
    CLASSIFYING = "classifying"
    AWAITING_REVIEW = "awaiting_review"
    COMPRESSING = "compressing"
    COMPLETE = "complete"
    FAILED = "failed"


class Job(BaseModel):
    """In-memory job record used by the FastAPI service layer."""

    id: str
    status: JobStatus
    input_path: Path
    output_path: Path | None = None
    target_size_mb: float
    classifications: list[PageClassification] = Field(default_factory=list)
    thumbnails: list[Path] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
