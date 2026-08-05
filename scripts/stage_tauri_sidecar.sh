#!/usr/bin/env bash
# Copies the built backend sidecar binary into Tauri's resource staging path
# (frontend/src-tauri/resources/) so tauri.conf.json's bundle.resources can
# package it into the .app. Run ./scripts/bundle_backend.sh first.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BINARY="$ROOT/backend/dist/opencleaner-backend"
DEST_DIR="$ROOT/frontend/src-tauri/resources"
DEST="$DEST_DIR/opencleaner-backend"

if [[ ! -f "$BINARY" ]]; then
  echo "error: $BINARY not found — run ./scripts/bundle_backend.sh first" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
cp "$BINARY" "$DEST"
chmod +x "$DEST"

echo "Staged: $DEST"
