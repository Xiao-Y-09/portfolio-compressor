"""HTTP routes for upload, review, thumbnail, and download flows."""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from compressor.schemas import JobStatus, PageClassification
from server.config import MAX_UPLOAD_SIZE_MB, OUTPUT_DIR, RATE_LIMIT_UPLOADS, UPLOAD_DIR
from server.dto import (
    ClassificationSelection,
    JobConfirmRequest,
    JobConfirmResponse,
    JobCreateResponse,
    JobStatusResponse,
    PageClassificationSummary,
)
from server.jobs import JobManager
from server.ratelimit import limiter
from server.tasks import run_classification_phase, run_compression_phase

router = APIRouter()
CHUNK_SIZE_BYTES = 1024 * 1024


@router.post("/jobs", response_model=JobCreateResponse)
@limiter.limit(RATE_LIMIT_UPLOADS)
def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_size_mb: float = Form(...),
) -> JobCreateResponse:
    """Upload a PDF and create a background classification job."""
    if target_size_mb <= 0:
        raise HTTPException(status_code=400, detail="target_size_mb must be greater than 0")

    filename = file.filename or ""
    if file.content_type != "application/pdf" and not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")

    job_manager = _get_job_manager(request)
    job_id = str(uuid4())
    upload_path = UPLOAD_DIR / f"{job_id}.pdf"
    _save_uploaded_file(file, upload_path)

    job = job_manager.create_job(
        input_path=upload_path,
        target_size_mb=target_size_mb,
        job_id=job_id,
    )
    background_tasks.add_task(run_classification_phase, job_manager, job.id)
    return JobCreateResponse(job_id=job.id, status=job.status)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, request: Request) -> JobStatusResponse:
    """Return the current state of a job and any review/download metadata."""
    job_manager = _get_job_manager(request)
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    response = JobStatusResponse(job_id=job.id, status=job.status)

    if job.status == JobStatus.AWAITING_REVIEW:
        response.classifications = [
            PageClassificationSummary(
                page_num=item.page_num,
                page_type=item.page_type,
                confidence=item.confidence,
            )
            for item in job.classifications
        ]
        response.thumbnails = [
            f"/jobs/{job.id}/thumb/{index}"
            for index in range(1, len(job.thumbnails) + 1)
        ]
    elif job.status == JobStatus.COMPLETE:
        response.download_url = f"/jobs/{job.id}/download"
        if job.output_path is not None and job.output_path.exists():
            response.final_size_mb = job.output_path.stat().st_size / (1024 * 1024)
    elif job.status == JobStatus.FAILED:
        response.error = job.error_message

    return response


@router.post("/jobs/{job_id}/confirm", response_model=JobConfirmResponse)
def confirm_job(
    job_id: str,
    payload: JobConfirmRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> JobConfirmResponse:
    """Accept reviewed classifications and start background compression."""
    job_manager = _get_job_manager(request)
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.AWAITING_REVIEW:
        raise HTTPException(status_code=409, detail="Job is not awaiting review")
    if len(payload.classifications) != len(job.classifications):
        raise HTTPException(status_code=400, detail="Classification count does not match page count")

    updated_classifications = _merge_user_classifications(
        job.classifications,
        payload.classifications,
    )
    job_manager.update_status(
        job_id,
        JobStatus.COMPRESSING,
        classifications=updated_classifications,
    )
    background_tasks.add_task(run_compression_phase, job_manager, job_id)
    return JobConfirmResponse(job_id=job_id, status=JobStatus.COMPRESSING)


@router.get("/jobs/{job_id}/thumb/{page_num}")
def get_thumbnail(job_id: str, page_num: int, request: Request) -> FileResponse:
    """Return one generated thumbnail image for review."""
    job_manager = _get_job_manager(request)
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if page_num < 1 or page_num > len(job.thumbnails):
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    thumbnail_path = job.thumbnails[page_num - 1]
    if not thumbnail_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(thumbnail_path, media_type="image/jpeg")


@router.get("/jobs/{job_id}/download")
def download_result(job_id: str, request: Request) -> FileResponse:
    """Return the compressed PDF once the job is complete."""
    job_manager = _get_job_manager(request)
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETE:
        raise HTTPException(status_code=409, detail="Job is not complete")
    if job.output_path is None or not job.output_path.exists():
        raise HTTPException(status_code=404, detail="Compressed PDF not found")

    return FileResponse(
        job.output_path,
        media_type="application/pdf",
        filename="compressed.pdf",
    )


def _get_job_manager(request: Request) -> JobManager:
    """Fetch the shared JobManager from app state."""
    return request.app.state.job_manager


def _save_uploaded_file(file: UploadFile, upload_path: Path) -> None:
    """Persist an uploaded file in chunks while enforcing size limits."""
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_bytes = 0

    try:
        with upload_path.open("wb") as buffer:
            while chunk := file.file.read(CHUNK_SIZE_BYTES):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(status_code=400, detail="File too large")
                buffer.write(chunk)
    except HTTPException:
        if upload_path.exists():
            upload_path.unlink()
        raise
    finally:
        file.file.close()


def _merge_user_classifications(
    existing: list[PageClassification],
    selections: list[ClassificationSelection],
) -> list[PageClassification]:
    """Apply user-selected page types onto stored page classifications."""
    existing_by_page = {item.page_num: item for item in existing}
    merged: list[PageClassification] = []

    for selection in selections:
        current = existing_by_page.get(selection.page_num)
        if current is None:
            raise HTTPException(status_code=400, detail="Unknown page number in classifications")
        merged.append(
            current.model_copy(
                update={
                    "page_type": selection.page_type,
                    "user_override": True,
                }
            )
        )

    if {item.page_num for item in merged} != {item.page_num for item in existing}:
        raise HTTPException(status_code=400, detail="Classification page numbers do not match job pages")

    return sorted(merged, key=lambda item: item.page_num)
