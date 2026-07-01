"""Tests for upload rate limiting on the FastAPI routes layer."""

from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from server import config as server_config
from server import main as server_main
from server import routes as server_routes
from server import tasks as server_tasks
from server.ratelimit import limiter


@pytest.fixture(autouse=True)
def reset_limiter() -> None:
    """Reset in-memory rate-limit state between tests."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def tmp_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    """Redirect upload and output directories into a test-local temp tree."""
    upload_dir = tmp_path / "uploads"
    output_dir = tmp_path / "outputs"

    monkeypatch.setattr(server_config, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(server_config, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(server_routes, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(server_routes, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(server_tasks, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(server_tasks, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(server_main, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(server_main, "OUTPUT_DIR", output_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir, output_dir


@pytest.fixture
def client(tmp_storage: tuple[Path, Path]) -> TestClient:
    """Create a TestClient with isolated storage directories."""
    with TestClient(server_main.app) as test_client:
        yield test_client


def test_ratelimit_allows_under_threshold(client: TestClient) -> None:
    """Five uploads from one client IP should stay within the hourly limit."""
    for _ in range(5):
        response = client.post(
            "/jobs",
            files={"file": ("sample.pdf", _make_pdf_bytes(), "application/pdf")},
            data={"target_size_mb": "5"},
        )
        assert response.status_code == 200


def test_ratelimit_blocks_over_threshold(client: TestClient) -> None:
    """The sixth upload from one client IP should be rejected with 429."""
    for _ in range(5):
        response = client.post(
            "/jobs",
            files={"file": ("sample.pdf", _make_pdf_bytes(), "application/pdf")},
            data={"target_size_mb": "5"},
        )
        assert response.status_code == 200

    blocked_response = client.post(
        "/jobs",
        files={"file": ("sample.pdf", _make_pdf_bytes(), "application/pdf")},
        data={"target_size_mb": "5"},
    )

    assert blocked_response.status_code == 429
    payload = blocked_response.json()
    assert "detail" in payload or "error" in payload


def test_ratelimit_isolated_from_other_endpoints(client: TestClient) -> None:
    """Non-limited endpoints should remain available regardless of upload usage."""
    for _ in range(3):
        response = client.post(
            "/jobs",
            files={"file": ("sample.pdf", _make_pdf_bytes(), "application/pdf")},
            data={"target_size_mb": "5"},
        )
        assert response.status_code == 200

    for _ in range(100):
        response = client.get("/")
        assert response.status_code == 200


def _make_pdf_bytes() -> bytes:
    """Create a small valid PDF payload for upload tests."""
    document = fitz.open()
    page = document.new_page(width=180, height=240)
    color = (0.2, 0.5, 0.8)
    page.draw_rect(page.rect, color=color, fill=color)
    page.insert_text((24, 120), "Rate limit test", fontsize=18, color=(1, 1, 1))
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes
