#!/usr/bin/env bash
# Builds the opencleaner-backend sidecar binary from backend/app/sidecar.py via PyInstaller.
# Does not start the server and does not spawn/wire the Tauri sidecar.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"

if [[ ! -f "$BACKEND/app/sidecar.py" ]]; then
  echo "error: expected $BACKEND/app/sidecar.py — run this script from an OpenCleaner checkout" >&2
  exit 1
fi

cd "$BACKEND"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e ".[packaging]"

rm -rf build dist opencleaner-backend.spec
pyinstaller --onefile --name opencleaner-backend \
  --paths "$BACKEND" \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  app/sidecar.py

echo "Built: $BACKEND/dist/opencleaner-backend"
