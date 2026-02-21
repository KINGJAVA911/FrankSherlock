#!/usr/bin/env python3
"""Phase 3c: Compare Chromaprint/AcoustID vs Whisper audio recognition results."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import save_result, RESULTS_DIR

OUTPUT_DIR = RESULTS_DIR / "phase3_audio"


def load_json(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"  [WARN] Not found: {path}")
        return None


def extract_chromaprint_summary(entry: dict) -> dict:
    """Summarize chromaprint/acoustid results."""
    fp = entry.get("fingerprint", {})
    acoustid = entry.get("acoustid", {})
    has_fp = bool(fp.get("fingerprint"))
    duration = fp.get("duration", 0)

    # Check for AcoustID matches
    matches = []
    if isinstance(acoustid, dict):
        for result in acoustid.get("results", []):
            for rec in result.get("recordings", []):
                matches.append({
                    "title": rec.get("title", ""),
                    "artists": [a.get("name", "") for a in rec.get("artists", [])],
                    "score": result.get("score", 0),
                })

    return {
        "has_fingerprint": has_fp,
        "duration": duration,
        "acoustid_matches": matches,
        "acoustid_status": acoustid.get("status", "unknown") if isinstance(acoustid, dict) else "error",
    }


def extract_whisper_summary(entry: dict) -> dict:
    """Summarize whisper transcription results."""
    summary = {"models": {}}

    for model_name, data in entry.get("models", {}).items():
        if isinstance(data, dict) and "text" in data:
            summary["models"][model_name] = {
                "language": data.get("language", "unknown"),
                "text_preview": data["text"][:200],
                "num_segments": len(data.get("segments", [])),
            }
        elif isinstance(data, dict) and "error" in data:
            summary["models"][model_name] = {"error": data["error"]}

    # Also handle segment-based results (long videos)
    for seg_name, seg_data in entry.get("segments", {}).items():
        for model_name, data in seg_data.get("models", {}).items():
            key = f"{model_name}_{seg_name}"
            if isinstance(data, dict) and "text" in data:
                summary["models"][key] = {
                    "language": data.get("language", "unknown"),
                    "text_preview": data["text"][:200],
                }

    return summary


def main():
    print("=" * 60)
    print("Phase 3c: Audio Recognition Comparison")
    print("=" * 60)

    chromaprint_data = load_json(OUTPUT_DIR / "chromaprint_results.json")
    whisper_data = load_json(OUTPUT_DIR / "whisper_results.json")

    if not chromaprint_data or not whisper_data:
        print("Missing data files — run phase3a and phase3b first.")
        return

    chromaprint_by_file = {r["filename"]: r for r in chromaprint_data.get("results", [])}
    whisper_by_file = {r["filename"]: r for r in whisper_data.get("results", [])}

    all_files = sorted(set(list(chromaprint_by_file.keys()) + list(whisper_by_file.keys())))

    comparisons = []
    for filename in all_files:
        cp_entry = chromaprint_by_file.get(filename)
        wh_entry = whisper_by_file.get(filename)

        cp_summary = extract_chromaprint_summary(cp_entry) if cp_entry else None
        wh_summary = extract_whisper_summary(wh_entry) if wh_entry else None

        # Determine which tool was more useful
        cp_useful = False
        wh_useful = False

        if cp_summary:
            cp_useful = bool(cp_summary.get("acoustid_matches"))
        if wh_summary:
            for model_data in wh_summary.get("models", {}).values():
                if isinstance(model_data, dict) and model_data.get("text_preview", "").strip():
                    wh_useful = True
                    break

        winner = "tie"
        if cp_useful and not wh_useful:
            winner = "chromaprint"
        elif wh_useful and not cp_useful:
            winner = "whisper"
        elif cp_useful and wh_useful:
            winner = "both"

        comparisons.append({
            "filename": filename,
            "source_video": (cp_entry.get("source_video") if cp_entry else None) or (wh_entry.get("source_video") if wh_entry else None),
            "chromaprint": cp_summary,
            "whisper": wh_summary,
            "winner": winner,
        })

    # Summary
    winners = {"chromaprint": 0, "whisper": 0, "both": 0, "tie": 0}
    for c in comparisons:
        winners[c["winner"]] += 1

    # Timing comparison from source data
    chromaprint_timing = chromaprint_data.get("timing_summary", {})
    whisper_timing = whisper_data.get("timing_summary", {})

    output = {
        "phase": "3c_comparison",
        "summary": {
            "total_files": len(comparisons),
            "winners": winners,
            "timing_comparison": {
                "chromaprint_per_file_avg_s": chromaprint_timing.get("per_file_avg_s", "N/A"),
                "chromaprint_phase_total_s": chromaprint_timing.get("phase_total_s", "N/A"),
                "whisper_per_file_avg_s": whisper_timing.get("per_file_avg_s", "N/A"),
                "whisper_phase_total_s": whisper_timing.get("phase_total_s", "N/A"),
            },
        },
        "comparisons": comparisons,
    }
    save_result(output, OUTPUT_DIR / "comparison_report.json")

    print(f"\n{'=' * 60}")
    print(f"  Summary: {winners}")
    print(f"{'=' * 60}")
    print("\nPer-file results:")
    for c in comparisons:
        src = f" (from {c['source_video']})" if c.get("source_video") else ""
        print(f"  {c['filename']}{src}: {c['winner']}")
        if c["whisper"]:
            for model, data in c["whisper"]["models"].items():
                if isinstance(data, dict) and "language" in data:
                    print(f"    whisper-{model}: lang={data['language']}, text='{data.get('text_preview', '')[:80]}'")
        if c["chromaprint"] and c["chromaprint"]["acoustid_matches"]:
            for m in c["chromaprint"]["acoustid_matches"][:2]:
                print(f"    acoustid: {m['title']} by {m['artists']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
