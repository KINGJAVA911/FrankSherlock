## Frank Sherlock — Benchmark Results (Updated)

### Scope

This report consolidates the local benchmark runs for phases 1-6 and includes the new vision contenders added in this round.

- Hardware: RTX 5090 + AMD 7850X3D
- Corpus: 94 files (`60` images, `9` audio, `13` video, `12` documents)
- Constraint: local/self-hosted open-source stack

---

### Phase 1 — Metadata Baseline

- `94/94` files processed successfully.
- Output: `results/phase1_metadata/all_metadata.json`
- Timing: `phase_total_s=7.0078`, `per_file_avg_s=0.0746`

---

### Phase 2 — Images

#### 2a Vision LLM benchmark (ground-truth subset)

Configuration:
- `30` labeled images
- models: `qwen2.5vl:7b`, `llava:13b`, `minicpm-v:8b`
- prompts: `describe`, `classify`

Timing (`results/phase2_images/ollama_vision_results.json`):
- `qwen2.5vl:7b/describe`: `5.4561s`
- `qwen2.5vl:7b/classify`: `0.5518s`
- `llava:13b/describe`: `3.9249s`
- `llava:13b/classify`: `1.6163s`
- `minicpm-v:8b/describe`: `2.2572s`
- `minicpm-v:8b/classify`: `1.6320s`
- per-image average (all model/prompt calls): `15.4384s`

Accuracy (`results/phase2_images/comparison_report.json`):
- `qwen2.5vl:7b`: `type_accuracy=0.8000`, `series_accuracy=0.1429`, `json_valid=0.8667`
- `minicpm-v:8b`: `type_accuracy=0.5000`, `series_accuracy=0.0000`, `json_valid=0.8333`
- `llava:13b`: `type_accuracy=0.3333`, `series_accuracy=0.0556`, `json_valid=0.8333`

#### 2b WD tagger benchmark

Models:
- `SmilingWolf/wd-swinv2-tagger-v3`
- `SmilingWolf/wd-vit-tagger-v3`
- `SmilingWolf/wd-vit-large-tagger-v3`

Timing (`results/phase2_images/wd_tagger_results.json`):
- per-image avg: `0.5287s`

Anime-detection metrics (30 labeled images):
- `wd-swinv2`: `accuracy=0.8667`, `precision=1.0000`, `recall=0.7778`
- `wd-vit-large`: `accuracy=0.7667`, `precision=1.0000`, `recall=0.6111`
- `wd-vit`: `accuracy=0.6333`, `precision=1.0000`, `recall=0.3889`

#### 2d OCR benchmark

Engines:
- `surya`
- `ollama_vision`

Timing (`results/phase2_images/ocr_results.json`):
- `surya`: `8.1545s/image`
- `ollama_vision`: `1.7302s/image`

Extraction summary:
- `surya`: text found in `54/65`, avg ref similarity `0.9455`
- `ollama_vision`: text found in `38/65`, avg ref similarity `0.9419`

Interpretation:
- `surya` has materially better text coverage.
- `ollama_vision` is much faster.

#### 2e Model-size and contender checks

##### A) `qwen2.5vl:7b` vs `qwen2.5vl:32b` (isolated classify-only passes)

Source files:
- `results/phase2_images/qwen_size_compare_7b.json`
- `results/phase2_images/qwen_size_compare_32b.json`

Results on 30 labeled images:
- `qwen2.5vl:7b`: `type_accuracy=0.8667`, `series_accuracy=0.1875`, `json_valid=0.9333`, `avg_latency=0.7727s`
- `qwen2.5vl:32b`: `type_accuracy=0.8667`, `series_accuracy=0.2500`, `json_valid=0.9333`, `avg_latency=22.4574s`

Conclusion:
- `32b` gives only `+0.0625` series gain (1 extra correct over 16 series-labeled items) at `29.06x` slower latency.
- Keep `7b` as default; reserve `32b` only for selective fallback.

##### B) New Qwen3-VL contenders vs `qwen2.5vl:7b` (repeat-aware)

Command used:
- `uv run python -u scripts/phase2e_qwen_size_compare.py --models qwen2.5vl:7b,qwen3-vl:8b,qwen3-vl:30b-a3b --repeats 3`

Output:
- `results/phase2_images/qwen_size_compare_report.json`

Results (mean across 3 trials):
- `qwen2.5vl:7b`: `type_accuracy=0.8889` (CI95 `[0.8671,0.9107]`), `series_accuracy=0.1875`, `json_valid=0.9333`, `avg_latency=0.9097s` (CI95 `[0.8532,0.9661]`)
- `qwen3-vl:8b`: `type_accuracy=0.5555` (CI95 `[0.5120,0.5991]`), `series_accuracy=0.1111`, `json_valid=0.6778`, `avg_latency=1.8021s` (CI95 `[1.6722,1.9320]`)
- `qwen3-vl:30b-a3b`: `type_accuracy=0.5445` (CI95 `[0.5009,0.5880]`), `series_accuracy=0.1556`, `json_valid=0.6667`, `avg_latency=2.0057s` (CI95 `[1.8178,2.1937]`)

