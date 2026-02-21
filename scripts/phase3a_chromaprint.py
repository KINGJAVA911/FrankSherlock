#!/usr/bin/env python3
"""Phase 3a: Audio fingerprinting with Chromaprint/fpcalc + optional AcoustID lookup."""

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, detect_media_type,
    relative_path, run_command, save_result, RESULTS_DIR, TEST_FILES,
)

OUTPUT_DIR = RESULTS_DIR / "phase3_audio"
ACOUSTID_API_KEY = None  # Set to your API key if you have one
ACOUSTID_URL = "https://api.acoustid.org/v2/lookup"


def run_fpcalc(filepath: Path) -> dict | None:
    """Run fpcalc to generate Chromaprint fingerprint."""
    result = run_command(["fpcalc", "-json", str(filepath)], timeout=60)
    if result["returncode"] == 0 and result["stdout"].strip():
        try:
            return json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "JSON parse failed", "raw": result["stdout"][:500]}
    return {"error": result["stderr"][:500]}


def extract_audio_from_video(video_path: Path, output_path: Path) -> bool:
    """Extract audio track from video using ffmpeg."""
    result = run_command([
        "ffmpeg", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
        "-ar", "44100", "-ac", "1", "-y", str(output_path),
    ], timeout=120)
    return result["returncode"] == 0


def lookup_acoustid(fingerprint: str, duration: int) -> dict | None:
    """Look up fingerprint on AcoustID (requires API key)."""
    if not ACOUSTID_API_KEY:
        return {"status": "skipped", "reason": "no API key configured"}

    try:
        resp = requests.get(ACOUSTID_URL, params={
            "client": ACOUSTID_API_KEY,
            "fingerprint": fingerprint,
            "duration": duration,
            "meta": "recordings+releasegroups+compress",
        }, timeout=10)
        if resp.ok:
            return resp.json()
        return {"error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def process_audio_file(filepath: Path) -> dict:
    """Process a single audio file."""
    rel = relative_path(filepath)
    print(f"\n--- {rel} ---")

    if filepath.stat().st_size == 0:
        return {"file": rel, "filename": filepath.name, "error": "zero-byte file"}

    entry = {"file": rel, "filename": filepath.name}

    with TimedOperation(f"fpcalc/{filepath.name}"):
        fp = run_fpcalc(filepath)
    entry["fingerprint"] = fp

    if fp and "fingerprint" in fp:
        duration = fp.get("duration", 0)
        with TimedOperation(f"acoustid/{filepath.name}"):
            lookup = lookup_acoustid(fp["fingerprint"], int(duration))
        entry["acoustid"] = lookup
    else:
        entry["acoustid"] = {"status": "skipped", "reason": "no fingerprint generated"}

    return entry


def main():
    print("=" * 60)
    print("Phase 3a: Chromaprint Audio Fingerprinting")
    print("=" * 60)

    # Process audio files
    audio_files = collect_test_files("audio")
    print(f"\nProcessing {len(audio_files)} audio files...\n")

    results = []
    for filepath in audio_files:
        entry = process_audio_file(filepath)
        results.append(entry)

    # Extract and fingerprint audio from video files
    video_files = collect_test_files("video")
    playable_videos = [v for v in video_files if v.stat().st_size > 0]
    print(f"\nExtracting audio from {len(playable_videos)} videos...\n")

    temp_dir = OUTPUT_DIR / "temp_audio"
    temp_dir.mkdir(parents=True, exist_ok=True)

    for video in playable_videos:
        temp_wav = temp_dir / f"{video.stem}_audio.wav"
        print(f"\n--- Extracting: {relative_path(video)} ---")
        with TimedOperation(f"extract/{video.name}"):
            ok = extract_audio_from_video(video, temp_wav)
        if ok and temp_wav.exists() and temp_wav.stat().st_size > 0:
            entry = process_audio_file(temp_wav)
            entry["source_video"] = relative_path(video)
            results.append(entry)
        else:
            results.append({
                "file": relative_path(video),
                "filename": video.name,
                "error": "audio extraction failed",
                "source_video": relative_path(video),
            })

    output = {
        "phase": "3a_chromaprint",
        "total_files": len(results),
        "acoustid_api_key_set": ACOUSTID_API_KEY is not None,
        "results": results,
    }
    save_result(output, OUTPUT_DIR / "chromaprint_results.json")

    print(f"\n{'=' * 60}")
    fp_ok = sum(1 for r in results if r.get("fingerprint", {}).get("fingerprint"))
    print(f"Phase 3a Complete: {len(results)} files, {fp_ok} fingerprints generated")
    print("=" * 60)


if __name__ == "__main__":
    main()
