#!/usr/bin/env python3
"""Phase 5: Unified media catalog CLI — auto-detect, classify, and catalog all media files."""

import base64
import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, detect_media_type,
    relative_path, run_command, save_result, RESULTS_DIR,
)

OUTPUT_DIR = RESULTS_DIR
OLLAMA_URL = "http://localhost:11434/api/generate"
VISION_MODEL = "qwen2.5vl:7b"


def run_ocr(filepath: Path) -> dict | None:
    """Run best available OCR engine on an image. Returns extracted text or None."""
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        result = ocr.ocr(str(filepath), cls=True)
        if result and result[0]:
            lines = [det[1][0] for det in result[0] if det[1][1] >= 0.5]
            if lines:
                return {"engine": "paddleocr", "text": "\n".join(lines), "line_count": len(lines)}
    except ImportError:
        pass

    try:
        from PIL import Image as PILImage
        from surya.recognition import RecognitionPredictor
        from surya.detection import DetectionPredictor
        image = PILImage.open(filepath).convert("RGB")
        det = DetectionPredictor()
        rec = RecognitionPredictor()
        preds = rec([image], [["en"]], det)
        if preds and preds[0].text_lines:
            lines = [l.text for l in preds[0].text_lines
                     if (l.confidence if l.confidence is not None else 1.0) >= 0.5]
            if lines:
                return {"engine": "surya", "text": "\n".join(lines), "line_count": len(lines)}
    except ImportError:
        pass

    return None


def catalog_image(filepath: Path) -> dict:
    """Classify a single image using Ollama vision + OCR."""
    with open(filepath, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    prompt = (
        "Analyze this image and provide a JSON classification with: "
        '"title" (descriptive name), "description" (1-2 sentences), '
        '"type" (screenshot/anime/manga/photo/artwork/other), '
        '"anime_series" (name or null), "characters" (list), '
        '"tags" (list of descriptive tags), "language" (if text visible), '
        '"confidence" (0-1). Respond ONLY with valid JSON.'
    )

    payload = {
        "model": VISION_MODEL,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 300},
    }
    result = {}
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        json_match = re.search(r'\{[^}]*\}', raw, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = {"description": raw[:300]}
    except Exception as e:
        result = {"error": str(e)}

    # Run OCR for text extraction
    ocr_result = run_ocr(filepath)
    if ocr_result:
        result["ocr"] = ocr_result

    return result


def catalog_audio(filepath: Path) -> dict:
    """Catalog audio using fingerprint + basic metadata."""
    # Fingerprint
    result = run_command(["fpcalc", "-json", str(filepath)], timeout=60)
    fp_data = {}
    if result["returncode"] == 0:
        try:
            fp_data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            pass

    # ffprobe metadata
    probe = run_command([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(filepath),
    ])
    probe_data = {}
    if probe["returncode"] == 0:
        try:
            probe_data = json.loads(probe["stdout"])
        except json.JSONDecodeError:
            pass

    fmt = probe_data.get("format", {})
    tags = fmt.get("tags", {})

    return {
        "title": tags.get("title", filepath.stem),
        "description": f"Audio file: {fmt.get('format_long_name', 'unknown format')}",
        "type": "audio",
        "artist": tags.get("artist"),
        "album": tags.get("album"),
        "duration_seconds": float(fmt.get("duration", 0)),
        "tags": [fmt.get("format_name", ""), tags.get("genre", "")],
        "fingerprint_duration": fp_data.get("duration"),
        "confidence": 0.5,  # metadata-only baseline
    }


def catalog_video(filepath: Path) -> dict:
    """Catalog video using metadata + first keyframe classification."""
    # Get metadata
    probe = run_command([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(filepath),
    ])
    probe_data = {}
    if probe["returncode"] == 0:
        try:
            probe_data = json.loads(probe["stdout"])
        except json.JSONDecodeError:
            pass

    fmt = probe_data.get("format", {})
    streams = probe_data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})

    # Extract one keyframe for vision classification
    temp_frame = OUTPUT_DIR / "temp" / f"{filepath.stem}_catalog_frame.jpg"
    temp_frame.parent.mkdir(parents=True, exist_ok=True)
    frame_result = run_command([
        "ffmpeg", "-i", str(filepath), "-vf", "select='eq(n,30)'",
        "-frames:v", "1", "-q:v", "2", "-y", str(temp_frame),
    ], timeout=30)

    vision_info = {}
    if frame_result["returncode"] == 0 and temp_frame.exists():
        vision_info = catalog_image(temp_frame)

    # Parse filename hints
    name = filepath.stem
    hints = {}
    if re.search(r'\(op\d*\)', name, re.IGNORECASE):
        hints["likely_type"] = "anime opening"
    elif "trailer" in name.lower():
        hints["likely_type"] = "trailer"
    elif "clip" in name.lower():
        hints["likely_type"] = "clip"

    # Check for NFO
    nfo_files = list(filepath.parent.glob("*.nfo"))
    nfo_info = {}
    if nfo_files:
        try:
            text = nfo_files[0].read_text(errors="replace")
            imdb = re.search(r'http\S*imdb\S+', text)
            if imdb:
                nfo_info["imdb_url"] = imdb.group()
        except Exception:
            pass

    return {
        "title": vision_info.get("title", name),
        "description": vision_info.get("description", f"Video: {fmt.get('format_long_name', '')}"),
        "type": hints.get("likely_type", vision_info.get("type", "video")),
        "resolution": f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')}",
        "duration_seconds": float(fmt.get("duration", 0)),
        "video_codec": video_stream.get("codec_name", ""),
        "tags": vision_info.get("tags", []),
        "anime_series": vision_info.get("anime_series"),
        "imdb_url": nfo_info.get("imdb_url"),
        "confidence": vision_info.get("confidence", 0.3),
    }


