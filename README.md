# OpenCleaner

OpenCleaner is an open-source, **local-first** desktop application for understanding and safely controlling what's running on your computer. Think **Task Manager, but understandable, safe, beautiful, and chat-controlled** — not another aggressive junk-file cleaner.

This repository contains:

- `backend/`: Python **FastAPI** service, **SQLite** storage, modular scanners (processes, services, startup, scheduled tasks, filesystem, browser profiles), a deterministic rules engine, a local Windows intelligence database, local ML-assisted ranking, and quarantine + audit logging.
- `frontend/`: **Tauri + React + Vite** UI (dark dashboard, sortable inventory, charts, Explain This, Safety Center, mode switching).

## Product direction

OpenCleaner should help a normal user answer, in plain English:

- What is running on my computer right now?
- What does each process, service, startup entry, or scheduled task actually do?
- Is it essential, important, non-essential, gaming-relevant, or unknown?
- What can I safely stop or suspend before gaming — and what should I never touch?
- What could break if I stop something?

The goal is a **chat-driven process/task intelligence and control center**: explain what's running, recommend what's safe to pause, and refuse to touch anything that could break the system — driven by conversation as much as by clicking. File cleanup (quarantine-based) remains a supported, secondary surface rather than the headline feature.

See [`docs/PROCESS_CONTROL_PIVOT_PLAN.md`](docs/PROCESS_CONTROL_PIVOT_PLAN.md) for the detailed technical plan behind this direction.

## Safety model

OpenCleaner is built around **explainability and reversibility**, not maximally aggressive action:

- **Permission modes**, enforced in both UI and API:
  1. **Read-only** — scanning, reporting, explanations only. No destructive operations.
  2. **Assisted cleanup** — file moves go to **quarantine** first, with rollback; medium+ risk items require explicit confirmation.
  3. **Performance / gaming** — **no** file deletion; process suspension is **preview-first** with an explicit `confirm_apply`, and stop/rollback resumes suspended PIDs.
- **Preview before action**: cleanup and performance changes always require a preview step before anything executes.
- **Hard-protected items**: a central protected registry (`backend/app/engine/protected_registry.py`) blocks OS-critical, security, anti-cheat, GPU, audio, and networking processes/services from being touched at all — no code path may re-implement or bypass this list.
- **ML and intelligence never authorize deletion or termination** — they inform ranking and explanations only; the rules engine and action-gating stage have final say.
- **Unknown items are never assumed safe** — they're surfaced for the user to decide, never auto-selected.
- Every cleanup and performance action is written to a local audit log.

## Architecture

Layers are intentionally separated:

- **Scanners** (`backend/app/scanners/`): gather facts — processes, services, startup entries, scheduled tasks, filesystem, browser trees.
- **Rules engine** (`backend/app/engine/rules_engine.py`): deterministic safety and classification buckets; process criticality delegates to `protected_registry`.
- **ML ranker** (`backend/app/engine/ml_ranker.py`): local, feature-based ranking and explain-supporting scores. Optional scikit-learn calibrator trained on synthetic data; never authorizes deletion.
- **Intelligence** (`backend/data/windows_intelligence.json`, `backend/app/services/intelligence_service.py`): local, offline explanations and conservative classification hints for common Windows and gaming-ecosystem software; never enables deletion alone.
- **Actions** (`backend/app/actions/`): quarantine moves, assisted cleanup orchestration, performance (suspend/resume) sessions.
- **Persistence** (`backend/sql/schema.sql`): scans, items, audit log, quarantine metadata, user feedback for local learning nudges.

Windows-specific probes (services, scheduled tasks, registry Run keys) activate when `sys.platform == "win32"`. Non-Windows development uses live `psutil` data where possible, with `backend/data/sample_scan.json` as a mock fallback.

## Current capabilities

