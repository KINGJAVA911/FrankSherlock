#!/usr/bin/env python3
"""Phase 2c: Compare vision and tagging results with ground-truth labels."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    DOCS_DIR,
    RESULTS_DIR,
    extract_first_json_object,
    load_json,
    save_result,
)

OUTPUT_DIR = RESULTS_DIR / "phase2_images"
GROUND_TRUTH_PATH = DOCS_DIR / "ground_truth_images.json"


def normalize_series(value: str | None) -> str:
    return (value or "").strip().lower()


def normalize_file_key(path_value: str) -> str:
    path_value = (path_value or "").strip()
    if path_value.startswith("test_files/"):
        return path_value[len("test_files/"):]
    return path_value


def evaluate_ollama(ollama_data: dict, ground_truth: dict) -> dict:
    by_model = {}
    for entry in ollama_data.get("results", []):
        file_key = normalize_file_key(entry.get("file", ""))
        truth = ground_truth.get(file_key)
        if not truth:
            continue

        for model_name, prompts in entry.get("models", {}).items():
            stats = by_model.setdefault(model_name, {
                "files_with_labels": 0,
                "json_valid": 0,
                "type_correct": 0,
                "series_correct": 0,
                "series_files": 0,
                "errors": 0,
            })
            stats["files_with_labels"] += 1

            classify_raw = prompts.get("classify", {}).get("response", "")
            parsed = extract_first_json_object(classify_raw)
            if parsed:
                stats["json_valid"] += 1
                pred_type = (parsed.get("type") or "").strip().lower()
                true_type = (truth.get("type") or "").strip().lower()
                if pred_type == true_type:
                    stats["type_correct"] += 1

                if truth.get("anime_series") is not None:
                    stats["series_files"] += 1
                    pred_series = normalize_series(parsed.get("anime_series"))
                    true_series = normalize_series(truth.get("anime_series"))
                    if pred_series == true_series:
                        stats["series_correct"] += 1
            else:
                stats["errors"] += 1

    summary = {}
    for model_name, stats in by_model.items():
        labeled = max(stats["files_with_labels"], 1)
        series_files = max(stats["series_files"], 1)
        summary[model_name] = {
            **stats,
            "json_valid_rate": round(stats["json_valid"] / labeled, 4),
            "type_accuracy": round(stats["type_correct"] / labeled, 4),
            "series_accuracy": round(stats["series_correct"] / series_files, 4),
        }
    return summary


def evaluate_wd(wd_data: dict, ground_truth: dict) -> dict:
    model_stats = {}
    anime_positive_types = {"anime", "manga"}
    anime_cues = {"anime", "manga", "retro_artstyle"}

    for entry in wd_data.get("results", []):
        file_key = normalize_file_key(entry.get("file", ""))
        truth = ground_truth.get(file_key)
        if not truth:
            continue
        truth_is_anime = (truth.get("type") or "").lower() in anime_positive_types

        for model_name, model_out in entry.get("models", {}).items():
            if "error" in model_out:
                continue
            stats = model_stats.setdefault(model_name, {
                "files_with_labels": 0,
                "tp": 0,
                "tn": 0,
                "fp": 0,
                "fn": 0,
            })
            stats["files_with_labels"] += 1

            top_tags = set(model_out.get("top_general", []))
            predicted_anime = any(cue in top_tags for cue in anime_cues)

            if truth_is_anime and predicted_anime:
                stats["tp"] += 1
            elif truth_is_anime and not predicted_anime:
                stats["fn"] += 1
            elif not truth_is_anime and predicted_anime:
                stats["fp"] += 1
            else:
                stats["tn"] += 1

    summary = {}
    for model_name, stats in model_stats.items():
        total = max(stats["files_with_labels"], 1)
        tp = stats["tp"]
        fp = stats["fp"]
        fn = stats["fn"]
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        summary[model_name] = {
            **stats,
            "anime_detection_accuracy": round((stats["tp"] + stats["tn"]) / total, 4),
            "anime_detection_precision": round(precision, 4),
            "anime_detection_recall": round(recall, 4),
        }
    return summary


def main():
    print("=" * 60)
    print("Phase 2c: Image Benchmark Comparison")
    print("=" * 60)

    ollama_data = load_json(OUTPUT_DIR / "ollama_vision_results.json", default={}) or {}
    wd_data = load_json(OUTPUT_DIR / "wd_tagger_results.json", default={}) or {}
    ground_truth = load_json(GROUND_TRUTH_PATH, default={}) or {}

    if not ollama_data:
        print("Missing Ollama result file — run phase2a first.")
        return
    if not wd_data:
        print("Missing WD result file — run phase2b first.")
        return
    if not ground_truth:
        print(f"Missing ground-truth labels: {GROUND_TRUTH_PATH}")
        return

    ollama_eval = evaluate_ollama(ollama_data, ground_truth)
    wd_eval = evaluate_wd(wd_data, ground_truth)

    output = {
        "phase": "2c_comparison",
        "ground_truth_file": str(GROUND_TRUTH_PATH),
        "ground_truth_items": len(ground_truth),
        "ollama_eval": ollama_eval,
        "wd_eval": wd_eval,
        "timing_comparison": {
            "ollama": ollama_data.get("timing_summary", {}),
            "wd": wd_data.get("timing_summary", {}),
        },
    }
    save_result(output, OUTPUT_DIR / "comparison_report.json")

    print("\nOllama model ranking (type accuracy):")
    for model_name, stats in sorted(ollama_eval.items(), key=lambda i: i[1]["type_accuracy"], reverse=True):
        print(
            f"  {model_name}: type_acc={stats['type_accuracy']:.3f}, "
            f"series_acc={stats['series_accuracy']:.3f}, json_valid={stats['json_valid_rate']:.3f}"
        )

    print("\nWD model ranking (anime detection accuracy):")
    for model_name, stats in sorted(wd_eval.items(), key=lambda i: i[1]["anime_detection_accuracy"], reverse=True):
        print(
            f"  {model_name}: acc={stats['anime_detection_accuracy']:.3f}, "
            f"precision={stats['anime_detection_precision']:.3f}, recall={stats['anime_detection_recall']:.3f}"
        )


if __name__ == "__main__":
    main()
