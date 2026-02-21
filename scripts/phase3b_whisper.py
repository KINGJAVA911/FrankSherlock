#!/usr/bin/env python3
"""Phase 3b: Speech-to-text / audio transcription using local Whisper on GPU."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, relative_path,
    run_command, save_result, RESULTS_DIR,
)

OUTPUT_DIR = RESULTS_DIR / "phase3_audio"
WHISPER_MODELS = ["base", "small"]
# For Goldfinger: extract only first 60s + a segment from ~30min in
GOLDFINGER_SEGMENTS = [
    {"name": "first_60s", "start": 0, "duration": 60},
    {"name": "mid_60s", "start": 1800, "duration": 60},
]


def extract_audio_segment(video_path: Path, output_path: Path,
                          start: int = 0, duration: int | None = None) -> bool:
    """Extract audio segment from media file using ffmpeg."""
    cmd = ["ffmpeg", "-i", str(video_path), "-vn",
           "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"]
    if start > 0:
        cmd.extend(["-ss", str(start)])
    if duration:
        cmd.extend(["-t", str(duration)])
    cmd.extend(["-y", str(output_path)])
    result = run_command(cmd, timeout=120)
    return result["returncode"] == 0


def transcribe_with_whisper(audio_path: Path, model_name: str) -> dict:
    """Transcribe audio using local Whisper model on GPU."""
    import whisper

    model = whisper.load_model(model_name, device="cuda")
    result = model.transcribe(
        str(audio_path),
        fp16=True,
        language=None,  # auto-detect
    )
    return {
        "text": result.get("text", ""),
        "language": result.get("language", "unknown"),
        "segments": [
            {"start": s["start"], "end": s["end"], "text": s["text"]}
            for s in result.get("segments", [])[:20]  # limit segments
        ],
    }


def process_audio(filepath: Path, is_long_video: bool = False) -> dict:
    """Process a single audio file with all Whisper models."""
    rel = relative_path(filepath)
    print(f"\n--- {rel} ---")

    if filepath.stat().st_size == 0:
        return {"file": rel, "filename": filepath.name, "error": "zero-byte file"}

    entry = {"file": rel, "filename": filepath.name, "models": {}}

    # Prepare audio (convert to wav if needed)
    temp_dir = OUTPUT_DIR / "temp_whisper"
    temp_dir.mkdir(parents=True, exist_ok=True)

    if filepath.suffix.lower() in (".wav",):
        audio_path = filepath
    else:
        audio_path = temp_dir / f"{filepath.stem}.wav"
        if not audio_path.exists():
            with TimedOperation(f"convert/{filepath.name}"):
                ok = extract_audio_segment(filepath, audio_path)
            if not ok:
                return {"file": rel, "filename": filepath.name, "error": "audio conversion failed"}

    for model_name in WHISPER_MODELS:
        with TimedOperation(f"whisper-{model_name}/{filepath.name}"):
            try:
                result = transcribe_with_whisper(audio_path, model_name)
                entry["models"][model_name] = result
            except Exception as e:
                entry["models"][model_name] = {"error": str(e)}

    return entry


def process_long_video(video_path: Path) -> dict:
    """Process a long video by extracting specific segments."""
    rel = relative_path(video_path)
    print(f"\n--- {rel} (long video — segments only) ---")

    temp_dir = OUTPUT_DIR / "temp_whisper"
    temp_dir.mkdir(parents=True, exist_ok=True)

    entry = {"file": rel, "filename": video_path.name, "segments": {}}

    for seg in GOLDFINGER_SEGMENTS:
        seg_path = temp_dir / f"{video_path.stem}_{seg['name']}.wav"
        with TimedOperation(f"extract/{seg['name']}"):
            ok = extract_audio_segment(video_path, seg_path, seg["start"], seg["duration"])
        if not ok:
            entry["segments"][seg["name"]] = {"error": "extraction failed"}
            continue

        segment_results = {"models": {}}
        for model_name in WHISPER_MODELS:
            with TimedOperation(f"whisper-{model_name}/{seg['name']}"):
                try:
                    result = transcribe_with_whisper(seg_path, model_name)
                    segment_results["models"][model_name] = result
                except Exception as e:
                    segment_results["models"][model_name] = {"error": str(e)}
        entry["segments"][seg["name"]] = segment_results

    return entry


def main():
    print("=" * 60)
    print("Phase 3b: Whisper Audio Transcription")
    print("=" * 60)

    results = []

    # Process audio files
    audio_files = collect_test_files("audio")
    print(f"\nProcessing {len(audio_files)} audio files with models: {WHISPER_MODELS}\n")

    for filepath in audio_files:
        entry = process_audio(filepath)
        results.append(entry)

    # Process video files
    video_files = collect_test_files("video")
    playable_videos = [v for v in video_files if v.stat().st_size > 0]
    print(f"\nProcessing {len(playable_videos)} video files...\n")

    from lib.common import TEST_FILES
    goldfinger_dir = TEST_FILES / "007 James Bond Goldfinger 1964 1080p BluRay x264 AC3 - Ozlem"

    for video in playable_videos:
        if str(goldfinger_dir) in str(video):
            entry = process_long_video(video)
        else:
            # Short video — extract first 60s only
            temp_dir = OUTPUT_DIR / "temp_whisper"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_wav = temp_dir / f"{video.stem}_audio.wav"
            with TimedOperation(f"extract/{video.name}"):
                ok = extract_audio_segment(video, temp_wav, duration=60)
            if ok and temp_wav.exists():
                entry = process_audio(temp_wav)
                entry["source_video"] = relative_path(video)
            else:
                entry = {
                    "file": relative_path(video),
                    "filename": video.name,
                    "error": "audio extraction failed",
                }
        results.append(entry)

    output = {
        "phase": "3b_whisper",
        "models": WHISPER_MODELS,
        "total_files": len(results),
        "results": results,
    }
    save_result(output, OUTPUT_DIR / "whisper_results.json")

    print(f"\n{'=' * 60}")
    ok = sum(1 for r in results if not r.get("error"))
    print(f"Phase 3b Complete: {len(results)} files, {ok} successfully transcribed")
    langs = set()
    for r in results:
        for model_data in r.get("models", {}).values():
            if isinstance(model_data, dict) and "language" in model_data:
                langs.add(model_data["language"])
        for seg_data in r.get("segments", {}).values():
            for model_data in seg_data.get("models", {}).values():
                if isinstance(model_data, dict) and "language" in model_data:
                    langs.add(model_data["language"])
    print(f"Languages detected: {langs}")
    print("=" * 60)


if __name__ == "__main__":
    main()
