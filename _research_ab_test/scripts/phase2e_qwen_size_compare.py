#!/usr/bin/env python3
"""Phase 2e: Controlled Qwen size comparison on labeled image subset."""

import argparse
import base64
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    DOCS_DIR,
    PROJECT_ROOT,
    RESULTS_DIR,
    extract_first_json_object,
    save_result,
    summarize_samples,
)

OLLAMA_URL = "http://localhost:11434/api/generate"
OUTPUT_DIR = RESULTS_DIR / "phase2_images"
GROUND_TRUTH_PATH = DOCS_DIR / "ground_truth_images.json"

CLASSIFY_PROMPT = (
    "Classify this image. Respond ONLY with valid JSON (no markdown) using this schema: "
    '{"type": "screenshot|anime|manga|photo|document|artwork|other", '
    '"anime_series": "name or null", "characters": ["name"], '
    '"description": "brief description", "art_style": "digital|cel|manga|photo|pixel|other", '
    '"confidence": 0.0-1.0}'
)


def normalize_file_key(path_value: str) -> str:
    path_value = (path_value or "").strip()
    if path_value.startswith("test_files/"):
        return path_value[len("test_files/"):]
    return path_value


def normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def call_ollama(model: str, image_b64: str) -> dict:
    payload = {
        "model": model,
        "prompt": CLASSIFY_PROMPT,
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=240)
        resp.raise_for_status()
        data = resp.json()
        return {
            "response": data.get("response", ""),
            "total_duration_ms": data.get("total_duration", 0) / 1e6,
        }
    except Exception as e:
        return {"error": str(e)}


def run_model_on_truth(model: str, truth: dict, repeat_index: int, repeats: int) -> dict:
    print(f"\n=== Running model: {model} (trial {repeat_index}/{repeats}) ===")
    results = []
    for rel in sorted(truth.keys()):
        image_path = PROJECT_ROOT / "test_files" / rel
        if not image_path.exists():
            continue
        print(f"  - {rel}")
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        out = call_ollama(model, image_b64)
        results.append({
            "file": f"test_files/{rel}",
            "filename": image_path.name,
            "classify": out,
        })
    return {"model": model, "trial": repeat_index, "results": results}


def evaluate_model(run_data: dict, truth: dict) -> dict:
    stats = {
        "model": run_data["model"],
        "files_with_labels": 0,
        "json_valid": 0,
        "type_correct": 0,
        "series_correct": 0,
        "series_files": 0,
        "errors": 0,
        "wall_clock_total_s": 0.0,
        "wall_clock_avg_s": 0.0,
    }
    latencies = []
    for entry in run_data.get("results", []):
        key = normalize_file_key(entry.get("file", ""))
        expected = truth.get(key)
        if not expected:
            continue
        stats["files_with_labels"] += 1
        result = entry.get("classify", {})
        if "error" in result:
            stats["errors"] += 1
            continue

        # Ollama reports nanoseconds; we store milliseconds in `total_duration_ms`.
        # Convert to seconds for human-facing latency metrics.
        latencies.append(float(result.get("total_duration_ms", 0)) / 1000.0)
        parsed = extract_first_json_object(result.get("response", ""))
        if not parsed:
            stats["errors"] += 1
            continue

        stats["json_valid"] += 1

        pred_type = normalize_text(parsed.get("type"))
        true_type = normalize_text(expected.get("type"))
        if pred_type == true_type:
            stats["type_correct"] += 1

        true_series_raw = expected.get("anime_series")
        if true_series_raw is not None:
            stats["series_files"] += 1
            pred_series = normalize_text(parsed.get("anime_series"))
            true_series = normalize_text(true_series_raw)
            if pred_series == true_series:
                stats["series_correct"] += 1

    labeled = max(stats["files_with_labels"], 1)
    series_files = max(stats["series_files"], 1)
    stats["json_valid_rate"] = round(stats["json_valid"] / labeled, 4)
    stats["type_accuracy"] = round(stats["type_correct"] / labeled, 4)
    stats["series_accuracy"] = round(stats["series_correct"] / series_files, 4)
    stats["wall_clock_total_s"] = round(sum(latencies), 4)
    stats["wall_clock_avg_s"] = round(sum(latencies) / max(len(latencies), 1), 4)
    return stats


def aggregate_trials(model_name: str, trial_stats: list[dict]) -> dict:
    type_acc = [t.get("type_accuracy", 0.0) for t in trial_stats]
    series_acc = [t.get("series_accuracy", 0.0) for t in trial_stats]
    json_valid = [t.get("json_valid_rate", 0.0) for t in trial_stats]
    latency = [t.get("wall_clock_avg_s", 0.0) for t in trial_stats]
    errors = [t.get("errors", 0) for t in trial_stats]

    type_summary = summarize_samples(type_acc)
    series_summary = summarize_samples(series_acc)
    json_summary = summarize_samples(json_valid)
    latency_summary = summarize_samples(latency)

    return {
        "model": model_name,
        "repeats": len(trial_stats),
        "files_with_labels": trial_stats[0].get("files_with_labels", 0) if trial_stats else 0,
        "series_files": trial_stats[0].get("series_files", 0) if trial_stats else 0,
        "type_accuracy": type_summary["mean"],
        "series_accuracy": series_summary["mean"],
        "json_valid_rate": json_summary["mean"],
        "wall_clock_avg_s": latency_summary["mean"],
        "errors_avg": round(sum(errors) / max(len(errors), 1), 4),
        "type_accuracy_stats": type_summary,
        "series_accuracy_stats": series_summary,
        "json_valid_rate_stats": json_summary,
        "wall_clock_avg_s_stats": latency_summary,
        "trial_stats": trial_stats,
    }


