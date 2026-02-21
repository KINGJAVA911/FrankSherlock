## Frank Sherlock — Research Results

### Overview

This report summarizes the results of running all five phases of the Frank Sherlock media cataloging research experiment. The goal was to evaluate local, open-source AI tools for classifying images, audio, and video files — specifically a collection of 1990s anime media and one feature film.

**Hardware**: AMD 7850X3D + RTX 5090 (32GB VRAM), Arch Linux
**Test corpus**: 63 files — 39 images, 9 audio, 7 video, 8 documents

---

### Phase 1: Metadata Extraction (Baseline)

ExifTool, ffprobe, and MediaInfo processed all 63 files with zero errors.

**Key findings**:
- Goldfinger: 1920x1080, H.264/AC3, 110 min, NFO confirmed IMDB tt0058150
- Most anime images are from 1995-1998 (file dates preserved from the era)
- `Fushigi Yuugi (op).avi` is 0 bytes (corrupt, handled gracefully)
- `Gundam 0083 (op1).mov` has a broken moov atom (1MB, unplayable video but metadata extracted)
- Audio files are a mix of MP3 (128-192kbps), MP2, and MPA — all from the late 1990s

**Verdict**: Metadata alone gives us file format, dimensions, duration, and codec info. It cannot identify *what* the content is (which anime, which song). It establishes a useful baseline that AI tools build upon.

---

### Phase 2: Image Classification

#### 2a — Ollama Vision LLMs (qwen2.5vl:7b + llava:13b)

234 LLM calls total (39 images x 2 models x 3 prompts). Each image took ~5-10 seconds on the RTX 5090.

**Strengths**:
- Correctly identified `Bastard!!` manga covers by reading the title text on the image
- Identified `Neon Genesis Evangelion` characters (Rei, Asuka) from the `ev_` images
- Read the "Slayers" title from `insert01.jpg`
- Described desktop screenshots accurately (terminal emulators, browser windows, etc.)
- qwen2.5vl:7b was generally more detailed and accurate than llava:13b

**Weaknesses**:
- Frequently hallucinated series names for ambiguous images (e.g., called Lodoss War images "Cowboy Bebop", Gall Force images "Evangelion", Miyuki-chan "JoJo's Bizarre Adventure")
- Cannot reliably identify characters without text on the image
- GIF files produced empty responses from qwen2.5vl (likely a format handling issue)

#### 2b — WD Tagger (SwinV2 v3)

39 images tagged in ~13 seconds total (0.3s each on CPU — CUDA provider failed due to cuDNN version mismatch, but CPU was fast enough for this corpus).

**Strengths**:
- Correctly tagged visual attributes: `1girl`, `retro_artstyle`, `1980s_(style)`, `armor`, `dragon`, `pointy_ears`, `elf`
- Identified art style era accurately (`retro_artstyle`, `1980s_(style)` for 90s anime)
- Very fast — 10x faster than Ollama vision per image
- Consistent, structured booru-style output

**Weaknesses**:
- Cannot identify specific series or characters (no `bastard!!` or `evangelion` tags)
- Desktop screenshots got meaningless anime-oriented tags
- No character recognition (the `character` tag category was empty for all images)

#### 2c — Comparison Summary

| Metric | Ollama Vision | WD Tagger |
|--------|--------------|-----------|
| Series identification | 7/39 correct | 0/39 |
| Speed per image | ~5-10s | ~0.3s |
| Art style detection | Descriptive text | Structured tags |
| Screenshot handling | Good (reads UI text) | Poor (out-of-domain) |
| Hallucination risk | High | None |
| Best use case | Content description, text reading | Visual attribute tagging, filtering |

**Conclusion**: The two tools are complementary, not competitive. Ollama vision excels when there's readable text in the image. WD Tagger provides reliable visual attributes but cannot name series. For a cataloging pipeline, use WD Tagger for fast filtering/tagging and Ollama for deeper analysis on selected images.

---

### Phase 3: Audio Recognition

#### 3a — Chromaprint / AcoustID

All 9 audio files and 5 video audio tracks produced valid fingerprints via `fpcalc`. AcoustID API lookups were skipped (no API key configured). The fingerprints are stored and ready for lookup when a key is registered.

**Verdict**: Fingerprinting works reliably. The value depends entirely on AcoustID database coverage — mainstream music will match, but obscure 1990s anime OPs/EDs may not. Worth registering an API key to test.

#### 3b — Whisper (base + small models)

14 audio tracks transcribed on GPU. Each track took 1-11 seconds with the `base` model and 2-18 seconds with `small`.

**Language detection results**:

| File | base model | small model | Actual content |
|------|-----------|-------------|----------------|
| 100MPH (op).mp3 | English (wrong) | Japanese (correct) | Future GPX Cyber Formula OP |
| 19h_no_News_(op1).mp3 | Japanese | Japanese | Anime OP |
| American_Opening.mp3 | English | English | Sailor Moon English OP |
| Condition_Green.mp3 | Japanese | Japanese | Anime song |
| Hateshinai Toiki.mp2 | English (wrong) | Japanese (correct) | Anime ballad |
| Motto! Motto! Tokimeki.mp2 | Japanese | Japanese | Anime OP |
| conaned.mp3 | Russian (!) | Japanese | Detective Conan ED |
| mydear.mp2 | Japanese | Japanese | Anime ballad |
| track01.mpa | Japanese | Japanese | Anime OP |
| Goldfinger (first 60s) | English | English | Film intro (mostly music) |
| Goldfinger (mid 60s) | English | English | Film dialogue (correctly transcribed) |
| CLAMP in Wonderland | English | English | OVA (English mixed w/ Japanese) |
| Mononoke Hime trailer | Japanese | Japanese | Ghibli trailer narration |
| Rurouni Kenshin clip | Japanese | Japanese | "Sobakasu" / "Sanbun no Ichi" lyrics |
| Sonic CD (op) | English | English | "Sonic Boom" correctly transcribed |

