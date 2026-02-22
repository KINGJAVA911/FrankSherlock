#!/usr/bin/env python3
"""Phase 0: Verify environment — CUDA/GPU, system tools, Ollama."""

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import TEST_FILES, collect_test_files

CHECKS_PASSED = 0
CHECKS_FAILED = 0


def check(name: str, passed: bool, detail: str = ""):
    global CHECKS_PASSED, CHECKS_FAILED
    status = "PASS" if passed else "FAIL"
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if passed:
        CHECKS_PASSED += 1
    else:
        CHECKS_FAILED += 1


def main():
    print("=" * 60)
    print("Phase 0: Environment Verification")
    print("=" * 60)

    # GPU / CUDA
    print("\n--- GPU ---")
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader"],
            text=True
        ).strip()
        check("nvidia-smi", True, out)
    except Exception as e:
        check("nvidia-smi", False, str(e))

    try:
        import torch
        cuda_ok = torch.cuda.is_available()
        detail = f"CUDA {torch.version.cuda}, device: {torch.cuda.get_device_name(0)}" if cuda_ok else "CUDA not available"
        check("PyTorch CUDA", cuda_ok, detail)
    except ImportError:
        check("PyTorch CUDA", False, "torch not installed yet (will be installed with whisper)")

    # System tools
    print("\n--- System Tools ---")
    for tool in ["ffmpeg", "ffprobe", "exiftool", "fpcalc", "mediainfo"]:
        path = shutil.which(tool)
        if path:
            try:
                ver = subprocess.check_output([tool, "-version" if tool != "exiftool" else "-ver"],
                                              text=True, stderr=subprocess.STDOUT).split("\n")[0]
                check(tool, True, f"{path} — {ver[:80]}")
            except Exception:
                check(tool, True, path)
        else:
            check(tool, False, "not found in PATH")

    # Ollama
    print("\n--- Ollama ---")
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.ok:
            models = [m["name"] for m in resp.json().get("models", [])]
            check("Ollama server", True, f"running, models: {models or '(none yet)'}")
        else:
            check("Ollama server", False, f"HTTP {resp.status_code}")
    except Exception as e:
        check("Ollama server", False, str(e))

    # Test files
    print("\n--- Test Files ---")
    all_files = collect_test_files()
    images = collect_test_files("image")
    audio = collect_test_files("audio")
    video = collect_test_files("video")
    docs = collect_test_files("document")
    check("Test files found", len(all_files) > 0,
          f"{len(all_files)} total: {len(images)} images, {len(audio)} audio, "
          f"{len(video)} video, {len(docs)} docs")

    # Zero-byte check
    zero_byte = [f for f in all_files if f.stat().st_size == 0]
    if zero_byte:
        print(f"  [WARN] Zero-byte files: {[f.name for f in zero_byte]}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Results: {CHECKS_PASSED} passed, {CHECKS_FAILED} failed")
    if CHECKS_FAILED:
        print("Some checks failed — install missing tools before proceeding.")
    else:
        print("All checks passed!")
    print("=" * 60)

    return 0 if CHECKS_FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
