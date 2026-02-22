#!/usr/bin/env python3
"""Phase 2b: WD Tagger (SwinV2) — anime-focused booru-style image tagging on GPU."""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from huggingface_hub import hf_hub_download
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, relative_path,
    save_result, RESULTS_DIR, load_benchmark_config,
)

OUTPUT_DIR = RESULTS_DIR / "phase2_images"
MODEL_FILENAME = "model.onnx"
LABEL_FILENAME = "selected_tags.csv"
IMAGE_SIZE = 448
CONFIDENCE_THRESHOLD = 0.35
DEFAULT_MODEL_REPOS = load_benchmark_config().get(
    "wd_tagger_models",
    ["SmilingWolf/wd-swinv2-tagger-v3"],
)


def download_model(model_repo: str) -> tuple[str, list[dict]]:
    """Download ONNX model and labels from HuggingFace."""
    print(f"Downloading WD Tagger model: {model_repo}")
    model_path = hf_hub_download(model_repo, MODEL_FILENAME)
    label_path = hf_hub_download(model_repo, LABEL_FILENAME)

    tags = []
    with open(label_path, "r") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            tags.append({"id": int(row[0]), "name": row[1], "category": int(row[2])})
    return model_path, tags


def preprocess_image(filepath: Path) -> np.ndarray:
    """Preprocess image for WD Tagger: resize, pad, normalize."""
    img = Image.open(filepath).convert("RGBA")

    # Composite onto white background
    background = Image.new("RGBA", img.size, (255, 255, 255, 255))
    background.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
    img = background.convert("RGB")

    # Resize maintaining aspect ratio, then pad
    max_dim = max(img.size)
    pad_x = (max_dim - img.size[0]) // 2
    pad_y = (max_dim - img.size[1]) // 2
    padded = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
    padded.paste(img, (pad_x, pad_y))
    img = padded.resize((IMAGE_SIZE, IMAGE_SIZE), Image.BICUBIC)

    # Convert to numpy, BGR, float32
    arr = np.array(img, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR
    return np.expand_dims(arr, axis=0)


def run_tagger(session, tags: list[dict], filepath: Path) -> dict:
    """Run WD Tagger on a single image."""
    input_data = preprocess_image(filepath)
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    probs = session.run([output_name], {input_name: input_data})[0][0]

    results = {"general": [], "character": [], "rating": []}
    # Category mapping: 0=general, 4=character, 9=rating
    cat_map = {0: "general", 4: "character", 9: "rating"}

    for i, tag in enumerate(tags):
        if i >= len(probs):
            break
        prob = float(probs[i])
        cat = cat_map.get(tag["category"], "general")
        if prob >= CONFIDENCE_THRESHOLD:
            results[cat].append({"tag": tag["name"], "confidence": round(prob, 4)})

    # Sort by confidence
    for cat in results:
        results[cat].sort(key=lambda x: x["confidence"], reverse=True)

    return results


def main():
    parser = argparse.ArgumentParser(description="Phase 2b WD tagger benchmark")
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODEL_REPOS),
        help="Comma-separated HF repos for WD tagger models",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=0,
        help="Optional cap for number of images (0 = all)",
    )
    args = parser.parse_args()
    model_repos = [m.strip() for m in args.models.split(",") if m.strip()]

    print("=" * 60)
    print("Phase 2b: WD Tagger (SwinV2) Image Classification")
    print("=" * 60)

    # Init ONNX Runtime with CUDA
    import onnxruntime as ort
    providers = ort.get_available_providers()
    print(f"ONNX providers: {providers}")

    sessions = {}
    tags_by_model = {}
    model_errors = {}
    for model_repo in model_repos:
        try:
            model_path, tags = download_model(model_repo)
            use_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            session = ort.InferenceSession(model_path, providers=use_providers)
            sessions[model_repo] = session
            tags_by_model[model_repo] = tags
            print(f"  Loaded {model_repo} ({len(tags)} tags) providers={session.get_providers()}")
        except Exception as e:
            model_errors[model_repo] = str(e)
            print(f"  [ERROR] Failed to load {model_repo}: {e}")

    if not sessions:
        print("No WD tagger models loaded successfully.")
        return

    images = collect_test_files("image")
    if args.max_images > 0:
        images = images[:args.max_images]
    print(f"\nProcessing {len(images)} images...\n")

    results = []
    for filepath in images:
        rel = relative_path(filepath)
        print(f"\n--- {rel} ---")
        entry = {
            "file": rel,
            "filename": filepath.name,
            "models": {},
            "timing": {},
        }
        for model_repo, session in sessions.items():
            try:
                with TimedOperation(f"{model_repo}/{filepath.name}") as t:
                    tag_result = run_tagger(session, tags_by_model[model_repo], filepath)
                entry["models"][model_repo] = {
                    "tags": tag_result,
                    "top_general": [t_tag["tag"] for t_tag in tag_result["general"][:10]],
                    "top_characters": [t_tag["tag"] for t_tag in tag_result["character"][:5]],
                    "rating": tag_result["rating"],
                }
                entry["timing"][f"{model_repo}_s"] = round(t.elapsed, 4)
            except Exception as e:
                entry["models"][model_repo] = {"error": str(e)}
                print(f"  [ERROR] {model_repo}: {e}")
        entry["timing"]["total_s"] = round(
            sum(v for v in entry["timing"].values() if isinstance(v, float)), 4
        )
        results.append(entry)

    # Timing summary
    timing_by_model = {}
    for r in results:
        for key, val in r.get("timing", {}).items():
            if key.endswith("_s") and key != "total_s":
                timing_by_model.setdefault(key, []).append(val)

    inference_times = [v for vals in timing_by_model.values() for v in vals]
    timing_summary = {
        "total_images": len(images),
        "per_image_avg_s": round(sum(inference_times) / max(len(inference_times), 1), 4),
        "per_image_min_s": round(min(inference_times), 4) if inference_times else 0,
        "per_image_max_s": round(max(inference_times), 4) if inference_times else 0,
        "phase_total_s": round(sum(inference_times), 4),
        "per_model_avg_s": {k: round(sum(v) / len(v), 4) for k, v in timing_by_model.items()},
    }

    output = {
        "phase": "2b_wd_tagger",
        "models": list(sessions.keys()),
        "model_errors": model_errors,
        "threshold": CONFIDENCE_THRESHOLD,
        "total_images": len(images),
        "timing_summary": timing_summary,
        "results": results,
    }
    save_result(output, OUTPUT_DIR / "wd_tagger_results.json")

    print(f"\n{'=' * 60}")
    print(f"Phase 2b Complete: {len(results)} images tagged")
    print("=" * 60)


if __name__ == "__main__":
    main()