Speed relative to `qwen2.5vl:7b`:
- `qwen3-vl:8b`: `1.98x` slower
- `qwen3-vl:30b-a3b`: `2.20x` slower

Interpretation:
- On this dataset/prompt schema, both Qwen3-VL contenders underperform `qwen2.5vl:7b` in accuracy and robustness.

---

### Phase 3 — Audio

#### 3a Chromaprint

- `20/21` fingerprints generated (`0.9524` success)
- AcoustID lookups disabled (no API key)
- Output: `results/phase3_audio/chromaprint_results.json`

#### 3b/3c/3d ASR comparison

Models:
- `base`, `small`, `medium`

Language accuracy on labeled subset (`n=15`):
- `base`: `0.8000`
- `small`: `1.0000`
- `medium`: `1.0000`

Non-empty transcripts:
- all three: `1.0000`

Timing:
- `base`: `10.2287s` avg component
- `small`: `15.7406s`
- `medium`: `35.1508s`
- phase per-file average: `61.1564s`

`faster-whisper` run (`results/phase3_audio/faster_whisper_results.json`):
- runtime: `device=cpu`, `compute_type=int8`
- models: `small`, `distil-large-v3`
- `faster_whisper_small`: `7.9297s` avg component
- `faster_whisper_distil-large-v3`: `25.0194s` avg component
- phase per-file average: `33.0051s`

`faster-whisper` accuracy on labeled subset (`n=9`, from `results/phase3_audio/comparison_report.json`):
- `small`: `language_accuracy=1.0000`, `non_empty=1.0000`
- `distil-large-v3`: `language_accuracy=0.1111`, `non_empty=1.0000`

Environment check:
- `uv run python -c "import torch; print(torch.cuda.is_available())"` returned `False` on this machine during this run, so Whisper executed CPU-only.

Recommendation:
- Keep `whisper-small` as default in current pipeline.
- `faster-whisper small` is a strong throughput candidate, but should be revalidated again after GPU ASR path is fixed.

---

### Phase 4 — Video

#### 4a Frame extraction

- `13` videos processed, `200` frames extracted
- scene detect avg: `0.678s/video`
- Output: `results/phase4_video/frame_extraction.json`

#### 4b Multi-signal video identification (repeat-aware contender run)

Command used:
- `uv run python -u scripts/phase4b_video_classify.py --models qwen2.5vl:7b,qwen3-vl:8b,qwen3-vl:30b-a3b --repeats 3`

Output:
- `results/phase4_video/video_classification.json`

Ground-truth title hit rate (`12` labeled videos, mean across 3 trials):
- `qwen2.5vl:7b`: `content_only=0.2500`, `full_context=0.6667`
- `qwen3-vl:8b`: `content_only=0.0000`, `full_context=0.0000`
- `qwen3-vl:30b-a3b`: `content_only=0.0000`, `full_context=0.0555` (CI95 `[0.0011,0.1100]`)

Timing:
- `25.6810s/video` average (CI95 `[25.6196,25.7424]`)
- `333.8532s` phase total (CI95 `[333.0552,334.6511]`)

Interpretation:
- `qwen2.5vl:7b` remains clearly better in this pipeline.
- Qwen3-VL frequently returned empty/truncated JSON responses in synthesis steps.

---

### Phase 5 — Unified Catalog

- `94` files cataloged
- timing by type:
  - images: `9.1257s/file`
  - videos: `3.4163s/file`
  - audio: `0.1193s/file`
  - documents: `0.0620s/file`
- output: `results/catalog.json`

---

### Phase 6 — Cost/Time Projection (refreshed after new video run)

From `results/cost_estimation.json`:
- current test estimate: `23.8 min`, local electricity cost `$0.0214`
- small NAS: `6.6 hours`, `$0.3569`
- medium NAS: `2.6 days`, `$3.3698`
- large NAS: `26.0 days`, `$33.6984`

Caveat:
- Audio throughput remains limited by CPU-only Whisper in current environment.

---

## Final Recommendations

- Image semantic classification: `qwen2.5vl:7b`
- Image tagging/filtering: `wd-swinv2-tagger-v3`
- OCR: hybrid (`surya` for recall, `ollama_vision` for speed)
- Audio ASR: `whisper-small` (current environment)
- Audio throughput contender: `faster-whisper small` (CPU run was much faster; re-test on GPU-enabled ASR stack before final switch)
- Audio fingerprinting: `chromaprint` (+ AcoustID key when needed)
- Video synthesis: multi-signal pipeline with `qwen2.5vl:7b` as default

`7b` vs `32b` decision:
- Keep `qwen2.5vl:7b` as primary.
- Use `qwen2.5vl:32b` only as targeted fallback for hard/ambiguous cases.

---

## Contender Status In This Round

Successfully tested:
- `qwen3-vl:8b`
- `qwen3-vl:30b-a3b`

Not available via current Ollama registry tags in this environment (`2026-02-22`):
- `llava-onevision:7b` (`pull model manifest: file does not exist`)
- `internvl3:8b` (`pull model manifest: file does not exist`)
