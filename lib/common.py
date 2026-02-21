"""Shared utilities for Frank Sherlock media cataloging."""

import json
import mimetypes
import os
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TEST_FILES = PROJECT_ROOT / "test_files"
RESULTS_DIR = PROJECT_ROOT / "results"


def detect_media_type(filepath: str | Path) -> str:
    """Detect media type from file extension and MIME type.

    Returns one of: 'image', 'audio', 'video', 'document', 'unknown'
    """
    filepath = Path(filepath)
    ext = filepath.suffix.lower()

    ext_map = {
        # Images
        ".jpg": "image", ".jpeg": "image", ".png": "image",
        ".gif": "image", ".bmp": "image", ".webp": "image",
        ".tiff": "image", ".tif": "image",
        # Audio
        ".mp3": "audio", ".mp2": "audio", ".mpa": "audio",
        ".wav": "audio", ".flac": "audio", ".ogg": "audio",
        ".m4a": "audio", ".aac": "audio", ".wma": "audio",
        # Video
        ".mp4": "video", ".avi": "video", ".mov": "video",
        ".mkv": "video", ".mpg": "video", ".mpeg": "video",
        ".wmv": "video", ".flv": "video", ".webm": "video",
        # Documents
        ".pdf": "document", ".docx": "document", ".xlsx": "document",
        ".pptx": "document", ".doc": "document", ".xls": "document",
        ".txt": "document", ".nfo": "document",
    }

    if ext in ext_map:
        return ext_map[ext]

    mime, _ = mimetypes.guess_type(str(filepath))
    if mime:
        category = mime.split("/")[0]
        if category in ("image", "audio", "video"):
            return category
        if mime == "application/pdf":
            return "document"

    # Fallback: use `file` command for extensionless files
    if not ext:
        try:
            result = subprocess.run(
                ["file", "--brief", "--mime-type", str(filepath)],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                detected_mime = result.stdout.strip()
                cat = detected_mime.split("/")[0]
                if cat in ("image", "audio", "video"):
                    return cat
                if "pdf" in detected_mime or "document" in detected_mime:
                    return "document"
        except Exception:
            pass

    return "unknown"


class TimedOperation:
    """Context manager for timing operations."""

    def __init__(self, name: str):
        self.name = name
        self.elapsed = 0.0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed = time.perf_counter() - self.start
        print(f"  [{self.name}] {self.elapsed:.2f}s")


def save_result(data: dict | list, output_path: str | Path):
    """Save result data as JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Saved: {output_path}")


def run_command(cmd: list[str], timeout: int = 300) -> dict:
    """Run an external command and return stdout/stderr/returncode."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Timeout after {timeout}s", "returncode": -1}
    except FileNotFoundError:
        return {"stdout": "", "stderr": f"Command not found: {cmd[0]}", "returncode": -1}


def collect_test_files(media_type: str | None = None) -> list[Path]:
    """Collect all test files, optionally filtered by media type."""
    files = []
    for root, _, filenames in os.walk(TEST_FILES):
        for fname in sorted(filenames):
            fpath = Path(root) / fname
            if fpath.name.startswith(".") or "@eaDir" in str(fpath):
                continue
            if media_type is None or detect_media_type(fpath) == media_type:
                files.append(fpath)
    return sorted(files)


def relative_path(filepath: Path) -> str:
    """Return path relative to project root for display."""
    try:
        return str(filepath.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(filepath)
