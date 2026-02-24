#!/usr/bin/env bash
set -e

cd "$(git rev-parse --show-toplevel)/sherlock/desktop/src-tauri"

echo "==> cargo fmt --check"
cargo fmt --check

echo "==> cargo clippy"
cargo clippy -- -D warnings

echo "==> cargo test"
cargo test

cd ..

echo "==> frontend tests"
npx vitest run

echo "==> All checks passed"
