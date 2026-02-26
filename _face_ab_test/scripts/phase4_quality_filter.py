#!/usr/bin/env python3
"""Phase 4: Test quality filtering strategies to reduce noise in face detection."""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    RESULTS_DIR,
    TimedOperation,
    collect_test_images,
    compute_detection_metrics,
    load_config,
    load_ground_truth,
    load_image,
    relative_path,
    save_result,
)

OUTPUT_FILE = RESULTS_DIR / "phase4_quality_filter.json"


def compute_blur_score(face_crop: np.ndarray) -> float:
    """Compute Laplacian variance as blur metric (higher = sharper)."""
    gray = cv2.cvtColor(face_crop, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def face_size_px(bbox: list) -> int:
    """Return the minimum dimension of a face bounding box."""
    _, _, w, h = bbox
    return min(w, h)


def _detect_all_faces(images: list[Path], config: dict) -> list[dict]:
    """Detect all faces across all images using SCRFD.

    Returns list of dicts with keys: file, bbox, confidence, face_crop, blur_score, face_size.
    """
    from insightface.app import FaceAnalysis

    det_cfg = config.get("detection", {}).get("scrfd", {})
    det_size = tuple(det_cfg.get("det_size", [640, 640]))

    print("Initializing SCRFD detector...")
    app = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=det_size)

    all_faces = []

    for img_path in images:
        try:
            img = load_image(img_path)
            with TimedOperation(f"detect {img_path.name}") as t:
                faces = app.get(img)

            h, w = img.shape[:2]

            for i, face in enumerate(faces):
                x1, y1, x2, y2 = face.bbox.astype(int).tolist()
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                if x2 <= x1 or y2 <= y1:
                    continue

                face_crop = img[y1:y2, x1:x2]
                bbox = [x1, y1, x2 - x1, y2 - y1]

                all_faces.append({
                    "file": img_path.name,
                    "face_idx": i,
                    "bbox": bbox,
                    "confidence": round(float(face.det_score), 4),
                    "face_crop": face_crop,
                    "blur_score": round(compute_blur_score(face_crop), 2),
                    "face_size": face_size_px(bbox),
                    "embedding_norm": round(float(np.linalg.norm(face.embedding)), 4) if face.embedding is not None else None,
                })

        except Exception as e:
            print(f"  ERROR: {img_path.name} — {e}")

    return all_faces


def evaluate_filter(
    all_faces: list[dict],
    ground_truth: dict | None,
    confidence_min: float = 0.0,
    size_min: int = 0,
    blur_min: float = 0.0,
) -> dict:
    """Apply filters and compute how many faces remain + optional metrics."""
    filtered = [
        f for f in all_faces
        if f["confidence"] >= confidence_min
        and f["face_size"] >= size_min
        and f["blur_score"] >= blur_min
    ]

    result = {
        "confidence_min": confidence_min,
        "size_min": size_min,
        "blur_min": blur_min,
        "faces_before": len(all_faces),
        "faces_after": len(filtered),
        "faces_removed": len(all_faces) - len(filtered),
        "removal_rate": round(1 - len(filtered) / len(all_faces), 4) if all_faces else 0,
    }

    # Per-image metrics if ground truth available
    if ground_truth:
        gt_images = ground_truth.get("images", {})

        per_image_metrics = []
        for fname in set(f["file"] for f in all_faces):
            if fname not in gt_images:
                continue

            gt_faces = gt_images[fname]["faces"]
            pred_faces = [
                {"bbox": f["bbox"], "confidence": f["confidence"]}
                for f in filtered
                if f["file"] == fname
            ]

            metrics = compute_detection_metrics(pred_faces, gt_faces)
            per_image_metrics.append(metrics)

        if per_image_metrics:
            result["avg_precision"] = round(float(np.mean([m["precision"] for m in per_image_metrics])), 4)
            result["avg_recall"] = round(float(np.mean([m["recall"] for m in per_image_metrics])), 4)
            result["avg_f1"] = round(float(np.mean([m["f1"] for m in per_image_metrics])), 4)

    return result


