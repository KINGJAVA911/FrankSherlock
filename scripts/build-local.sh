#!/usr/bin/env bash
set -euo pipefail

# Build Frank Sherlock AppImage locally on Arch Linux.
# Usage: ./scripts/build-local.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DESKTOP_DIR="$PROJECT_ROOT/sherlock/desktop"

echo "==> Installing frontend dependencies"
cd "$DESKTOP_DIR"
npm install

echo "==> Running Rust tests"
cd "$DESKTOP_DIR/src-tauri"
cargo test

echo "==> Building Tauri app (release)"
cd "$DESKTOP_DIR"
npm run tauri:build

echo ""
echo "==> Build complete!"
echo "    AppImage: $(find "$DESKTOP_DIR/src-tauri/target/release/bundle" -name '*.AppImage' 2>/dev/null | head -1)"
