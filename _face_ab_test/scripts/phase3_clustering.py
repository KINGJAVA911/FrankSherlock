#!/usr/bin/env python3
"""Phase 3: Compare clustering algorithms on face embeddings."""

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    RESULTS_DIR,
    TimedOperation,
    collect_test_images,
    compute_clustering_metrics,
    cosine_similarity,
    load_config,
    load_ground_truth,
    load_image,
    save_result,
)

OUTPUT_FILE = RESULTS_DIR / "phase3_clustering.json"


# --- Chinese Whispers (the algorithm Immich uses) ---


def chinese_whispers(
    embeddings: list[np.ndarray],
    iterations: int = 20,
    similarity_threshold: float = 0.65,
) -> list[int]:
    """Chinese Whispers graph clustering on embeddings.

    1. Build a similarity graph: edge between faces with cosine similarity > threshold.
    2. Each node starts as its own cluster.
    3. For each iteration, shuffle nodes and assign each to the most frequent
       cluster label among its neighbors (weighted by similarity).
    """
    n = len(embeddings)
    if n == 0:
        return []

    # Build adjacency list with similarities
    adjacency: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for i in range(n):
        for j in range(i + 1, n):
            sim = cosine_similarity(embeddings[i], embeddings[j])
            if sim >= similarity_threshold:
                adjacency[i].append((j, sim))
                adjacency[j].append((i, sim))

    # Initialize: each node is its own cluster
    labels = list(range(n))
    nodes = list(range(n))

    for _ in range(iterations):
        random.shuffle(nodes)
        changed = False
        for node in nodes:
            neighbors = adjacency.get(node, [])
            if not neighbors:
                continue

            # Weighted vote: accumulate similarity per neighbor label
            label_weights: dict[int, float] = defaultdict(float)
            for neighbor, sim in neighbors:
                label_weights[labels[neighbor]] += sim

            best_label = max(label_weights, key=label_weights.get)
            if labels[node] != best_label:
                labels[node] = best_label
                changed = True

        if not changed:
            break

    # Relabel clusters to be contiguous 0..k-1
    unique_labels = sorted(set(labels))
    label_map = {old: new for new, old in enumerate(unique_labels)}
    return [label_map[l] for l in labels]


# --- DBSCAN ---


def cluster_dbscan(
    embeddings: list[np.ndarray],
    eps: float = 0.5,
    min_samples: int = 2,
) -> list[int]:
    """DBSCAN clustering on cosine distance."""
    from sklearn.cluster import DBSCAN
    from sklearn.preprocessing import normalize

    X = np.array(embeddings)
    X_norm = normalize(X)
    # Cosine distance = 1 - cosine_similarity
    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine").fit(X_norm)
    return clustering.labels_.tolist()


# --- HDBSCAN ---


def cluster_hdbscan(
    embeddings: list[np.ndarray],
    min_cluster_size: int = 2,
    min_samples: int = 2,
) -> list[int]:
    """HDBSCAN clustering."""
    from sklearn.cluster import HDBSCAN
    from sklearn.preprocessing import normalize

    X = np.array(embeddings)
    X_norm = normalize(X)
    clustering = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
    ).fit(X_norm)
    return clustering.labels_.tolist()


def _load_embeddings_from_phase2() -> tuple[dict[str, list[np.ndarray]], str | None]:
    """Try to load precomputed embeddings from phase 2 results."""
    phase2_file = RESULTS_DIR / "phase2_embedding.json"
    if not phase2_file.exists():
        return {}, None

    with open(phase2_file) as f:
        data = json.load(f)

    # We can't load raw embeddings from JSON (they're not stored),
    # so we need to recompute. Return None to signal that.
    return {}, None


def _compute_embeddings(images: list[Path], config: dict) -> tuple[list[np.ndarray], list[str]]:
    """Detect faces and compute ArcFace embeddings for all images.

    Returns (embeddings, face_labels) where face_labels are "filename:face_idx".
    """
    from insightface.app import FaceAnalysis

    det_cfg = config.get("detection", {}).get("scrfd", {})
    det_size = tuple(det_cfg.get("det_size", [640, 640]))

    print("Initializing InsightFace (SCRFD + ArcFace)...")
    app = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=det_size)

    all_embeddings = []
    all_labels = []

    for img_path in images:
        try:
            img = load_image(img_path)
            with TimedOperation(f"detect+embed {img_path.name}") as t:
                faces = app.get(img)

            for i, face in enumerate(faces):
                if face.embedding is not None:
                    all_embeddings.append(face.embedding)
                    all_labels.append(f"{img_path.name}:{i}")
        except Exception as e:
            print(f"  ERROR: {img_path.name} — {e}")

    return all_embeddings, all_labels


