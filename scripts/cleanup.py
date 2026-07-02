"""Delete stale temporary upload and output files from the workspace."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

STALE_AGE_SECONDS = 60 * 60
TARGET_DIRECTORIES = (Path("data/uploads"), Path("data/outputs"))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the cleanup script."""
    parser = argparse.ArgumentParser(description="Clean stale temporary PDF files.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which files would be deleted without removing them.",
    )
    return parser.parse_args()


def main() -> None:
    """Scan target directories, delete stale files, and print a summary."""
    args = parse_args()
    now = time.time()
    deleted_count = 0
    freed_bytes = 0

    for directory in TARGET_DIRECTORIES:
        for path in _iter_candidate_files(directory):
            try:
                stat = path.stat()
            except OSError:
                continue

            age_seconds = now - stat.st_mtime
            if age_seconds <= STALE_AGE_SECONDS:
                continue

            deleted_count += 1
            freed_bytes += stat.st_size

            if args.dry_run:
                print(f"Would delete: {path} ({stat.st_size} bytes)")
                continue

            try:
                path.unlink()
                print(f"Deleted: {path} ({stat.st_size} bytes)")
            except OSError as exc:
                print(f"Failed to delete {path}: {exc}")

    mode = "Dry run" if args.dry_run else "Cleanup complete"
    print(
        f"{mode}: removed {deleted_count} files, freed {freed_bytes} bytes "
        f"({freed_bytes / (1024 * 1024):.2f} MB)."
    )


def _iter_candidate_files(directory: Path) -> list[Path]:
    """Return non-.gitkeep files under one cleanup target directory."""
    if not directory.exists():
        return []
    return [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    ]


if __name__ == "__main__":
    main()
