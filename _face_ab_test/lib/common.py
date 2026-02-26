"""Shared utilities for face recognition A/B testing."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
TEST_FILES = PROJECT_ROOT / "test_files"
RESULTS_DIR = PROJECT_ROOT / "results"
DOCS_DIR = PROJECT_ROOT / "docs"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}


class TimedOperation:
    """Context manager for measuring wall-clock time."""

    def __init__(self, label: str = ""):
        self.label = label
        self.elapsed: float = 0.0

    def __enter__(self):
        self.start = time.perf_counter()
        if self.label:
            print(f"  [{self.label}] starting...")
        return self

    def __exit__(self, *exc):
        self.elapsed = time.perf_counter() - self.start
        if self.label:
            print(f"  [{self.label}] done in {self.elapsed:.4f}s")
        return False


def save_result(data: dict, output_path: Path) -> None:
    """Write JSON results with timestamp metadata."""
    data["_generated_at"] = datetime.now(timezone.utc).isoformat()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Results saved to {output_path.relative_to(PROJECT_ROOT)}")


def load_json(path: Path, default: Any = None) -> Any:
    """Safe JSON loading with fallback."""
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def load_config() -> dict:
    """Load BENCHMARK_CONFIG.json."""
    return load_json(DOCS_DIR / "BENCHMARK_CONFIG.json", {})


def load_ground_truth() -> dict | None:
    """Load GROUND_TRUTH.json. Returns None if not populated."""
    gt = load_json(DOCS_DIR / "GROUND_TRUTH.json")
    if gt is None:
        return None
    images = gt.get("images", {})
    # Check if only example entries remain
    real_images = {k: v for k, v in images.items() if not k.startswith("example_")}
    if not real_images:
        return None
    return gt


def collect_test_images(test_dir: Path | None = None) -> list[Path]:
    """Find image files recursively in test_files/."""
    root = test_dir or TEST_FILES
    if not root.exists():
        return []
    images = []
    for ext in IMAGE_EXTENSIONS:
        images.extend(root.rglob(f"*{ext}"))
        images.extend(root.rglob(f"*{ext.upper()}"))
    # Deduplicate (case-insensitive extensions may overlap)
    seen = set()
    unique = []
    for p in sorted(images):
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def load_image(path: Path) -> np.ndarray:
    """Load image as RGB numpy array using OpenCV."""
    import cv2

    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Failed to load image: {path}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def relative_path(filepath: Path) -> str:
    """Display path relative to project root."""
    try:
        return str(filepath.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(filepath)


def iou(box1: list, box2: list) -> float:
    """Intersection-over-union for [x, y, w, h] bounding boxes."""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2

    xa = max(x1, x2)
    ya = max(y1, y2)
    xb = min(x1 + w1, x2 + w2)
    yb = min(y1 + h1, y2 + h2)

    inter = max(0, xb - xa) * max(0, yb - ya)
    area1 = w1 * h1
    area2 = w2 * h2
    union = area1 + area2 - inter

    if union == 0:
        return 0.0
    return inter / union


def compute_detection_metrics(
    predicted: list[dict], ground_truth: list[dict], iou_threshold: float = 0.5
) -> dict:
    """Compute precision/recall/F1 for face detection.

    Args:
        predicted: list of {"bbox": [x,y,w,h], "confidence": float}
        ground_truth: list of {"bbox_approx": [x,y,w,h], "person": str}
        iou_threshold: minimum IoU to count as a match

    Returns:
        dict with precision, recall, f1, true_positives, false_positives, false_negatives
    """
    matched_gt = set()
    true_positives = 0
    false_positives = 0

    # Sort predictions by confidence (highest first)
    sorted_preds = sorted(predicted, key=lambda p: p.get("confidence", 0), reverse=True)

    for pred in sorted_preds:
        best_iou = 0.0
        best_gt_idx = -1
        for i, gt in enumerate(ground_truth):
            if i in matched_gt:
                continue
            score = iou(pred["bbox"], gt["bbox_approx"])
            if score > best_iou:
                best_iou = score
                best_gt_idx = i

        if best_iou >= iou_threshold and best_gt_idx >= 0:
            true_positives += 1
            matched_gt.add(best_gt_idx)
        else:
            false_positives += 1

    false_negatives = len(ground_truth) - true_positives
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
    }


def compute_clustering_metrics(
    predicted_labels: list[int], ground_truth_labels: list[int]
) -> dict:
    """Compute clustering quality metrics.

    Args:
        predicted_labels: cluster assignment per face (-1 = noise)
        ground_truth_labels: ground truth person ID per face

    Returns:
        dict with ari, nmi, purity, n_clusters_predicted, n_clusters_truth
    """
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    ari = adjusted_rand_score(ground_truth_labels, predicted_labels)
    nmi = normalized_mutual_info_score(ground_truth_labels, predicted_labels)

    # Purity: fraction of faces in each predicted cluster matching the majority label
    pred_set = set(predicted_labels)
    pred_set.discard(-1)  # exclude noise
    total = 0
    correct = 0
    for cluster_id in pred_set:
        members = [gt for pred, gt in zip(predicted_labels, ground_truth_labels) if pred == cluster_id]
        if members:
            from collections import Counter
            most_common_count = Counter(members).most_common(1)[0][1]
            correct += most_common_count
            total += len(members)

    purity = correct / total if total > 0 else 0.0

    return {
        "ari": round(ari, 4),
        "nmi": round(nmi, 4),
        "purity": round(purity, 4),
        "n_clusters_predicted": len(set(predicted_labels) - {-1}),
        "n_clusters_truth": len(set(ground_truth_labels)),
    }


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"