def catalog_document(filepath: Path) -> dict:
    """Basic document cataloging from metadata."""
    result = run_command(["exiftool", "-json", str(filepath)])
    exif = {}
    if result["returncode"] == 0:
        try:
            data = json.loads(result["stdout"])
            exif = data[0] if data else {}
        except json.JSONDecodeError:
            pass

    return {
        "title": exif.get("ExifTool:Title", filepath.stem),
        "description": f"Document: {filepath.suffix.upper()} file",
        "type": "document",
        "format": filepath.suffix.lower(),
        "author": exif.get("ExifTool:Author") or exif.get("ExifTool:Creator"),
        "pages": exif.get("ExifTool:PageCount"),
        "tags": [filepath.suffix.lower()],
        "confidence": 0.7,
    }


def process_file(filepath: Path) -> dict:
    """Route a file to the appropriate cataloging pipeline."""
    media_type = detect_media_type(filepath)
    rel = relative_path(filepath)

    if filepath.stat().st_size == 0:
        return {
            "file": rel, "filename": filepath.name, "media_type": media_type,
            "file_size": 0, "error": "zero-byte file",
        }

    entry = {
        "file": rel,
        "filename": filepath.name,
        "media_type": media_type,
        "file_size": filepath.stat().st_size,
    }

    try:
        if media_type == "image":
            entry["classification"] = catalog_image(filepath)
        elif media_type == "audio":
            entry["classification"] = catalog_audio(filepath)
        elif media_type == "video":
            entry["classification"] = catalog_video(filepath)
        elif media_type == "document":
            entry["classification"] = catalog_document(filepath)
        else:
            entry["classification"] = {"type": "unknown", "confidence": 0}
    except Exception as e:
        entry["error"] = str(e)

    return entry


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Frank Sherlock Media Catalog")
    parser.add_argument("path", nargs="?", default="test_files",
                        help="File or directory to catalog")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"Error: {target} not found")
        sys.exit(1)

    print("=" * 60)
    print("Phase 5: Unified Media Catalog")
    print("=" * 60)

    if target.is_file():
        files = [target]
    else:
        files = collect_test_files()

    print(f"\nCataloging {len(files)} files...\n")

    catalog = []
    for filepath in files:
        print(f"  Processing: {relative_path(filepath)}...")
        with TimedOperation(f"catalog/{filepath.name}") as t:
            entry = process_file(filepath)
        entry["timing"] = {"catalog_s": round(t.elapsed, 4)}
        catalog.append(entry)

    # Timing summary
    times_by_type = {}
    for e in catalog:
        mt = e.get("media_type", "unknown")
        ct = e.get("timing", {}).get("catalog_s", 0)
        times_by_type.setdefault(mt, []).append(ct)
    timing_summary = {
        "total_files": len(catalog),
        "per_type_avg_s": {k: round(sum(v) / len(v), 4) for k, v in times_by_type.items()},
        "per_type_total_s": {k: round(sum(v), 4) for k, v in times_by_type.items()},
        "phase_total_s": round(sum(e.get("timing", {}).get("catalog_s", 0) for e in catalog), 4),
    }

    output = {
        "catalog_version": "1.0",
        "total_files": len(catalog),
        "timing_summary": timing_summary,
        "entries": catalog,
    }
    save_result(output, OUTPUT_DIR / "catalog.json")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Catalog Complete: {len(catalog)} files")
    by_type = {}
    for e in catalog:
        t = e.get("media_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    for t, count in sorted(by_type.items()):
        print(f"  {t}: {count}")
    errors = [e for e in catalog if e.get("error")]
    if errors:
        print(f"  errors: {len(errors)}")
    print(f"\nOutput: {OUTPUT_DIR / 'catalog.json'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
