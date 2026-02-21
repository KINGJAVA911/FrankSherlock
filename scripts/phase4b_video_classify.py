#!/usr/bin/env python3
"""Phase 4b: Multi-signal video classification — combine metadata, vision, audio, filename, NFO."""

import base64
import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, relative_path,
    run_command, save_result, RESULTS_DIR, TEST_FILES,
)

OUTPUT_DIR = RESULTS_DIR / "phase4_video"
OLLAMA_URL = "http://localhost:11434/api/generate"
VISION_MODEL = "qwen2.5vl:7b"
TEXT_MODEL = "qwen2.5vl:7b"  # Also works for text synthesis


def load_prior_results() -> dict:
    """Load results from prior phases."""
    data = {}
    files = {
        "metadata": RESULTS_DIR / "phase1_metadata" / "all_metadata.json",
        "chromaprint": RESULTS_DIR / "phase3_audio" / "chromaprint_results.json",
        "whisper": RESULTS_DIR / "phase3_audio" / "whisper_results.json",
        "frames": OUTPUT_DIR / "frame_extraction.json",
    }
    for key, path in files.items():
        try:
            with open(path) as f:
                data[key] = json.load(f)
        except FileNotFoundError:
            print(f"  [WARN] Missing: {path}")
            data[key] = None
    return data


def get_metadata_for_file(prior: dict, filename: str) -> dict:
    """Get Phase 1 metadata for a specific video file."""
    if not prior.get("metadata"):
        return {}
    for entry in prior["metadata"].get("files", []):
        if entry.get("filename") == filename:
            ffprobe = entry.get("ffprobe", {})
            fmt = ffprobe.get("format", {})
            streams = ffprobe.get("streams", [])
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
            audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
            return {
                "format": fmt.get("format_long_name", ""),
                "duration": fmt.get("duration", ""),
                "video_codec": video_stream.get("codec_name", ""),
                "resolution": f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')}",
                "audio_codec": audio_stream.get("codec_name", ""),
            }
    return {}


def get_audio_results(prior: dict, filename: str) -> dict:
    """Get Chromaprint + Whisper results for a video's audio."""
    audio_info = {}
    stem = Path(filename).stem

    if prior.get("chromaprint"):
        for entry in prior["chromaprint"].get("results", []):
            # Match by source_video or by derived filename
            if entry.get("source_video", "").endswith(filename) or stem in entry.get("filename", ""):
                fp = entry.get("fingerprint", {})
                audio_info["chromaprint"] = {
                    "has_fingerprint": bool(fp.get("fingerprint")),
                    "duration": fp.get("duration"),
                }
                # AcoustID matches
                acoustid = entry.get("acoustid", {})
                matches = []
                for r in acoustid.get("results", []):
                    for rec in r.get("recordings", []):
                        matches.append(rec.get("title", ""))
                if matches:
                    audio_info["acoustid_matches"] = matches

    if prior.get("whisper"):
        for entry in prior["whisper"].get("results", []):
            if entry.get("source_video", "").endswith(filename) or stem in entry.get("filename", ""):
                for model_name, data in entry.get("models", {}).items():
                    if isinstance(data, dict) and "text" in data:
                        audio_info[f"whisper_{model_name}"] = {
                            "language": data.get("language"),
                            "text": data["text"][:300],
                        }
                # Segments for long videos
                for seg_name, seg_data in entry.get("segments", {}).items():
                    for model_name, data in seg_data.get("models", {}).items():
                        if isinstance(data, dict) and "text" in data:
                            audio_info[f"whisper_{model_name}_{seg_name}"] = {
                                "language": data.get("language"),
                                "text": data["text"][:300],
                            }

    return audio_info


def get_frame_paths(prior: dict, filename: str) -> list[str]:
    """Get extracted frame paths for a video."""
    if not prior.get("frames"):
        return []
    for entry in prior["frames"].get("results", []):
        if entry.get("filename") == filename:
            paths = entry.get("scene_frame_paths", []) + entry.get("interval_frame_paths", [])
            return paths[:5]  # Limit to 5 frames for LLM analysis
    return []


