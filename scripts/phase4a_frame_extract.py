#!/usr/bin/env python3
"""Phase 4a: Video keyframe extraction using ffmpeg scene detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, relative_path,
    run_command, save_result, RESULTS_DIR,
)

OUTPUT_DIR = RESULTS_DIR / "phase4_video"
FRAMES_DIR = OUTPUT_DIR / "frames"
MAX_FRAMES = 20
SCENE_THRESHOLD = 0.3
FALLBACK_INTERVAL = 30  # seconds


def get_video_duration(filepath: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    result = run_command([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(filepath),
    ])
    try:
        return float(result["stdout"].strip())
    except (ValueError, AttributeError):
        return 0.0


def extract_scene_keyframes(filepath: Path, output_dir: Path) -> list[Path]:
    """Extract keyframes using scene change detection."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(output_dir / f"{filepath.stem}_scene_%03d.jpg")

    result = run_command([
        "ffmpeg", "-i", str(filepath),
        "-vf", f"select='gt(scene,{SCENE_THRESHOLD})',setpts=N/FRAME_RATE/TB",
        "-frames:v", str(MAX_FRAMES),
        "-vsync", "vfr",
        "-q:v", "2",
        "-y", pattern,
    ], timeout=120)

    if result["returncode"] != 0:
        return []

    # Collect extracted frames
    frames = sorted(output_dir.glob(f"{filepath.stem}_scene_*.jpg"))
    return frames[:MAX_FRAMES]


def extract_interval_keyframes(filepath: Path, output_dir: Path, duration: float) -> list[Path]:
    """Extract keyframes at regular intervals as fallback."""
    output_dir.mkdir(parents=True, exist_ok=True)
    interval = max(FALLBACK_INTERVAL, duration / MAX_FRAMES)
    pattern = str(output_dir / f"{filepath.stem}_interval_%03d.jpg")

    result = run_command([
        "ffmpeg", "-i", str(filepath),
        "-vf", f"fps=1/{int(interval)}",
        "-frames:v", str(MAX_FRAMES),
        "-q:v", "2",
        "-y", pattern,
    ], timeout=120)

    if result["returncode"] != 0:
        return []

    frames = sorted(output_dir.glob(f"{filepath.stem}_interval_*.jpg"))
    return frames[:MAX_FRAMES]


def process_video(filepath: Path) -> dict:
    """Extract keyframes from a single video."""
    rel = relative_path(filepath)
    print(f"\n--- {rel} ---")

    if filepath.stat().st_size == 0:
        print("  [SKIP] Zero-byte file")
        return {"file": rel, "filename": filepath.name, "error": "zero-byte file"}

    entry = {"file": rel, "filename": filepath.name}

    duration = get_video_duration(filepath)
    entry["duration_seconds"] = duration
    print(f"  Duration: {duration:.1f}s")

    video_frames_dir = FRAMES_DIR / filepath.stem

    # Try scene detection first
    with TimedOperation(f"scene_detect/{filepath.name}"):
        scene_frames = extract_scene_keyframes(filepath, video_frames_dir)
    entry["scene_frames"] = len(scene_frames)
    entry["scene_frame_paths"] = [str(f) for f in scene_frames]

    # If scene detection got few frames, try interval sampling
    if len(scene_frames) < 3 and duration > 10:
        print(f"  Scene detection got {len(scene_frames)} frames, trying interval...")
        with TimedOperation(f"interval/{filepath.name}"):
            interval_frames = extract_interval_keyframes(filepath, video_frames_dir, duration)
        entry["interval_frames"] = len(interval_frames)
        entry["interval_frame_paths"] = [str(f) for f in interval_frames]
    else:
        entry["interval_frames"] = 0
        entry["interval_frame_paths"] = []

    total = entry["scene_frames"] + entry["interval_frames"]
    print(f"  Total frames extracted: {total}")

    return entry


def main():
    print("=" * 60)
    print("Phase 4a: Video Keyframe Extraction")
    print("=" * 60)

    videos = collect_test_files("video")
    print(f"\nProcessing {len(videos)} video files...\n")

    results = []
    for filepath in videos:
        entry = process_video(filepath)
        results.append(entry)

    output = {
        "phase": "4a_frame_extraction",
        "total_videos": len(videos),
        "results": results,
    }
    save_result(output, OUTPUT_DIR / "frame_extraction.json")

    print(f"\n{'=' * 60}")
    total_frames = sum(r.get("scene_frames", 0) + r.get("interval_frames", 0) for r in results)
    print(f"Phase 4a Complete: {len(results)} videos, {total_frames} total frames extracted")
    print("=" * 60)


if __name__ == "__main__":
    main()
