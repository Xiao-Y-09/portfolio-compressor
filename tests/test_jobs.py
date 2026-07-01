"""Tests for the in-memory JobManager."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from compressor.schemas import JobStatus, PageClassification, PageFeatures, PageType
from server.jobs import JobManager


def test_create_job(tmp_path: Path) -> None:
    """Creating a job should store a received job with a UUID4 id."""
    manager = JobManager()
    job = manager.create_job(tmp_path / "input.pdf", 15.0)

    parsed = UUID(job.id, version=4)
    assert str(parsed) == job.id
    assert job.status == JobStatus.RECEIVED
    assert manager.get_job(job.id) is not None


def test_create_job_with_explicit_id(tmp_path: Path) -> None:
    """Providing an explicit job id should be preserved."""
    manager = JobManager()

    job = manager.create_job(tmp_path / "input.pdf", 15.0, job_id="fixed-job-id")

    assert job.id == "fixed-job-id"


def test_get_nonexistent_returns_none() -> None:
    """Missing job ids should return None."""
    manager = JobManager()

    assert manager.get_job("bogus-id") is None


def test_update_status(tmp_path: Path) -> None:
    """Updating a job should persist the new status and fields."""
    manager = JobManager()
    job = manager.create_job(tmp_path / "input.pdf", 15.0)
    classifications = [
        PageClassification(
            page_num=1,
            page_type=PageType.HERO,
            confidence=0.9,
            features=PageFeatures(
                color_entropy=1.0,
                edge_density=0.2,
                image_area_ratio=0.7,
                text_area_ratio=0.0,
            ),
        )
    ]

    updated = manager.update_status(
        job.id,
        JobStatus.CLASSIFYING,
        classifications=classifications,
    )

    assert updated.status == JobStatus.CLASSIFYING
    assert updated.completed_at is None
    fetched = manager.get_job(job.id)
    assert fetched is not None
    assert fetched.status == JobStatus.CLASSIFYING
    assert fetched.classifications == classifications

    completed = manager.update_status(job.id, JobStatus.COMPLETE, output_path=tmp_path / "output.pdf")
    assert completed.completed_at is not None
    assert completed.completed_at.tzinfo == timezone.utc


def test_delete_job(tmp_path: Path) -> None:
    """Deleting a job should remove it from the store."""
    manager = JobManager()
    job = manager.create_job(tmp_path / "input.pdf", 15.0)

    manager.delete_job(job.id)

    assert manager.get_job(job.id) is None


def test_list_expired(tmp_path: Path) -> None:
    """Expired jobs should be identified by age threshold."""
    expired_time = datetime.now(timezone.utc) - timedelta(hours=2)
    fresh_time = datetime.now(timezone.utc)

    expired_manager = JobManager(_clock=lambda: expired_time)
    expired_one = expired_manager.create_job(tmp_path / "old1.pdf", 10.0)
    expired_two = expired_manager.create_job(tmp_path / "old2.pdf", 10.0)

    fresh_manager = JobManager(_clock=lambda: fresh_time)
    fresh_job = fresh_manager.create_job(tmp_path / "fresh.pdf", 10.0)

    manager = JobManager(_clock=lambda: fresh_time)
    manager._jobs = {
        expired_one.id: expired_one,
        expired_two.id: expired_two,
        fresh_job.id: fresh_job,
    }

    expired_ids = manager.list_expired(older_than_seconds=3600)

    assert sorted(expired_ids) == sorted([expired_one.id, expired_two.id])
