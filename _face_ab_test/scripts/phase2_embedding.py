#!/usr/bin/env python3
"""Phase 2: Compare face embedding/recognition models for verification quality."""

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    RESULTS_DIR,
    TimedOperation,
    collect_test_images,
    cosine_similarity,
    load_config,
    load_ground_truth,
    load_image,
    relative_path,
    save_result,
)

OUTPUT_FILE = RESULTS_DIR / "phase2_embedding.json"


def _get_scrfd_detector(config: dict):
    """Initialize the SCRFD detector (fixed detector for fair embedding comparison)."""
    from insightface.app import FaceAnalysis

    det_cfg = config.get("detection", {}).get("scrfd", {})
    det_size = tuple(det_cfg.get("det_size", [640, 640]))
    app = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=det_size)
    return app


def _detect_faces(detector, img_rgb: np.ndarray) -> list:
    """Detect faces with SCRFD and return insightface Face objects."""
    return detector.get(img_rgb)


# --- Embedding extractors ---


def embed_arcface(faces: list, img_rgb: np.ndarray, config: dict) -> list[np.ndarray]:
    """ArcFace embeddings from InsightFace (already computed during detection)."""
    return [face.embedding for face in faces if face.embedding is not None]


def embed_facenet(faces: list, img_rgb: np.ndarray, config: dict) -> list[np.ndarray]:
    """FaceNet embeddings via facenet-pytorch InceptionResnetV1."""
    import torch
    from facenet_pytorch import InceptionResnetV1
    from PIL import Image

    if not hasattr(embed_facenet, "_model"):
        emb_cfg = config.get("embedding", {}).get("facenet", {})
        pretrained = emb_cfg.get("model", "vggface2")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = InceptionResnetV1(pretrained=pretrained).eval().to(device)
        embed_facenet._model = model
        embed_facenet._device = device

    model = embed_facenet._model
    device = embed_facenet._device

    embeddings = []
    for face in faces:
        bbox = face.bbox.astype(int)
        x1, y1, x2, y2 = bbox
        # Clamp to image bounds
        h, w = img_rgb.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            continue

        face_crop = img_rgb[y1:y2, x1:x2]
        pil_crop = Image.fromarray(face_crop).resize((160, 160))

        # Normalize to [-1, 1]
        tensor = torch.tensor(np.array(pil_crop)).permute(2, 0, 1).float() / 255.0
        tensor = (tensor - 0.5) / 0.5
        tensor = tensor.unsqueeze(0).to(device)

        with torch.no_grad():
            emb = model(tensor).cpu().numpy().flatten()
        embeddings.append(emb)

    return embeddings


def embed_deepface_arcface(faces: list, img_rgb: np.ndarray, config: dict) -> list[np.ndarray]:
    """ArcFace embeddings via DeepFace wrapper (for comparison with native insightface)."""
    from deepface import DeepFace
    from PIL import Image

    embeddings = []
    for face in faces:
        bbox = face.bbox.astype(int)
        x1, y1, x2, y2 = bbox
        h, w = img_rgb.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            continue

        face_crop = img_rgb[y1:y2, x1:x2]

        try:
            result = DeepFace.represent(
                face_crop,
                model_name="ArcFace",
                enforce_detection=False,
                detector_backend="skip",
            )
            if result:
                embeddings.append(np.array(result[0]["embedding"]))
        except Exception:
            continue

    return embeddings


EMBEDDING_MODELS = {
    "arcface_insightface": embed_arcface,
    "facenet": embed_facenet,
    "arcface_deepface": embed_deepface_arcface,
}


