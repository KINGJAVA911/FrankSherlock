#!/usr/bin/env python3
"""Phase 2c: Compare Ollama Vision vs WD Tagger results side-by-side."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import save_result, RESULTS_DIR

OUTPUT_DIR = RESULTS_DIR / "phase2_images"


def load_json(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"  [WARN] Not found: {path}")
        return None


def extract_ollama_summary(entry: dict) -> dict:
    """Extract key info from an Ollama vision result entry."""
    summary = {"descriptions": {}, "classifications": {}}
    for model, prompts in entry.get("models", {}).items():
        desc = prompts.get("describe", {}).get("response", "")
        summary["descriptions"][model] = desc[:300]

        classify_raw = prompts.get("classify", {}).get("response", "")
        try:
            # Try to parse JSON from response
            import re
            json_match = re.search(r'\{[^}]+\}', classify_raw, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                summary["classifications"][model] = parsed
            else:
                summary["classifications"][model] = classify_raw[:200]
        except (json.JSONDecodeError, AttributeError):
            summary["classifications"][model] = classify_raw[:200]

        anime = prompts.get("anime_check", {}).get("response", "")
        summary[f"anime_check_{model}"] = anime[:200]

    return summary


def extract_wd_summary(entry: dict) -> dict:
    """Extract key info from a WD Tagger result entry."""
    return {
        "top_tags": entry.get("top_general", []),
        "characters": entry.get("top_characters", []),
        "rating": entry.get("rating", []),
        "error": entry.get("error"),
    }


def score_identification(filename: str, ollama_entry: dict, wd_entry: dict) -> dict:
    """Score how well each tool identified the content based on filename hints."""
    filename_lower = filename.lower()
    scores = {"filename": filename, "ollama_score": 0, "wd_score": 0, "notes": []}

    # Known series from filenames
    series_hints = {
        "bastard": "Bastard!!", "gallf": "Gall Force", "gallforce": "Gall Force",
        "lodoss": "Record of Lodoss War", "miyukichan": "Miyuki-chan in Wonderland",
        "relena": "Gundam Wing", "treize": "Gundam Wing", "treune": "Gundam Wing",
        "ev_": "Evangelion", "megmpa": "Megami Paradise",
        "clamp": "CLAMP", "cd_": "anime CD artwork",
        "screenshot": "desktop screenshot",
        "capa": "anime cover", "cast": "anime cast",
        "sample": "anime sample", "insert": "CD insert",
        "elf_lite": "Elf/anime", "mp_": "anime",
    }

    detected_series = None
    for hint, series in series_hints.items():
        if hint in filename_lower:
            detected_series = series
            break

    if detected_series:
        # Check if Ollama mentions it
        ollama_text = json.dumps(ollama_entry).lower() if ollama_entry else ""
        wd_text = json.dumps(wd_entry).lower() if wd_entry else ""

        series_lower = detected_series.lower()
        if series_lower in ollama_text:
            scores["ollama_score"] = 1
            scores["notes"].append(f"Ollama identified '{detected_series}'")

        # WD Tagger uses booru tags, check for related tags
        wd_tags_text = " ".join(wd_entry.get("top_tags", [])) if wd_entry else ""
        if any(word in wd_tags_text for word in series_lower.split()):
            scores["wd_score"] = 1
            scores["notes"].append(f"WD Tagger tagged '{detected_series}'")

        scores["expected_series"] = detected_series

    return scores


def main():
    print("=" * 60)
    print("Phase 2c: Image Classification Comparison")
    print("=" * 60)

    ollama_data = load_json(OUTPUT_DIR / "ollama_vision_results.json")
    wd_data = load_json(OUTPUT_DIR / "wd_tagger_results.json")

    if not ollama_data or not wd_data:
        print("Missing data files — run phase2a and phase2b first.")
        return

    ollama_by_file = {r["filename"]: r for r in ollama_data.get("results", [])}
    wd_by_file = {r["filename"]: r for r in wd_data.get("results", [])}

    all_files = sorted(set(list(ollama_by_file.keys()) + list(wd_by_file.keys())))
    comparisons = []
    identification_scores = []

    for filename in all_files:
        ollama_entry = ollama_by_file.get(filename)
        wd_entry = wd_by_file.get(filename)

        comp = {
            "filename": filename,
            "ollama": extract_ollama_summary(ollama_entry) if ollama_entry else None,
            "wd_tagger": extract_wd_summary(wd_entry) if wd_entry else None,
        }
        comparisons.append(comp)

        score = score_identification(filename, ollama_entry, wd_entry)
        identification_scores.append(score)

    # Summary stats
    ollama_wins = sum(1 for s in identification_scores if s["ollama_score"] > s["wd_score"])
    wd_wins = sum(1 for s in identification_scores if s["wd_score"] > s["ollama_score"])
    ties = sum(1 for s in identification_scores if s["ollama_score"] == s["wd_score"])

    # Timing comparison from source data
    ollama_timing = ollama_data.get("timing_summary", {})
    wd_timing = wd_data.get("timing_summary", {})

    summary = {
        "total_images": len(all_files),
        "ollama_wins": ollama_wins,
        "wd_wins": wd_wins,
        "ties": ties,
        "note": "Wins based on series identification from filename hints",
        "timing_comparison": {
            "ollama_per_image_avg_s": ollama_timing.get("per_image_avg_s", "N/A"),
            "ollama_phase_total_s": ollama_timing.get("phase_total_s", "N/A"),
            "wd_tagger_per_image_avg_s": wd_timing.get("per_image_avg_s", "N/A"),
            "wd_tagger_phase_total_s": wd_timing.get("phase_total_s", "N/A"),
        },
    }

    output = {
        "phase": "2c_comparison",
        "summary": summary,
        "identification_scores": identification_scores,
        "comparisons": comparisons,
    }
    save_result(output, OUTPUT_DIR / "comparison_report.json")

    # Print readable summary
    print(f"\n{'=' * 60}")
    print(f"  Summary: Ollama wins={ollama_wins}, WD wins={wd_wins}, Ties={ties}")
    print(f"{'=' * 60}")
    print("\nPer-image highlights:")
    for score in identification_scores:
        if score.get("expected_series"):
            winner = "Ollama" if score["ollama_score"] > score["wd_score"] else \
                     "WD" if score["wd_score"] > score["ollama_score"] else "Tie"
            notes = "; ".join(score["notes"]) if score["notes"] else "neither identified"
            print(f"  {score['filename']}: expected='{score['expected_series']}' → {winner} ({notes})")
    print("=" * 60)


if __name__ == "__main__":
    main()
