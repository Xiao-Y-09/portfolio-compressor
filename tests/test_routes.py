"""Tests for the FastAPI routes layer."""

from io import BytesIO
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from compressor.schemas import JobStatus, PageClassification, PageFeatures, PageType
from server import config as server_config
from server import main as server_main
from server import routes as server_routes
from server import tasks as server_tasks


def test_create_job_success(client: TestClient, tmp_storage: tuple[Path, Path]) -> None:
    """Uploading a valid PDF should create a job and persist the upload."""
    upload_dir, _ = tmp_storage
    pdf_bytes = _make_pdf_bytes()

    response = client.post(
        "/jobs",
        files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
        data={"target_size_mb": "5"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "received"
    assert (upload_dir / f"{payload['job_id']}.pdf").exists()


def test_create_job_wrong_type(client: TestClient) -> None:
    """Uploading a non-PDF should return 400."""
    response = client.post(
        "/jobs",
        files={"file": ("sample.txt", b"hello", "text/plain")},
        data={"target_size_mb": "5"},
    )

    assert response.status_code == 400


def test_create_job_invalid_target(client: TestClient) -> None:
    """Non-positive targets should return 400."""
    response = client.post(
        "/jobs",
        files={"file": ("sample.pdf", _make_pdf_bytes(), "application/pdf")},
        data={"target_size_mb": "-5"},
    )

    assert response.status_code == 400


def test_get_nonexistent_job(client: TestClient) -> None:
    """Unknown jobs should return 404."""
    response = client.get("/jobs/bogus")

    assert response.status_code == 404


def test_confirm_wrong_status(client: TestClient, tmp_path: Path) -> None:
    """Confirming a job not awaiting review should return 409."""
    job_manager = client.app.state.job_manager
    job = job_manager.create_job(tmp_path / "input.pdf", 5.0)

    response = client.post(f"/jobs/{job.id}/confirm", json={"classifications": []})

    assert response.status_code == 409


def test_confirm_mismatched_length(client: TestClient, tmp_path: Path) -> None:
    """Confirming with the wrong number of classifications should return 400."""
    job_manager = client.app.state.job_manager
    job = job_manager.create_job(tmp_path / "input.pdf", 5.0)
    classifications = [_classification(page_num=1)]
    job_manager.update_status(
        job.id,
        JobStatus.AWAITING_REVIEW,
        classifications=classifications,
        thumbnails=[tmp_path / "thumb_1.jpg"],
    )

    response = client.post(
        f"/jobs/{job.id}/confirm",
        json={"classifications": []},
    )

    assert response.status_code == 400


def test_download_not_ready(client: TestClient, tmp_path: Path) -> None:
    """Downloading before completion should return 409."""
    job_manager = client.app.state.job_manager
    job = job_manager.create_job(tmp_path / "input.pdf", 5.0)

    response = client.get(f"/jobs/{job.id}/download")

    assert response.status_code == 409


def test_end_to_end_flow(client: TestClient) -> None:
    """Upload, review, confirm, and download should complete end-to-end."""
    response = client.post(
        "/jobs",
        files={"file": ("sample.pdf", _make_pdf_bytes(page_count=5), "application/pdf")},
        data={"target_size_mb": "5"},
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    status_response = client.get(f"/jobs/{job_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "awaiting_review"
    assert len(status_payload["classifications"]) == 5

    confirm_response = client.post(
        f"/jobs/{job_id}/confirm",
        json={
            "classifications": [
                {
                    "page_num": item["page_num"],
                    "page_type": item["page_type"],
                }
                for item in status_payload["classifications"]
            ]
        },
    )
    assert confirm_response.status_code == 200

    complete_response = client.get(f"/jobs/{job_id}")
    assert complete_response.status_code == 200
    complete_payload = complete_response.json()
    assert complete_payload["status"] == "complete"

    download_response = client.get(f"/jobs/{job_id}/download")
    assert download_response.status_code == 200
    document = fitz.open(stream=download_response.content, filetype="pdf")
    try:
        assert document.page_count == 5
    finally:
        document.close()


def _classification(page_num: int) -> PageClassification:
    """Create a minimal page classification fixture."""
    return PageClassification(
        page_num=page_num,
        page_type=PageType.HERO,
        confidence=0.9,
        features=PageFeatures(
            color_entropy=1.0,
            edge_density=0.2,
            image_area_ratio=0.8,
            text_area_ratio=0.0,
        ),
    )


def _make_pdf_bytes(page_count: int = 3) -> bytes:
    """Create a synthetic PDF payload for route tests."""
    document = fitz.open()
    colors = [
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.5, 0.0),
        (0.4, 0.0, 0.8),
    ]

    for index in range(page_count):
        page = document.new_page(width=180, height=240)
        color = colors[index % len(colors)]
        page.draw_rect(page.rect, color=color, fill=color)
        page.insert_text((30, 120), f"Route Page {index + 1}", fontsize=18, color=(1, 1, 1))

    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


@pytest.fixture
def tmp_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    """Redirect upload and output directories into the pytest temp tree."""
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
