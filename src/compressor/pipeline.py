"""Pipeline orchestration for PDF rendering, classification, and compression."""

from pathlib import Path

from compressor.classifier import classify_pages
from compressor.compress import binary_search_compress
from compressor.pdf_io import render_pdf_pages
from compressor.schemas import (
    CompressionConfig,
    CompressionStats,
    PageClassification,
    PageData,
)


def compress_pdf(
    input_path: Path,
    output_path: Path,
    target_size_mb: float,
    user_classifications: list[PageClassification] | None = None,
    config: CompressionConfig | None = None,
) -> CompressionStats:
    """Run the full PDF compression pipeline from input PDF to output PDF.

    Args:
        input_path: Path to the source PDF file.
        output_path: Path where the compressed PDF will be written.
        target_size_mb: Desired maximum output size in megabytes.
        user_classifications: Optional per-page classifications supplied by the caller.
        config: Optional compression configuration override.

    Returns:
        Compression statistics for the completed pipeline run.

    Raises:
        ValueError: If the provided inputs are inconsistent.
        PDFParseError: If the input PDF cannot be rendered.
        ClassificationError: If page classification fails.
        CompressionError: If compression fails to produce a valid result.
        OSError: If writing the output PDF fails.
    """
    if config is None:
        effective_config = CompressionConfig(target_size_mb=target_size_mb)
    else:
        if target_size_mb != config.target_size_mb:
            raise ValueError("target_size_mb must match config.target_size_mb")
        effective_config = config

    images = render_pdf_pages(input_path, dpi=effective_config.render_dpi)

    if user_classifications is not None:
        if len(user_classifications) != len(images):
            raise ValueError(
                "user_classifications length must match rendered page count"
            )
        classifications = user_classifications
    else:
        classifications = classify_pages(images)

    pages = [
        PageData(image=image, classification=classification)
        for image, classification in zip(images, classifications, strict=True)
    ]

    pdf_bytes, stats = binary_search_compress(pages, effective_config)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)
    return stats
