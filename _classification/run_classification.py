#!/usr/bin/env python3
"""Prototype image classification pipeline for IDEA2.

This prototype:
- runs sequentially over all images under an input root
- uses qwen2.5vl:7b as primary vision model
- enriches anime-like images with character/series details
- enriches text-heavy/document-like images with OCR + receipt parsing
- writes mirrored outputs as .yml (JSON-compatible YAML) and .txt
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import time
from pathlib import Path

import requests
from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import extract_first_json_object

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5vl:7b"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}

PRIMARY_PROMPT = (
    "Analyze this image and respond ONLY with valid JSON. Schema: "
    '{"media_type":"screenshot|anime|manga|photo|document|artwork|other",'
    '"contains_text":true,'
    '"is_anime_related":false,'
    '"is_document_like":false,'
    '"description":"short factual description",'
    '"series_candidates":["name"],'
    '"character_candidates":["name"],'
    '"confidence":0.0}'
    " Rules: "
    "1) Use null-like empty arrays when unknown. "
    "2) If image has visible text (UI, receipt, scan, subtitles), contains_text=true. "
    "3) is_document_like=true for receipts/invoices/forms/scanned docs/screenshots of documents. "
    "4) series_candidates and character_candidates must be unique and max 5 items each. "
    "5) Keep description under 24 words. "
    "6) Favor precision over guesswork."
)

PRIMARY_PROMPT_FALLBACK = (
    "Return ONLY valid compact JSON with schema: "
    '{"media_type":"screenshot|anime|manga|photo|document|artwork|other",'
    '"contains_text":true,'
    '"is_anime_related":false,'
    '"is_document_like":false,'
    '"description":"max 24 words",'
    '"series_candidates":["max 3 unique names"],'
    '"character_candidates":["max 3 unique names"],'
    '"confidence":0.0}'
    " Never exceed 3 items in candidates arrays. Never repeat entries. No markdown."
)

ANIME_PROMPT = (
    "This appears anime/manga-related. Return ONLY valid JSON with schema: "
    '{"series":"name or null",'
    '"franchise":"name or null",'
    '"characters":[{"name":"full canonical name","series":"name or null","confidence":0.0}],'
    '"canonical_mentions":["Name from Series"],'
    '"scene_summary":"short",'
    '"confidence":0.0}'
    " Rules: prefer canonical full names when possible; if unknown set null/empty."
)

OCR_PROMPT = (
    "Extract ALL visible text exactly as seen. "
    "Return ONLY raw text. Preserve line breaks."
)

RECEIPT_PROMPT = (
    "Given OCR text from a potential receipt/bank document, extract structured fields. "
    "Return ONLY valid JSON schema: "
    '{"document_kind":"receipt|invoice|bank_transfer|statement|other",'
    '"issuer":"string or null",'
    '"counterparty":"string or null",'
    '"date":"YYYY-MM-DD or null",'
    '"time":"HH:MM:SS or null",'
    '"amount":"string or null",'
    '"currency":"BRL|USD|EUR|other|null",'
    '"transaction_id":"string or null",'
    '"reference_numbers":["string"],'
    '"important_fields":[{"key":"string","value":"string"}],'
    '"confidence":0.0}'
    " OCR text:\n"
)

_SURYA_DET = None
_SURYA_REC = None


def iter_images(input_root: Path) -> list[Path]:
    files = []
    for p in input_root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            files.append(p)
    return sorted(files)


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_as_yaml_text(data: dict) -> str:
    # JSON is valid YAML 1.2 and keeps output deterministic.
    return json.dumps(data, indent=2, ensure_ascii=True) + "\n"


def write_yaml(path: Path, data: dict):
    ensure_dir(path.parent)
    path.write_text(json_as_yaml_text(data))


def write_text(path: Path, text: str):
    ensure_dir(path.parent)
    path.write_text((text or "").strip() + "\n")


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def ollama_generate(
    model: str,
    prompt: str,
    image_path: Path | None = None,
    num_predict: int = 700,
    timeout: int = 180,
    json_mode: bool = False,
) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "20m",
        "options": {
            "temperature": 0.1,
            "num_predict": num_predict,
        },
    }
    if image_path:
        payload["images"] = [encode_image(image_path)]
    if json_mode:
        payload["format"] = "json"

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return {
            "ok": True,
            "raw": data.get("response", ""),
            "total_duration_s": round(float(data.get("total_duration", 0)) / 1e9, 4),
            "eval_count": data.get("eval_count", 0),
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "raw": ""}


def parse_json_response(raw: str) -> dict | None:
    if not raw:
        return None
    return extract_first_json_object(raw)


def _extract_quoted_items(list_fragment: str, limit: int = 5) -> list[str]:
    items = re.findall(r'"([^"]+)"', list_fragment or "")
    out = []
    seen = set()
    for item in items:
        val = item.strip()
        if not val:
            continue
        key = val.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(val)
        if len(out) >= limit:
            break
    return out


def salvage_primary_from_raw(raw: str) -> dict | None:
    if not raw:
        return None

    media_type_m = re.search(r'"media_type"\s*:\s*"([^"]+)"', raw, flags=re.IGNORECASE)
    if not media_type_m:
        return None
    media_type = media_type_m.group(1).strip().lower()

    def _extract_bool(key: str, default: bool = False) -> bool:
        m = re.search(rf'"{key}"\s*:\s*(true|false)', raw, flags=re.IGNORECASE)
        if not m:
            return default
        return m.group(1).lower() == "true"

    desc_m = re.search(r'"description"\s*:\s*"([^"]*)"', raw, flags=re.IGNORECASE)
    conf_m = re.search(r'"confidence"\s*:\s*([0-9]*\.?[0-9]+)', raw, flags=re.IGNORECASE)
    series_m = re.search(r'"series_candidates"\s*:\s*\[([^\]]*)', raw, flags=re.IGNORECASE | re.DOTALL)
    chars_m = re.search(r'"character_candidates"\s*:\s*\[([^\]]*)', raw, flags=re.IGNORECASE | re.DOTALL)

    return {
        "media_type": media_type if media_type in {"screenshot", "anime", "manga", "photo", "document", "artwork", "other"} else "other",
        "contains_text": _extract_bool("contains_text", False),
        "is_anime_related": _extract_bool("is_anime_related", media_type in {"anime", "manga", "artwork"}),
        "is_document_like": _extract_bool("is_document_like", media_type in {"document", "screenshot"}),
        "description": (desc_m.group(1).strip() if desc_m else ""),
        "series_candidates": _extract_quoted_items(series_m.group(1) if series_m else "", limit=5),
        "character_candidates": _extract_quoted_items(chars_m.group(1) if chars_m else "", limit=5),
        "confidence": float(conf_m.group(1)) if conf_m else 0.0,
    }


def normalize_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    for x in value:
        if isinstance(x, str):
            s = x.strip()
            if s and s.lower() not in {"null", "none", "unknown"}:
                out.append(s)
    return out


def clean_nullable_str(value: str | None):
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s or s.lower() in {"null", "none", "unknown", "n/a"}:
        return None
    return s


def first_frame_if_gif(image_path: Path, tmp_dir: Path) -> Path:
    if image_path.suffix.lower() != ".gif":
        return image_path
    ensure_dir(tmp_dir)
    out = tmp_dir / f"{image_path.stem}_frame1.png"
    if out.exists():
        return out
    with Image.open(image_path) as im:
        im.seek(0)
        im.convert("RGB").save(out, format="PNG")
    return out


def classify_primary(model: str, image_path: Path) -> dict:
    raw_attempts = []
    call = ollama_generate(
        model=model,
        prompt=PRIMARY_PROMPT,
        image_path=image_path,
        num_predict=500,
        json_mode=True,
    )
    raw_attempts.append(call.get("raw", ""))
    parsed = parse_json_response(call.get("raw", "")) if call.get("ok") else None
    if not parsed:
        retry_prompt = PRIMARY_PROMPT + " Return a single JSON object only."
        call = ollama_generate(
            model=model,
            prompt=retry_prompt,
            image_path=image_path,
            num_predict=500,
            json_mode=False,
        )
        raw_attempts.append(call.get("raw", ""))
        parsed = parse_json_response(call.get("raw", "")) if call.get("ok") else None
    if not parsed:
        call = ollama_generate(
            model=model,
            prompt=PRIMARY_PROMPT_FALLBACK,
            image_path=image_path,
            num_predict=260,
            json_mode=True,
        )
        raw_attempts.append(call.get("raw", ""))
        parsed = parse_json_response(call.get("raw", "")) if call.get("ok") else None
    if not parsed:
        salvage = None
        for raw in raw_attempts:
            salvage = salvage_primary_from_raw(raw)
            if salvage:
                break
        if salvage:
            return {
                **salvage,
                "timing_s": call.get("total_duration_s", 0.0),
                "raw": call.get("raw", ""),
                "salvaged": True,
            }
        return {
            "error": call.get("error", "invalid_json"),
            "raw": call.get("raw", ""),
            "media_type": "other",
            "contains_text": False,
            "is_anime_related": False,
            "is_document_like": False,
            "description": "",
            "series_candidates": [],
            "character_candidates": [],
            "confidence": 0.0,
            "timing_s": call.get("total_duration_s", 0.0),
        }
    return {
        "media_type": (parsed.get("media_type") or "other"),
        "contains_text": bool(parsed.get("contains_text", False)),
        "is_anime_related": bool(parsed.get("is_anime_related", False)),
        "is_document_like": bool(parsed.get("is_document_like", False)),
        "description": (parsed.get("description") or "").strip(),
        "series_candidates": normalize_list(parsed.get("series_candidates")),
        "character_candidates": normalize_list(parsed.get("character_candidates")),
        "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        "timing_s": call.get("total_duration_s", 0.0),
        "raw": call.get("raw", ""),
    }


def classify_anime_details(model: str, image_path: Path) -> dict | None:
    call = ollama_generate(
        model=model,
        prompt=ANIME_PROMPT,
        image_path=image_path,
        num_predict=600,
        json_mode=True,
    )
    parsed = parse_json_response(call.get("raw", "")) if call.get("ok") else None
    if not parsed:
        call = ollama_generate(
            model=model,
            prompt=ANIME_PROMPT + " Return a single JSON object only.",
            image_path=image_path,
            num_predict=600,
            json_mode=False,
        )
        parsed = parse_json_response(call.get("raw", "")) if call.get("ok") else None
    if not parsed:
        return None
    characters = []
    for c in parsed.get("characters", []):
        if isinstance(c, dict):
            name = clean_nullable_str(c.get("name"))
            if name:
                characters.append({
                    "name": name,
                    "series": clean_nullable_str(c.get("series")),
                    "confidence": float(c.get("confidence", 0.0) or 0.0),
                })
    canonical_mentions = normalize_list(parsed.get("canonical_mentions"))
    canonical_mentions = [m for m in canonical_mentions if clean_nullable_str(m)]
    series = clean_nullable_str(parsed.get("series"))
    franchise = clean_nullable_str(parsed.get("franchise"))
    scene_summary = clean_nullable_str(parsed.get("scene_summary")) or ""
    confidence = float(parsed.get("confidence", 0.0) or 0.0)
    if not any([series, franchise, characters, canonical_mentions]) and confidence < 0.2:
        return None
    return {
        "series": series,
        "franchise": franchise,
        "characters": characters,
        "canonical_mentions": canonical_mentions,
        "scene_summary": scene_summary,
        "confidence": confidence,
        "timing_s": call.get("total_duration_s", 0.0),
    }


def _get_surya_predictors():
    global _SURYA_DET, _SURYA_REC
    if _SURYA_DET is None:
        from surya.detection import DetectionPredictor
        _SURYA_DET = DetectionPredictor()
    if _SURYA_REC is None:
        from surya.recognition import RecognitionPredictor
        _SURYA_REC = RecognitionPredictor()
    return _SURYA_DET, _SURYA_REC


def run_surya_ocr(image_path: Path) -> dict:
    try:
        det_predictor, rec_predictor = _get_surya_predictors()
    except Exception as e:
        return {"ok": False, "engine": "surya", "error": f"surya_init_failed: {e}", "text": ""}
    try:
        image = Image.open(image_path).convert("RGB")
        predictions = rec_predictor([image], [["en", "ja", "pt"]], det_predictor)
        lines = []
        if predictions and len(predictions) > 0:
            page = predictions[0]
            for line in page.text_lines:
                txt = (line.text or "").strip()
                if txt:
                    lines.append(txt)
        text = "\n".join(lines).strip()
        return {"ok": True, "engine": "surya", "line_count": len(lines), "text": text}
    except Exception as e:
        return {"ok": False, "engine": "surya", "error": f"surya_ocr_failed: {e}", "text": ""}


def run_llm_ocr(model: str, image_path: Path) -> dict:
    call = ollama_generate(model=model, prompt=OCR_PROMPT, image_path=image_path, num_predict=2000, timeout=240)
    if not call.get("ok"):
        return {"ok": False, "engine": "vision_llm", "error": call.get("error", "ocr_failed"), "text": ""}
    return {
        "ok": True,
        "engine": "vision_llm",
        "line_count": len((call.get("raw", "") or "").splitlines()),
        "text": (call.get("raw", "") or "").strip(),
        "timing_s": call.get("total_duration_s", 0.0),
    }


def extract_receipt_regex(text: str) -> dict:
    text = text or ""
    date_patterns = [
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(\d{2}/\d{2}/\d{4})\b",
        r"\b(\d{2}-\d{2}-\d{4})\b",
    ]
    amount_patterns = [
        r"\b(?:R\$|\$|EUR|USD)\s?[0-9][0-9\.,]*\b",
        r"\b[0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2}\b",
        r"\b[0-9]+(?:\.[0-9]{2})\b",
    ]
    transaction_patterns = [
        r"\b(?:ID|Tx|Transaction|Protocolo|Comprovante|Reference)[:\s#-]*([A-Za-z0-9\-_/]{6,})\b",
    ]
    dates = []
    for pat in date_patterns:
        dates.extend(re.findall(pat, text, flags=re.IGNORECASE))
    amounts = []
    for pat in amount_patterns:
        amounts.extend(re.findall(pat, text, flags=re.IGNORECASE))
    refs = []
    for pat in transaction_patterns:
        refs.extend(re.findall(pat, text, flags=re.IGNORECASE))
    currency = None
    if "R$" in text:
        currency = "BRL"
    elif "USD" in text or "$" in text:
        currency = "USD"
    elif "EUR" in text:
        currency = "EUR"

    return {
        "dates": list(dict.fromkeys(dates))[:6],
        "amount_candidates": list(dict.fromkeys(amounts))[:10],
        "reference_numbers": list(dict.fromkeys(refs))[:10],
        "currency_guess": currency,
    }


def extract_receipt_llm(model: str, ocr_text: str) -> dict | None:
    if not ocr_text.strip():
        return None
    prompt = RECEIPT_PROMPT + ocr_text[:5000]
    call = ollama_generate(
        model=model,
        prompt=prompt,
        image_path=None,
        num_predict=700,
        timeout=180,
        json_mode=True,
    )
    parsed = parse_json_response(call.get("raw", "")) if call.get("ok") else None
    if not parsed:
        call = ollama_generate(
            model=model,
            prompt=prompt + "\nReturn one JSON object only.",
            image_path=None,
            num_predict=700,
            timeout=180,
            json_mode=False,
        )
        parsed = parse_json_response(call.get("raw", "")) if call.get("ok") else None
    if not parsed:
        return None
    return {
        "document_kind": clean_nullable_str(parsed.get("document_kind")),
        "issuer": clean_nullable_str(parsed.get("issuer")),
        "counterparty": clean_nullable_str(parsed.get("counterparty")),
        "date": clean_nullable_str(parsed.get("date")),
        "time": clean_nullable_str(parsed.get("time")),
        "amount": clean_nullable_str(parsed.get("amount")),
        "currency": clean_nullable_str(parsed.get("currency")),
        "transaction_id": clean_nullable_str(parsed.get("transaction_id")),
        "reference_numbers": normalize_list(parsed.get("reference_numbers")),
        "important_fields": parsed.get("important_fields") if isinstance(parsed.get("important_fields"), list) else [],
        "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        "timing_s": call.get("total_duration_s", 0.0),
    }


def build_index_text(record: dict) -> str:
    lines = []
    src = record.get("source", {})
    primary = record.get("primary_classification", {})
    lines.append(f"file: {src.get('relative_path', '')}")
    lines.append(f"media_type: {primary.get('media_type', '')}")
    lines.append(f"confidence_primary: {primary.get('confidence', 0.0)}")
    lines.append(f"description: {primary.get('description', '')}")
    if primary.get("series_candidates"):
        lines.append("series_candidates: " + ", ".join(primary["series_candidates"]))
    if primary.get("character_candidates"):
        lines.append("character_candidates: " + ", ".join(primary["character_candidates"]))

    anime = record.get("anime_details")
    if anime:
        lines.append(f"confidence_anime: {anime.get('confidence', 0.0)}")
        if anime.get("series"):
            lines.append(f"anime_series: {anime.get('series')}")
        if anime.get("canonical_mentions"):
            lines.append("canonical_mentions: " + ", ".join(anime["canonical_mentions"]))
        if anime.get("characters"):
            for c in anime["characters"]:
                lines.append(f"character: {c.get('name')} from {c.get('series')}")

    doc = record.get("document_details")
    if doc:
        llm_doc = (doc.get("llm_fields") or {})
        if llm_doc:
            lines.append(f"confidence_document: {llm_doc.get('confidence', 0.0)}")
        lines.append(f"document_kind: {doc.get('document_kind')}")
        lines.append(f"issuer: {doc.get('issuer')}")
        lines.append(f"counterparty: {doc.get('counterparty')}")
        lines.append(f"date: {doc.get('date')}")
        lines.append(f"amount: {doc.get('amount')} {doc.get('currency')}")
        if doc.get("reference_numbers"):
            lines.append("reference_numbers: " + ", ".join(doc["reference_numbers"]))

    ocr = record.get("ocr")
    if ocr and ocr.get("text"):
        lines.append("ocr_text:")
        lines.append(ocr["text"])

    return "\n".join([ln for ln in lines if ln is not None])


def should_run_document_enrichment(primary: dict) -> bool:
    mt = (primary.get("media_type") or "").lower()
    if mt in {"document", "screenshot"}:
        return True
    return bool(primary.get("contains_text") or primary.get("is_document_like"))


def should_run_anime_enrichment(primary: dict) -> bool:
    mt = (primary.get("media_type") or "").lower()
    if mt in {"anime", "manga", "artwork"}:
        return True
    return bool(primary.get("is_anime_related"))


def process_image(image_path: Path, input_root: Path, output_root: Path, model: str, tmp_dir: Path) -> dict:
    t0 = time.perf_counter()
    rel = image_path.relative_to(input_root)
    print(f"\n--- {rel} ---")
    model_image_path = first_frame_if_gif(image_path, tmp_dir=tmp_dir)

    primary = classify_primary(model=model, image_path=model_image_path)
    anime_details = None
    ocr = None
    document_details = None

    if should_run_anime_enrichment(primary):
        anime_details = classify_anime_details(model=model, image_path=model_image_path)

    if should_run_document_enrichment(primary):
        ocr = run_surya_ocr(model_image_path)
        if not ocr.get("ok"):
            ocr = run_llm_ocr(model=model, image_path=model_image_path)
        regex_fields = extract_receipt_regex(ocr.get("text", ""))
        llm_fields = extract_receipt_llm(model=model, ocr_text=ocr.get("text", ""))
        document_details = {
            "regex_fields": regex_fields,
            "llm_fields": llm_fields,
            "document_kind": (llm_fields or {}).get("document_kind"),
            "issuer": (llm_fields or {}).get("issuer"),
            "counterparty": (llm_fields or {}).get("counterparty"),
            "date": (llm_fields or {}).get("date"),
            "time": (llm_fields or {}).get("time"),
            "amount": (llm_fields or {}).get("amount"),
            "currency": (llm_fields or {}).get("currency") or regex_fields.get("currency_guess"),
            "reference_numbers": (llm_fields or {}).get("reference_numbers") or regex_fields.get("reference_numbers", []),
        }
        txid = (llm_fields or {}).get("transaction_id")
        if isinstance(txid, str) and txid.strip().lower() in {"ted realizado com sucesso.", "ted realizado com sucesso"}:
            txid = None
        if not txid:
            auth_matches = re.findall(r"\b[A-Z0-9]{12,}\b", ocr.get("text", ""))
            if auth_matches:
                mixed = [m for m in auth_matches if re.search(r"[A-Z]", m) and re.search(r"[0-9]", m)]
                alpha_num = [m for m in auth_matches if re.search(r"[A-Z]", m)]
                txid = mixed[0] if mixed else (alpha_num[0] if alpha_num else auth_matches[0])
        if txid:
            document_details["transaction_id"] = txid

    record = {
        "prototype_version": "idea2-classification-v1",
        "source": {
            "absolute_path": str(image_path.resolve()),
            "relative_path": str(rel),
            "filename": image_path.name,
            "size_bytes": image_path.stat().st_size,
            "sha256": sha256_file(image_path),
        },
        "model": {
            "provider": "ollama",
            "name": model,
        },
        "primary_classification": primary,
        "anime_details": anime_details,
        "ocr": ocr,
        "document_details": document_details,
        "timing_s": round(time.perf_counter() - t0, 4),
    }
    index_text = build_index_text(record)
    record["index_text"] = index_text

    out_base = output_root / rel.with_suffix("")
    yml_path = out_base.with_suffix(".yml")
    txt_path = out_base.with_suffix(".txt")
    write_yaml(yml_path, record)
    write_text(txt_path, index_text)

    return {
        "relative_path": str(rel),
        "media_type": primary.get("media_type", "other"),
        "timing_s": record["timing_s"],
        "out_yml": str(yml_path),
        "out_txt": str(txt_path),
        "error": primary.get("error"),
    }


def check_model_available(model: str) -> bool:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=8)
        resp.raise_for_status()
        names = [m.get("name") for m in resp.json().get("models", [])]
        return model in names
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="IDEA2 image classification prototype")
    parser.add_argument("--input-root", default="test_files", help="Root folder to scan for images")
    parser.add_argument("--output-root", default="classification/test_results", help="Output root")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama vision model")
    parser.add_argument("--max-images", type=int, default=0, help="Optional cap for quick runs")
    args = parser.parse_args()

    input_root = Path(args.input_root).resolve()
    output_root = Path(args.output_root).resolve()
    tmp_dir = (output_root.parent / "tmp").resolve()
    ensure_dir(output_root)
    ensure_dir(tmp_dir)

    if not input_root.exists():
        raise SystemExit(f"Input root does not exist: {input_root}")
    if not check_model_available(args.model):
        raise SystemExit(f"Model not available in Ollama: {args.model}")

    images = iter_images(input_root)
    if args.max_images > 0:
        images = images[:args.max_images]

    print("=" * 60)
    print("IDEA2 Classification Prototype")
    print("=" * 60)
    print(f"Input root: {input_root}")
    print(f"Output root: {output_root}")
    print(f"Model: {args.model}")
    print(f"Images found: {len(images)}")
    print("Execution mode: sequential (single worker)")

    start = time.perf_counter()
    entries = []
    by_type = {}
    errors = 0

    for img in images:
        res = process_image(
            image_path=img,
            input_root=input_root,
            output_root=output_root,
            model=args.model,
            tmp_dir=tmp_dir,
        )
        entries.append(res)
        mt = res.get("media_type", "other")
        by_type[mt] = by_type.get(mt, 0) + 1
        if res.get("error"):
            errors += 1

    elapsed = round(time.perf_counter() - start, 4)
    avg_s = round(elapsed / max(len(images), 1), 4)
    report = {
        "prototype_version": "idea2-classification-v1",
        "model": args.model,
        "input_root": str(input_root),
        "output_root": str(output_root),
        "total_images": len(images),
        "errors": errors,
        "timing": {
            "total_s": elapsed,
            "avg_per_image_s": avg_s,
        },
        "media_type_counts": by_type,
        "entries": entries,
    }
    report_path = output_root / "_run_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")

    # Easier batch indexing later.
    index_path = output_root / "index.jsonl"
    with open(index_path, "w") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=True) + "\n")

    print("\n" + "=" * 60)
    print("Prototype complete")
    print(f"Report: {report_path}")
    print(f"Index:  {index_path}")
    print(f"Total: {elapsed}s ({avg_s}s/image)")
    print("=" * 60)


if __name__ == "__main__":
    main()
