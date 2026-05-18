# OpenCleaner AI

OpenCleaner AI is an open-source, **local-first** desktop optimization and cleaning application aimed at **explainability**, **reversibility**, and **safety** (not maximally aggressive deletion).

This repository contains:

- `backend/`: Python **FastAPI** service, **SQLite** storage, modular scanners, deterministic rules engine, local ML-assisted ranking, quarantine + audit logging.
- `frontend/`: **Tauri + React + Vite** UI (dark dashboard, sortable inventory, charts, Explain This, mode switching).

## Quick start (development)

### 1) Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export PYTHONPATH="$(pwd)"
uvicorn app.main:app --host 127.0.0.1 --port 8742
```

Or:

```bash
./scripts/run_backend.sh
```

Data is stored under `~/.opencleaner/` by default (database, quarantine, logs).

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

### 3) Desktop shell (Tauri)

```bash
cd frontend
npm install
npm run tauri dev
```

Requirements: **Rust** toolchain for Tauri. The dev UI loads the Vite dev server and talks to the backend at `http://127.0.0.1:8742`.

Optional:

```bash
export VITE_API_BASE="http://127.0.0.1:8742"
```

## Permission modes (enforced in UI + API behavior)

1. **Read-only**: scanning, reporting, explanations. No destructive operations.
2. **Assisted cleanup**: file moves into **quarantine** first; rollback supported; medium+ risk requires explicit confirmation flags.
3. **Performance / gaming**: **no** file deletion; temporary suspension/optimization patterns with **stop/rollback**.

## Architecture (high level)

Layers are intentionally separated:

- **Scanners** (`backend/app/scanners/`): gather facts (processes, services, startup, tasks, filesystem, browser trees).
- **Rules engine** (`backend/app/engine/rules_engine.py`): deterministic safety and classification buckets.
- **ML ranker** (`backend/app/engine/ml_ranker.py`): local, feature-based ranking and explain-supporting scores. Optional **scikit-learn** calibrator trained on synthetic data mirroring the heuristic mapping; **never** authorizes deletion.
- **Actions** (`backend/app/actions/`): quarantine moves, assisted cleanup orchestration, performance sessions.
- **Persistence** (`backend/sql/schema.sql`): scans, items, audit log, quarantine metadata, user feedback for local learning nudges.

Windows-specific probes (Services, scheduled tasks, registry Run keys) activate when `sys.platform == "win32"`. Non-Windows development uses live `psutil` data where possible plus `backend/data/sample_scan.json` fallbacks.

## Security notes

- **No cloud dependency** and **no telemetry by default** (`telemetry_enabled=false` in settings; stored as `settings.telemetry=false` in SQLite).
- Destructive paths are blocked against a conservative critical-prefix list for Windows system directories.
- **Admin/elevation** may still be required for some OS policies (for example certain `powercfg` operations). The app is designed to degrade gracefully when elevation is missing.
- **ML cannot delete**: cleanup requires Assisted mode + explicit selection + rule gates.

## Testing

Backend unit tests:

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=. pytest
```

Frontend typecheck + production bundle:

```bash
cd frontend
npm run build
```

## Mock scan mode

Force mock dataset only (useful on CI or sandboxes):

```bash
export OPENCLEANER_USE_MOCK=1
```

## Roadmap (short)

- Deeper Windows scheduled task XML parsing and integrity-level aware scanning.
- macOS/Linux parity: LaunchAgents parsing, `launchctl`, Linux systemd user units, package-manager orphan hints.
- Optional **NVML** GPU process attribution (explicit dependency) behind a feature flag.
- Signed auto-updates for the desktop bundle and reproducible builds.

## UI mock

See `docs/UI_MOCK_LAYOUT.txt` for an ASCII layout sketch.

## License

MIT: see `LICENSE`.