def main():
    parser = argparse.ArgumentParser(description="Phase 4: Quality filter benchmark")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max images to process (0 = all)")
    args = parser.parse_args()

    print("=" * 60)
    print("Phase 4: Quality Filter Strategies")
    print("=" * 60)

    config = load_config()
    ground_truth = load_ground_truth()
    quality_cfg = config.get("quality_filters", {})

    images = collect_test_images()
    if not images:
        print("ERROR: No test images found in test_files/")
        return 1

    if args.limit > 0:
        images = images[: args.limit]

    print(f"\nImages: {len(images)}")
    if ground_truth:
        print("Ground truth: loaded")
    else:
        print("Ground truth: not available")

    # Detect all faces
    print(f"\n{'─' * 40}")
    print("Detecting all faces...")
    print(f"{'─' * 40}")

    all_faces = _detect_all_faces(images, config)
    print(f"\nTotal faces detected: {len(all_faces)}")

    if not all_faces:
        print("No faces detected.")
        return 1

    # Distribution stats
    confs = [f["confidence"] for f in all_faces]
    sizes = [f["face_size"] for f in all_faces]
    blurs = [f["blur_score"] for f in all_faces]
    norms = [f["embedding_norm"] for f in all_faces if f["embedding_norm"] is not None]

    distributions = {
        "confidence": {
            "min": round(min(confs), 4), "max": round(max(confs), 4),
            "mean": round(float(np.mean(confs)), 4), "median": round(float(np.median(confs)), 4),
        },
        "face_size_px": {
            "min": min(sizes), "max": max(sizes),
            "mean": round(float(np.mean(sizes)), 1), "median": round(float(np.median(sizes)), 1),
        },
        "blur_score": {
            "min": round(min(blurs), 2), "max": round(max(blurs), 2),
            "mean": round(float(np.mean(blurs)), 2), "median": round(float(np.median(blurs)), 2),
        },
    }
    if norms:
        distributions["embedding_norm"] = {
            "min": round(min(norms), 4), "max": round(max(norms), 4),
            "mean": round(float(np.mean(norms)), 4), "median": round(float(np.median(norms)), 4),
        }

    print(f"\nDistributions:")
    for name, stats in distributions.items():
        print(f"  {name}: min={stats['min']}, max={stats['max']}, "
              f"mean={stats['mean']}, median={stats['median']}")

    # --- Test individual filter dimensions ---
    confidence_thresholds = quality_cfg.get("min_confidence_thresholds", [0.3, 0.5, 0.7, 0.8])
    size_thresholds = quality_cfg.get("min_face_size_px", [32, 48, 64, 96])
    blur_thresholds = quality_cfg.get("blur_threshold_laplacian", [50, 100, 200])

    # Confidence sweep
    print(f"\n{'─' * 40}")
    print("Confidence threshold sweep")
    print(f"{'─' * 40}")

    confidence_results = []
    for thresh in confidence_thresholds:
        r = evaluate_filter(all_faces, ground_truth, confidence_min=thresh)
        confidence_results.append(r)
        line = f"  conf>={thresh}: {r['faces_after']}/{r['faces_before']} faces ({r['removal_rate']:.1%} removed)"
        if "avg_f1" in r:
            line += f" | P={r['avg_precision']:.3f} R={r['avg_recall']:.3f} F1={r['avg_f1']:.3f}"
        print(line)

    # Size sweep
    print(f"\n{'─' * 40}")
    print("Face size threshold sweep")
    print(f"{'─' * 40}")

    size_results = []
    for thresh in size_thresholds:
        r = evaluate_filter(all_faces, ground_truth, size_min=thresh)
        size_results.append(r)
        line = f"  size>={thresh}px: {r['faces_after']}/{r['faces_before']} faces ({r['removal_rate']:.1%} removed)"
        if "avg_f1" in r:
            line += f" | P={r['avg_precision']:.3f} R={r['avg_recall']:.3f} F1={r['avg_f1']:.3f}"
        print(line)

    # Blur sweep
    print(f"\n{'─' * 40}")
    print("Blur threshold sweep")
    print(f"{'─' * 40}")

    blur_results = []
    for thresh in blur_thresholds:
        r = evaluate_filter(all_faces, ground_truth, blur_min=thresh)
        blur_results.append(r)
        line = f"  blur>={thresh}: {r['faces_after']}/{r['faces_before']} faces ({r['removal_rate']:.1%} removed)"
        if "avg_f1" in r:
            line += f" | P={r['avg_precision']:.3f} R={r['avg_recall']:.3f} F1={r['avg_f1']:.3f}"
        print(line)

    # --- Combined filter grid search ---
    print(f"\n{'─' * 40}")
    print("Combined filter grid search (top combinations)")
    print(f"{'─' * 40}")

    combined_results = []
    for conf in confidence_thresholds:
        for size in size_thresholds:
            for blur in blur_thresholds:
                r = evaluate_filter(all_faces, ground_truth,
                                    confidence_min=conf, size_min=size, blur_min=blur)
                combined_results.append(r)

    # Sort by F1 if available, otherwise by faces_after (keep more faces)
    if combined_results and "avg_f1" in combined_results[0]:
        combined_results.sort(key=lambda r: r.get("avg_f1", 0), reverse=True)
    else:
        combined_results.sort(key=lambda r: r["faces_after"], reverse=True)

    # Show top 10
    for i, r in enumerate(combined_results[:10]):
        line = (f"  #{i + 1}: conf>={r['confidence_min']}, size>={r['size_min']}px, blur>={r['blur_min']} "
                f"→ {r['faces_after']}/{r['faces_before']} faces")
        if "avg_f1" in r:
            line += f" | P={r['avg_precision']:.3f} R={r['avg_recall']:.3f} F1={r['avg_f1']:.3f}"
        print(line)

    # Per-face detail (without the numpy crop)
    face_details = []
    for f in all_faces:
        face_details.append({
            "file": f["file"],
            "face_idx": f["face_idx"],
            "bbox": f["bbox"],
            "confidence": f["confidence"],
            "blur_score": f["blur_score"],
            "face_size": f["face_size"],
            "embedding_norm": f["embedding_norm"],
        })

    output = {
        "phase": "4_quality_filter",
        "total_faces": len(all_faces),
        "distributions": distributions,
        "sweeps": {
            "confidence": confidence_results,
            "face_size": size_results,
            "blur": blur_results,
        },
        "combined_grid": combined_results[:20],
        "face_details": face_details,
    }

    save_result(output, OUTPUT_FILE)

    # Best recommendation
    print(f"\n{'=' * 60}")
    if combined_results and "avg_f1" in combined_results[0]:
        best = combined_results[0]
        print(f"Recommended filter: conf>={best['confidence_min']}, "
              f"size>={best['size_min']}px, blur>={best['blur_min']}")
        print(f"  F1={best['avg_f1']:.3f}, keeps {best['faces_after']}/{best['faces_before']} faces")
    else:
        print("No ground truth available — review face_details in results to pick thresholds manually")
    print(f"{'=' * 60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
