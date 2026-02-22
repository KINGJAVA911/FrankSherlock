#!/usr/bin/env python3
"""Phase 2a: Image classification using Ollama vision LLMs (qwen2.5vl:7b + llava:13b)."""

import argparse
import base64
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, relative_path,
    save_result, RESULTS_DIR, load_benchmark_config, DOCS_DIR, load_json, PROJECT_ROOT,
)

OUTPUT_DIR = RESULTS_DIR / "phase2_images"
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODELS = load_benchmark_config().get("vision_models", ["qwen2.5vl:7b", "llava:13b"])

PROMPTS = {
    "describe": (
        "Describe this image in detail. What do you see? "
        "If it's anime/manga art, identify the style, characters, series if possible. "
        "If it's a screenshot, describe the application and content visible."
    ),
    "classify": (
        "Classify this image. Respond ONLY with valid JSON (no markdown) using this schema: "
        '{"type": "screenshot|anime|manga|photo|artwork|other", '
        '"anime_series": "name or null", "characters": ["name"], '
        '"description": "brief description", "art_style": "digital|cel|manga|photo|pixel", '
        '"confidence": 0.0-1.0}'
    ),
    "anime_check": (
        "Is this image from an anime or manga? If yes, identify: "
        "1) The specific anime/manga series name "
        "2) Any character names visible "
        "3) Whether this is official art, fan art, a scan, or a screenshot "
        "Answer concisely."
    ),
}


def encode_image(filepath: Path) -> str:
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _query_ollama_payload(payload: dict) -> dict:
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return {
        "response": data.get("response", ""),
        "total_duration_ms": data.get("total_duration", 0) / 1e6,
        "eval_count": data.get("eval_count", 0),
    }


def query_ollama(model: str, prompt: str, image_b64: str, json_mode: bool = False) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512},
    }
    if json_mode:
        payload["format"] = "json"
    try:
        return _query_ollama_payload(payload)
    except Exception as e:
        # Some models reject JSON mode; retry once without it.
        if json_mode:
            payload.pop("format", None)
            try:
                result = _query_ollama_payload(payload)
                result["json_mode_fallback_used"] = True
                return result
            except Exception:
                pass
        return {"error": str(e)}


def process_image(filepath: Path, models: list[str], prompts: dict[str, str]) -> dict:
    rel = relative_path(filepath)
    print(f"\n--- {rel} ---")

    image_b64 = encode_image(filepath)
    entry = {"file": rel, "filename": filepath.name, "models": {}, "timing": {}}

    for model in models:
        entry["models"][model] = {}
        for prompt_name, prompt_text in prompts.items():
            label = f"{model}/{prompt_name}/{filepath.name}"
            with TimedOperation(label) as t:
                result = query_ollama(
                    model,
                    prompt_text,
                    image_b64,
                    json_mode=False,
                )
            result["wall_clock_s"] = round(t.elapsed, 4)
            entry["models"][model][prompt_name] = result
            entry["timing"][f"{model}/{prompt_name}"] = round(t.elapsed, 4)

    entry["timing"]["total_s"] = round(sum(
        v for k, v in entry["timing"].items() if k != "total_s"
    ), 4)
    return entry


def main():
    parser = argparse.ArgumentParser(description="Phase 2a Ollama vision benchmark")
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="Comma-separated Ollama models to benchmark",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=0,
        help="Optional cap for number of images (0 = all)",
    )
    parser.add_argument(
        "--prompts",
        default="describe,classify,anime_check",
        help="Comma-separated prompt keys to run",
    )
    parser.add_argument(
        "--ground-truth-only",
        action="store_true",
        help="Benchmark only files listed in docs/ground_truth_images.json",
    )
    args = parser.parse_args()

    requested_models = [m.strip() for m in args.models.split(",") if m.strip()]
    selected_prompts = [p.strip() for p in args.prompts.split(",") if p.strip() in PROMPTS]
    if not selected_prompts:
        print("  [ERROR] No valid prompts selected.")
        return

    print("=" * 60)
    print("Phase 2a: Ollama Vision LLM Image Classification")
    print("=" * 60)

    if args.ground_truth_only:
        truth = load_json(DOCS_DIR / "ground_truth_images.json", default={}) or {}
        images = []
        for rel in sorted(truth.keys()):
            p = PROJECT_ROOT / "test_files" / rel
            if p.exists():
                images.append(p)
        if not images:
            print("  [ERROR] Ground-truth file list is empty or files are missing.")
            return
    else:
        images = collect_test_files("image")
    if args.max_images > 0:
        images = images[:args.max_images]

    # Verify models are available
    available = []
    unavailable = []
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        available = [m["name"] for m in resp.json().get("models", [])]
    except Exception as e:
        print(f"  [ERROR] Cannot reach Ollama: {e}")
        return

    models = [m for m in requested_models if m in available]
    unavailable = [m for m in requested_models if m not in available]
    if unavailable:
        print(f"  [WARN] Unavailable models skipped: {unavailable}")
    if not models:
        print("  [ERROR] No requested models are available in Ollama.")
        return

    print(f"\nProcessing {len(images)} images x {len(models)} models x {len(selected_prompts)} prompts")
    print(f"= {len(images) * len(models) * len(selected_prompts)} total LLM calls\n")

    selected_prompt_map = {k: PROMPTS[k] for k in selected_prompts}
    results = []
    for filepath in images:
        entry = process_image(filepath, models, selected_prompt_map)
        results.append(entry)
        # Save incrementally
        save_result(results, OUTPUT_DIR / "ollama_vision_results.json")

    # Timing summary
    timing_by_model_prompt = {}
    for r in results:
        for key, val in r.get("timing", {}).items():
            if key == "total_s":
                continue
            timing_by_model_prompt.setdefault(key, []).append(val)
    timing_summary = {
        "total_images": len(images),
        "total_calls": len(images) * len(models) * len(selected_prompts),
        "per_model_prompt_avg_s": {k: round(sum(v) / len(v), 4) for k, v in timing_by_model_prompt.items()},
        "per_image_avg_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results) / max(len(results), 1), 4),
        "phase_total_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results), 4),
    }

    output = {
        "phase": "2a_ollama_vision",
        "requested_models": requested_models,
        "models": models,
        "unavailable_models": unavailable,
        "prompts": selected_prompts,
        "total_images": len(images),
        "total_calls": len(images) * len(models) * len(selected_prompts),
        "timing_summary": timing_summary,
        "results": results,
    }
    save_result(output, OUTPUT_DIR / "ollama_vision_results.json")

    print(f"\n{'=' * 60}")
    print(f"Phase 2a Complete: {len(results)} images processed")
    print("=" * 60)


if __name__ == "__main__":
    main()
