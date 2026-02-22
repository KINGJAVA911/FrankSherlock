#!/usr/bin/env python3
"""Phase 2d: OCR text extraction — A/B test PaddleOCR vs Surya vs Ollama Vision on screenshots/documents."""

import base64
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    TimedOperation, collect_test_files, relative_path,
    save_result, RESULTS_DIR, run_command, similarity_ratio,
)

OUTPUT_DIR = RESULTS_DIR / "phase2_images"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_VISION_MODEL = "qwen2.5vl:7b"

# Confidence threshold for reporting detected text
MIN_CONFIDENCE = 0.5


def pdf_to_image(pdf_path: Path) -> Path | None:
    """Convert first page of a PDF to a PNG image for OCR processing."""
    temp_dir = OUTPUT_DIR / "temp_ocr"
    temp_dir.mkdir(parents=True, exist_ok=True)
    out_path = temp_dir / f"{pdf_path.stem}_page1.png"
    if out_path.exists():
        return out_path
    # Use ImageMagick's convert or pdftoppm (poppler)
    run_command([
        "pdftoppm", "-png", "-f", "1", "-l", "1", "-r", "300",
        str(pdf_path), str(temp_dir / pdf_path.stem),
    ], timeout=30)
    # pdftoppm outputs <prefix>-1.png
    expected = temp_dir / f"{pdf_path.stem}-1.png"
    if expected.exists():
        expected.rename(out_path)
        return out_path
    # Fallback: try with just the output (some pdftoppm versions differ)
    candidates = list(temp_dir.glob(f"{pdf_path.stem}*.png"))
    if candidates:
        candidates[0].rename(out_path)
        return out_path
    return None


# ---------------------------------------------------------------------------
# PaddleOCR engine
# ---------------------------------------------------------------------------
def run_paddleocr(filepath: Path, langs: list[str]) -> dict:
    """Run PaddleOCR on a single image."""
    from paddleocr import PaddleOCR

    # PaddleOCR language codes: 'en', 'japan', 'ch', 'pt' (Portuguese), etc.
    # Use first lang for the primary model, PaddleOCR can only use one at a time
    lang = langs[0] if langs else "en"
    ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
    result = ocr.ocr(str(filepath), cls=True)

    lines = []
    if result and result[0]:
        for detection in result[0]:
            bbox, (text, confidence) = detection
            if confidence >= MIN_CONFIDENCE:
                lines.append({
                    "text": text,
                    "confidence": round(float(confidence), 4),
                    "bbox": [[round(c) for c in pt] for pt in bbox],
                })

    full_text = "\n".join(l["text"] for l in lines)
    avg_conf = sum(l["confidence"] for l in lines) / max(len(lines), 1)

    return {
        "lines": lines,
        "full_text": full_text,
        "line_count": len(lines),
        "avg_confidence": round(avg_conf, 4),
    }


# ---------------------------------------------------------------------------
# Surya OCR engine (models cached at module level to avoid reloading per image)
# ---------------------------------------------------------------------------
_surya_det = None
_surya_rec = None


def _get_surya_predictors():
    global _surya_det, _surya_rec
    if _surya_det is None:
        from surya.detection import DetectionPredictor
        _surya_det = DetectionPredictor()
    if _surya_rec is None:
        from surya.recognition import RecognitionPredictor
        _surya_rec = RecognitionPredictor()
    return _surya_det, _surya_rec


def run_surya(filepath: Path, langs: list[str]) -> dict:
    """Run Surya OCR on a single image (surya-ocr 0.12.x class-based API)."""
    from PIL import Image

    if not langs:
        langs = ["en"]

    image = Image.open(filepath).convert("RGB")

    det_predictor, rec_predictor = _get_surya_predictors()

    predictions = rec_predictor([image], [langs], det_predictor)

    lines = []
    if predictions and len(predictions) > 0:
        page = predictions[0]
        for line in page.text_lines:
            conf = line.confidence if line.confidence is not None else 1.0
            if conf >= MIN_CONFIDENCE:
                lines.append({
                    "text": line.text,
                    "confidence": round(float(conf), 4),
                    "bbox": line.bbox if hasattr(line, "bbox") else [],
                })

    full_text = "\n".join(l["text"] for l in lines)
    avg_conf = sum(l["confidence"] for l in lines) / max(len(lines), 1)

    return {
        "lines": lines,
        "full_text": full_text,
        "line_count": len(lines),
        "avg_confidence": round(avg_conf, 4),
    }


