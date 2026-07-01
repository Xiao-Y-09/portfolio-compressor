"""Tests for the command-line entry point."""

import subprocess
import sys
from pathlib import Path

import fitz


def test_cli_help() -> None:
    """The CLI help output should describe target and output arguments."""
    result = subprocess.run(
        [sys.executable, "-m", "compressor", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "target" in result.stdout.lower()
    assert "output" in result.stdout.lower()


def test_cli_success(tmp_path: Path) -> None:
    """The CLI should compress a synthetic PDF and write the default output."""
    input_path = _create_synthetic_pdf(tmp_path / "sample.pdf")
    expected_output = tmp_path / "sample_compressed.pdf"

    result = subprocess.run(
        [sys.executable, "-m", "compressor", str(input_path), "--target", "5"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert expected_output.exists()


def test_cli_missing_input(tmp_path: Path) -> None:
    """Missing input files should return exit code 1."""
    missing_path = tmp_path / "missing.pdf"

    result = subprocess.run(
        [sys.executable, "-m", "compressor", str(missing_path), "--target", "5"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "not found" in result.stderr.lower()


def test_cli_invalid_target(tmp_path: Path) -> None:
    """Non-positive target sizes should return exit code 1."""
    input_path = _create_synthetic_pdf(tmp_path / "sample.pdf")

    result = subprocess.run(
        [sys.executable, "-m", "compressor", str(input_path), "--target", "-5"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1


def test_cli_wrong_extension(tmp_path: Path) -> None:
    """Non-PDF inputs should return exit code 1 with a helpful error."""
    input_path = tmp_path / "sample.txt"
    input_path.write_text("not a pdf", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "compressor", str(input_path), "--target", "5"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert ".pdf" in result.stderr.lower()


def _create_synthetic_pdf(output_path: Path) -> Path:
    """Create a small synthetic PDF for CLI tests."""
    document = fitz.open()

    for index, color in enumerate(
        [
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ]
    ):
        page = document.new_page(width=180, height=240)
        page.draw_rect(page.rect, color=color, fill=color)
        page.insert_text((30, 120), f"CLI Page {index + 1}", fontsize=18, color=(1, 1, 1))

    document.save(output_path)
    document.close()
    return output_path
