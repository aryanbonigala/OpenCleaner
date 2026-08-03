#!/usr/bin/env bash
# Outline script: run on a builder machine with PyInstaller installed.
# Customize paths and venv before use. Not executed in CI by default.
# PyInstaller is not yet a backend dependency (see backend/pyproject.toml) —
# this remains a stub until packaging is actually verified.
set -euo pipefail
echo "This is a stub. Example PyInstaller invocation, targeting the sidecar entrypoint:"
echo "  pyinstaller --onefile --name opencleaner-backend \\"
echo "    --hidden-import uvicorn.logging \\"
echo "    --hidden-import uvicorn.loops.auto \\"
echo "    --hidden-import uvicorn.protocols.http.auto \\"
echo "    -m app.sidecar"
exit 0
