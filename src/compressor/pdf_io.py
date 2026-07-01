"""PDF input/output helpers for rendering pages and assembling compressed PDFs."""

from pathlib import Path

import fitz
import numpy as np

from compressor.exceptions import PDFParseError


def render_pdf_pages(pdf_path: Path, dpi: int = 200) -> list[np.ndarray]:
    """Render a PDF into a list of RGB page images.

    Args:
        pdf_path: Path to the source PDF file.
        dpi: Rendering resolution in dots per inch.

    Returns:
        A list of RGB numpy arrays with shape ``(H, W, 3)`` and dtype
        ``uint8``.

    Raises:
        PDFParseError: If the PDF cannot be opened or rendered.
    """
    try:
        document = fitz.open(pdf_path)
    except (RuntimeError, ValueError, TypeError, FileNotFoundError) as exc:
        raise PDFParseError(f"Failed to open PDF: {pdf_path}") from exc

    scale = dpi / 72
    matrix = fitz.Matrix(scale, scale)
    pages: list[np.ndarray] = []

    try:
        for page in document:
            pixmap = page.get_pixmap(
                matrix=matrix,
                colorspace=fitz.csRGB,
                alpha=False,
            )
            page_array = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height,
                pixmap.width,
                pixmap.n,
            )
            pages.append(page_array.copy())
    except (RuntimeError, ValueError, TypeError) as exc:
        raise PDFParseError(f"Failed to render PDF pages: {pdf_path}") from exc
    finally:
        document.close()

    return pages


def _build_pdf_document(images: list[bytes], dpi: int = 200) -> fitz.Document:
    """Build a PDF document from JPEG image bytes.

    Args:
        images: JPEG-encoded image bytes in page order.
        dpi: Source JPEG resolution used to map pixels to PDF points.

    Returns:
        A PyMuPDF document containing one page per JPEG image.

    Raises:
        PDFParseError: If an image cannot be read or inserted into the PDF.
    """
    document = fitz.open()

    try:
        for image_bytes in images:
            try:
                image_document = fitz.open(stream=image_bytes, filetype="jpeg")
            except (RuntimeError, ValueError, TypeError) as exc:
                raise PDFParseError("Failed to open JPEG image bytes.") from exc

            try:
                image_page = image_document[0]
                pixel_width = int(image_page.rect.width)
                pixel_height = int(image_page.rect.height)
            finally:
                image_document.close()

            width_pt = pixel_width * 72 / dpi
            height_pt = pixel_height * 72 / dpi
            new_page = document.new_page(width=width_pt, height=height_pt)
            new_page.insert_image(new_page.rect, stream=image_bytes)
    except PDFParseError:
        document.close()
        raise
    except (RuntimeError, ValueError, TypeError) as exc:
        document.close()
        raise PDFParseError("Failed to build PDF from JPEG images.") from exc

    return document


def assemble_pdf_to_bytes(images: list[bytes], dpi: int = 200) -> bytes:
    """Assemble JPEG image bytes into PDF bytes.

    Args:
        images: JPEG-encoded image bytes in page order.
        dpi: Source JPEG resolution used to map pixels to PDF points.

    Returns:
        PDF bytes containing one page per JPEG image.

    Raises:
        PDFParseError: If the PDF cannot be assembled.
    """
    document = _build_pdf_document(images, dpi=dpi)

    try:
        return document.tobytes()
    except (RuntimeError, ValueError, TypeError) as exc:
        raise PDFParseError("Failed to serialize assembled PDF to bytes.") from exc
    finally:
        document.close()


def assemble_pdf_from_images(
    images: list[bytes],
    output_path: Path,
    dpi: int = 200,
) -> None:
    """Assemble a PDF from JPEG image bytes.

    Args:
        images: JPEG-encoded image bytes in page order.
        output_path: Destination path for the assembled PDF.
        dpi: Source JPEG resolution used to map pixels to PDF points.

    Returns:
        None.

    Raises:
        PDFParseError: If an image cannot be read or the PDF cannot be saved.
    """
    document = _build_pdf_document(images, dpi=dpi)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document.save(output_path)
    except (RuntimeError, ValueError, TypeError, OSError) as exc:
        raise PDFParseError(f"Failed to assemble PDF: {output_path}") from exc
    finally:
        document.close()
