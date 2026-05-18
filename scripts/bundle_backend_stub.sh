#!/usr/bin/env bash
# Outline script: run on a Windows machine with PyInstaller installed.
# Customize paths and venv before use. Not executed in CI by default.
set -euo pipefail
echo "This is a stub. Example PyInstaller invocation:"
echo "  pyinstaller --onefile --name opencleaner-backend \\"
echo "    --hidden-import uvicorn.logging \\"
echo "    --hidden-import uvicorn.loops.auto \\"
echo "    --hidden-import uvicorn.protocols.http.auto \\"
echo "    -m uvicorn app.main:app --host 127.0.0.1 --port 8742"
exit 0
