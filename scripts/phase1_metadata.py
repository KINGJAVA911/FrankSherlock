#!/usr/bin/env python3
"""Phase 1: Metadata extraction baseline — ExifTool, ffprobe, MediaInfo on all test files."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, detect_media_type,
    relative_path, run_command, save_result, RESULTS_DIR, TEST_FILES,
)

OUTPUT_DIR = RESULTS_DIR / "phase1_metadata"


def run_exiftool(filepath: Path) -> dict | None:
    result = run_command(["exiftool", "-json", "-G", str(filepath)])
    if result["returncode"] == 0 and result["stdout"].strip():
        try:
            data = json.loads(result["stdout"])
            return data[0] if data else None
        except json.JSONDecodeError:
            return {"error": "JSON parse failed", "raw": result["stdout"][:500]}
    return {"error": result["stderr"][:500]} if result["stderr"] else None


def run_ffprobe(filepath: Path) -> dict | None:
    result = run_command([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(filepath),
    ])
    if result["returncode"] == 0 and result["stdout"].strip():
        try:
            return json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "JSON parse failed"}
    return {"error": result["stderr"][:500]} if result["stderr"] else None


def run_mediainfo(filepath: Path) -> dict | None:
    result = run_command(["mediainfo", "--Output=JSON", str(filepath)])
    if result["returncode"] == 0 and result["stdout"].strip():
        try:
            return json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "JSON parse failed"}
    return {"error": result["stderr"][:500]} if result["stderr"] else None


def parse_nfo(filepath: Path) -> dict | None:
    """Parse NFO file for structured metadata."""
    try:
        text = filepath.read_text(errors="replace")
    except Exception:
        return None

    patterns = {
        "encoder": r"Encoder\.+:\s*(.+)",
        "file_size": r"File Size\.+:\s*(.+)",
        "source": r"Source\.+:\s*(.+)",
        "runtime": r"Runtime\.+:\s*(.+)",
        "resolution": r"Resolution\.+:\s*(.+)",
        "video_codec": r"Video Codec\.+:\s*(.+)",
        "video_format": r"Video Format\.+:\s*(.+)",
        "frame_rate": r"Frame Rate\.+:\s*(.+)",
        "audio_language": r"Audio Language\.+:\s*(.+)",
        "subtitles": r"Subtitles\.+:\s*(.+)",
        "imdb_rating": r"IMDB Rating\.+:\s*(.+)",
        "imdb_url": r"IMDb\.+:\s*(http\S+)",
    }

    info = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            info[key] = match.group(1).strip()
    return info if info else None


def process_file(filepath: Path) -> dict:
    """Process a single file with all available metadata tools."""
    media_type = detect_media_type(filepath)
    file_size = filepath.stat().st_size
    rel = relative_path(filepath)

    entry = {
        "file": rel,
        "filename": filepath.name,
        "media_type": media_type,
        "file_size": file_size,
        "file_size_human": format_size(file_size),
        "timing": {},
    }

    # Skip zero-byte files
    if file_size == 0:
        entry["error"] = "zero-byte file"
        print(f"  [SKIP] {rel} (0 bytes)")
        return entry

    # ExifTool — works on everything
    with TimedOperation(f"exiftool {filepath.name}") as t:
        exif = run_exiftool(filepath)
    entry["timing"]["exiftool_s"] = round(t.elapsed, 4)
    if exif:
        entry["exiftool"] = exif

    # ffprobe + MediaInfo — audio/video only
    if media_type in ("audio", "video"):
        with TimedOperation(f"ffprobe {filepath.name}") as t:
            ffp = run_ffprobe(filepath)
        entry["timing"]["ffprobe_s"] = round(t.elapsed, 4)
        if ffp:
            entry["ffprobe"] = ffp

        with TimedOperation(f"mediainfo {filepath.name}") as t:
            mi = run_mediainfo(filepath)
        entry["timing"]["mediainfo_s"] = round(t.elapsed, 4)
        if mi:
            entry["mediainfo"] = mi

    # NFO parsing
    if filepath.suffix.lower() == ".nfo":
        nfo = parse_nfo(filepath)
        if nfo:
            entry["nfo_parsed"] = nfo

    # Total time for this file
    entry["timing"]["total_s"] = round(sum(entry["timing"].values()), 4)

    return entry


def format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def main():
    print("=" * 60)
    print("Phase 1: Metadata Extraction")
    print("=" * 60)

    all_files = collect_test_files()
    print(f"\nProcessing {len(all_files)} files...\n")

    results = []
    errors = []

    for filepath in all_files:
        print(f"\n--- {relative_path(filepath)} ---")
        try:
            entry = process_file(filepath)
            results.append(entry)
        except Exception as e:
            print(f"  [ERROR] {e}")
            errors.append({"file": str(filepath), "error": str(e)})

    # Also process NFO file specifically
    nfo_path = TEST_FILES / "007 James Bond Goldfinger 1964 1080p BluRay x264 AC3 - Ozlem" / "NFO.nfo"
    if nfo_path.exists() and not any(r.get("file", "").endswith("NFO.nfo") for r in results):
        print(f"\n--- {relative_path(nfo_path)} ---")
        entry = process_file(nfo_path)
        results.append(entry)

    # Compute timing summary
    timing_by_tool = {}
    for r in results:
        for key, val in r.get("timing", {}).items():
            if key == "total_s":
                continue
            timing_by_tool.setdefault(key, []).append(val)
    timing_summary = {
        "total_files": len(results),
        "per_tool_avg_s": {k: round(sum(v) / len(v), 4) for k, v in timing_by_tool.items()},
        "per_tool_total_s": {k: round(sum(v), 4) for k, v in timing_by_tool.items()},
        "per_file_avg_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results) / max(len(results), 1), 4),
        "phase_total_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results), 4),
    }

    # Summary
    output = {
        "phase": "1_metadata",
        "total_files": len(results),
        "timing_summary": timing_summary,
        "errors": errors,
        "files": results,
    }
    save_result(output, OUTPUT_DIR / "all_metadata.json")

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Phase 1 Complete: {len(results)} files processed, {len(errors)} errors")
    by_type = {}
    for r in results:
        t = r.get("media_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    for t, count in sorted(by_type.items()):
        print(f"  {t}: {count}")

    zero_byte = [r for r in results if r.get("error") == "zero-byte file"]
    if zero_byte:
        print(f"  zero-byte files: {[r['filename'] for r in zero_byte]}")
    print("=" * 60)


if __name__ == "__main__":
    main()
