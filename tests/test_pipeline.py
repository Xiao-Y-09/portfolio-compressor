"""Integration tests for the end-to-end PDF compression pipeline."""

from pathlib import Path

import fitz
import pytest

from compressor.classifier import classify_pages
from compressor.pdf_io import render_pdf_pages
from compressor.pipeline import compress_pdf
from compressor.schemas import (
    CompressionConfig,
    CompressionStats,
    PageClassification,
)


def test_compress_pdf_end_to_end(tmp_path: Path) -> None:
    """The pipeline should render, classify, compress, and write a PDF."""
    input_path = _create_synthetic_pdf(tmp_path / "input.pdf")
    output_path = tmp_path / "output.pdf"

    stats = compress_pdf(
        input_path=input_path,
        output_path=output_path,
        target_size_mb=5.0,
    )

    assert output_path.exists()
    assert isinstance(stats, CompressionStats)

    document = fitz.open(output_path)
    try:
        assert document.page_count == 5
    finally:
        document.close()


def test_compress_pdf_with_user_classifications(tmp_path: Path) -> None:
    """User classifications should influence the compression result."""
    input_path = _create_synthetic_pdf(tmp_path / "input.pdf")
    images = render_pdf_pages(input_path)
    auto_classifications = classify_pages(images)

    hero_classifications = [
        PageClassification(
            page_num=item.page_num,
            page_type=item.page_type.HERO,
            confidence=item.confidence,
            features=item.features,
            user_override=True,
        )
        for item in auto_classifications
    ]
    process_classifications = [
        PageClassification(
            page_num=item.page_num,
            page_type=item.page_type.PROCESS,
            confidence=item.confidence,
            features=item.features,
            user_override=True,
        )
        for item in auto_classifications
    ]

    hero_output_path = tmp_path / "hero_output.pdf"
    process_output_path = tmp_path / "process_output.pdf"

    # Use a very loose target so the pipeline returns the full-quality result,
    # then allow a 5% reversal window because tiny PDFs can vary slightly.
    compress_pdf(
        input_path=input_path,
        output_path=hero_output_path,
        target_size_mb=100.0,
        user_classifications=hero_classifications,
        config=CompressionConfig(target_size_mb=100.0),
    )
    compress_pdf(
        input_path=input_path,
        output_path=process_output_path,
        target_size_mb=100.0,
        user_classifications=process_classifications,
        config=CompressionConfig(target_size_mb=100.0),
    )

    hero_size = hero_output_path.stat().st_size
    process_size = process_output_path.stat().st_size
    assert hero_size >= process_size * 0.95


def test_compress_pdf_mismatched_classifications(tmp_path: Path) -> None:
    """Classification count must match the rendered page count."""
    input_path = _create_synthetic_pdf(tmp_path / "input.pdf")
    images = render_pdf_pages(input_path)
    classifications = classify_pages(images[:3])
    output_path = tmp_path / "output.pdf"

    with pytest.raises(ValueError):
        compress_pdf(
            input_path=input_path,
            output_path=output_path,
            target_size_mb=5.0,
            user_classifications=classifications,
        )


def test_compress_pdf_config_target_mismatch(tmp_path: Path) -> None:
    """An explicit config and target size must agree."""
    input_path = _create_synthetic_pdf(tmp_path / "input.pdf")
    output_path = tmp_path / "output.pdf"

    with pytest.raises(ValueError):
        compress_pdf(
            input_path=input_path,
            output_path=output_path,
            target_size_mb=5.0,
            config=CompressionConfig(target_size_mb=3.0),
        )


def test_compress_pdf_write_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The pipeline should not swallow write errors from Path.write_bytes."""
    input_path = _create_synthetic_pdf(tmp_path / "input.pdf")
    output_path = tmp_path / "output.pdf"

    def raise_write_error(self: Path, data: bytes) -> int:
        raise OSError("write failed")

    monkeypatch.setattr(Path, "write_bytes", raise_write_error)

    with pytest.raises(OSError, match="write failed"):
        compress_pdf(
            input_path=input_path,
            output_path=output_path,
            target_size_mb=5.0,
        )


def _create_synthetic_pdf(output_path: Path) -> Path:
    """Create a five-page synthetic PDF for pipeline integration tests."""
    document = fitz.open()
    colors = [
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.5, 0.0),
        (0.4, 0.0, 0.8),
    ]

    for index, color in enumerate(colors):
        page = document.new_page(width=180, height=240)
        page.draw_rect(page.rect, color=color, fill=color)
        page.draw_rect(fitz.Rect(20, 20, 140, 120), color=(1, 1, 1), fill=(1, 1, 1))
        page.insert_text((30, 150), f"Page {index + 1}", fontsize=18, color=(0, 0, 0))

    document.save(output_path)
    document.close()
    return output_path
