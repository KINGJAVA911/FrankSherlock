#!/usr/bin/env python3
"""Phase 4b: Multi-signal video classification — combine metadata, vision, audio, filename, NFO."""

import argparse
import base64
import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, relative_path,
    run_command, save_result, RESULTS_DIR, TEST_FILES, load_benchmark_config,
    load_json, extract_first_json_object, DOCS_DIR, summarize_samples,
)

OUTPUT_DIR = RESULTS_DIR / "phase4_video"
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODELS = load_benchmark_config().get("vision_models", ["qwen2.5vl:7b"])
GROUND_TRUTH_PATH = DOCS_DIR / "ground_truth_videos.json"


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


def classify_frame(frame_path: str, model_name: str) -> dict:
    """Send a single frame to Ollama vision for classification."""
    try:
        with open(frame_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
    except FileNotFoundError:
        return {"description": "frame not found", "total_duration_ms": 0}

    payload = {
        "model": model_name,
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


def synthesize_identification(signals: dict, model_name: str) -> dict:
    """Use text LLM to synthesize all signals into a unified identification."""
    prompt = (
        "Based on the following signals about a video file, identify what this video is. "
        "Provide a JSON response with: title, type (movie/anime/trailer/clip/music_video/game), "
        "series (if applicable), year (if known), language, confidence (0-1), and reasoning.\n\n"
        f"Signals:\n{json.dumps(signals, indent=2, default=str)}\n\n"
        "Respond ONLY with valid JSON (no markdown)."
    )

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 500},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        parsed = extract_first_json_object(raw)
        if parsed:
            return parsed
        return {"raw_response": raw[:500]}
    except Exception as e:
        return {"error": str(e)}


def process_video(filepath: Path, prior: dict, models: list[str]) -> dict:
    """Combine all signals for a single video."""
    rel = relative_path(filepath)
    print(f"\n{'=' * 50}")
    print(f"  Video: {rel}")
    print(f"{'=' * 50}")

    if filepath.stat().st_size == 0:
        return {"file": rel, "filename": filepath.name, "error": "zero-byte file", "timing": {}}

    entry = {"file": rel, "filename": filepath.name, "signals": {}, "timing": {}, "model_runs": {}}

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

    # Signal 4: Audio analysis
    audio = get_audio_results(prior, filepath.name)
    if audio:
        entry["signals"]["audio"] = audio

    # Signal 5: Frame paths
    frame_paths = get_frame_paths(prior, filepath.name)
    entry["signals"]["frame_paths_used"] = frame_paths[:3]

    # Model-specific runs
    for model_name in models:
        model_key = model_name.replace("/", "_")
        model_entry = {"content_only": {}, "full_context": {}, "frame_descriptions": [], "timing": {}}

        if frame_paths:
            frame_total = 0.0
            for fp in frame_paths[:3]:
                with TimedOperation(f"frame_classify/{model_name}/{Path(fp).name}") as t:
                    result = classify_frame(fp, model_name)
                frame_total += t.elapsed
                model_entry["frame_descriptions"].append(result["description"])
            model_entry["timing"]["frame_classify_s"] = round(frame_total, 4)

        content_signals = {
            "metadata": entry["signals"].get("metadata", {}),
            "audio": entry["signals"].get("audio", {}),
            "frame_descriptions": model_entry["frame_descriptions"],
        }
        full_signals = dict(content_signals)
        full_signals["filename_hints"] = entry["signals"].get("filename_hints", {})
        if "nfo" in entry["signals"]:
            full_signals["nfo"] = entry["signals"]["nfo"]

        print(f"  Synthesizing identification with {model_name} (content-only)...")
        with TimedOperation(f"synthesis/content/{model_name}") as t:
            model_entry["content_only"] = synthesize_identification(content_signals, model_name)
        model_entry["timing"]["content_only_s"] = round(t.elapsed, 4)

        print(f"  Synthesizing identification with {model_name} (full-context)...")
        with TimedOperation(f"synthesis/full/{model_name}") as t:
            model_entry["full_context"] = synthesize_identification(full_signals, model_name)
        model_entry["timing"]["full_context_s"] = round(t.elapsed, 4)
        model_entry["timing"]["total_s"] = round(
            sum(v for v in model_entry["timing"].values() if isinstance(v, float)), 4
        )

        entry["model_runs"][model_name] = model_entry
        entry["timing"][f"{model_key}_total_s"] = model_entry["timing"]["total_s"]

    entry["timing"]["total_s"] = round(sum(v for v in entry["timing"].values() if isinstance(v, float)), 4)
    return entry


def evaluate_ground_truth(results: list[dict], models: list[str], truth: dict) -> dict:
    """Compute per-model title hit rates for one trial."""
    eval_summary = {}
    for model_name in models:
        content_hits = 0
        full_hits = 0
        total = 0
        for r in results:
            gt = truth.get(r.get("filename", ""))
            if not gt:
                continue
            total += 1
            runs = r.get("model_runs", {}).get(model_name, {})
            content_title = json.dumps(runs.get("content_only", {})).lower()
            full_title = json.dumps(runs.get("full_context", {})).lower()
            gt_title = (gt.get("title") or "").lower()
            if gt_title and gt_title in content_title:
                content_hits += 1
            if gt_title and gt_title in full_title:
                full_hits += 1
        eval_summary[model_name] = {
            "labeled_videos": total,
            "content_only_title_hit_rate": round(content_hits / max(total, 1), 4),
            "full_context_title_hit_rate": round(full_hits / max(total, 1), 4),
        }
    return eval_summary


def aggregate_eval_trials(eval_trials: list[dict], models: list[str]) -> dict:
    """Aggregate per-trial hit rates with confidence intervals."""
    out = {}
    for model_name in models:
        content_rates = []
        full_rates = []
        labeled_videos = 0
        for trial_eval in eval_trials:
            row = trial_eval.get(model_name, {})
            if not row:
                continue
            labeled_videos = max(labeled_videos, row.get("labeled_videos", 0))
            content_rates.append(row.get("content_only_title_hit_rate", 0.0))
            full_rates.append(row.get("full_context_title_hit_rate", 0.0))
        out[model_name] = {
            "labeled_videos": labeled_videos,
            "content_only_title_hit_rate": summarize_samples(content_rates)["mean"],
            "full_context_title_hit_rate": summarize_samples(full_rates)["mean"],
            "content_only_title_hit_rate_stats": summarize_samples(content_rates),
            "full_context_title_hit_rate_stats": summarize_samples(full_rates),
        }
    return out


def main():
    parser = argparse.ArgumentParser(description="Phase 4b video classification benchmark")
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="Comma-separated Ollama models",
    )
    parser.add_argument(
        "--max-videos",
        type=int,
        default=0,
        help="Optional cap on video files (0 = all)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Number of repeated trials for confidence intervals",
    )
    args = parser.parse_args()
    requested_models = [m.strip() for m in args.models.split(",") if m.strip()]
    repeats = max(args.repeats, 1)

    print("=" * 60)
    print("Phase 4b: Multi-Signal Video Classification")
    print("=" * 60)

    # Check available models
    available = []
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        available = [m["name"] for m in resp.json().get("models", [])]
    except Exception as e:
        print(f"  [ERROR] Cannot query Ollama models: {e}")
        return
    models = [m for m in requested_models if m in available]
    missing = [m for m in requested_models if m not in available]
    if missing:
        print(f"  [WARN] Unavailable models skipped: {missing}")
    if not models:
        print("No requested models available.")
        return

    prior = load_prior_results()
    videos = collect_test_files("video")
    if args.max_videos > 0:
        videos = videos[:args.max_videos]
    print(f"\nProcessing {len(videos)} video files...\n")

    trial_results = []
    trial_summaries = []
    trial_evals = []
    for trial_idx in range(1, repeats + 1):
        print(f"\n--- Trial {trial_idx}/{repeats} ---")
        results = []
        for filepath in videos:
            entry = process_video(filepath, prior, models)
            results.append(entry)

        timing_summary = {
            "total_videos": len(videos),
            "per_video_avg_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results) / max(len(results), 1), 4),
            "phase_total_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results), 4),
        }
        trial_results.append(results)
        trial_summaries.append({"trial": trial_idx, "timing_summary": timing_summary})

    output = {
        "phase": "4b_video_classification",
        "models": models,
        "missing_models": missing,
        "repeats": repeats,
        "total_videos": len(videos),
        "trial_summaries": trial_summaries,
        "results": trial_results[-1] if trial_results else [],
    }

    # Evaluate with optional ground truth
    truth = load_json(GROUND_TRUTH_PATH, default={}) or {}
    if truth:
        for idx, results in enumerate(trial_results, start=1):
            eval_summary = evaluate_ground_truth(results, models, truth)
            trial_evals.append(eval_summary)
            trial_summaries[idx - 1]["ground_truth_eval"] = eval_summary
        output["ground_truth_eval"] = aggregate_eval_trials(trial_evals, models)

    per_video_samples = [t["timing_summary"]["per_video_avg_s"] for t in trial_summaries]
    phase_total_samples = [t["timing_summary"]["phase_total_s"] for t in trial_summaries]
    per_video_stats = summarize_samples(per_video_samples)
    phase_total_stats = summarize_samples(phase_total_samples)
    output["timing_summary"] = {
        "total_videos": len(videos),
        "per_video_avg_s": per_video_stats["mean"],
        "phase_total_s": phase_total_stats["mean"],
        "per_video_avg_s_stats": per_video_stats,
        "phase_total_s_stats": phase_total_stats,
    }

    save_result(output, OUTPUT_DIR / "video_classification.json")

    print(f"\n{'=' * 60}")
    print("Phase 4b Complete — Video Identifications:")
    for r in output["results"]:
        for model_name in models:
            ident = r.get("model_runs", {}).get(model_name, {}).get("full_context", {})
            title = ident.get("title", "unknown")
            vtype = ident.get("type", "?")
            conf = ident.get("confidence", "?")
            print(f"  {r['filename']} [{model_name}]: {title} ({vtype}, confidence={conf})")
    if output.get("ground_truth_eval"):
        print("\nGround-truth title hit rates:")
        for model_name, stats in output["ground_truth_eval"].items():
            print(
                f"  {model_name}: content_only={stats['content_only_title_hit_rate']:.3f}, "
                f"full_context={stats['full_context_title_hit_rate']:.3f}"
            )
    print("=" * 60)


if __name__ == "__main__":
    main()
