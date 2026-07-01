"""Configuration values for the FastAPI service layer."""

from pathlib import Path

UPLOAD_DIR = Path("data/uploads")
OUTPUT_DIR = Path("data/outputs")
MAX_UPLOAD_SIZE_MB = 100
RATE_LIMIT_UPLOADS = "5/hour"