# ---------------------------------------------------------------------------
# Ollama Vision OCR (qwen2.5-vl)
# ---------------------------------------------------------------------------
def run_ollama_ocr(filepath: Path) -> dict:
    """Use Ollama vision model as an OCR engine."""
    with open(filepath, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    prompt = (
        "Extract ALL visible text from this image exactly as it appears. "
        "Preserve line breaks, formatting, and any special characters. "
        "Include UI labels, button text, menu items, headers, body text, "
        "code, URLs, and any other readable text. "
        "Do NOT describe the image — only output the raw extracted text. "
        "If text is in a non-English language, output it in the original language."
    )

    payload = {
        "model": OLLAMA_VISION_MODEL,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2048},
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "")
        return {
            "full_text": text.strip(),
            "line_count": len(text.strip().splitlines()),
            "total_duration_ms": data.get("total_duration", 0) / 1e6,
            "eval_count": data.get("eval_count", 0),
        }
    except Exception as e:
        return {"error": str(e), "full_text": ""}


# ---------------------------------------------------------------------------
# Engine availability checks
# ---------------------------------------------------------------------------
def check_paddleocr() -> bool:
    try:
        import paddleocr  # noqa: F401
        return True
    except ImportError:
        return False


def check_surya() -> bool:
    try:
        import surya  # noqa: F401
        return True
    except ImportError:
        return False


def check_ollama() -> bool:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        return resp.ok
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def guess_languages(filepath: Path) -> list[str]:
    """Guess likely languages from filename or default to English."""
    name = filepath.stem.lower()
    if any(token in name for token in ["santander", "procuração", "procuracao", "comprovante"]):
        return ["pt", "en"]
    if any(token in name for token in ["op", "ed", "gundam", "kenshin", "mononoke", "ev_", "megmpa", "lodoss", "miyuki"]):
        return ["ja", "en"]
    if "screenshot" in name:
        return ["en", "pt"]
    return ["en", "ja", "pt"]


def extract_pdf_text_reference(filepath: Path) -> str:
    """Extract reference text from PDF text layer when available."""
    if filepath.suffix.lower() != ".pdf" and filepath.suffix:
        return ""
    probe = run_command(["file", "--brief", "--mime-type", str(filepath)], timeout=5)
    if "pdf" not in probe.get("stdout", ""):
        return ""
    text_out = run_command(["pdftotext", "-f", "1", "-l", "1", str(filepath), "-"], timeout=20)
    if text_out["returncode"] == 0:
        return text_out.get("stdout", "").strip()
    return ""


def process_image(filepath: Path, engines: dict) -> dict:
    """Run all available OCR engines on a single image (or PDF converted to image)."""
    rel = relative_path(filepath)
    print(f"\n--- {rel} ---")

    entry = {
        "file": rel,
        "filename": filepath.name,
        "engines": {},
        "timing": {},
    }

    # Convert PDF to image if needed
    ocr_filepath = filepath
    if filepath.suffix.lower() == ".pdf" or not filepath.suffix:
        # Check if it's actually a PDF
        probe = run_command(["file", "--brief", "--mime-type", str(filepath)], timeout=5)
        if "pdf" in probe.get("stdout", ""):
            converted = pdf_to_image(filepath)
            if converted:
                ocr_filepath = converted
                entry["pdf_converted_to"] = str(converted)
                print(f"  Converted PDF to image: {converted.name}")
            else:
                entry["error"] = "PDF conversion failed (install poppler-utils for pdftoppm)"
                return entry

    langs = guess_languages(filepath)
    entry["languages_tested"] = langs
    reference_text = extract_pdf_text_reference(filepath)
    if reference_text:
        entry["reference_text"] = reference_text[:5000]

    if engines.get("paddleocr"):
        with TimedOperation(f"paddleocr/{filepath.name}") as t:
            try:
                result = run_paddleocr(ocr_filepath, [langs[0]])
                if reference_text:
                    result["reference_similarity"] = similarity_ratio(result.get("full_text", ""), reference_text)
                entry["engines"]["paddleocr"] = result
            except Exception as e:
                entry["engines"]["paddleocr"] = {"error": str(e), "full_text": ""}
                print(f"  [ERROR] PaddleOCR: {e}")
        entry["timing"]["paddleocr_s"] = round(t.elapsed, 4)

    if engines.get("surya"):
        with TimedOperation(f"surya/{filepath.name}") as t:
            try:
                result = run_surya(ocr_filepath, langs)
                if reference_text:
                    result["reference_similarity"] = similarity_ratio(result.get("full_text", ""), reference_text)
                entry["engines"]["surya"] = result
            except Exception as e:
                entry["engines"]["surya"] = {"error": str(e), "full_text": ""}
                print(f"  [ERROR] Surya: {e}")
        entry["timing"]["surya_s"] = round(t.elapsed, 4)

    if engines.get("ollama"):
        with TimedOperation(f"ollama_ocr/{filepath.name}") as t:
            try:
                # Ollama can handle PDFs directly as images if converted,
                # but send the original for vision context
                result = run_ollama_ocr(ocr_filepath)
                if reference_text:
                    result["reference_similarity"] = similarity_ratio(result.get("full_text", ""), reference_text)
                entry["engines"]["ollama_vision"] = result
            except Exception as e:
                entry["engines"]["ollama_vision"] = {"error": str(e), "full_text": ""}
                print(f"  [ERROR] Ollama: {e}")
        entry["timing"]["ollama_vision_s"] = round(t.elapsed, 4)

    entry["timing"]["total_s"] = round(
        sum(v for v in entry["timing"].values() if isinstance(v, float)), 4
    )

    # Quick comparison: which engine extracted the most text?
    text_lengths = {}
    for eng_name, eng_result in entry["engines"].items():
        if isinstance(eng_result, dict):
            text_lengths[eng_name] = len(eng_result.get("full_text", ""))
    entry["text_length_comparison"] = text_lengths

    return entry


