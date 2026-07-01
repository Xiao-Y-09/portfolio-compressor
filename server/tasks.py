"""Background task helpers for classification and compression phases."""

from pathlib import Path

from PIL import Image

from compressor.classifier import classify_pages
from compressor.exceptions import ClassificationError, CompressionError, PDFParseError
from compressor.pdf_io import render_pdf_pages
from compressor.pipeline import compress_pdf
from compressor.schemas import JobStatus
from server.config import OUTPUT_DIR, UPLOAD_DIR
from server.jobs import JobManager


def run_classification_phase(job_manager: JobManager, job_id: str) -> None:
    """Render pages, classify them, and generate thumbnails for review."""
    try:
        job_manager.update_status(job_id, JobStatus.CLASSIFYING)
        job = job_manager.get_job(job_id)
        if job is None:
            return

        images = render_pdf_pages(job.input_path)
        classifications = classify_pages(images)
        thumbnails = [
            _save_thumbnail(job_id, page_num, image)
            for page_num, image in enumerate(images, start=1)
        ]
        job_manager.update_status(
            job_id,
            JobStatus.AWAITING_REVIEW,
            classifications=classifications,
            thumbnails=thumbnails,
        )
    except (PDFParseError, ClassificationError, OSError, ValueError) as exc:
        _mark_job_failed(job_manager, job_id, str(exc))


def run_compression_phase(job_manager: JobManager, job_id: str) -> None:
    """Compress a reviewed job and persist the output PDF path."""
    try:
        job_manager.update_status(job_id, JobStatus.COMPRESSING)
        job = job_manager.get_job(job_id)
        if job is None:
            return

        output_path = OUTPUT_DIR / f"{job_id}.pdf"
        compress_pdf(
            input_path=job.input_path,
            output_path=output_path,
            target_size_mb=job.target_size_mb,
            user_classifications=job.classifications,
        )
        job_manager.update_status(
            job_id,
            JobStatus.COMPLETE,
            output_path=output_path,
        )
    except (
        PDFParseError,
        ClassificationError,
        CompressionError,
        ValueError,
        OSError,
    ) as exc:
        _mark_job_failed(job_manager, job_id, str(exc))


def _save_thumbnail(job_id: str, page_num: int, image) -> Path:
    """Save a ~200px-wide JPEG thumbnail for one rendered page."""
    thumbnail_path = UPLOAD_DIR / f"{job_id}_thumb_{page_num}.jpg"
    pil_image = Image.fromarray(image, mode="RGB")
    if pil_image.width > 200:
        height = max(1, int(pil_image.height * (200 / pil_image.width)))
        pil_image = pil_image.resize((200, height))
    pil_image.save(thumbnail_path, format="JPEG", quality=75)
    return thumbnail_path


def _mark_job_failed(job_manager: JobManager, job_id: str, message: str) -> None:
    """Best-effort transition of a job into failed state."""
    try:
        job_manager.update_status(
            job_id,
            JobStatus.FAILED,
            error_message=message,
        )
    except KeyError:
        return
