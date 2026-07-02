"""Anonymous JSONL logging helpers for completed compression jobs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from compressor.schemas import CompressionStats, Job, PageClassification, PageType

LOG_DIR = Path("data/logs")
HASH_READ_BYTES = 64 * 1024


def log_job_completion(
    job: Job,
    stats: CompressionStats | None,
    error: str | None,
) -> None:
    """Append one anonymous job-completion record to the daily JSONL log.

    Args:
        job: Completed or failed job record.
        stats: Compression statistics when compression succeeded.
        error: Error message when compression failed, otherwise None.
    """
    timestamp = datetime.now(timezone.utc)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{timestamp.date().isoformat()}.jsonl"

    payload = {
        "timestamp": _isoformat_utc(timestamp),
        "job_id": job.id,
        "input_hash": _hash_input_prefix(job.input_path),
        "input_size_bytes": _safe_size(job.input_path),
        "input_page_count": len(job.classifications),
        "target_size_mb": job.target_size_mb,
        "final_size_bytes": _safe_size(job.output_path),
        "duration_seconds": _duration_seconds(job, timestamp),
        "classifications": [_classification_log(item) for item in job.classifications],
        "iterations_used": stats.iterations_used if stats is not None else None,
        "final_multiplier": stats.final_multiplier if stats is not None else None,
        "status": "success" if error is None else "failed",
        "error": error,
        "user_agent_hash": None,
    }

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _hash_input_prefix(path: Path) -> str | None:
    """Return a short SHA256 fingerprint for the input PDF contents."""
    try:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            hasher.update(handle.read(HASH_READ_BYTES))
        return f"sha256:{hasher.hexdigest()[:16]}"
    except OSError:
        return None


def _safe_size(path: Path | None) -> int | None:
    """Return file size in bytes when the path exists, otherwise None."""
    if path is None:
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


def _duration_seconds(job: Job, fallback_end: datetime) -> float | None:
    """Measure elapsed time from creation until completion or fallback timestamp."""
    end_time = job.completed_at or fallback_end
    if end_time.tzinfo is None or job.created_at.tzinfo is None:
        return None
    return round((end_time - job.created_at).total_seconds(), 3)


def _classification_log(classification: PageClassification) -> dict[str, object]:
    """Serialize one classification row for the anonymous log format."""
    page = classification.page_num
    user_type = classification.page_type.value
    ai_type = user_type
    if classification.user_override:
        ai_type = (
            PageType.PROCESS.value
            if classification.page_type == PageType.HERO
            else PageType.HERO.value
        )

    return {
        "page": page,
        "ai_type": ai_type,
        "user_type": user_type,
        "confidence": classification.confidence,
    }


def _isoformat_utc(value: datetime) -> str:
    """Format a UTC datetime with a trailing Z suffix."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
