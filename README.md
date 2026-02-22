# Frank Sherlock

Local-only, AI-powered image cataloging and search for your NAS. Scans directories of images, classifies them using local vision LLMs, extracts text via OCR, generates thumbnails, and indexes everything into a searchable database — all without sending a single byte to the cloud.

## What It Does

- Scans image directories read-only (JPEG, PNG, GIF, BMP, WebP, TIFF)
- Classifies each image using Ollama's `qwen2.5vl:7b` vision model (media type, description, anime/manga identification, document detection)
- Extracts text via Surya OCR (with vision LLM fallback) for documents, receipts, screenshots
- Generates 300px JPEG thumbnails for fast browsing
- Indexes everything into SQLite + FTS5 for natural language search
- Detects renamed/moved files by fingerprint — no re-classification needed
- Resumes interrupted scans from the last checkpoint

## Screenshot

The app provides a VSCode-inspired search interface with custom titlebar, collapsible sidebar, thumbnail grid, media type filters, confidence slider, click-to-preview overlay, and automatic light/dark theme support.

## Requirements

- Linux (tested on Arch Linux with Hyprland/Wayland)
- [Ollama](https://ollama.com) installed and running (`ollama serve`)
- NVIDIA GPU recommended (RTX series for best performance with qwen2.5vl:7b)
- Node.js 20+
- Rust 1.77+

## Quick Start

```bash
# 1. Start Ollama
ollama serve

# 2. Build and run
cd sherlock/desktop
npm install
npm run tauri:dev
```

On first launch, the app will prompt you to download the required model (`qwen2.5vl:7b`) if it's not already installed. Click "Add Folder..." in the sidebar to pick a directory and start indexing.

### Wayland/NVIDIA Workaround

If the WebKit window is blank on Wayland with NVIDIA drivers:

```bash
WEBKIT_DISABLE_DMABUF_RENDERER=1 GDK_BACKEND=wayland,x11 npm run tauri:dev
```

## Build AppImage

```bash
cd sherlock/desktop
npm run tauri:build
```

The AppImage will be at `sherlock/desktop/src-tauri/target/release/bundle/appimage/`.

## Run Tests

```bash
cd sherlock/desktop/src-tauri
cargo test
```

49 unit tests covering classification JSON parsing, thumbnail generation, incremental scanning, database operations, scan cancellation, and query parsing.

## How It Works

### Incremental Scanning

Scans are designed for large NAS directories with 100k+ files:

1. **Discovery phase** — walks the directory tree using only filesystem metadata (mtime, size). Files matching their previous mtime and size are marked unchanged with zero file reads.
2. **Processing phase** — only new and modified files go through classification + thumbnail generation. Moved files are detected by fingerprint and only update their path reference.
3. **Cleanup phase** — files no longer on disk are soft-deleted, and their cached thumbnails are removed.

A rescan of an unchanged 10k-image directory completes in seconds.

### Classification Pipeline

Each new image goes through a multi-stage pipeline:

1. **Primary classification** — 3-attempt strategy with progressive fallback prompts and regex salvage for malformed JSON
2. **Anime enrichment** — conditional on media type; identifies series, characters, and canonical names
3. **OCR** — Surya OCR (isolated Python venv) with vision LLM fallback; triggered for documents, screenshots, and text-containing images
4. **Document extraction** — regex + LLM extraction of dates, amounts, transaction IDs from OCR text

### Search

Full-text search over filenames, paths, descriptions, OCR text, and character/series names. Supports natural language queries like:

- `anime ranma`
- `bank transfer 2024`
- `receipt santander`
- `screenshot confidence >= 0.8`

## Project Structure

```
sherlock/                  <- Main application
  desktop/
    src-tauri/src/         <- Rust backend
      classify.rs          <- Ollama vision + Surya OCR pipeline
      thumbnail.rs         <- Thumbnail generation
      scan.rs              <- Incremental scanner with cancellation
      db.rs                <- SQLite + FTS5
      config.rs            <- App paths
      lib.rs               <- Tauri commands, auto-cleanup
      query_parser.rs      <- NL query parsing
      runtime.rs           <- Ollama/GPU status
    scripts/
      surya_ocr.py         <- Isolated OCR script
    src/                   <- React frontend (VSCode-inspired UI)
classification/            <- Python PoC of the classification pipeline
```

### Research & Prototyping (Historical)

These directories contain the A/B testing research that informed Frank Sherlock's model selection and pipeline design. They are not part of the main application.

```
_research_ab_test/
  scripts/                 <- A/B benchmark scripts for model selection
  docs/                    <- Research notes (IDEA.md, RESULTS.md, etc.)
  lib/                     <- Shared Python helpers for benchmark scripts
  results/                 <- Generated benchmark outputs (gitignored)
  test_files/              <- Test corpus (gitignored, see note below)
```

> **Note:** The original test files (images, audio, video, documents) used for A/B benchmarking are **not included** in this repository. They contained copyrighted media and personal documents used only for private testing. If you want to re-run the A/B benchmarks, you need to:
>
> 1. Provide your own media files in `_research_ab_test/test_files/` with subdirectories like `images/`, `old_audio/`, `old_docs/`, `old_tvseries/`
> 2. Update the ground truth JSON files in `_research_ab_test/docs/` to match your test corpus
> 3. Adjust the benchmark scripts as needed — you can use Claude Code to help adapt them to your file structure

The benchmark results (`_research_ab_test/docs/RESULTS.md`) document why `qwen2.5vl:7b` was chosen over `llava:13b` and `minicpm-v:8b` (80% type accuracy vs 33-50%), and why Surya was chosen as primary OCR (95% reference similarity, better coverage than vision LLM alone).

## Data Storage

All application data is stored under `~/.local/share/frank_sherlock/`:

```
db/index.sqlite            <- SQLite database with FTS5
cache/thumbnails/          <- Generated thumbnails (mirrored path structure)
cache/classifications/     <- Classification cache
cache/tmp/                 <- Temporary files (GIF frames, etc.)
surya_venv/                <- Isolated Python venv for Surya OCR
```

Source directories are **never modified** — Frank Sherlock is strictly read-only.

## License

Private project.
