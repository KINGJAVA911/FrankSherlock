# Face Recognition A/B Testing Framework

Standalone benchmarking framework to evaluate face detection, embedding, and clustering solutions before integrating into Frank Sherlock.

## Setup

```bash
cd _face_ab_test
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

GPU is recommended but not required — all models fall back to CPU.

### Verify environment

```bash
python scripts/phase0_verify_env.py
```

This checks Python version, GPU availability, library imports, and model downloads.

## Test images

Place your test images in `test_files/`. This directory is gitignored. Supported formats: jpg, jpeg, png, bmp, webp, tiff.

For best results, include:
- Group photos (multiple people)
- Solo portraits / selfies
- The same person across multiple photos
- Varied lighting, angles, and distances
- Some challenging cases (side profiles, partially obscured faces)

## Ground truth (optional)

Edit `docs/GROUND_TRUTH.json` to label faces in your test images. This enables precision/recall/F1 metrics for detection and ARI/NMI/purity for clustering.

Format:
```json
{
  "images": {
    "photo1.jpg": {
      "faces": [
        { "bbox_approx": [x, y, width, height], "person": "Alice" }
      ]
    }
  },
  "expected_clusters": {
    "Alice": ["photo1.jpg:0", "photo3.jpg:0"],
    "Bob": ["photo1.jpg:1", "photo2.jpg:0"]
  }
}
```

Face indices (`photo1.jpg:0`, `photo1.jpg:1`) are zero-based, ordered by detection position (typically left-to-right). Scripts work without ground truth — they just skip metric computation.

## Running benchmarks

Run phases sequentially. Each saves results to `results/`.

### Phase 1: Detection

Compare face detection backends (SCRFD, MTCNN, YOLOv8, MediaPipe).

```bash
python scripts/phase1_detection.py
python scripts/phase1_detection.py --detectors scrfd mtcnn   # specific detectors
python scripts/phase1_detection.py --limit 10                # first 10 images
```

Output: `results/phase1_detection.json`

### Phase 2: Embedding

Compare face embedding models (ArcFace, FaceNet, DeepFace ArcFace). Uses SCRFD as the fixed detector to isolate embedding quality.

```bash
python scripts/phase2_embedding.py
python scripts/phase2_embedding.py --models arcface_insightface facenet
```

Output: `results/phase2_embedding.json`

### Phase 3: Clustering

Compare clustering algorithms (Chinese Whispers, DBSCAN, HDBSCAN) on ArcFace embeddings.

```bash
python scripts/phase3_clustering.py
```

Output: `results/phase3_clustering.json`

### Phase 4: Quality filters

Test confidence, face size, and blur thresholds to find optimal noise reduction.

```bash
python scripts/phase4_quality_filter.py
```

Output: `results/phase4_quality_filter.json`

## Interpreting results

Each phase outputs a JSON file with:
- **Raw data**: per-image/per-face measurements
- **Aggregate stats**: averages, distributions
- **Metrics** (with ground truth): precision, recall, F1, ARI, NMI, purity

Key things to compare:
- **Detection**: F1 score and speed — which detector finds the most real faces with the fewest false positives?
- **Embedding**: AUC and optimal threshold — which model best separates same-person from different-person pairs?
- **Clustering**: ARI and purity — which algorithm best groups faces into correct people?
- **Quality filters**: The sweet spot where removing noisy detections improves downstream clustering without losing real faces.

## Solutions being evaluated

| Category | Tool | Library |
|----------|------|---------|
| Detection | SCRFD | insightface (buffalo_l) |
| Detection | MTCNN | facenet-pytorch |
| Detection | YOLOv8-face | ultralytics |
| Detection | MediaPipe | mediapipe |
| Embedding | ArcFace | insightface (buffalo_l) |
| Embedding | FaceNet | facenet-pytorch |
| Embedding | ArcFace (DeepFace) | deepface |
| Clustering | Chinese Whispers | custom (networkx-style) |
| Clustering | DBSCAN | scikit-learn |
| Clustering | HDBSCAN | scikit-learn |
