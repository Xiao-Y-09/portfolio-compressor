"""Tests for PDF rendering and assembly helpers."""

from io import BytesIO
from pathlib import Path

import fitz
import numpy as np
import pytest
from PIL import Image

from compressor.exceptions import PDFParseError
from compressor.pdf_io import assemble_pdf_from_images, render_pdf_pages


@pytest.fixture
def synthetic_pdf_path(tmp_path: Path) -> Path:
    """Create a three-page synthetic PDF with solid color backgrounds."""
    pdf_path = tmp_path / "synthetic.pdf"
    document = fitz.open()

    colors = [
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    ]

    for color in colors:
        page = document.new_page(width=120, height=120)
        page.draw_rect(page.rect, color=color, fill=color)

    document.save(pdf_path)
    document.close()
    return pdf_path


def test_render_pdf_pages(synthetic_pdf_path: Path) -> None:
    """Rendered PDF pages should have RGB arrays with distinct colors."""
    pages = render_pdf_pages(synthetic_pdf_path)

    assert len(pages) == 3
    for page in pages:
        assert isinstance(page, np.ndarray)
        assert page.ndim == 3
        assert page.shape[2] == 3
        assert page.dtype == np.uint8

    page_channel_means = [page.mean(axis=(0, 1)) for page in pages]
    assert np.linalg.norm(page_channel_means[0] - page_channel_means[1]) > 10
    assert np.linalg.norm(page_channel_means[1] - page_channel_means[2]) > 10


def test_assemble_pdf_from_images(tmp_path: Path) -> None:
    """JPEG bytes should be assembled into a PDF with matching page count."""
    image_bytes_list: list[bytes] = []

    for color in [(255, 0, 0), (0, 255, 0)]:
        image = Image.new("RGB", (80, 60), color=color)
        buffer = BytesIO()
        image.save(buffer, format="JPEG")
        image_bytes_list.append(buffer.getvalue())

    output_path = tmp_path / "assembled.pdf"
    assemble_pdf_from_images(image_bytes_list, output_path)

    assert output_path.exists()

    document = fitz.open(output_path)
    try:
        assert document.page_count == 2
    finally:
        document.close()


def test_render_nonexistent_file(tmp_path: Path) -> None:
    """Missing PDF input should raise a PDFParseError."""
    missing_path = tmp_path / "missing.pdf"

    with pytest.raises(PDFParseError):
        render_pdf_pages(missing_path)


def test_render_corrupt_file(tmp_path: Path) -> None:
    """Corrupt PDF input should raise a PDFParseError."""
    corrupt_path = tmp_path / "corrupt.pdf"
    corrupt_path.write_bytes(b"not-a-real-pdf")

    with pytest.raises(PDFParseError):
        render_pdf_pages(corrupt_path)
