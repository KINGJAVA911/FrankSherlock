# Classification Prototype (IDEA2)

Run:

```bash
uv run python classification/run_classification.py
```

Quick smoke test:

```bash
uv run python classification/run_classification.py --max-images 5
```

Defaults:
- input root: `test_files`
- output root: `classification/test_results`
- model: `qwen2.5vl:7b`
- execution mode: sequential (single worker)

Outputs per source image:
- mirrored `*.yml` structured file
- mirrored `*.txt` index/search text

Batch outputs:
- `classification/test_results/_run_report.json`
- `classification/test_results/index.jsonl`