def classify_frame(frame_path: str) -> dict:
    """Send a single frame to Ollama vision for classification."""
    try:
        with open(frame_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
    except FileNotFoundError:
        return {"description": "frame not found", "total_duration_ms": 0}

    payload = {
        "model": VISION_MODEL,
        "prompt": "Briefly describe this video frame. Is it anime, live action, animation, or other? "
                  "Identify any characters, text, or notable visual elements. Be concise (2-3 sentences).",
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 200},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return {
            "description": data.get("response", ""),
            "total_duration_ms": data.get("total_duration", 0) / 1e6,
        }
    except Exception as e:
        return {"description": f"error: {e}", "total_duration_ms": 0}


def parse_filename(filename: str) -> dict:
    """Extract hints from filename."""
    name = Path(filename).stem
    # Common patterns
    hints = {"raw_name": name}

    # Check for parenthetical info like (op), (op1)
    paren_match = re.findall(r'\(([^)]+)\)', name)
    if paren_match:
        hints["parenthetical"] = paren_match

    # Check for known series/content in name
    name_lower = name.lower()
    if any(w in name_lower for w in ["op", "ed", "opening", "ending"]):
        hints["likely_type"] = "anime opening/ending"
    if "trailer" in name_lower:
        hints["likely_type"] = "trailer"
    if "clip" in name_lower:
        hints["likely_type"] = "clip"

    return hints


def parse_nfo_for_video(video_path: Path) -> dict | None:
    """Check if NFO file exists near the video."""
    nfo_files = list(video_path.parent.glob("*.nfo"))
    if not nfo_files:
        return None

    nfo_path = nfo_files[0]
    try:
        text = nfo_path.read_text(errors="replace")
    except Exception:
        return None

    patterns = {
        "runtime": r"Runtime\.+:\s*(.+)",
        "resolution": r"Resolution\.+:\s*(.+)",
        "imdb_url": r"IMDb\.+:\s*(http\S+)",
        "imdb_rating": r"IMDB Rating\.+:\s*(.+)",
    }
    info = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            info[key] = match.group(1).strip()
    return info if info else None


def synthesize_identification(signals: dict) -> dict:
    """Use text LLM to synthesize all signals into a unified identification."""
    prompt = (
        "Based on the following signals about a video file, identify what this video is. "
        "Provide a JSON response with: title, type (movie/anime/trailer/clip/music_video/game), "
        "series (if applicable), year (if known), language, confidence (0-1), and reasoning.\n\n"
        f"Signals:\n{json.dumps(signals, indent=2, default=str)}\n\n"
        "Respond ONLY with valid JSON (no markdown)."
    )

    payload = {
        "model": TEXT_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 500},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        # Try to extract JSON
        json_match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"raw_response": raw[:500]}
    except Exception as e:
        return {"error": str(e)}


def process_video(filepath: Path, prior: dict) -> dict:
    """Combine all signals for a single video."""
    rel = relative_path(filepath)
    print(f"\n{'=' * 50}")
    print(f"  Video: {rel}")
    print(f"{'=' * 50}")

    if filepath.stat().st_size == 0:
        return {"file": rel, "filename": filepath.name, "error": "zero-byte file", "timing": {}}

    entry = {"file": rel, "filename": filepath.name, "signals": {}, "timing": {}}

    # Signal 1: Metadata
    with TimedOperation("metadata") as t:
        entry["signals"]["metadata"] = get_metadata_for_file(prior, filepath.name)
    entry["timing"]["metadata_lookup_s"] = round(t.elapsed, 4)

    # Signal 2: Filename parsing
    entry["signals"]["filename_hints"] = parse_filename(filepath.name)

    # Signal 3: NFO
    nfo = parse_nfo_for_video(filepath)
    if nfo:
        entry["signals"]["nfo"] = nfo

    # Signal 4: Frame classification (use up to 3 frames)
    frame_paths = get_frame_paths(prior, filepath.name)
    if frame_paths:
        entry["signals"]["frame_descriptions"] = []
        frame_total = 0.0
        for fp in frame_paths[:3]:
            with TimedOperation(f"frame_classify/{Path(fp).name}") as t:
                result = classify_frame(fp)
            frame_total += t.elapsed
            entry["signals"]["frame_descriptions"].append(result["description"])
        entry["timing"]["frame_classify_s"] = round(frame_total, 4)
        entry["timing"]["frame_classify_count"] = len(frame_paths[:3])

    # Signal 5: Audio analysis
    audio = get_audio_results(prior, filepath.name)
    if audio:
        entry["signals"]["audio"] = audio

    # Synthesize
    print("  Synthesizing identification...")
    with TimedOperation("synthesis") as t:
        entry["identification"] = synthesize_identification(entry["signals"])
    entry["timing"]["synthesis_s"] = round(t.elapsed, 4)

    entry["timing"]["total_s"] = round(sum(v for v in entry["timing"].values() if isinstance(v, float)), 4)
    return entry


def main():
    print("=" * 60)
    print("Phase 4b: Multi-Signal Video Classification")
    print("=" * 60)

    prior = load_prior_results()
    videos = collect_test_files("video")
    print(f"\nProcessing {len(videos)} video files...\n")

    results = []
    for filepath in videos:
        entry = process_video(filepath, prior)
        results.append(entry)

    # Timing summary
    timing_summary = {
        "total_videos": len(videos),
        "per_video_avg_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results) / max(len(results), 1), 4),
        "phase_total_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results), 4),
    }

    output = {
        "phase": "4b_video_classification",
        "total_videos": len(videos),
        "timing_summary": timing_summary,
        "results": results,
    }
    save_result(output, OUTPUT_DIR / "video_classification.json")

    print(f"\n{'=' * 60}")
    print("Phase 4b Complete — Video Identifications:")
    for r in results:
        ident = r.get("identification", {})
        title = ident.get("title", "unknown")
        vtype = ident.get("type", "?")
        conf = ident.get("confidence", "?")
        print(f"  {r['filename']}: {title} ({vtype}, confidence={conf})")
    print("=" * 60)


if __name__ == "__main__":
    main()
