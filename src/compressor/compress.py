"""Page compression and binary search quality control utilities."""

from io import BytesIO

import numpy as np
from PIL import Image

from compressor.exceptions import CompressionError
from compressor.pdf_io import assemble_pdf_to_bytes
from compressor.schemas import CompressionConfig, CompressionStats, PageData, PageType

BYTES_PER_MEGABYTE = 1024 * 1024


def compress_page_to_jpeg(image: np.ndarray, quality: int) -> bytes:
    """Compress one RGB page image into JPEG bytes.

    Args:
        image: Page image as an RGB numpy array with dtype ``uint8``.
        quality: JPEG quality level to encode with.

    Returns:
        JPEG-encoded bytes for the page image.

    Raises:
        CompressionError: If the input image is invalid or cannot be encoded.
    """
    if image.ndim != 3 or image.shape[2] != 3:
        raise CompressionError("Expected an RGB image with shape (H, W, 3).")
    if image.dtype != np.uint8:
        raise CompressionError("Expected image dtype uint8.")

    try:
        pil_image = Image.fromarray(image, mode="RGB")
        buffer = BytesIO()
        pil_image.save(buffer, format="JPEG", quality=quality)
        return buffer.getvalue()
    except (OSError, ValueError, TypeError) as exc:
        raise CompressionError("Failed to compress page image to JPEG.") from exc


def binary_search_compress(
    pages: list[PageData],
    config: CompressionConfig,
) -> tuple[bytes, CompressionStats]:
    """Compress classified pages with binary search until the target size is met.

    Args:
        pages: Rendered page images paired with heuristic classifications.
        config: Compression configuration and search parameters.

    Returns:
        A tuple of compressed PDF bytes and compression summary statistics.

    Raises:
        CompressionError: If compression cannot produce a result below target.
    """
    if not pages:
        raise CompressionError("At least one page is required for compression.")

    initial_pdf_bytes = assemble_pdf_to_bytes(
        [
            compress_page_to_jpeg(
                page.image,
                _compute_quality(page, 1.0, config),
            )
            for page in pages
        ],
        dpi=config.render_dpi,
    )
    initial_size_mb = len(initial_pdf_bytes) / BYTES_PER_MEGABYTE

    if initial_size_mb <= config.target_size_mb:
        return initial_pdf_bytes, CompressionStats(
            iterations_used=1,
            final_multiplier=1.0,
            final_size_mb=initial_size_mb,
            converged=True,
        )

    minimum_pdf_bytes = assemble_pdf_to_bytes(
        [
            compress_page_to_jpeg(
                page.image,
                _compute_min_quality(page, config),
            )
            for page in pages
        ],
        dpi=config.render_dpi,
    )
    minimum_size_mb = len(minimum_pdf_bytes) / BYTES_PER_MEGABYTE

    if minimum_size_mb > config.target_size_mb:
        raise CompressionError(
            "Target "
            f"{config.target_size_mb:g} MB is unreachable. Minimum size for this PDF "
            f"is {minimum_size_mb:.2f} MB at lowest quality. Try a larger target."
        )

    lo = 0.0
    hi = 1.0
    best_result: tuple[bytes, CompressionStats] | None = (
        minimum_pdf_bytes,
        CompressionStats(
            iterations_used=0,
            final_multiplier=0.0,
            final_size_mb=minimum_size_mb,
            converged=False,
        ),
    )
    current_result: tuple[bytes, CompressionStats] | None = None
    converged = False

    for iteration in range(config.max_iterations):
        multiplier = (lo + hi) / 2
        jpeg_images = [
            compress_page_to_jpeg(
                page.image,
                _compute_quality(page, multiplier, config),
            )
            for page in pages
        ]
        pdf_bytes = assemble_pdf_to_bytes(jpeg_images, dpi=config.render_dpi)
        size_mb = len(pdf_bytes) / BYTES_PER_MEGABYTE

        if size_mb > config.target_size_mb:
            hi = multiplier
            continue

        if size_mb < config.target_size_mb - config.tolerance_mb:
            lo = multiplier
            best_result = (
                pdf_bytes,
                CompressionStats(
                    iterations_used=iteration + 1,
                    final_multiplier=multiplier,
                    final_size_mb=size_mb,
                    converged=False,
                ),
            )
            continue

        converged = True
        current_result = (
            pdf_bytes,
            CompressionStats(
                iterations_used=iteration + 1,
                final_multiplier=multiplier,
                final_size_mb=size_mb,
                converged=True,
            ),
        )
        break

    if converged and current_result is not None:
        return current_result

    if best_result is not None:
        return best_result

    raise CompressionError("Failed to converge below target size")


def _compute_quality(
    page: PageData,
    multiplier: float,
    config: CompressionConfig,
) -> int:
    """Compute the JPEG quality for one page given a multiplier."""
    if page.classification.page_type == PageType.HERO:
        base_quality = config.hero_base_quality
        min_quality = config.hero_min_quality
    else:
        base_quality = config.process_base_quality
        min_quality = config.process_min_quality

    return max(min_quality, int(base_quality * multiplier))


def _compute_min_quality(page: PageData, config: CompressionConfig) -> int:
    """Return the minimum allowed JPEG quality for one classified page."""
    if page.classification.page_type == PageType.HERO:
        return config.hero_min_quality

    return config.process_min_quality
