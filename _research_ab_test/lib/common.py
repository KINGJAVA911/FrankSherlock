"""Shared utilities for Frank Sherlock media cataloging."""

import json
import math
import mimetypes
import os
import statistics
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TEST_FILES = PROJECT_ROOT / "test_files"
RESULTS_DIR = PROJECT_ROOT / "results"
DOCS_DIR = PROJECT_ROOT / "docs"


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


def load_json(path: str | Path, default=None):
    """Load JSON file and return default if file is missing or invalid."""
    path = Path(path)
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


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


def extract_first_json_object(text: str) -> dict | None:
    """Extract first valid JSON object from free-form model text."""
    if not text:
        return None

    # Fast path: full JSON object
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    # Balanced-brace scan, then parse each candidate
    starts = [i for i, ch in enumerate(text) if ch == "{"]
    for start in starts:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
    return None


def load_benchmark_config() -> dict:
    """Load benchmark configuration from docs with sane defaults."""
    defaults = {
        "vision_models": ["qwen2.5vl:7b", "llava:13b", "qwen2.5vl:3b", "minicpm-v:8b"],
        "wd_tagger_models": [
            "SmilingWolf/wd-swinv2-tagger-v3",
            "SmilingWolf/wd-vit-tagger-v3",
            "SmilingWolf/wd-vit-large-tagger-v3",
        ],
        "whisper_models": ["base", "small", "medium"],
        "faster_whisper_models": ["small", "distil-large-v3"],
    }
    cfg = load_json(DOCS_DIR / "BENCHMARK_CONFIG.json", default={}) or {}
    merged = defaults.copy()
    for key, value in cfg.items():
        merged[key] = value
    return merged


def normalize_text(text: str) -> str:
    """Normalize text for rough OCR/ASR comparisons."""
    return " ".join((text or "").strip().lower().split())


def levenshtein_distance(a: str, b: str) -> int:
    """Compute Levenshtein edit distance with O(min(a,b)) memory."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    if len(a) < len(b):
        a, b = b, a

    previous = list(range(len(b) + 1))
    for i, ch_a in enumerate(a, start=1):
        current = [i]
        for j, ch_b in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (ch_a != ch_b)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def similarity_ratio(a: str, b: str) -> float:
    """Return normalized similarity in [0, 1] based on edit distance."""
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)
    if not a_norm and not b_norm:
        return 1.0
    max_len = max(len(a_norm), len(b_norm), 1)
    return round(1.0 - (levenshtein_distance(a_norm, b_norm) / max_len), 4)


def summarize_samples(samples: list[float]) -> dict:
    """Summarize repeated-trial values with mean/std/95% CI."""
    values = [float(x) for x in samples if x is not None]
    if not values:
        return {
            "n": 0,
            "mean": 0.0,
            "stddev": 0.0,
            "ci95_low": 0.0,
            "ci95_high": 0.0,
            "min": 0.0,
            "max": 0.0,
        }

    n = len(values)
    mean = statistics.fmean(values)
    if n > 1:
        stddev = statistics.stdev(values)
        margin = 1.96 * stddev / math.sqrt(n)
    else:
        stddev = 0.0
        margin = 0.0

    return {
        "n": n,
        "mean": round(mean, 4),
        "stddev": round(stddev, 4),
        "ci95_low": round(mean - margin, 4),
        "ci95_high": round(mean + margin, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }
