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

## macOS dev-checkout spawn prototype

`frontend/src-tauri/src/main.rs` now spawns the backend on macOS when running
from a dev checkout: on startup it checks `GET 127.0.0.1:8742/health`; if
already responding, it does not spawn a second backend. Otherwise it looks
for `backend/dist/opencleaner-backend` at `<repo root>/backend/dist/` (i.e.
built via `./scripts/bundle_backend.sh`) and spawns it via
`std::process::Command`, redirecting stdout/stderr to
`~/.opencleaner/logs/sidecar.log`. It then polls `/health` with a bounded
retry/backoff (20 attempts, 250ms apart) before continuing; the existing
frontend readiness gate still reports "backend not reachable" on failure. On
`ExitRequested`, only the child process this app instance spawned is killed —
a pre-existing backend it didn't start is left alone.

### SIGTERM/SIGINT cleanup

`RunEvent::ExitRequested` is driven by Tauri's windowing event loop (window
close / OS "Quit"), not by process-level signals — a plain `SIGTERM` to the
Tauri parent (e.g. a killed/force-quit process) previously left a spawned
backend orphaned. `main.rs` now shares one `kill_tracked_child` helper
between `ExitRequested` and a new signal path: on Unix, a background thread
(via the `signal-hook` crate, the one new Cargo dependency this task added,
scoped to `[target.'cfg(unix)'.dependencies]` so it isn't pulled in on
Windows) blocks for `SIGTERM`/`SIGINT`, kills only the tracked child, and
exits with `128 + signal number`. As before, a pre-existing backend Tauri
didn't spawn is never touched, since it was never stored in `SidecarChild`.

Smoke-testing this fix surfaced a second, deeper gap: the PyInstaller
`--onefile` `opencleaner-backend` binary is a bootloader that forks its own
worker process and only supervises it — `Command::spawn()` from Rust
captures just the bootloader's PID. `Child::kill()` sends `SIGKILL`, which
can't be caught, so it killed the bootloader instantly without giving it a
chance to forward anything to its forked worker, which then survived,
reparented to PID 1, still bound to port 8742 (confirmed by process-tree
inspection: `SIGTERM` to the bootloader — which it can catch — took both
processes down together every time; `SIGKILL` orphaned the worker every
time). Fixed with a `terminate_child` step ahead of `kill_tracked_child`'s
final `kill()`: send `SIGTERM` to the tracked child via the system `kill`
binary (`Command::new("kill")` — no new dependency, no unsafe FFI), poll
`try_wait()` for up to 2 seconds, and fall back to `child.kill()`
(`SIGKILL`) only if the bootloader hasn't exited by then.

**Verified** (rebuilt release binary, backend rebuilt via
`scripts/bundle_backend.sh`): pre-existing backend survives Tauri
`SIGTERM` with no double-spawn; a Tauri-spawned backend (bootloader +
forked worker) is fully gone — confirmed via `ps`/`lsof`, no process and no
port 8742 listener — after both `SIGTERM` and `SIGINT` to the Tauri
process; GUI `ExitRequested` cleanup uses the identical helper, so it gets
the same fix.

**Not covered, and not coverable by any userspace handler**: `SIGKILL` sent
directly to the Tauri process, a crash, or power loss — a spawned backend
(and its forked worker) would be orphaned in all of these.

## Packaged-app resource path (macOS)

The binary path resolution now tries the packaged app resource path first,
falling back to the dev-checkout path (`CARGO_MANIFEST_DIR`-derived) second —
see `backend_binary_path()` in `frontend/src-tauri/src/main.rs`.

**Resource staging**: `scripts/stage_tauri_sidecar.sh` copies
`backend/dist/opencleaner-backend` (built by `scripts/bundle_backend.sh`) to
`frontend/src-tauri/resources/opencleaner-backend`. It fails clearly if the
backend binary hasn't been built yet. The staged file is git-ignored (never
committed) — run it fresh before every `tauri build`.

**Tauri config**: `tauri.conf.json`'s `bundle` now has `"active": true`,
`"targets": ["app"]` (macOS `.app` only — no dmg/installer), and
`"resources": ["resources/opencleaner-backend"]`, which Tauri 1.x places at
`$RESOURCE/resources/opencleaner-backend` inside the bundle (structure
preserved relative to `src-tauri`). Note: `tauri-build`'s build script
validates that `bundle.resources` paths exist even at `cargo check`/`cargo
build` time — the resource must be staged before those commands, not just
before `tauri build`.

**Rust resolution order**: at startup, `handle.path_resolver().resource_dir()`
gives the resource directory (works for both a bundled `.app` — resolves
into `Contents/Resources/` — and an unbundled `cargo build`/`tauri build`
release binary, where Tauri also copies `bundle.resources` into
`target/release/resources/` for convenience). `backend_binary_path()` joins
`resources/opencleaner-backend` onto that dir and uses it if the file exists;
otherwise it falls back to `<repo root>/backend/dist/opencleaner-backend`
resolved from `CARGO_MANIFEST_DIR`, exactly as before.

**Verified** (macOS arm64, this task): `cargo check`, `cargo test` (5 unit
tests, including a new resource-first-precedence test using a temp dir),
`npm run build`, `npm run tauri build` — all pass; a `.app` bundle was
produced containing the binary at `Contents/Resources/resources/
opencleaner-backend` (confirmed via `file`, a Mach-O arm64 executable).
Running `OpenCleaner AI.app/Contents/MacOS/OpenCleaner AI` directly spawned
the backend from that packaged resource path (confirmed via `ps` — parent
`OpenCleaner AI` → bootloader → forked worker, all under
`Contents/Resources/resources/opencleaner-backend`), `GET /health` returned
`200` with `component: "opencleaner-backend"`, and `SIGTERM` to the app
process cleanly killed both the bootloader and its forked worker (confirmed
via `ps`/`lsof`: no process, port 8742 free) — the same `kill_tracked_child`/
`terminate_child` helpers as before, unchanged. `SIGINT` was not
separately re-run against the packaged binary this task since it shares the
identical, signal-agnostic code path already proven for `SIGTERM` here and
for both signals previously against the dev-checkout binary.

The dev-checkout fallback still works: with the `target/release/resources/`
copy temporarily moved aside (simulating no resource dir available), the
unbundled release binary fell back to spawning
`backend/dist/opencleaner-backend` directly, `/health` still came up, and
`SIGTERM` cleanup was still clean.

### Repeatable macOS packaging smoke

`./scripts/build_macos_app.sh` runs the full sequence above end-to-end from a
clean checkout: builds the backend sidecar, stages it as a Tauri resource,
builds the frontend and the Tauri `.app`, then launches the packaged `.app`
directly, polls `/health` for `component: "opencleaner-backend"`, sends it
`SIGTERM`, and confirms port 8742 is free afterward. It fails clearly (no
kill) if port 8742 is already occupied before the smoke, and only ever
terminates the app process it launched. macOS only — this is the repeatable
verification path for the checks described above; it does not add
signing, notarization, DMG, or Windows/Linux packaged spawn.

**Still unverified**: Windows and Linux packaged spawn (out of scope this
task); `SIGKILL`, crash, and power-loss cleanup (not coverable by any
userspace handler, as before).

**Fixed**: the PyInstaller `--onefile` binary previously failed at runtime with
`ERROR: Could not import module "app.main"`, because `uvicorn.run("app.main:app", ...)`
resolves that string via module import machinery that PyInstaller's frozen
importer doesn't support. `backend/app/sidecar.py` now imports the FastAPI
`app` object directly inside `main()` (`from app.main import app`) and passes
the object to `uvicorn.run(app, ...)` instead of the string form; importing
`app.sidecar` on its own still never imports `app.main` or starts a server.
A second gap surfaced once the import fixed itself: `app/db.py` locates
`sql/schema.sql` relative to `__file__` at runtime, and PyInstaller does not
bundle non-Python data files by default, so `init_db` silently found no
schema file and every query failed with `no such table`.
`scripts/bundle_backend.sh` now passes `--add-data "sql/schema.sql:sql"` to
PyInstaller so the schema file is present at the same relative path inside
the frozen bundle. With both fixes, `backend/dist/opencleaner-backend`
started directly (bounded run, `OPENCLEANER_USE_MOCK=1`, isolated
`OPENCLEANER_DATA_DIR`) now serves `GET /health` with `200 OK` on macOS.

Tauri sidecar spawning is otherwise still not implemented for packaged
builds — this script only produces the binary; nothing places it next to the
Tauri bundle or launches it there.

### Platform build matrix

| Platform | Status | Notes |
|---|---|---|
| macOS (arm64) | **Verified** | Re-verified 2026-08-03 (this fix). `scripts/bundle_backend.sh` built `backend/dist/opencleaner-backend` via PyInstaller 6.x / Python 3.14 (venv), including the `app.main` object-import fix and bundled `sql/schema.sql`. `opencleaner-backend --help` exits 0; running the binary directly now also serves `GET /health` with `200 OK`. |
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
