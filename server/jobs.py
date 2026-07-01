"""In-memory job manager for the FastAPI service layer."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Callable
from uuid import uuid4

from compressor.schemas import Job, JobStatus


class JobManager:
    """Thread-safe in-memory store for compression jobs."""

    def __init__(
        self,
        _clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        self._clock = _clock or (lambda: datetime.now(timezone.utc))

    def create_job(
        self,
        input_path: Path,
        target_size_mb: float,
        job_id: str | None = None,
    ) -> Job:
        """Create and store a new job in received state."""
        job = Job(
            id=job_id or str(uuid4()),
            status=JobStatus.RECEIVED,
            input_path=input_path,
            target_size_mb=target_size_mb,
            created_at=self._clock(),
        )
        with self._lock:
            self._jobs[job.id] = job
        return job.model_copy(deep=True)

    def get_job(self, job_id: str) -> Job | None:
        """Return a copy of a job by id, or None if it does not exist."""
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job is not None else None

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        **kwargs,
    ) -> Job:
        """Update a job's status and validated fields, then return a copy."""
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None:
                raise KeyError(job_id)

            allowed_fields = set(Job.model_fields.keys()) - {
                "id",
                "created_at",
                "completed_at",
                "status",
            }
            invalid_fields = set(kwargs) - allowed_fields
            if invalid_fields:
                invalid_list = ", ".join(sorted(invalid_fields))
                raise ValueError(f"Unknown or immutable job fields: {invalid_list}")

            payload = current.model_dump()
            payload.update(kwargs)
            payload["status"] = status
            if status in {JobStatus.COMPLETE, JobStatus.FAILED}:
                payload["completed_at"] = self._clock()
            updated = Job.model_validate(payload)
            self._jobs[job_id] = updated
            return updated.model_copy(deep=True)

    def list_expired(self, older_than_seconds: int) -> list[str]:
        """List job ids older than the provided age threshold."""
        cutoff = self._clock() - timedelta(seconds=older_than_seconds)
        with self._lock:
            return [
                job_id
                for job_id, job in self._jobs.items()
                if job.created_at < cutoff
            ]

    def delete_job(self, job_id: str) -> None:
        """Remove a job from the store if it exists."""
        with self._lock:
            self._jobs.pop(job_id, None)

    def count(self) -> int:
        """Return the number of active jobs."""
        with self._lock:
            return len(self._jobs)

    def clear(self) -> None:
        """Remove all jobs from memory."""
        with self._lock:
            self._jobs.clear()