def main():
    print("=" * 60)
    print("Phase 2d: OCR Text Extraction (A/B/C Test)")
    print("=" * 60)

    # Check which engines are available
    engines = {
        "paddleocr": check_paddleocr(),
        "surya": check_surya(),
        "ollama": check_ollama(),
    }
    print(f"\nAvailable engines:")
    for name, available in engines.items():
        status = "OK" if available else "NOT INSTALLED"
        print(f"  {name}: {status}")

    if not any(engines.values()):
        print("\nNo OCR engines available. Install paddleocr, surya-ocr, or start Ollama.")
        return

    # Collect images — process ALL images (screenshots will have more text,
    # but anime art with text overlays is also interesting for OCR)
    # Also include PDF documents since they often contain scannable text
    images = collect_test_files("image")
    # Add PDFs that might be in the images folder (receipts, legal docs)
    documents = collect_test_files("document")
    pdf_docs = [d for d in documents if d.suffix.lower() == ".pdf"]
    all_files = images + pdf_docs
    print(f"\nProcessing {len(all_files)} files ({len(images)} images + {len(pdf_docs)} PDFs) "
          f"with {sum(engines.values())} engine(s)...\n")

    results = []
    for filepath in all_files:
        entry = process_image(filepath, engines)
        results.append(entry)

    # Timing summary
    timing_by_engine = {}
    for r in results:
        for key, val in r.get("timing", {}).items():
            if key == "total_s":
                continue
            timing_by_engine.setdefault(key, []).append(val)

    timing_summary = {
        "total_images": len(images),
        "engines_used": [k for k, v in engines.items() if v],
        "per_engine_avg_s": {k: round(sum(v) / len(v), 4) for k, v in timing_by_engine.items()},
        "per_engine_total_s": {k: round(sum(v), 4) for k, v in timing_by_engine.items()},
        "phase_total_s": round(sum(r.get("timing", {}).get("total_s", 0) for r in results), 4),
    }

    # Text extraction comparison
    extraction_summary = {}
    for eng_name in ["paddleocr", "surya", "ollama_vision"]:
        texts = []
        similarities = []
        for r in results:
            if eng_name not in r.get("engines", {}):
                continue
            eng = r["engines"].get(eng_name, {})
            texts.append(eng.get("full_text", ""))
            sim = eng.get("reference_similarity")
            if isinstance(sim, (int, float)):
                similarities.append(float(sim))
        if texts:
            extraction_summary[eng_name] = {
                "images_processed": len(texts),
                "images_with_text": sum(1 for t in texts if t.strip()),
                "avg_text_length": round(sum(len(t) for t in texts) / len(texts), 1),
                "total_chars_extracted": sum(len(t) for t in texts),
                "avg_reference_similarity": round(sum(similarities) / len(similarities), 4) if similarities else None,
                "reference_samples": len(similarities),
            }

    output = {
        "phase": "2d_ocr",
        "engines_available": engines,
        "total_images": len(images),
        "timing_summary": timing_summary,
        "extraction_summary": extraction_summary,
        "results": results,
    }
    save_result(output, OUTPUT_DIR / "ocr_results.json")

    # Print summary
    print(f"\n{'=' * 60}")
    print("Phase 2d Complete — OCR Results:")
    print(f"{'=' * 60}")
    print(f"\nImages processed: {len(results)}")
    for eng_name, summary in extraction_summary.items():
        print(f"\n  {eng_name}:")
        print(f"    Images with text: {summary['images_with_text']}/{summary['images_processed']}")
        print(f"    Avg text length: {summary['avg_text_length']} chars")
        print(f"    Total chars: {summary['total_chars_extracted']}")

    if timing_summary.get("per_engine_avg_s"):
        print(f"\n  Speed comparison (avg per image):")
        for eng, avg in timing_summary["per_engine_avg_s"].items():
            print(f"    {eng}: {avg:.3f}s")

    # Show top OCR results for screenshots
    print(f"\n--- Top OCR extractions (screenshots) ---")
    for r in results:
        if "screenshot" in r["filename"].lower():
            print(f"\n  {r['filename']}:")
            for eng_name, eng_result in r["engines"].items():
                text = eng_result.get("full_text", "")[:150]
                if text:
                    print(f"    {eng_name}: \"{text}...\"")
                else:
                    print(f"    {eng_name}: (no text)")
    print("=" * 60)


if __name__ == "__main__":
    main()
