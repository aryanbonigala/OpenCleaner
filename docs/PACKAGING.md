# Packaging: OpenCleaner AI (v0.2)

This document describes how to ship the **Python FastAPI backend** together with the **Tauri desktop shell** using a **sidecar** pattern: the UI spawns (or expects) a local `opencleaner-backend` binary next to the main executable.

No code signing or notarization steps are mandated here; integrate your own release pipeline when you publish broadly.

## Local development (no sidecar)

1. **Backend** — from repo root:

   ```bash
   ./scripts/run_backend.sh
   ```

   Listens on `127.0.0.1:8742` by default.

2. **Frontend** — second terminal:

   ```bash
   cd frontend && npm install && npm run dev
   ```

3. **Tauri shell** (optional):

   ```bash
   cd frontend && npm run tauri dev
   ```

The Vite app uses `VITE_API_BASE` (default `http://127.0.0.1:8742`).

## Sidecar concept

- **Main app**: Tauri bundle (OpenCleaner UI).
- **Sidecar**: Same-version backend executable that speaks HTTP on loopback.
- **Startup**: On launch, the Rust shell can:
  - start the sidecar if not already running (check `GET /health`), or
  - document that the user must start the backend (simpler for early releases).

Recommended loopback binding: `127.0.0.1:8742` (already the backend default).

Data lives under the user profile (`~/.opencleaner` / `%USERPROFILE%\.opencleaner`): database, quarantine, logs. No cloud.

## Windows build notes

1. **Python environment** (builder machine):

   - Install Python 3.10+.
   - `pip install -e backend/` or produce a **PyInstaller** / **Nuitka** one-folder or one-file artifact that runs:

     `uvicorn app.main:app --host 127.0.0.1 --port 8742`

   - Name the artifact `opencleaner-backend.exe` (convention).

2. **Tauri**:

   - Install [Rust](https://rustup.rs/) and MSVC build tools.
   - `cd frontend && npm run tauri build`
   - Place `opencleaner-backend.exe` beside `OpenCleaner AI.exe` (e.g. `resources/` or same folder as the main binary), depending on how you wire spawn paths in Rust.

3. **Spawning sidecar (outline)**:

   - Use `std::process::Command` with the directory of the current executable (`tauri::api::path::resource_dir` or executable dir).
   - Pass `--port` if you make the port configurable later.
   - On upgrade, stop the old sidecar before replacing the binary.

4. **Elevation**: Most OpenCleaner actions avoid admin. Optional `powercfg` calls may fail without elevation; the app must tolerate that.

## macOS / Linux (future)

- Same sidecar idea: ship a `opencleaner-backend` binary (PyInstaller or native build).
- macOS: Gatekeeper / notarization if you distribute outside your org; use hardened runtime per Apple docs.
- Linux: prefer distro-neutral tarballs or Flatpak; keep port on loopback.

## Scripts in this repo

- `scripts/run_backend.sh` — developer backend runner.
- `scripts/bundle_backend_stub.sh` — **outline only**: documents the PyInstaller command you might run on a Windows CI host (edit paths before use).

## Known limitations (v0.2)

- Sidecar lifecycle management (auto-restart, port collision) is left to the integrator.
- No auto-update channel is defined.
- Windows scheduled task XML depends on OS encoding; the parser falls back to LIST format if needed.
- Filesystem scans use conservative caps; very large trees may be partially scanned (truncation flags in item details where applicable).

## Security recap

- Default: **no telemetry**, **no cloud APIs** for scanning or cleanup.
- Performance mode: **preview-first**, explicit `confirm_apply`, protected-process registry for suspend decisions.
- ML ranks and explains; **it never deletes**.
