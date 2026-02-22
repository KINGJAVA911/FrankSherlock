#!/usr/bin/env python3
"""Phase 3d: Speech-to-text / audio transcription using faster-whisper."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation,
    collect_test_files,
    load_benchmark_config,
    relative_path,
    run_command,
    save_result,
    RESULTS_DIR,
)

OUTPUT_DIR = RESULTS_DIR / "phase3_audio"
DEFAULT_MODELS = load_benchmark_config().get("faster_whisper_models", ["small", "distil-large-v3"])
GOLDFINGER_SEGMENTS = [
    {"name": "first_60s", "start": 0, "duration": 60},
    {"name": "mid_60s", "start": 1800, "duration": 60},
]
MODEL_CACHE = {}
ASR_DEVICE = None
ASR_COMPUTE_TYPE = None


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


def detect_runtime() -> tuple[str, str]:
    """Pick device and compute type for faster-whisper."""
    global ASR_DEVICE, ASR_COMPUTE_TYPE
    if ASR_DEVICE is not None and ASR_COMPUTE_TYPE is not None:
        return ASR_DEVICE, ASR_COMPUTE_TYPE

    try:
        import torch
        if torch.cuda.is_available():
            ASR_DEVICE = "cuda"
            ASR_COMPUTE_TYPE = "float16"
        else:
            ASR_DEVICE = "cpu"
            ASR_COMPUTE_TYPE = "int8"
    except Exception:
        ASR_DEVICE = "cpu"
        ASR_COMPUTE_TYPE = "int8"
    return ASR_DEVICE, ASR_COMPUTE_TYPE


def get_model(model_name: str):
    """Load a faster-whisper model once and cache it."""
    if model_name in MODEL_CACHE:
        return MODEL_CACHE[model_name]

    from faster_whisper import WhisperModel

    device, compute_type = detect_runtime()
    MODEL_CACHE[model_name] = WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
    )
    return MODEL_CACHE[model_name]


def transcribe_with_faster_whisper(audio_path: Path, model_name: str) -> dict:
    """Transcribe audio with faster-whisper."""
    model = get_model(model_name)
    segments, info = model.transcribe(
        str(audio_path),
        beam_size=1,
        vad_filter=False,
    )
    rows = []
    full_text_parts = []
    for i, seg in enumerate(segments):
        if i < 20:
            rows.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
            })
        full_text_parts.append(seg.text)

    return {
        "text": "".join(full_text_parts).strip(),
        "language": getattr(info, "language", "unknown"),
        "language_probability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 4),
        "segments": rows,
    }


def process_audio(filepath: Path, model_names: list[str]) -> dict:
    """Process a single audio file with all configured faster-whisper models."""
    rel = relative_path(filepath)
    print(f"\n--- {rel} ---")

    if filepath.stat().st_size == 0:
        return {"file": rel, "filename": filepath.name, "error": "zero-byte file", "timing": {}}

    entry = {"file": rel, "filename": filepath.name, "models": {}, "timing": {}}

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

    for model_name in model_names:
        with TimedOperation(f"faster-whisper-{model_name}/{filepath.name}") as t:
            try:
                out = transcribe_with_faster_whisper(audio_path, model_name)
                out["elapsed_s"] = round(t.elapsed, 4)
                entry["models"][model_name] = out
            except Exception as e:
                entry["models"][model_name] = {"error": str(e)}
        entry["timing"][f"faster_whisper_{model_name}_s"] = round(t.elapsed, 4)

    entry["timing"]["total_s"] = round(sum(entry["timing"].values()), 4)
    return entry


def process_long_video(video_path: Path, model_names: list[str]) -> dict:
    """Process a long video by extracting specific segments."""
    rel = relative_path(video_path)
    print(f"\n--- {rel} (long video — segments only) ---")

    temp_dir = OUTPUT_DIR / "temp_whisper"
    temp_dir.mkdir(parents=True, exist_ok=True)

    entry = {"file": rel, "filename": video_path.name, "segments": {}, "timing": {}}

    for seg in GOLDFINGER_SEGMENTS:
        seg_path = temp_dir / f"{video_path.stem}_{seg['name']}_fw.wav"
        with TimedOperation(f"extract/{seg['name']}") as t:
            ok = extract_audio_segment(video_path, seg_path, seg["start"], seg["duration"])
        entry["timing"][f"extract_{seg['name']}_s"] = round(t.elapsed, 4)
        if not ok:
            entry["segments"][seg["name"]] = {"error": "extraction failed"}
            continue

        segment_results = {"models": {}, "timing": {}}
        for model_name in model_names:
            with TimedOperation(f"faster-whisper-{model_name}/{seg['name']}") as t:
                try:
                    out = transcribe_with_faster_whisper(seg_path, model_name)
                    out["elapsed_s"] = round(t.elapsed, 4)
                    segment_results["models"][model_name] = out
                except Exception as e:
                    segment_results["models"][model_name] = {"error": str(e)}
            segment_results["timing"][f"faster_whisper_{model_name}_s"] = round(t.elapsed, 4)
            entry["timing"][f"faster_whisper_{model_name}_{seg['name']}_s"] = round(t.elapsed, 4)
        entry["segments"][seg["name"]] = segment_results

    entry["timing"]["total_s"] = round(sum(entry["timing"].values()), 4)
    return entry


def main():
    parser = argparse.ArgumentParser(description="Phase 3d faster-whisper benchmark")
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="Comma-separated faster-whisper model names",
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
    model_names = [m.strip() for m in args.models.split(",") if m.strip()]

    print("=" * 60)
    print("Phase 3d: faster-whisper Audio Transcription")
    print("=" * 60)

    try:
        import faster_whisper  # noqa: F401
    except Exception as e:
        print(f"[ERROR] faster-whisper is not installed or failed to import: {e}")
        return

    valid_models = []
    for model_name in model_names:
        try:
            with TimedOperation(f"load_model/{model_name}"):
                get_model(model_name)
            valid_models.append(model_name)
        except Exception as e:
            print(f"  [WARN] Skipping model {model_name}: {e}")
    model_names = valid_models
    if not model_names:
        print("No faster-whisper models available to benchmark.")
        return

    device, compute_type = detect_runtime()
    print(f"Runtime: device={device}, compute_type={compute_type}")

    results = []

    audio_files = collect_test_files("audio")
    if args.max_audio > 0:
        audio_files = audio_files[:args.max_audio]
    print(f"\nProcessing {len(audio_files)} audio files with models: {model_names}\n")
    for filepath in audio_files:
        results.append(process_audio(filepath, model_names))

    video_files = collect_test_files("video")
    playable_videos = [v for v in video_files if v.stat().st_size > 0]
    if args.max_video > 0:
        playable_videos = playable_videos[:args.max_video]
    print(f"\nProcessing {len(playable_videos)} video files...\n")

    from lib.common import TEST_FILES
    goldfinger_dir = TEST_FILES / "007 James Bond Goldfinger 1964 1080p BluRay x264 AC3 - Ozlem"

    for video in playable_videos:
        if str(goldfinger_dir) in str(video):
            entry = process_long_video(video, model_names)
        else:
            temp_dir = OUTPUT_DIR / "temp_whisper"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_wav = temp_dir / f"{video.stem}_audio_fw.wav"
            with TimedOperation(f"extract/{video.name}") as t_extract:
                ok = extract_audio_segment(video, temp_wav, duration=60)
            if ok and temp_wav.exists():
                entry = process_audio(temp_wav, model_names)
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

    timing_by_model = {}
    for r in results:
        for key, val in r.get("timing", {}).items():
            if key == "total_s":
                continue
            for model_name in model_names:
                if f"faster_whisper_{model_name}" in key:
                    timing_by_model.setdefault(f"faster_whisper_{model_name}", []).append(val)
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
        "phase": "3d_faster_whisper",
        "models": model_names,
        "device": device,
        "compute_type": compute_type,
        "total_files": len(results),
        "timing_summary": timing_summary,
        "results": results,
    }
    save_result(output, OUTPUT_DIR / "faster_whisper_results.json")


if __name__ == "__main__":
    main()
