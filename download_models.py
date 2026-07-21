#!/usr/bin/env python3
"""
Download Kokoro ONNX model files from GitHub releases.
Run this before starting the server for the first time.
"""

import os
import sys
import urllib.request
from pathlib import Path

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "models"))

MODELS = {
    "kokoro-v1.0.int8.onnx": {
        "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx",
        "size_mb": 88,
    },
    "voices-v1.0.bin": {
        "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
        "size_mb": 25,
    },
}


def download_file(url: str, dest: Path, expected_size_mb: int):
    """Download a file with progress reporting."""
    if dest.exists():
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  ✓ Already exists: {dest.name} ({size_mb:.1f} MB)")
        return

    print(f"  ↓ Downloading {dest.name} (~{expected_size_mb} MB)...")
    print(f"    URL: {url}")

    def progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(100, downloaded * 100 / total_size)
            bar = "#" * int(pct // 2) + "-" * (50 - int(pct // 2))
            print(f"\r    [{bar}] {pct:.0f}% ({downloaded // 1024 // 1024}MB)", end="", flush=True)

    try:
        urllib.request.urlretrieve(url, str(dest), reporthook=progress)
        print()  # newline after progress bar
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  ✓ Downloaded: {dest.name} ({size_mb:.1f} MB)")
    except Exception as e:
        print(f"\n  ✗ Failed: {e}")
        dest.unlink(missing_ok=True)
        sys.exit(1)


def main():
    print("=" * 60)
    print("  Kokoro TTS — Model Downloader")
    print("=" * 60)
    print()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Model directory: {MODEL_DIR.resolve()}")
    print()

    for filename, info in MODELS.items():
        dest = MODEL_DIR / filename
        download_file(info["url"], dest, info["size_mb"])

    print()
    print("=" * 60)
    print("  All models downloaded! Run: python server.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