- Scan processes, services, startup entries, scheduled tasks, filesystem locations, and browser profiles into a unified `ScanItem` model.
- Plain-English explanations per item ("Explain This"), backed by the local intelligence database and rules engine.
- Assisted file cleanup: preview → confirm → quarantine → restore, with size and risk reporting.
- Performance mode: preview-first process suspension for gaming/performance sessions, with rollback.
- Local settings (cleanup mode, risk visibility, scanner toggles, quarantine retention, logging mode).
- Safety Center summary API (quarantine stats, performance session snapshot, protected-item counts, recent audit actions).
- Local, offline Windows intelligence database with known/unknown labeling — nothing is called "safe" by omission.

## Current limitations

- File quarantine is implemented; process/service/startup control is currently **report-only** in the UI (chat-driven process control is the active development direction — see the pivot plan).
- Preview sessions must match execute item IDs exactly and expire after about an hour.
- Unknown or medium-risk items require explicit opt-in before they can be previewed or executed.
- Permanent Recycle Bin emptying requires a separate confirmation flag.
- No cloud APIs, telemetry, registry cleaning, or automatic service disabling.

## Running the backend

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

## Running the frontend

```bash
cd frontend
npm install
npm run dev
```

Optional: point the dev UI at a non-default backend URL:

```bash
export VITE_API_BASE="http://127.0.0.1:8742"
```

## Running the desktop shell (Tauri)

```bash
cd frontend
npm install
npm run tauri dev
```

Requires the **Rust** toolchain. The dev shell loads the Vite dev server and talks to the backend at `http://127.0.0.1:8742`.

See [`docs/PACKAGING.md`](docs/PACKAGING.md) for sidecar packaging (bundling the backend with the Tauri build).

## Running tests

Backend:

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=. pytest
```

Frontend (typecheck, unit tests, production bundle):

```bash
cd frontend
npm install
npm run test
npm run build
```

### Mock scan mode

Force the mock dataset (useful on CI or sandboxes without live process/service access):

```bash
export OPENCLEANER_USE_MOCK=1
```

### Local data directory

Local data (SQLite database, quarantine, logs) is stored under `~/.opencleaner/` by default. Override it with:

```bash
export OPENCLEANER_DATA_DIR=/path/to/dir
```

## Safe smoke test

A copy-pasteable, non-mutating way to verify a fresh clone is wired correctly. Runs the backend in **mock mode** and builds the frontend — it does not touch live OS process/service/filesystem state, and does not start cleanup, performance, or process-end execution flows:

```bash
cd backend
source .venv/bin/activate
OPENCLEANER_USE_MOCK=1 python -c "import app.main"

cd ../frontend
npm run build
```

A clean import and a successful `dist/` build mean the backend and frontend are both wired correctly, with no live scan and no mutation of local state.

## Privacy and local-first notes

- No cloud dependency and **no telemetry by default** (`telemetry_enabled=false` in settings, stored as `settings.telemetry=false` in SQLite).
- All scanning, reasoning, and storage happen locally in SQLite under `~/.opencleaner/`.
- Destructive paths are blocked against a conservative critical-prefix list for system directories.
- Admin/elevation may still be required for some OS-level operations (for example certain `powercfg` calls); the app is designed to degrade gracefully when elevation is missing.

## Roadmap direction

The near-term focus is turning process, service, startup, and task visibility into a full **chat-driven control center**: live process inventory with essential/important/non-essential/gaming-impact classification, an FPS optimization advisor, and a chat interface that can explain and preview actions but never executes without explicit, separately-confirmed user consent. File cleanup stays supported as a secondary "Storage" surface. Longer-term directions include macOS/Linux parity (`launchctl`, systemd user units) and optional GPU process attribution. See [`docs/PROCESS_CONTROL_PIVOT_PLAN.md`](docs/PROCESS_CONTROL_PIVOT_PLAN.md) for the full technical plan.

## UI mock

See [`docs/UI_MOCK_LAYOUT.txt`](docs/UI_MOCK_LAYOUT.txt) for an ASCII layout sketch.

## License

MIT: see [`LICENSE`](LICENSE).
