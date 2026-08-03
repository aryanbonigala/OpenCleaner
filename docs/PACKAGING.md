# Packaging: OpenCleaner AI

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

## Building the backend sidecar binary (current platform, verified)

```bash
./scripts/bundle_backend.sh
```

This creates/reuses `backend/.venv`, installs the backend package with its
`packaging` extra (`pyinstaller>=6.0`), and runs PyInstaller (`--onefile`)
against `backend/app/sidecar.py` — never raw `uvicorn` — producing
`backend/dist/opencleaner-backend`. The script does not start the server; it
only builds the binary. The binary itself was verified on macOS (arm64,
Python 3.14) by running `opencleaner-backend --help`, which prints argparse
usage and exits 0 without binding a port.

`backend/build/`, `backend/dist/`, and `*.spec` are git-ignored — the binary
is never committed. PyInstaller output is platform-native (no
cross-compilation) — each target OS must run `scripts/bundle_backend.sh`
itself to produce its own binary.

Tauri sidecar spawning is still not implemented — this script only produces
the binary; nothing places it next to the Tauri bundle or launches it.

### Platform build matrix

| Platform | Status | Notes |
|---|---|---|
| macOS (arm64) | **Verified** | Re-verified at commit `5f36cc4`, 2026-08-03. `scripts/bundle_backend.sh` built `backend/dist/opencleaner-backend` via PyInstaller 6.x / Python 3.14 (venv). `opencleaner-backend --help` printed argparse usage and exited 0 without binding a port. |
| Linux | **Verified** | Verified at commit `411b160`, 2026-08-03, in a `python:3.12-slim` (linux/arm64) container via Docker Desktop 28.3.2 (daemon started via `open -a Docker`). Container installed `binutils` (needed by PyInstaller's Linux bootloader to append the archive to the ELF section; absent from the slim base image) then ran `scripts/bundle_backend.sh` unmodified, building `backend/dist/opencleaner-backend` via PyInstaller 6.x / Python 3.12. `opencleaner-backend --help` printed argparse usage and exited 0 without binding a port. Container-local `.venv`, `build/`, `dist/`, and `.spec`/`.egg-info` outputs were discarded with the container; nothing was committed. |
| Windows | **Blocked** | No Windows build environment (VM, physical machine, or CI runner) is available in this session. Wine and cross-compilation are explicitly unsupported for PyInstaller output, so this must be verified on real Windows. |

## Windows build notes

1. **Python environment** (builder machine):

   - Install Python 3.10+.
   - Run `scripts/bundle_backend.sh` (or the equivalent PyInstaller command by hand) to produce an artifact that runs the sidecar entrypoint (`backend/app/sidecar.py`), which serves the same app as:

     `uvicorn app.main:app --host 127.0.0.1 --port 8742`

   - Name the artifact `opencleaner-backend.exe` (convention). **Not yet verified on Windows** — verified only on macOS so far (see above).

2. **Tauri**:

   - Install [Rust](https://rustup.rs/) and MSVC build tools.
   - `cd frontend && npm run tauri build`
   - Place `opencleaner-backend.exe` beside `OpenCleaner AI.exe` (e.g. `resources/` or same folder as the main binary), depending on how you wire spawn paths in Rust.

3. **Spawning sidecar (outline)**:

   - Use `std::process::Command` with the directory of the current executable (`tauri::api::path::resource_dir` or executable dir).
   - Pass `--port` if you make the port configurable later.
   - On upgrade, stop the old sidecar before replacing the binary.

4. **Elevation**: Most OpenCleaner actions avoid admin. Optional `powercfg` calls may fail without elevation; the app must tolerate that.

## macOS / Linux

- Same sidecar idea: ship a `opencleaner-backend` binary. `scripts/bundle_backend.sh` (PyInstaller) is verified on both macOS (native) and Linux (container, see above).
- macOS: Gatekeeper / notarization if you distribute outside your org; use hardened runtime per Apple docs.
- Linux: prefer distro-neutral tarballs or Flatpak; keep port on loopback.

## Scripts in this repo

- `scripts/run_backend.sh` — developer backend runner.
- `backend/app/sidecar.py` — importable, testable entrypoint (`main()`) that serves the FastAPI app via uvicorn on `127.0.0.1:8742` by default; the PyInstaller build target. Importing it never starts a server.
- `scripts/bundle_backend.sh` — **real build script**, verified on macOS (native) and Linux (container): builds `backend/dist/opencleaner-backend` via PyInstaller against `app/sidecar.py`. See "Building the backend sidecar binary" above.

## Known limitations

- Sidecar lifecycle management (auto-restart, port collision) is left to the integrator.
- No auto-update channel is defined.
- Windows scheduled task XML depends on OS encoding; the parser falls back to LIST format if needed.
- Filesystem scans use conservative caps; very large trees may be partially scanned (truncation flags in item details where applicable).

## Security recap

- Default: **no telemetry**, **no cloud APIs** for scanning or cleanup.
- Performance mode: **preview-first**, explicit `confirm_apply`, protected-process registry for suspend decisions.
- ML ranks and explains; **it never deletes**.