def _build_gt_labels(face_labels: list[str], ground_truth: dict) -> list[int] | None:
    """Map face labels to ground truth person IDs for metric computation."""
    gt_images = ground_truth.get("images", {})
    expected = ground_truth.get("expected_clusters", {})

    # Build reverse map: "filename:idx" -> person
    face_to_person = {}
    for person, refs in expected.items():
        for ref in refs:
            face_to_person[ref] = person

    # Map each face to a person ID
    person_to_id = {}
    gt_labels = []
    all_mapped = True

    for label in face_labels:
        person = face_to_person.get(label)
        if person is None:
            all_mapped = False
            gt_labels.append(-1)
        else:
            if person not in person_to_id:
                person_to_id[person] = len(person_to_id)
            gt_labels.append(person_to_id[person])

    if not any(l >= 0 for l in gt_labels):
        return None

    return gt_labels


def main():
    parser = argparse.ArgumentParser(description="Phase 3: Face clustering benchmark")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max images to process (0 = all)")
    args = parser.parse_args()

    print("=" * 60)
    print("Phase 3: Clustering Algorithm Comparison")
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
    if ground_truth:
        n_people = len(ground_truth.get("expected_clusters", {}))
        print(f"Ground truth: {n_people} people labeled")
    else:
        print("Ground truth: not available (metrics will be skipped)")

    # Compute embeddings
    print(f"\n{'─' * 40}")
    print("Computing face embeddings (ArcFace via InsightFace)...")
    print(f"{'─' * 40}")

    embeddings, face_labels = _compute_embeddings(images, config)
    print(f"\nTotal face embeddings: {len(embeddings)}")

    if len(embeddings) < 2:
        print("Not enough faces for clustering (need at least 2).")
        return 1

    # Build ground truth labels
    gt_labels = None
    if ground_truth:
        gt_labels = _build_gt_labels(face_labels, ground_truth)
        if gt_labels:
            mapped = sum(1 for l in gt_labels if l >= 0)
            print(f"Ground truth mapped: {mapped}/{len(face_labels)} faces")

    # --- Run clustering algorithms ---
    clustering_cfg = config.get("clustering", {})
    results = {}

    # Chinese Whispers
    print(f"\n{'─' * 40}")
    print("Chinese Whispers")
    print(f"{'─' * 40}")

    cw_cfg = clustering_cfg.get("chinese_whispers", {})
    cw_iterations = cw_cfg.get("iterations", 20)

    cw_results = []
    for threshold in [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]:
        with TimedOperation(f"chinese_whispers threshold={threshold}") as t:
            labels = chinese_whispers(embeddings, iterations=cw_iterations, similarity_threshold=threshold)

        n_clusters = len(set(labels))
        entry = {
            "threshold": threshold,
            "n_clusters": n_clusters,
            "time_s": round(t.elapsed, 4),
            "cluster_sizes": dict(Counter(labels)),
        }

        if gt_labels:
            # Filter to only faces with ground truth
            pred_filtered = [l for l, g in zip(labels, gt_labels) if g >= 0]
            gt_filtered = [g for g in gt_labels if g >= 0]
            if pred_filtered:
                metrics = compute_clustering_metrics(pred_filtered, gt_filtered)
                entry["metrics"] = metrics
                print(f"    threshold={threshold}: {n_clusters} clusters, "
                      f"ARI={metrics['ari']:.3f} NMI={metrics['nmi']:.3f} purity={metrics['purity']:.3f}")
            else:
                print(f"    threshold={threshold}: {n_clusters} clusters")
        else:
            print(f"    threshold={threshold}: {n_clusters} clusters")

        cw_results.append(entry)

    results["chinese_whispers"] = cw_results

    # DBSCAN
    print(f"\n{'─' * 40}")
    print("DBSCAN")
    print(f"{'─' * 40}")

    dbscan_cfg = clustering_cfg.get("dbscan", {})
    eps_values = dbscan_cfg.get("eps_values", [0.4, 0.5, 0.6, 0.7, 0.8])
    min_samples_db = dbscan_cfg.get("min_samples", 2)

    dbscan_results = []
    for eps in eps_values:
        with TimedOperation(f"dbscan eps={eps}") as t:
            labels = cluster_dbscan(embeddings, eps=eps, min_samples=min_samples_db)

        n_clusters = len(set(labels) - {-1})
        n_noise = labels.count(-1)
        entry = {
            "eps": eps,
            "min_samples": min_samples_db,
            "n_clusters": n_clusters,
            "n_noise": n_noise,
            "time_s": round(t.elapsed, 4),
        }

        if gt_labels:
            pred_filtered = [l for l, g in zip(labels, gt_labels) if g >= 0]
            gt_filtered = [g for g in gt_labels if g >= 0]
            if pred_filtered:
                metrics = compute_clustering_metrics(pred_filtered, gt_filtered)
                entry["metrics"] = metrics
                print(f"    eps={eps}: {n_clusters} clusters, {n_noise} noise, "
                      f"ARI={metrics['ari']:.3f} NMI={metrics['nmi']:.3f}")
            else:
                print(f"    eps={eps}: {n_clusters} clusters, {n_noise} noise")
        else:
            print(f"    eps={eps}: {n_clusters} clusters, {n_noise} noise")

        dbscan_results.append(entry)

    results["dbscan"] = dbscan_results

    # HDBSCAN
    print(f"\n{'─' * 40}")
    print("HDBSCAN")
    print(f"{'─' * 40}")

    hdbscan_cfg = clustering_cfg.get("hdbscan", {})
    min_cluster_sizes = hdbscan_cfg.get("min_cluster_size_values", [2, 3, 5])
    min_samples_hdb = hdbscan_cfg.get("min_samples", 2)

    hdbscan_results = []
    for mcs in min_cluster_sizes:
        with TimedOperation(f"hdbscan min_cluster_size={mcs}") as t:
            labels = cluster_hdbscan(embeddings, min_cluster_size=mcs, min_samples=min_samples_hdb)

        n_clusters = len(set(labels) - {-1})
        n_noise = labels.count(-1)
        entry = {
            "min_cluster_size": mcs,
            "min_samples": min_samples_hdb,
            "n_clusters": n_clusters,
            "n_noise": n_noise,
            "time_s": round(t.elapsed, 4),
        }

        if gt_labels:
            pred_filtered = [l for l, g in zip(labels, gt_labels) if g >= 0]
            gt_filtered = [g for g in gt_labels if g >= 0]
            if pred_filtered:
                metrics = compute_clustering_metrics(pred_filtered, gt_filtered)
                entry["metrics"] = metrics
                print(f"    min_cluster_size={mcs}: {n_clusters} clusters, {n_noise} noise, "
                      f"ARI={metrics['ari']:.3f} NMI={metrics['nmi']:.3f}")
            else:
                print(f"    min_cluster_size={mcs}: {n_clusters} clusters, {n_noise} noise")
        else:
            print(f"    min_cluster_size={mcs}: {n_clusters} clusters, {n_noise} noise")

        hdbscan_results.append(entry)

    results["hdbscan"] = hdbscan_results

    # Save
    output = {
        "phase": "3_clustering",
        "total_faces": len(embeddings),
        "face_labels": face_labels,
        "embedding_model": "arcface_insightface",
        "algorithms": results,
    }

    save_result(output, OUTPUT_FILE)

    # Summary
    print(f"\n{'=' * 60}")
    print("Clustering Comparison Summary")
    print(f"{'=' * 60}")

    for algo_name, algo_results in results.items():
        print(f"\n{algo_name}:")
        best = None
        best_ari = -1
        for entry in algo_results:
            if "metrics" in entry and entry["metrics"]["ari"] > best_ari:
                best_ari = entry["metrics"]["ari"]
                best = entry
        if best:
            m = best["metrics"]
            params = {k: v for k, v in best.items() if k not in ("metrics", "time_s", "cluster_sizes", "n_clusters", "n_noise")}
            print(f"  Best config: {params}")
            print(f"  Clusters: {best.get('n_clusters', '?')}, ARI={m['ari']:.3f}, NMI={m['nmi']:.3f}, purity={m['purity']:.3f}")
        else:
            print("  No ground truth metrics available")

    return 0


if __name__ == "__main__":
    sys.exit(main())