def main():
    parser = argparse.ArgumentParser(description="Phase 2e Qwen size comparison")
    parser.add_argument(
        "--models",
        default="qwen2.5vl:7b,qwen3-vl:8b,qwen3-vl:30b-a3b",
        help="Comma-separated Ollama models to compare",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Number of repeated runs per model for confidence intervals",
    )
    args = parser.parse_args()

    requested_models = [m.strip() for m in args.models.split(",") if m.strip()]
    repeats = max(args.repeats, 1)

    with open(GROUND_TRUTH_PATH) as f:
        truth = json.load(f)

    model_runs = []
    trial_stats_by_model = {m: [] for m in requested_models}
    for model in requested_models:
        for i in range(1, repeats + 1):
            run_data = run_model_on_truth(model, truth, i, repeats)
            model_runs.append(run_data)
            trial_stats_by_model[model].append(evaluate_model(run_data, truth))

    model_stats = [aggregate_trials(model_name, stats) for model_name, stats in trial_stats_by_model.items()]
    by_name = {row["model"]: row for row in model_stats}

    summary = {
        "phase": "2e_qwen_size_compare",
        "ground_truth_file": str(GROUND_TRUTH_PATH),
        "ground_truth_items": len(truth),
        "repeats": repeats,
        "models": model_stats,
        "speed_ratios_vs_7b": {},
        "type_accuracy_delta_vs_7b": {},
        "series_accuracy_delta_vs_7b": {},
        "speed_ratio_32b_vs_7b": None,
        "type_accuracy_delta_32b_minus_7b": None,
        "series_accuracy_delta_32b_minus_7b": None,
        "raw_runs": model_runs,
    }

    if "qwen2.5vl:7b" in by_name:
        m7 = by_name["qwen2.5vl:7b"]
        for name, row in by_name.items():
            if name == "qwen2.5vl:7b":
                continue
            if m7["wall_clock_avg_s"] > 0:
                summary["speed_ratios_vs_7b"][name] = round(row["wall_clock_avg_s"] / m7["wall_clock_avg_s"], 2)
            summary["type_accuracy_delta_vs_7b"][name] = round(row["type_accuracy"] - m7["type_accuracy"], 4)
            summary["series_accuracy_delta_vs_7b"][name] = round(row["series_accuracy"] - m7["series_accuracy"], 4)

    if "qwen2.5vl:7b" in by_name and "qwen2.5vl:32b" in by_name:
        m7 = by_name["qwen2.5vl:7b"]
        m32 = by_name["qwen2.5vl:32b"]
        if m7["wall_clock_avg_s"] > 0:
            summary["speed_ratio_32b_vs_7b"] = round(m32["wall_clock_avg_s"] / m7["wall_clock_avg_s"], 2)
        summary["type_accuracy_delta_32b_minus_7b"] = round(m32["type_accuracy"] - m7["type_accuracy"], 4)
        summary["series_accuracy_delta_32b_minus_7b"] = round(m32["series_accuracy"] - m7["series_accuracy"], 4)

    output_path = OUTPUT_DIR / "qwen_size_compare_report.json"
    save_result(summary, output_path)

    print(f"\nModel comparison summary (repeats={repeats}):")
    for row in model_stats:
        type_ci = row["type_accuracy_stats"]
        speed_ci = row["wall_clock_avg_s_stats"]
        print(
            f"  {row['model']}: type_acc={row['type_accuracy']:.4f}, "
            f"series_acc={row['series_accuracy']:.4f}, avg_s={row['wall_clock_avg_s']:.4f}, "
            f"json_valid={row['json_valid_rate']:.4f}, "
            f"type_ci95=[{type_ci['ci95_low']:.4f},{type_ci['ci95_high']:.4f}], "
            f"lat_ci95=[{speed_ci['ci95_low']:.4f},{speed_ci['ci95_high']:.4f}]"
        )
    if summary["speed_ratios_vs_7b"]:
        print("\nDeltas vs qwen2.5vl:7b:")
        for name in sorted(summary["speed_ratios_vs_7b"].keys()):
            print(
                f"  {name}: speed_ratio={summary['speed_ratios_vs_7b'][name]}x, "
                f"type_delta={summary['type_accuracy_delta_vs_7b'][name]}, "
                f"series_delta={summary['series_accuracy_delta_vs_7b'][name]}"
            )


if __name__ == "__main__":
    main()
