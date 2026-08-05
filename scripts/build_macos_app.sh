#!/usr/bin/env bash
# Builds the packaged macOS .app end-to-end (backend sidecar -> staged
# resource -> Tauri bundle) and runs a bounded smoke test against the
# packaged app's /health endpoint. macOS only. See docs/PACKAGING.md.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: this script only builds/smokes the macOS .app" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HEALTH_URL="http://127.0.0.1:8742/health"
PORT=8742
APP_PID=""

step() { echo "==> $*"; }

cleanup() {
  if [[ -n "$APP_PID" ]] && kill -0 "$APP_PID" 2>/dev/null; then
    kill -TERM "$APP_PID" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$APP_PID" 2>/dev/null || break
      sleep 0.1
    done
    kill -0 "$APP_PID" 2>/dev/null && kill -KILL "$APP_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if ! node --version 2>/dev/null | grep -q '^v22\.'; then
  for nvm_sh in "${NVM_DIR:-$HOME/.nvm}/nvm.sh" "$HOME/.nvm/nvm.sh"; do
    if [[ -s "$nvm_sh" ]]; then
      # shellcheck disable=SC1090
      source "$nvm_sh"
      nvm use 22 2>/dev/null || true
      break
    fi
  done
fi

if ! command -v cargo >/dev/null 2>&1 && [[ -f "$HOME/.cargo/env" ]]; then
  # shellcheck disable=SC1090
  source "$HOME/.cargo/env"
fi

step "Building backend sidecar"
./scripts/bundle_backend.sh >/tmp/build_macos_app.bundle_backend.log 2>&1 \
  || { echo "error: bundle_backend.sh failed, see /tmp/build_macos_app.bundle_backend.log" >&2; cat /tmp/build_macos_app.bundle_backend.log >&2; exit 1; }

step "Staging sidecar as Tauri resource"
./scripts/stage_tauri_sidecar.sh

step "Building frontend"
(cd frontend && npm run build) >/tmp/build_macos_app.frontend_build.log 2>&1 \
  || { echo "error: npm run build failed, see /tmp/build_macos_app.frontend_build.log" >&2; cat /tmp/build_macos_app.frontend_build.log >&2; exit 1; }

step "Building Tauri .app"
(cd frontend && npm run tauri build) >/tmp/build_macos_app.tauri_build.log 2>&1 \
  || { echo "error: npm run tauri build failed, see /tmp/build_macos_app.tauri_build.log" >&2; cat /tmp/build_macos_app.tauri_build.log >&2; exit 1; }

BUNDLE_DIR="frontend/src-tauri/target/release/bundle/macos"
APP_PATH="$(find "$BUNDLE_DIR" -maxdepth 1 -name "*.app" -print -quit)"
if [[ -z "$APP_PATH" ]]; then
  echo "error: no .app found under $BUNDLE_DIR" >&2
  exit 1
fi
step "Found app: $APP_PATH"

RESOURCE_BACKEND="$APP_PATH/Contents/Resources/resources/opencleaner-backend"
if [[ ! -x "$RESOURCE_BACKEND" ]]; then
  echo "error: $RESOURCE_BACKEND missing or not executable" >&2
  exit 1
fi
step "Verified packaged resource: $RESOURCE_BACKEND"

APP_BINARY="$(find "$APP_PATH/Contents/MacOS" -maxdepth 1 -type f -perm +111 -print -quit)"
if [[ -z "$APP_BINARY" ]]; then
  echo "error: no executable found under $APP_PATH/Contents/MacOS" >&2
  exit 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "error: port $PORT is already in use before the smoke — refusing to start (won't kill a process this script didn't launch)" >&2
  exit 1
fi

step "Launching packaged app for smoke test"
"$APP_BINARY" >/tmp/build_macos_app.smoke.log 2>&1 &
APP_PID=$!

step "Polling $HEALTH_URL"
HEALTHY=""
for _ in $(seq 1 40); do
  if BODY="$(curl -fsS --max-time 1 "$HEALTH_URL" 2>/dev/null)"; then
    if echo "$BODY" | grep -q '"component"[[:space:]]*:[[:space:]]*"opencleaner-backend"'; then
      HEALTHY=1
      break
    fi
  fi
  sleep 0.5
done

if [[ -z "$HEALTHY" ]]; then
  echo "error: /health did not report component=opencleaner-backend within bound, see /tmp/build_macos_app.smoke.log" >&2
  cat /tmp/build_macos_app.smoke.log >&2
  exit 1
fi
step "/health OK (component=opencleaner-backend)"

step "Terminating packaged app"
kill -TERM "$APP_PID"
for _ in $(seq 1 20); do
  kill -0 "$APP_PID" 2>/dev/null || break
  sleep 0.25
done
if kill -0 "$APP_PID" 2>/dev/null; then
  echo "error: app process $APP_PID did not exit after SIGTERM" >&2
  exit 1
fi
APP_PID=""

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "error: port $PORT still occupied after app termination" >&2
  exit 1
fi
step "Port $PORT confirmed free"

echo "SUCCESS: macOS packaged app built and smoke-tested"
