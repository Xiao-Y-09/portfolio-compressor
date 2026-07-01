"""Tests for JPEG compression and binary-search PDF compression."""

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from compressor.classifier import classify_pages
from compressor.compress import binary_search_compress, compress_page_to_jpeg
from compressor.exceptions import CompressionError
from compressor.pdf_io import assemble_pdf_to_bytes
from compressor.schemas import CompressionConfig, PageData

BYTES_PER_MEGABYTE = 1024 * 1024


def test_compress_page_to_jpeg_higher_quality_larger_bytes() -> None:
    """Higher-quality JPEG output should usually be larger on the same image."""
    rng = np.random.default_rng(7)
    image = rng.integers(0, 256, size=(320, 240, 3), dtype=np.uint8)

    low_quality = compress_page_to_jpeg(image, quality=30)
    high_quality = compress_page_to_jpeg(image, quality=90)

    assert len(high_quality) >= len(low_quality) * 0.9


def test_compress_page_to_jpeg_valid_jpeg() -> None:
    """JPEG bytes should be decodable and preserve image dimensions."""
    image = np.full((120, 80, 3), (20, 100, 220), dtype=np.uint8)

    jpeg_bytes = compress_page_to_jpeg(image, quality=75)
    decoded = Image.open(BytesIO(jpeg_bytes))

    assert decoded.size == (80, 120)


def test_binary_search_compress_converges() -> None:
    """Binary search should converge for a reachable target size."""
    pages = _make_synthetic_pages()
    full_quality_bytes = assemble_pdf_to_bytes(
        [
            compress_page_to_jpeg(
                page.image,
                90 if page.classification.page_type == page.classification.page_type.HERO else 55,
            )
            for page in pages
        ],
        dpi=200,
    )
    lower_quality_bytes = assemble_pdf_to_bytes(
        [
            compress_page_to_jpeg(
                page.image,
                60 if page.classification.page_type == page.classification.page_type.HERO else 27,
            )
            for page in pages
        ],
        dpi=200,
    )
    full_size_mb = len(full_quality_bytes) / BYTES_PER_MEGABYTE
    lower_size_mb = len(lower_quality_bytes) / BYTES_PER_MEGABYTE
    target_size_mb = (full_size_mb + lower_size_mb) / 2
    tolerance_mb = max((full_size_mb - lower_size_mb) / 3, 0.02)

    pdf_bytes, stats = binary_search_compress(
        pages,
        CompressionConfig(
            target_size_mb=target_size_mb,
            tolerance_mb=tolerance_mb,
            max_iterations=8,
        ),
    )

    assert stats.converged is True
    assert target_size_mb - tolerance_mb <= stats.final_size_mb <= target_size_mb
    assert len(pdf_bytes) > 0


def test_binary_search_target_impossible() -> None:
    """An impossibly small target should fail when no result fits below target."""
    pages = _make_synthetic_pages()

    with pytest.raises(CompressionError, match="unreachable|minimum size") as exc_info:
        binary_search_compress(
            pages,
            CompressionConfig(
                target_size_mb=0.01,
                tolerance_mb=0.001,
                max_iterations=4,
            ),
        )

    message = str(exc_info.value).lower()
    assert "unreachable" in message
    assert "minimum size" in message


def test_binary_search_target_already_met() -> None:
    """A target above the original output size should return after the pre-check."""
    pages = _make_synthetic_pages()

    _, stats = binary_search_compress(
        pages,
        CompressionConfig(
            target_size_mb=100.0,
            tolerance_mb=0.5,
            max_iterations=8,
        ),
    )

    assert stats.iterations_used == 1
    assert stats.final_multiplier == 1.0
    assert stats.converged is True


def _make_synthetic_pages() -> list[PageData]:
    """Create synthetic hero/process pages for compression tests."""
    images: list[np.ndarray] = []
    rng = np.random.default_rng(11)

    for _ in range(5):
        images.append(rng.integers(0, 256, size=(240, 180, 3), dtype=np.uint8))

    for index in range(5):
        page = np.full((240, 180, 3), 255, dtype=np.uint8)
        page[20 + index * 4 : 120 + index * 4, 25:155] = (20, 120, 220)
        images.append(page)

    classifications = classify_pages(images)
    return [
        PageData(image=image, classification=classification)
        for image, classification in zip(images, classifications, strict=True)
    ]
