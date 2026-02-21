#!/usr/bin/env python3
"""Phase 6: Cost estimation — project local GPU times to NAS scale, compare with commercial APIs."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import RESULTS_DIR


# --- Commercial API pricing (as of early 2025) ---
# These are approximate and will vary. Stored here for easy updating.
COMMERCIAL_PRICES = {
    "openai_gpt4o_vision": {
        "name": "OpenAI GPT-4o (vision)",
        "per_image_input_tokens": 1200,  # ~1 image + prompt
        "per_image_output_tokens": 300,
        "input_price_per_1k": 0.0025,    # $2.50/1M input
        "output_price_per_1k": 0.01,     # $10/1M output
    },
    "openai_gpt4_turbo_vision": {
        "name": "OpenAI GPT-4 Turbo (vision)",
        "per_image_input_tokens": 1200,
        "per_image_output_tokens": 300,
        "input_price_per_1k": 0.01,      # $10/1M input
        "output_price_per_1k": 0.03,     # $30/1M output
    },
    "openai_whisper_api": {
        "name": "OpenAI Whisper API",
        "per_minute_price": 0.006,       # $0.006/min
    },
    "google_gemini_flash": {
        "name": "Google Gemini 2.0 Flash",
        "per_image_input_tokens": 1200,
        "per_image_output_tokens": 300,
        "input_price_per_1k": 0.0001,    # $0.10/1M input (very cheap)
        "output_price_per_1k": 0.0004,   # $0.40/1M output
    },
    "anthropic_claude_sonnet": {
        "name": "Anthropic Claude 3.5 Sonnet (vision)",
        "per_image_input_tokens": 1600,  # images cost more tokens on Claude
        "per_image_output_tokens": 300,
        "input_price_per_1k": 0.003,     # $3/1M input
        "output_price_per_1k": 0.015,    # $15/1M output
    },
    "google_cloud_vision_ocr": {
        "name": "Google Cloud Vision OCR",
        "per_image_price": 0.0015,       # $1.50/1000 images
    },
    "aws_textract": {
        "name": "AWS Textract",
        "per_page_price": 0.0015,        # $1.50/1000 pages (detect text)
    },
}

# Local GPU electricity cost estimate
GPU_WATTS = 450  # RTX 5090 TDP
ELECTRICITY_KWH_PRICE = 0.12  # US average $/kWh


def load_json(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"  [WARN] Not found: {path}")
        return None


def collect_timing_data() -> dict:
    """Collect timing summaries from all phase results."""
    phases = {
        "phase1_metadata": RESULTS_DIR / "phase1_metadata" / "all_metadata.json",
        "phase2a_ollama_vision": RESULTS_DIR / "phase2_images" / "ollama_vision_results.json",
        "phase2b_wd_tagger": RESULTS_DIR / "phase2_images" / "wd_tagger_results.json",
        "phase2d_ocr": RESULTS_DIR / "phase2_images" / "ocr_results.json",
        "phase3a_chromaprint": RESULTS_DIR / "phase3_audio" / "chromaprint_results.json",
        "phase3b_whisper": RESULTS_DIR / "phase3_audio" / "whisper_results.json",
        "phase4a_frame_extract": RESULTS_DIR / "phase4_video" / "frame_extraction.json",
        "phase4b_video_classify": RESULTS_DIR / "phase4_video" / "video_classification.json",
        "phase5_catalog": RESULTS_DIR / "catalog.json",
    }

    data = {}
    for name, path in phases.items():
        result = load_json(path)
        if result:
            data[name] = {
                "timing_summary": result.get("timing_summary", {}),
                "total_files": result.get("total_files", result.get("total_images", result.get("total_videos", 0))),
            }
            # Also extract per-file timings for more granular analysis
            per_file = []
            for entry in result.get("results", result.get("files", result.get("entries", []))):
                if isinstance(entry, dict) and entry.get("timing"):
                    per_file.append({
                        "filename": entry.get("filename", ""),
                        "media_type": entry.get("media_type", ""),
                        "timing": entry["timing"],
                    })
            data[name]["per_file_timings"] = per_file
    return data


def compute_per_file_averages(timing_data: dict) -> dict:
    """Compute average processing time per file type per tool."""
    averages = {}

    # Phase 1: metadata tools
    p1 = timing_data.get("phase1_metadata", {})
    if p1.get("per_file_timings"):
        by_type = {}
        for pf in p1["per_file_timings"]:
            mt = pf.get("media_type", "unknown")
            by_type.setdefault(mt, []).append(pf["timing"].get("total_s", 0))
        averages["metadata_extraction"] = {
            mt: {"avg_s": round(sum(v) / len(v), 4), "count": len(v)}
            for mt, v in by_type.items()
        }

    # Phase 2a: Ollama vision
    p2a = timing_data.get("phase2a_ollama_vision", {})
    ts = p2a.get("timing_summary", {})
    if ts:
        averages["ollama_vision"] = {
            "per_image_avg_s": ts.get("per_image_avg_s", 0),
            "per_model_prompt_avg_s": ts.get("per_model_prompt_avg_s", {}),
            "total_images": p2a.get("total_files", 0),
        }

    # Phase 2d: OCR
    p2d = timing_data.get("phase2d_ocr", {})
    ts = p2d.get("timing_summary", {})
    if ts:
        averages["ocr"] = {
            "per_engine_avg_s": ts.get("per_engine_avg_s", {}),
            "phase_total_s": ts.get("phase_total_s", 0),
            "total_images": p2d.get("total_files", 0),
        }

    # Phase 2b: WD Tagger
    p2b = timing_data.get("phase2b_wd_tagger", {})
    ts = p2b.get("timing_summary", {})
    if ts:
        averages["wd_tagger"] = {
            "per_image_avg_s": ts.get("per_image_avg_s", 0),
            "per_image_min_s": ts.get("per_image_min_s", 0),
            "per_image_max_s": ts.get("per_image_max_s", 0),
            "total_images": p2b.get("total_files", 0),
        }

    # Phase 3a: Chromaprint
    p3a = timing_data.get("phase3a_chromaprint", {})
    ts = p3a.get("timing_summary", {})
    if ts:
        averages["chromaprint"] = {
            "per_file_avg_s": ts.get("per_file_avg_s", 0),
            "per_tool_avg_s": ts.get("per_tool_avg_s", {}),
            "total_files": p3a.get("total_files", 0),
        }

    # Phase 3b: Whisper
    p3b = timing_data.get("phase3b_whisper", {})
    ts = p3b.get("timing_summary", {})
    if ts:
        averages["whisper"] = {
            "per_file_avg_s": ts.get("per_file_avg_s", 0),
            "per_tool_avg_s": ts.get("per_tool_avg_s", {}),
            "total_files": p3b.get("total_files", 0),
        }

    # Phase 4a: Frame extraction
    p4a = timing_data.get("phase4a_frame_extract", {})
    ts = p4a.get("timing_summary", {})
    if ts:
        averages["frame_extraction"] = {
            "scene_detect_avg_s": ts.get("scene_detect_avg_s", 0),
            "phase_total_s": ts.get("phase_total_s", 0),
            "total_videos": p4a.get("total_files", 0),
        }

    # Phase 4b: Video classification
    p4b = timing_data.get("phase4b_video_classify", {})
    ts = p4b.get("timing_summary", {})
    if ts:
        averages["video_classification"] = {
            "per_video_avg_s": ts.get("per_video_avg_s", 0),
            "phase_total_s": ts.get("phase_total_s", 0),
            "total_videos": p4b.get("total_files", 0),
        }

    return averages


def project_to_scale(averages: dict, file_counts: dict) -> dict:
    """Project processing times for larger file collections."""
    projections = {}

    for scale_name, counts in file_counts.items():
        proj = {"scale": scale_name, "file_counts": counts, "estimated_times": {}}

        # Images: metadata + ollama vision + wd tagger + OCR
        n_images = counts.get("images", 0)
        if n_images > 0:
            meta_avg = averages.get("metadata_extraction", {}).get("image", {}).get("avg_s", 0.1)
            ollama_avg = averages.get("ollama_vision", {}).get("per_image_avg_s", 10)
            wd_avg = averages.get("wd_tagger", {}).get("per_image_avg_s", 0.5)
            # OCR: use the fastest engine average, or estimate
            ocr_avgs = averages.get("ocr", {}).get("per_engine_avg_s", {})
            ocr_avg = min(ocr_avgs.values()) if ocr_avgs else 0.5  # default estimate

            proj["estimated_times"]["images"] = {
                "metadata_s": round(n_images * meta_avg, 1),
                "ollama_vision_s": round(n_images * ollama_avg, 1),
                "wd_tagger_s": round(n_images * wd_avg, 1),
                "ocr_s": round(n_images * ocr_avg, 1),
                "total_s": round(n_images * (meta_avg + ollama_avg + wd_avg + ocr_avg), 1),
            }

        # Audio: metadata + chromaprint + whisper
        n_audio = counts.get("audio", 0)
        if n_audio > 0:
            meta_avg = averages.get("metadata_extraction", {}).get("audio", {}).get("avg_s", 0.5)
            cp_avg = averages.get("chromaprint", {}).get("per_file_avg_s", 1)
            wh_avg = averages.get("whisper", {}).get("per_file_avg_s", 15)

            proj["estimated_times"]["audio"] = {
                "metadata_s": round(n_audio * meta_avg, 1),
                "chromaprint_s": round(n_audio * cp_avg, 1),
                "whisper_s": round(n_audio * wh_avg, 1),
                "total_s": round(n_audio * (meta_avg + cp_avg + wh_avg), 1),
            }

        # Video: metadata + frame extract + classify (includes vision + whisper)
        n_video = counts.get("video", 0)
        if n_video > 0:
            meta_avg = averages.get("metadata_extraction", {}).get("video", {}).get("avg_s", 1)
            frame_avg = averages.get("frame_extraction", {}).get("scene_detect_avg_s", 5)
            classify_avg = averages.get("video_classification", {}).get("per_video_avg_s", 60)

            proj["estimated_times"]["video"] = {
                "metadata_s": round(n_video * meta_avg, 1),
                "frame_extract_s": round(n_video * frame_avg, 1),
                "classification_s": round(n_video * classify_avg, 1),
                "total_s": round(n_video * (meta_avg + frame_avg + classify_avg), 1),
            }

        # Grand total
        total_s = sum(
            t.get("total_s", 0) for t in proj["estimated_times"].values()
        )
        proj["grand_total_s"] = round(total_s, 1)
        proj["grand_total_human"] = format_duration(total_s)

        # Local electricity cost
        gpu_hours = total_s / 3600
        kwh = gpu_hours * (GPU_WATTS / 1000)
        proj["local_electricity_cost_usd"] = round(kwh * ELECTRICITY_KWH_PRICE, 4)

        projections[scale_name] = proj

    return projections


def estimate_commercial_costs(file_counts: dict) -> dict:
    """Estimate commercial API costs for the same workload."""
    estimates = {}

    for scale_name, counts in file_counts.items():
        n_images = counts.get("images", 0)
        n_audio = counts.get("audio", 0)
        n_video = counts.get("video", 0)
        avg_audio_minutes = counts.get("avg_audio_minutes", 3)
        avg_video_minutes = counts.get("avg_video_minutes", 5)

        est = {"scale": scale_name, "file_counts": counts, "api_costs": {}}

        for api_key, api in COMMERCIAL_PRICES.items():
            cost = 0.0
            detail = {}

            if "cloud_vision" in api_key or "textract" in api_key:
                # Dedicated OCR APIs — per-image/page pricing
                per_price = api.get("per_image_price") or api.get("per_page_price", 0)
                cost = (n_images + n_video * 5) * per_price  # images + video keyframes
                detail["total_cost_usd"] = round(cost, 4)
                est["api_costs"][api["name"]] = detail
                continue

            elif "vision" in api_key or "gemini" in api_key or "claude" in api_key:
                # Vision API — process images + video keyframes
                # Images: 1 call per image
                img_input_cost = n_images * api["per_image_input_tokens"] / 1000 * api["input_price_per_1k"]
                img_output_cost = n_images * api["per_image_output_tokens"] / 1000 * api["output_price_per_1k"]
                detail["image_cost"] = round(img_input_cost + img_output_cost, 4)

                # Videos: ~5 keyframes per video
                vid_frames = n_video * 5
                vid_input_cost = vid_frames * api["per_image_input_tokens"] / 1000 * api["input_price_per_1k"]
                vid_output_cost = vid_frames * api["per_image_output_tokens"] / 1000 * api["output_price_per_1k"]
                detail["video_frame_cost"] = round(vid_input_cost + vid_output_cost, 4)

                cost = detail["image_cost"] + detail["video_frame_cost"]

            elif "whisper" in api_key:
                # Whisper API — audio files + video audio
                total_minutes = (n_audio * avg_audio_minutes) + (n_video * avg_video_minutes)
                cost = total_minutes * api["per_minute_price"]
                detail["total_minutes"] = total_minutes

            detail["total_cost_usd"] = round(cost, 4)
            est["api_costs"][api["name"]] = detail

        # Total across all APIs (if using full pipeline)
        # Cheapest vision + whisper
        vision_costs = [
            v["total_cost_usd"] for k, v in est["api_costs"].items()
            if "Whisper" not in k
        ]
        whisper_cost = est["api_costs"].get("OpenAI Whisper API", {}).get("total_cost_usd", 0)
        cheapest_vision = min(vision_costs) if vision_costs else 0

        est["cheapest_combo"] = {
            "cheapest_vision_usd": round(cheapest_vision, 4),
            "whisper_usd": round(whisper_cost, 4),
            "total_usd": round(cheapest_vision + whisper_cost, 4),
        }
        est["most_expensive_combo"] = {
            "expensive_vision_usd": round(max(vision_costs) if vision_costs else 0, 4),
            "whisper_usd": round(whisper_cost, 4),
            "total_usd": round((max(vision_costs) if vision_costs else 0) + whisper_cost, 4),
        }

        # Network transfer estimate (upload files to API)
        avg_image_mb = 0.5
        avg_audio_mb = 5
        avg_video_mb = 50  # just keyframes + audio segments
        total_upload_mb = (n_images * avg_image_mb) + (n_audio * avg_audio_mb) + (n_video * avg_video_mb)
        est["network_transfer"] = {
            "total_upload_mb": round(total_upload_mb, 1),
            "total_upload_gb": round(total_upload_mb / 1024, 2),
            "at_100mbps_minutes": round(total_upload_mb * 8 / 100 / 60, 1),
        }

        estimates[scale_name] = est

    return estimates


def format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f} min"
    elif seconds < 86400:
        return f"{seconds / 3600:.1f} hours"
    else:
        return f"{seconds / 86400:.1f} days"


def main():
    print("=" * 60)
    print("Phase 6: Cost & Time Estimation")
    print("=" * 60)

    # 1. Collect timing from all phases
    print("\nCollecting timing data from all phases...")
    timing_data = collect_timing_data()

    phases_found = list(timing_data.keys())
    print(f"  Found timing data for: {phases_found}")

    if not timing_data:
        print("  No timing data found. Run the phases first (with timing enabled).")
        return

    # 2. Compute per-file averages
    averages = compute_per_file_averages(timing_data)

    # 3. Define scale scenarios
    scale_scenarios = {
        "current_test": {"images": 39, "audio": 9, "video": 7, "avg_audio_minutes": 3, "avg_video_minutes": 10},
        "small_nas": {"images": 500, "audio": 200, "video": 100, "avg_audio_minutes": 3, "avg_video_minutes": 10},
        "medium_nas": {"images": 5000, "audio": 2000, "video": 500, "avg_audio_minutes": 3, "avg_video_minutes": 15},
        "large_nas": {"images": 50000, "audio": 20000, "video": 5000, "avg_audio_minutes": 3, "avg_video_minutes": 15},
    }

    # 4. Project local processing times
    print("\nProjecting local GPU processing times...")
    projections = project_to_scale(averages, scale_scenarios)

    # 5. Estimate commercial API costs
    print("Estimating commercial API costs...")
    commercial = estimate_commercial_costs(scale_scenarios)

    # 6. Build report
    report = {
        "phase": "6_cost_estimation",
        "gpu": "NVIDIA RTX 5090 (32GB VRAM)",
        "gpu_tdp_watts": GPU_WATTS,
        "electricity_price_kwh": ELECTRICITY_KWH_PRICE,
        "measured_averages": averages,
        "local_projections": projections,
        "commercial_api_estimates": commercial,
        "comparison": {},
    }

    # Build comparison table
    for scale_name in scale_scenarios:
        local = projections.get(scale_name, {})
        cloud = commercial.get(scale_name, {})

        report["comparison"][scale_name] = {
            "local_time": local.get("grand_total_human", "N/A"),
            "local_time_s": local.get("grand_total_s", 0),
            "local_electricity_usd": local.get("local_electricity_cost_usd", 0),
            "cloud_cheapest_usd": cloud.get("cheapest_combo", {}).get("total_usd", 0),
            "cloud_expensive_usd": cloud.get("most_expensive_combo", {}).get("total_usd", 0),
            "network_upload_gb": cloud.get("network_transfer", {}).get("total_upload_gb", 0),
            "savings_vs_cheapest_usd": round(
                cloud.get("cheapest_combo", {}).get("total_usd", 0)
                - local.get("local_electricity_cost_usd", 0), 4
            ),
        }

    from lib.common import save_result
    output_path = RESULTS_DIR / "cost_estimation.json"
    save_result(report, output_path)

    # Print summary
    print(f"\n{'=' * 60}")
    print("COST & TIME PROJECTIONS")
    print(f"{'=' * 60}")

    print("\n--- Measured Averages (from test corpus) ---")
    for tool, data in averages.items():
        if isinstance(data, dict):
            avg = data.get("per_image_avg_s") or data.get("per_file_avg_s") or data.get("per_video_avg_s") or data.get("scene_detect_avg_s")
            if avg:
                print(f"  {tool}: {avg:.2f}s/file")

    print("\n--- Scale Projections ---")
    print(f"{'Scale':<16} {'Files':>8} {'Local Time':>14} {'Local $':>10} {'Cloud (cheap)':>14} {'Cloud ($$)':>12} {'Upload':>10}")
    print("-" * 86)
    for scale_name, comp in report["comparison"].items():
        counts = scale_scenarios[scale_name]
        total_files = sum(v for k, v in counts.items() if k not in ("avg_audio_minutes", "avg_video_minutes"))
        print(
            f"  {scale_name:<14} {total_files:>8} {comp['local_time']:>14} "
            f"${comp['local_electricity_usd']:>8.4f} "
            f"${comp['cloud_cheapest_usd']:>12.2f} "
            f"${comp['cloud_expensive_usd']:>10.2f} "
            f"{comp['network_upload_gb']:>8.1f}GB"
        )

    print(f"\n{'=' * 60}")
    print(f"Report saved: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