def compute_verification_stats(
    embeddings_by_image: dict[str, list[np.ndarray]],
    ground_truth: dict | None,
) -> dict:
    """Compute same-person vs different-person similarity distributions."""
    if ground_truth is None:
        return {}

    gt_images = ground_truth.get("images", {})

    # Build face-to-person mapping: (filename, face_idx) -> person
    face_to_person = {}
    for fname, data in gt_images.items():
        for i, face_info in enumerate(data["faces"]):
            face_to_person[(fname, i)] = face_info["person"]

    # Collect all (embedding, person) pairs
    pairs = []
    for fname, embs in embeddings_by_image.items():
        for i, emb in enumerate(embs):
            person = face_to_person.get((fname, i))
            if person:
                pairs.append((emb, person))

    if len(pairs) < 2:
        return {"error": "Not enough labeled face pairs for verification"}

    # Compute same-person and different-person similarities
    same_sims = []
    diff_sims = []
    for (emb_a, person_a), (emb_b, person_b) in itertools.combinations(pairs, 2):
        sim = cosine_similarity(emb_a, emb_b)
        if person_a == person_b:
            same_sims.append(sim)
        else:
            diff_sims.append(sim)

    stats = {}
    if same_sims:
        stats["same_person"] = {
            "count": len(same_sims),
            "mean": round(float(np.mean(same_sims)), 4),
            "std": round(float(np.std(same_sims)), 4),
            "min": round(float(np.min(same_sims)), 4),
            "max": round(float(np.max(same_sims)), 4),
        }
    if diff_sims:
        stats["diff_person"] = {
            "count": len(diff_sims),
            "mean": round(float(np.mean(diff_sims)), 4),
            "std": round(float(np.std(diff_sims)), 4),
            "min": round(float(np.min(diff_sims)), 4),
            "max": round(float(np.max(diff_sims)), 4),
        }

    # Simple ROC: try thresholds from 0 to 1
    if same_sims and diff_sims:
        best_threshold = 0.0
        best_acc = 0.0
        roc_points = []
        for thresh in np.arange(0.0, 1.01, 0.05):
            tp = sum(1 for s in same_sims if s >= thresh)
            fn = sum(1 for s in same_sims if s < thresh)
            fp = sum(1 for s in diff_sims if s >= thresh)
            tn = sum(1 for s in diff_sims if s < thresh)
            tpr = tp / (tp + fn) if (tp + fn) > 0 else 0
            fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
            acc = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0
            roc_points.append({"threshold": round(float(thresh), 2), "tpr": round(tpr, 4), "fpr": round(fpr, 4)})
            if acc > best_acc:
                best_acc = acc
                best_threshold = float(thresh)

        stats["optimal_threshold"] = round(best_threshold, 2)
        stats["best_accuracy"] = round(best_acc, 4)
        stats["roc_points"] = roc_points

        # Approximate AUC using trapezoidal rule
        sorted_roc = sorted(roc_points, key=lambda p: p["fpr"])
        auc = 0.0
        for i in range(1, len(sorted_roc)):
            dx = sorted_roc[i]["fpr"] - sorted_roc[i - 1]["fpr"]
            dy = (sorted_roc[i]["tpr"] + sorted_roc[i - 1]["tpr"]) / 2
            auc += dx * dy
        stats["auc"] = round(auc, 4)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Phase 2: Face embedding benchmark")
    parser.add_argument("--models", nargs="+", choices=list(EMBEDDING_MODELS.keys()),
                        default=list(EMBEDDING_MODELS.keys()),
                        help="Which embedding models to benchmark (default: all)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max images to process (0 = all)")
    args = parser.parse_args()

    print("=" * 60)
    print("Phase 2: Face Embedding Comparison")
    print("=" * 60)

    config = load_config()
    ground_truth = load_ground_truth()

    images = collect_test_images()
    if not images:
        print("ERROR: No test images found in test_files/")
        return 1

    if args.limit > 0:
        images = images[: args.limit]

    print(f"\nImages: {len(images)}")
    print(f"Embedding models: {', '.join(args.models)}")
    print(f"Fixed detector: SCRFD (insightface buffalo_l)")
    if ground_truth:
        print("Ground truth: loaded (verification metrics will be computed)")
    else:
        print("Ground truth: not available (skipping verification metrics)")

    # Initialize fixed detector
    print("\nInitializing SCRFD detector...")
    with TimedOperation("SCRFD init"):
        detector = _get_scrfd_detector(config)

    # Detect faces once for all images
    print(f"\n{'─' * 40}")
    print("Detecting faces (SCRFD)...")
    print(f"{'─' * 40}")

    detections = {}  # filename -> list of insightface Face objects
    detection_images = {}  # filename -> img_rgb
    for img_path in images:
        try:
            img = load_image(img_path)
            with TimedOperation(f"detect {img_path.name}") as t:
                faces = _detect_faces(detector, img)
            detections[img_path.name] = faces
            detection_images[img_path.name] = img
            print(f"    {len(faces)} faces")
        except Exception as e:
            print(f"  ERROR detecting {img_path.name}: {e}")

    total_faces = sum(len(f) for f in detections.values())
    print(f"\nTotal faces detected: {total_faces} across {len(detections)} images")

    if total_faces == 0:
        print("No faces detected. Cannot compare embeddings.")
        return 1

    # Compare embedding models
    results_by_model = {}

    for model_name in args.models:
        embed_fn = EMBEDDING_MODELS[model_name]
        print(f"\n{'─' * 40}")
        print(f"Embedding model: {model_name}")
        print(f"{'─' * 40}")

        embeddings_by_image = {}
        total_embeddings = 0
        total_time = 0.0
        embedding_dims = set()
        errors = []
        file_results = []

        for fname, faces in detections.items():
            if not faces:
                continue
            img = detection_images[fname]
            try:
                with TimedOperation(f"{model_name} {fname}") as t:
                    embs = embed_fn(faces, img, config)

                embeddings_by_image[fname] = embs
                total_embeddings += len(embs)
                total_time += t.elapsed

                for emb in embs:
                    embedding_dims.add(len(emb))

                file_results.append({
                    "file": fname,
                    "faces_detected": len(faces),
                    "embeddings_computed": len(embs),
                    "time_s": round(t.elapsed, 4),
                })
            except Exception as e:
                print(f"  ERROR: {fname} — {e}")
                errors.append({"file": fname, "error": str(e)})

        # Verification stats (if ground truth available)
        verification = compute_verification_stats(embeddings_by_image, ground_truth)

        results_by_model[model_name] = {
            "total_embeddings": total_embeddings,
            "embedding_dimensions": sorted(embedding_dims),
            "total_time_s": round(total_time, 4),
            "avg_time_per_face_s": round(total_time / total_embeddings, 4) if total_embeddings else 0,
            "verification": verification,
            "errors": errors,
            "files": file_results,
        }

        print(f"\n  Embeddings: {total_embeddings}, dims: {sorted(embedding_dims)}")
        print(f"  Time: {total_time:.4f}s total, {total_time / total_embeddings:.4f}s/face" if total_embeddings else "")
        if verification.get("optimal_threshold"):
            print(f"  Optimal threshold: {verification['optimal_threshold']}, "
                  f"accuracy: {verification['best_accuracy']:.3f}, AUC: {verification.get('auc', '—')}")

    output = {
        "phase": "2_embedding",
        "fixed_detector": "scrfd",
        "total_images": len(images),
        "total_faces_detected": total_faces,
        "models": results_by_model,
    }

    save_result(output, OUTPUT_FILE)

    # Final comparison
    print(f"\n{'=' * 60}")
    print("Embedding Comparison Summary")
    print(f"{'=' * 60}")
    print(f"{'Model':<25} {'Dim':>5} {'Time/face':>10} {'AUC':>6} {'Threshold':>10} {'Accuracy':>9}")
    print(f"{'─' * 25} {'─' * 5} {'─' * 10} {'─' * 6} {'─' * 10} {'─' * 9}")
    for name, r in results_by_model.items():
        dims = r["embedding_dimensions"][0] if r["embedding_dimensions"] else "?"
        v = r.get("verification", {})
        auc = f"{v['auc']:.3f}" if "auc" in v else "—"
        thresh = f"{v['optimal_threshold']:.2f}" if "optimal_threshold" in v else "—"
        acc = f"{v['best_accuracy']:.3f}" if "best_accuracy" in v else "—"
        print(f"{name:<25} {dims:>5} {r['avg_time_per_face_s']:>9.4f}s {auc:>6} {thresh:>10} {acc:>9}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