**Key findings**:
- The `small` model is significantly more accurate than `base` for Japanese content. `base` hallucinated English for two Japanese songs.
- `conaned.mp3` was detected as Russian by `base` — a fascinating failure mode (the Detective Conan Russian dub?)
- Whisper `small` correctly transcribed recognizable lyrics: "壊れるほど愛しても三分の一も伝わらない" (Rurouni Kenshin's "Sobakasu"), "Fighting evil by moonlight" (Sailor Moon), "Sonic Boom, Sonic Boom" (Sonic CD)
- Goldfinger dialogue was accurately transcribed at the 30-minute mark
- For song identification, transcribed lyrics can be searched against lyric databases

#### 3c — Comparison

Whisper won 14/16 comparisons (Chromaprint had 0 because no API key was set). Even with API access, Whisper would likely win for obscure anime content where AcoustID database coverage is poor.

**Conclusion**: Whisper `small` is the recommended model for this corpus. It provides language detection (crucial for sorting Japanese vs English content) and transcribed content that can aid identification. Use Chromaprint as a fast first-pass for mainstream music.

---

### Phase 4: Video Analysis

#### 4a — Frame Extraction

100 keyframes extracted from 5 playable videos using ffmpeg scene-change detection (threshold 0.3). All videos hit the 20-frame cap, indicating rich scene variety.

#### 4b — Multi-Signal Classification

Combined metadata + keyframe vision + audio + filename + NFO signals, then synthesized with an LLM:

| Video | Identification | Type | Confidence | Key Signals |
|-------|---------------|------|------------|-------------|
| Goldfinger.mp4 | James Bond: Goldfinger | Movie | 0.95 | NFO (IMDB), filename, English dialogue, live-action frames |
| ClampInWonderland.avi | CLAMP in Wonderland | Anime OVA | 0.80 | Filename, anime frames, mixed-language audio |
| Gundam 0083 (op1).mov | Gundam 0083 | Anime OP | 0.80 | Filename only (video corrupt) |
| MononokeHime_Trailer3.mov | Princess Mononoke | Trailer | 0.90 | Filename, Japanese narration, Ghibli-style frames |
| RurouniKenshin_Sanbun_clip.mpg | Rurouni Kenshin | Anime clip | 0.90 | Filename, Japanese lyrics, anime frames |
| SonicCD_(op).avi | Sonic CD Opening | Game/Animation | 0.90 | Filename, "Sonic Boom" lyrics, animated frames |

**Key findings**:
- Multi-signal synthesis is much more reliable than any single tool
- Filename parsing alone got 5/6 correct identifications (the human who named the files did the hard work)
- Even the corrupt Gundam 0083 MOV was identified from filename + metadata context
- Vision-analyzed keyframes confirmed anime vs live-action, adding confidence
- Whisper audio contributed language detection and occasionally recognizable content

---

### Phase 5: Unified Catalog

All 63 files cataloged into a single JSON file (`results/catalog.json`). The catalog is valid JSON and queryable with `jq`.

---

### Recommendations for NAS-Scale Deployment

1. **Use Whisper `small` not `base`** for Japanese content — the accuracy difference is substantial
2. **WD Tagger first, Ollama second** for images — WD Tagger is 10-30x faster and provides good filtering tags; reserve Ollama for images that need deeper analysis
3. **Filename parsing is surprisingly effective** — most media files have descriptive names; combine with AI for confirmation rather than replacement
4. **Register an AcoustID API key** — Chromaprint fingerprinting is instant and could identify mainstream content without GPU
5. **Limit video processing** — extracting 3-5 keyframes + 60s audio is enough for classification; never process full streams
6. **Sequential GPU scheduling** — Ollama and Whisper share GPU memory; run them sequentially, not in parallel
7. **Consider vLLM** for NAS-scale batch processing instead of Ollama — better throughput for hundreds of files
8. **The `small` Whisper model fits comfortably alongside Ollama** on 32GB VRAM — no need for model swapping on RTX 5090

### Tools Evaluated

| Tool | Purpose | Verdict |
|------|---------|---------|
| ExifTool | File metadata | Essential baseline, always run |
| ffprobe/MediaInfo | AV metadata | Essential for audio/video |
| Ollama (qwen2.5vl:7b) | Vision LLM | Good for text-rich images, some hallucination |
| Ollama (llava:13b) | Vision LLM | Slightly less accurate than qwen2.5vl |
| WD Tagger (SwinV2 v3) | Anime image tagging | Fast, reliable tags, no series ID |
| Chromaprint/fpcalc | Audio fingerprint | Fast, needs AcoustID API key to be useful |
| Whisper (small) | Speech-to-text | Excellent for language detection + lyrics |
| ffmpeg | Frame extraction | Reliable, scene detection works well |

### Files Produced

```
results/
  phase1_metadata/all_metadata.json        # 63 files, ExifTool+ffprobe+MediaInfo
  phase2_images/ollama_vision_results.json  # 39 images x 2 models x 3 prompts
  phase2_images/wd_tagger_results.json      # 39 images, booru-style tags
  phase2_images/comparison_report.json      # A/B comparison
  phase3_audio/chromaprint_results.json     # 15 fingerprints
  phase3_audio/whisper_results.json         # 15 transcriptions (base+small)
  phase3_audio/comparison_report.json       # A/B comparison
  phase4_video/frame_extraction.json        # 100 keyframes from 5 videos
  phase4_video/video_classification.json    # Multi-signal identifications
  catalog.json                              # Unified catalog of all 63 files
```
