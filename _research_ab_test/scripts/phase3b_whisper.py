#!/usr/bin/env python3
"""Phase 3b: Speech-to-text / audio transcription using local Whisper on GPU."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, relative_path,
    run_command, save_result, RESULTS_DIR, load_benchmark_config,
)

OUTPUT_DIR = RESULTS_DIR / "phase3_audio"
DEFAULT_WHISPER_MODELS = load_benchmark_config().get("whisper_models", ["base", "small"])
# For Goldfinger: extract only first 60s + a segment from ~30min in
GOLDFINGER_SEGMENTS = [
    {"name": "first_60s", "start": 0, "duration": 60},
    {"name": "mid_60s", "start": 1800, "duration": 60},
]
MODEL_CACHE = {}
WHISPER_DEVICE = None


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


def get_whisper_model(model_name: str):
    """Load a Whisper model once and cache it."""
    global WHISPER_DEVICE
    if WHISPER_DEVICE is None:
        try:
            import torch
            WHISPER_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            WHISPER_DEVICE = "cpu"
    if model_name not in MODEL_CACHE:
        import whisper
        MODEL_CACHE[model_name] = whisper.load_model(model_name, device=WHISPER_DEVICE)
    return MODEL_CACHE[model_name]


def transcribe_with_whisper(audio_path: Path, model_name: str) -> dict:
    """Transcribe audio using local Whisper model on GPU."""
    model = get_whisper_model(model_name)
    use_fp16 = WHISPER_DEVICE == "cuda"
    result = model.transcribe(
        str(audio_path),
        fp16=use_fp16,
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


def process_audio(filepath: Path, whisper_models: list[str]) -> dict:
    """Process a single audio file with all Whisper models."""
    rel = relative_path(filepath)
    print(f"\n--- {rel} ---")

    if filepath.stat().st_size == 0:
        return {"file": rel, "filename": filepath.name, "error": "zero-byte file", "timing": {}}

    entry = {"file": rel, "filename": filepath.name, "models": {}, "timing": {}}

    # Prepare audio (convert to wav if needed)
    temp_dir = OUTPUT_DIR / "temp_whisper"
    temp_dir.mkdir(parents=True, exist_ok=True)

    if filepath.suffix.lower() in (".wav",):
        audio_path = filepath
    else:
        audio_path = temp_dir / f"{filepath.stem}.wav"
        if not audio_path.exists():
            with TimedOperation(f"convert/{filepath.name}") as t:
                ok = extract_audio_segment(filepath, audio_path)
            entry["timing"]["convert_s"] = round(t.elapsed, 4)
            if not ok:
                return {"file": rel, "filename": filepath.name, "error": "audio conversion failed", "timing": entry["timing"]}

    for model_name in whisper_models:
        with TimedOperation(f"whisper-{model_name}/{filepath.name}") as t:
            try:
                result = transcribe_with_whisper(audio_path, model_name)
                result["elapsed_s"] = round(t.elapsed, 4)
                entry["models"][model_name] = result
            except Exception as e:
                entry["models"][model_name] = {"error": str(e)}
        entry["timing"][f"whisper_{model_name}_s"] = round(t.elapsed, 4)

    entry["timing"]["total_s"] = round(sum(entry["timing"].values()), 4)
    return entry


def process_long_video(video_path: Path, whisper_models: list[str]) -> dict:
    """Process a long video by extracting specific segments."""
    rel = relative_path(video_path)
    print(f"\n--- {rel} (long video — segments only) ---")

    temp_dir = OUTPUT_DIR / "temp_whisper"
    temp_dir.mkdir(parents=True, exist_ok=True)

    entry = {"file": rel, "filename": video_path.name, "segments": {}, "timing": {}}

    for seg in GOLDFINGER_SEGMENTS:
        seg_path = temp_dir / f"{video_path.stem}_{seg['name']}.wav"
        with TimedOperation(f"extract/{seg['name']}") as t:
            ok = extract_audio_segment(video_path, seg_path, seg["start"], seg["duration"])
        entry["timing"][f"extract_{seg['name']}_s"] = round(t.elapsed, 4)
        if not ok:
            entry["segments"][seg["name"]] = {"error": "extraction failed"}
            continue

        segment_results = {"models": {}, "timing": {}}
        for model_name in whisper_models:
            with TimedOperation(f"whisper-{model_name}/{seg['name']}") as t:
                try:
                    result = transcribe_with_whisper(seg_path, model_name)
                    result["elapsed_s"] = round(t.elapsed, 4)
                    segment_results["models"][model_name] = result
                except Exception as e:
                    segment_results["models"][model_name] = {"error": str(e)}
            segment_results["timing"][f"whisper_{model_name}_s"] = round(t.elapsed, 4)
            entry["timing"][f"whisper_{model_name}_{seg['name']}_s"] = round(t.elapsed, 4)
        entry["segments"][seg["name"]] = segment_results

    entry["timing"]["total_s"] = round(sum(entry["timing"].values()), 4)
    return entry


def main():
    parser = argparse.ArgumentParser(description="Phase 3b Whisper benchmark")
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_WHISPER_MODELS),
        help="Comma-separated Whisper model names",
    )
    parser.add_argument(
        "--max-audio",
        type=int,
        default=0,
        help="Optional cap on standalone audio files (0 = all)",
    )
    parser.add_argument(
        "--max-video",
        type=int,
        default=0,
        help="Optional cap on video files (0 = all)",
    )
    args = parser.parse_args()
    whisper_models = [m.strip() for m in args.models.split(",") if m.strip()]

    print("=" * 60)
    print("Phase 3b: Whisper Audio Transcription")
    print("=" * 60)

    valid_models = []
    for model_name in whisper_models:
        try:
            with TimedOperation(f"load_model/{model_name}"):
                get_whisper_model(model_name)
            valid_models.append(model_name)
        except Exception as e:
            print(f"  [WARN] Skipping model {model_name}: {e}")
    whisper_models = valid_models
    if not whisper_models:
        print("No Whisper models available to benchmark.")
        return

    results = []

    # Process audio files
    audio_files = collect_test_files("audio")
    if args.max_audio > 0:
        audio_files = audio_files[:args.max_audio]
    print(f"\nProcessing {len(audio_files)} audio files with models: {whisper_models}\n")

    for filepath in audio_files:
        entry = process_audio(filepath, whisper_models)
        results.append(entry)

    # Process video files
    video_files = collect_test_files("video")
    playable_videos = [v for v in video_files if v.stat().st_size > 0]
    if args.max_video > 0:
        playable_videos = playable_videos[:args.max_video]
    print(f"\nProcessing {len(playable_videos)} video files...\n")

    from lib.common import TEST_FILES
    goldfinger_dir = TEST_FILES / "007 James Bond Goldfinger 1964 1080p BluRay x264 AC3 - Ozlem"

    for video in playable_videos:
        if str(goldfinger_dir) in str(video):
            entry = process_long_video(video, whisper_models)
        else:
            # Short video — extract first 60s only
            temp_dir = OUTPUT_DIR / "temp_whisper"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_wav = temp_dir / f"{video.stem}_audio.wav"
            with TimedOperation(f"extract/{video.name}") as t_extract:
                ok = extract_audio_segment(video, temp_wav, duration=60)
            if ok and temp_wav.exists():
                entry = process_audio(temp_wav, whisper_models)
                entry["source_video"] = relative_path(video)
                entry["timing"]["audio_extract_s"] = round(t_extract.elapsed, 4)
            else:
                entry = {
                    "file": relative_path(video),
                    "filename": video.name,
                    "error": "audio extraction failed",
                    "timing": {"audio_extract_s": round(t_extract.elapsed, 4)},
                }
        results.append(entry)

    # Timing summary
    timing_by_model = {}
    for r in results:
        for key, val in r.get("timing", {}).items():
            if key == "total_s":
                continue
            # Normalize key to just the model name
            for m in whisper_models:
                if f"whisper_{m}" in key:
                    timing_by_model.setdefault(f"whisper_{m}", []).append(val)
                    break
            else:
                timing_by_model.setdefault(key, []).append(val)
    timing_summary = {
        "total_files": len(results),
        "per_tool_avg_s": {k: round(sum(v) / len(v), 4) for k, v in timing_by_model.items()},
        "per_tool_total_s": {k: round(sum(v), 4) for k, v in timing_by_model.items()},
        "per_file_avg_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results) / max(len(results), 1), 4),
        "phase_total_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results), 4),
    }

    output = {
        "phase": "3b_whisper",
        "models": whisper_models,
        "total_files": len(results),
        "timing_summary": timing_summary,
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
