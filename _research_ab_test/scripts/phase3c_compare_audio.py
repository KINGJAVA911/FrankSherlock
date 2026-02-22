#!/usr/bin/env python3
"""Phase 3c: Compare audio recognition with language-aware ground truth."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import DOCS_DIR, RESULTS_DIR, load_json, save_result

OUTPUT_DIR = RESULTS_DIR / "phase3_audio"
GROUND_TRUTH_PATH = DOCS_DIR / "ground_truth_audio.json"


def normalize_lang(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    aliases = {
        "japanese": "ja",
        "english": "en",
        "portuguese": "pt",
        "russian": "ru",
    }
    return aliases.get(value, value[:2])


def eval_asr_models(asr_data: dict, truth: dict) -> dict:
    model_stats = {}
    for entry in asr_data.get("results", []):
        filename = entry.get("filename", "")
        expected = truth.get(filename)
        if not expected:
            continue
        expected_lang = normalize_lang(expected.get("language"))
        for model_name, model_data in entry.get("models", {}).items():
            if not isinstance(model_data, dict):
                continue
            if "language" not in model_data:
                continue
            stats = model_stats.setdefault(model_name, {
                "files_with_labels": 0,
                "language_correct": 0,
                "non_empty_transcript": 0,
            })
            stats["files_with_labels"] += 1
            predicted_lang = normalize_lang(model_data.get("language"))
            if predicted_lang == expected_lang:
                stats["language_correct"] += 1
            if model_data.get("text", "").strip():
                stats["non_empty_transcript"] += 1

    for model_name, stats in model_stats.items():
        total = max(stats["files_with_labels"], 1)
        stats["language_accuracy"] = round(stats["language_correct"] / total, 4)
        stats["non_empty_rate"] = round(stats["non_empty_transcript"] / total, 4)
    return model_stats


def eval_chromaprint(chromaprint_data: dict) -> dict:
    files = chromaprint_data.get("results", [])
    total = len(files)
    with_fp = sum(1 for r in files if r.get("fingerprint", {}).get("fingerprint"))
    acoustid_matches = 0
    for r in files:
        acoustid = r.get("acoustid", {})
        if isinstance(acoustid, dict) and acoustid.get("results"):
            acoustid_matches += 1
    return {
        "total_files": total,
        "fingerprint_success": with_fp,
        "fingerprint_success_rate": round(with_fp / max(total, 1), 4),
        "acoustid_matches": acoustid_matches,
        "acoustid_match_rate": round(acoustid_matches / max(total, 1), 4),
        "acoustid_api_key_set": chromaprint_data.get("acoustid_api_key_set", False),
    }


def main():
    print("=" * 60)
    print("Phase 3c: Audio Recognition Comparison")
    print("=" * 60)

    chromaprint_data = load_json(OUTPUT_DIR / "chromaprint_results.json", default={}) or {}
    whisper_data = load_json(OUTPUT_DIR / "whisper_results.json", default={}) or {}
    faster_whisper_data = load_json(OUTPUT_DIR / "faster_whisper_results.json", default={}) or {}
    truth = load_json(GROUND_TRUTH_PATH, default={}) or {}

    if not chromaprint_data:
        print("Missing chromaprint results — run phase3a first.")
        return
    if not whisper_data:
        print("Missing whisper results — run phase3b first.")
        return

    whisper_eval = eval_asr_models(whisper_data, truth)
    faster_whisper_eval = eval_asr_models(faster_whisper_data, truth) if faster_whisper_data else {}
    chromaprint_eval = eval_chromaprint(chromaprint_data)

    output = {
        "phase": "3c_comparison",
        "ground_truth_file": str(GROUND_TRUTH_PATH),
        "ground_truth_items": len(truth),
        "whisper_eval": whisper_eval,
        "faster_whisper_eval": faster_whisper_eval,
        "chromaprint_eval": chromaprint_eval,
        "timing_comparison": {
            "chromaprint": chromaprint_data.get("timing_summary", {}),
            "whisper": whisper_data.get("timing_summary", {}),
            "faster_whisper": faster_whisper_data.get("timing_summary", {}),
        },
    }
    save_result(output, OUTPUT_DIR / "comparison_report.json")

    print("\nWhisper ranking (language accuracy):")
    for model_name, stats in sorted(whisper_eval.items(), key=lambda i: i[1]["language_accuracy"], reverse=True):
        print(
            f"  {model_name}: language_acc={stats['language_accuracy']:.3f}, "
            f"non_empty={stats['non_empty_rate']:.3f}, n={stats['files_with_labels']}"
        )
    if faster_whisper_eval:
        print("\nFaster-Whisper ranking (language accuracy):")
        for model_name, stats in sorted(faster_whisper_eval.items(), key=lambda i: i[1]["language_accuracy"], reverse=True):
            print(
                f"  {model_name}: language_acc={stats['language_accuracy']:.3f}, "
                f"non_empty={stats['non_empty_rate']:.3f}, n={stats['files_with_labels']}"
            )
    print("\nChromaprint summary:")
    print(
        f"  fp_success={chromaprint_eval['fingerprint_success_rate']:.3f}, "
        f"acoustid_match={chromaprint_eval['acoustid_match_rate']:.3f}, "
        f"acoustid_key={chromaprint_eval['acoustid_api_key_set']}"
    )


if __name__ == "__main__":
    main()
