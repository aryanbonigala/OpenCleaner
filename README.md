# OpenCleaner AI

OpenCleaner AI is an open-source, **local-first** desktop optimization and cleaning application aimed at **explainability**, **reversibility**, and **safety** (not maximally aggressive deletion).

This repository contains:

- `backend/`: Python **FastAPI** service, **SQLite** storage, modular scanners, deterministic rules engine, local ML-assisted ranking, quarantine + audit logging.
- `frontend/`: **Tauri + React + Vite** UI (dark dashboard, sortable inventory, charts, Explain This, Safety Center, mode switching).

## v0.4 (canonical scan model + reasoning pipeline)

- **Canonical `ScanItem`** (`backend/app/models/scan_item.py`) — unified typed schema for all inventory rows (metrics, intelligence, bucket, action flags, provenance).
- **Pipeline** (`backend/app/pipeline/`) — `normalize` → `rules` → `intelligence` → `ML` (metrics only) → `explanation` → `action_gating`; rules always win; intelligence cannot downgrade critical items.
- **Provenance** — every stage appends `decided_by` / `evidence` metadata; visible in JSON exports.
- **Deterministic export** — `serialize_scan_result()` stable key order and sorted items (`backend/app/pipeline/serialize.py`).
- **Frontend** — `frontend/src/scanItem.ts` helpers; API types aligned with canonical shape.
- **Docs** — [docs/SCAN_SCHEMA.md](docs/SCAN_SCHEMA.md), [docs/SCAN_PIPELINE.md](docs/SCAN_PIPELINE.md).

## v0.3 (Windows Intelligence Database)

- **Local encyclopedia**: `backend/data/windows_intelligence.json` — vendor/category, plain-English explanations, qualitative impact and risk hints for common Windows and gaming ecosystem software (no cloud APIs).
- **Intelligence service**: `backend/app/services/intelligence_service.py` — exact → alias → conservative fuzzy; unknown items stay **unknown / ask user** (never marked “safe” by omission).
- **Pipeline**: scans apply **rules → intelligence enrichment → ML ranking** (`backend/app/services/scan_service.py`); protected / critical rule buckets are **never** downgraded by intelligence.
- **Explain This**: prefers intelligence text when present; critical heuristics still override (`backend/app/engine/explain.py`).
- **UI**: Known / Unknown badges, vendor & category columns, stronger warnings for **unknown services**, filters (known, gaming / startup / risk).
- **Docs**: `docs/INTELLIGENCE_DATABASE.md` (schema, contribution, safety policy).

## v0.2 (safety and packaging hardening)

- **Filesystem scans**: directory walks use **`bounded_walk`** (`backend/app/utils/fs.py`) with caps on files, depth, bytes inspected, deadlines, symlink loop handling, and capped duplicate hashing (`backend/app/scanners/scan_limits.py`). Startup folders and browser profile sizing use the same walker.
- **Windows tasks**: prefer **`schtasks /query /xml`** with namespace-tolerant parsing; **LIST** fallback (`backend/app/scanners/tasks.py`). Fixture: `backend/tests/fixtures/sample_tasks.xml`.
- **Performance mode**: central **`protected_registry`** for suspend decisions; browsers/shells only if **explicitly listed**; **`POST /api/performance/preview`** before **`POST /api/performance/start`** with **`confirm_apply: true`**.
- **Safety Center API**: **`GET /api/safety/summary`** (quarantine stats, performance session snapshot, protected-pattern counts, recent audit actions).
- **Packaging**: see **`docs/PACKAGING.md`** and **`scripts/bundle_backend_stub.sh`** (PyInstaller outline).

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
3. **Performance / gaming**: **no** file deletion; **preview-first** process suspension with explicit **confirm_apply**; **stop/rollback** resumes PIDs.

## Architecture (high level)

Layers are intentionally separated:

- **Scanners** (`backend/app/scanners/`): gather facts (processes, services, startup, tasks, filesystem, browser trees).
- **Rules engine** (`backend/app/engine/rules_engine.py`): deterministic safety and classification buckets (process criticality delegates to **`protected_registry`**).
- **ML ranker** (`backend/app/engine/ml_ranker.py`): local, feature-based ranking and explain-supporting scores. Optional **scikit-learn** calibrator trained on synthetic data mirroring the heuristic mapping; **never** authorizes deletion.
- **Intelligence** (`backend/data/windows_intelligence.json`, `backend/app/services/intelligence_service.py`): local explanations and conservative classification hints; **never** enables deletion alone.
- **Actions** (`backend/app/actions/`): quarantine moves, assisted cleanup orchestration, performance sessions.
- **Persistence** (`backend/sql/schema.sql`): scans, items, audit log, quarantine metadata, user feedback for local learning nudges.

Windows-specific probes (Services, scheduled tasks, registry Run keys) activate when `sys.platform == "win32"`. Non-Windows development uses live `psutil` data where possible plus `backend/data/sample_scan.json` fallbacks.

**Desktop packaging** (sidecar backend + Tauri): see `docs/PACKAGING.md`.

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

- Integrity-level-aware Windows scanning and richer task trigger parsing.
- macOS/Linux parity: `launchctl`, Linux systemd user units, package-manager orphan hints.
- Optional **NVML** GPU process attribution (explicit dependency) behind a feature flag.
- Automate **PyInstaller** / CI-produced sidecar in `scripts/` (beyond the current stub).

## UI mock

See `docs/UI_MOCK_LAYOUT.txt` for an ASCII layout sketch.

## License

MIT: see `LICENSE`.
