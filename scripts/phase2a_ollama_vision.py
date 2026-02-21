#!/usr/bin/env python3
"""Phase 2a: Image classification using Ollama vision LLMs (qwen2.5vl:7b + llava:13b)."""

import base64
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, relative_path,
    save_result, RESULTS_DIR,
)

OUTPUT_DIR = RESULTS_DIR / "phase2_images"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODELS = ["qwen2.5vl:7b", "llava:13b"]

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


def query_ollama(model: str, prompt: str, image_b64: str) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return {
            "response": data.get("response", ""),
            "total_duration_ms": data.get("total_duration", 0) / 1e6,
            "eval_count": data.get("eval_count", 0),
        }
    except Exception as e:
        return {"error": str(e)}


def process_image(filepath: Path) -> dict:
    rel = relative_path(filepath)
    print(f"\n--- {rel} ---")

    image_b64 = encode_image(filepath)
    entry = {"file": rel, "filename": filepath.name, "models": {}, "timing": {}}

    for model in MODELS:
        entry["models"][model] = {}
        for prompt_name, prompt_text in PROMPTS.items():
            label = f"{model}/{prompt_name}/{filepath.name}"
            with TimedOperation(label) as t:
                result = query_ollama(model, prompt_text, image_b64)
            result["wall_clock_s"] = round(t.elapsed, 4)
            entry["models"][model][prompt_name] = result
            entry["timing"][f"{model}/{prompt_name}"] = round(t.elapsed, 4)

    entry["timing"]["total_s"] = round(sum(
        v for k, v in entry["timing"].items() if k != "total_s"
    ), 4)
    return entry


def main():
    print("=" * 60)
    print("Phase 2a: Ollama Vision LLM Image Classification")
    print("=" * 60)

    images = collect_test_files("image")
    print(f"\nProcessing {len(images)} images x {len(MODELS)} models x {len(PROMPTS)} prompts")
    print(f"= {len(images) * len(MODELS) * len(PROMPTS)} total LLM calls\n")

    # Verify models are available
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        available = [m["name"] for m in resp.json().get("models", [])]
        for model in MODELS:
            if model not in available:
                print(f"  [WARN] Model {model} not found. Available: {available}")
    except Exception as e:
        print(f"  [ERROR] Cannot reach Ollama: {e}")
        return

    results = []
    for filepath in images:
        entry = process_image(filepath)
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
        "total_calls": len(images) * len(MODELS) * len(PROMPTS),
        "per_model_prompt_avg_s": {k: round(sum(v) / len(v), 4) for k, v in timing_by_model_prompt.items()},
        "per_image_avg_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results) / max(len(results), 1), 4),
        "phase_total_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results), 4),
    }

    output = {
        "phase": "2a_ollama_vision",
        "models": MODELS,
        "prompts": list(PROMPTS.keys()),
        "total_images": len(images),
        "total_calls": len(images) * len(MODELS) * len(PROMPTS),
        "timing_summary": timing_summary,
        "results": results,
    }
    save_result(output, OUTPUT_DIR / "ollama_vision_results.json")

    print(f"\n{'=' * 60}")
    print(f"Phase 2a Complete: {len(results)} images processed")
    print("=" * 60)


if __name__ == "__main__":
    main()
