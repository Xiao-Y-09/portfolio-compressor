"""Command-line entry point for compressing a PDF to a target size."""

import argparse
import sys
from pathlib import Path

import fitz

from compressor.exceptions import ClassificationError, CompressionError, PDFParseError
from compressor.pipeline import compress_pdf


def main() -> None:
    """Parse CLI arguments and run the PDF compression pipeline."""
    parser = argparse.ArgumentParser(prog="compress")
    parser.add_argument("input_pdf", type=Path, help="Path to the input PDF file")
    parser.add_argument(
        "--target",
        "-t",
        type=float,
        required=True,
        help="Target output size in megabytes",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Optional output path for the compressed PDF",
    )
    args = parser.parse_args()

    input_path: Path = args.input_pdf
    output_path = args.output or input_path.with_name(f"{input_path.stem}_compressed.pdf")

    if input_path.suffix.lower() != ".pdf":
        print("Error: input file must have a .pdf extension", file=sys.stderr)
        raise SystemExit(1)

    if not input_path.exists() or not input_path.is_file():
        print("Error: input file not found", file=sys.stderr)
        raise SystemExit(1)

    if args.target <= 0:
        print("Error: target size must be greater than 0", file=sys.stderr)
        raise SystemExit(1)

    try:
        print("Rendering pages...", file=sys.stderr)
        page_count = _get_page_count(input_path)
        print(f"Classifying {page_count} pages...", file=sys.stderr)
        print(f"Compressing (target {args.target:g} MB)...", file=sys.stderr)
        stats = compress_pdf(
            input_path=input_path,
            output_path=output_path,
            target_size_mb=args.target,
        )
        final_size_mb = output_path.stat().st_size / (1024 * 1024)
        print(
            "Done. Final size: "
            f"{final_size_mb:.2f} MB "
            f"(iterations: {stats.iterations_used}, converged: {stats.converged})",
            file=sys.stderr,
        )
        raise SystemExit(0)
    except (
        PDFParseError,
        ClassificationError,
        CompressionError,
        ValueError,
        OSError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _get_page_count(input_path: Path) -> int:
    """Read the page count from a PDF for progress reporting."""
    document = fitz.open(input_path)
    try:
        return document.page_count
    finally:
        document.close()
