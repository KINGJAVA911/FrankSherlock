#!/usr/bin/env python3
"""Phase 2b: WD Tagger (SwinV2) — anime-focused booru-style image tagging on GPU."""

import csv
import sys
from pathlib import Path

import numpy as np
from huggingface_hub import hf_hub_download
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, relative_path,
    save_result, RESULTS_DIR,
)

OUTPUT_DIR = RESULTS_DIR / "phase2_images"
MODEL_REPO = "SmilingWolf/wd-swinv2-tagger-v3"
MODEL_FILENAME = "model.onnx"
LABEL_FILENAME = "selected_tags.csv"
IMAGE_SIZE = 448
CONFIDENCE_THRESHOLD = 0.35


def download_model() -> tuple[str, list[dict]]:
    """Download ONNX model and labels from HuggingFace."""
    print("Downloading WD Tagger model...")
    model_path = hf_hub_download(MODEL_REPO, MODEL_FILENAME)
    label_path = hf_hub_download(MODEL_REPO, LABEL_FILENAME)

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
    print("=" * 60)
    print("Phase 2b: WD Tagger (SwinV2) Image Classification")
    print("=" * 60)

    model_path, tags = download_model()
    print(f"Model: {model_path}")
    print(f"Tags: {len(tags)} total")

    # Init ONNX Runtime with CUDA
    import onnxruntime as ort
    providers = ort.get_available_providers()
    print(f"ONNX providers: {providers}")

    use_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    session = ort.InferenceSession(model_path, providers=use_providers)
    actual = session.get_providers()
    print(f"Using: {actual}")

    images = collect_test_files("image")
    print(f"\nProcessing {len(images)} images...\n")

    results = []
    for filepath in images:
        rel = relative_path(filepath)
        print(f"\n--- {rel} ---")
        try:
            with TimedOperation(f"wd_tagger/{filepath.name}") as t:
                tag_result = run_tagger(session, tags, filepath)
            entry = {
                "file": rel,
                "filename": filepath.name,
                "tags": tag_result,
                "top_general": [t_tag["tag"] for t_tag in tag_result["general"][:10]],
                "top_characters": [t_tag["tag"] for t_tag in tag_result["character"][:5]],
                "rating": tag_result["rating"],
                "timing": {"inference_s": round(t.elapsed, 4)},
            }
        except Exception as e:
            entry = {"file": rel, "filename": filepath.name, "error": str(e), "timing": {}}
            print(f"  [ERROR] {e}")
        results.append(entry)

    # Timing summary
    inference_times = [r["timing"]["inference_s"] for r in results if r.get("timing", {}).get("inference_s")]
    timing_summary = {
        "total_images": len(images),
        "per_image_avg_s": round(sum(inference_times) / max(len(inference_times), 1), 4),
        "per_image_min_s": round(min(inference_times), 4) if inference_times else 0,
        "per_image_max_s": round(max(inference_times), 4) if inference_times else 0,
        "phase_total_s": round(sum(inference_times), 4),
    }

    output = {
        "phase": "2b_wd_tagger",
        "model": MODEL_REPO,
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
