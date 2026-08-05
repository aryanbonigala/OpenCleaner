# Windows Packaged Sidecar Audit

Audited at commit `9054c54` ("Document macOS release smoke checklist"). Documentation-only
feasibility audit — no Windows code paths, scripts, or spawn behavior were implemented. Windows
remains **blocked/unverified**: no Windows build environment (VM, physical machine, CI runner) was
available in this session, and PyInstaller output is platform-native (no cross-compilation, no
Wine), so none of this can be confirmed without a real Windows builder.

## Current macOS-verified state (for contrast)

Per `docs/PACKAGING.md` and `docs/MACOS_RELEASE_CHECKLIST.md`:

- `scripts/bundle_backend.sh` builds `backend/dist/opencleaner-backend` via PyInstaller
  (`--onefile`) against `backend/app/sidecar.py`.
- `scripts/stage_tauri_sidecar.sh` copies that binary to
  `frontend/src-tauri/resources/opencleaner-backend`.
- `tauri.conf.json` bundles it via `"resources": ["resources/opencleaner-backend"]`,
  `"targets": ["app"]` (macOS `.app` only).
- `frontend/src-tauri/src/main.rs`'s `backend_binary_path()` resolves the packaged resource path
  first (`resource_dir/resources/opencleaner-backend`), then falls back to the dev-checkout path
  (`<repo root>/backend/dist/opencleaner-backend`).
- `./scripts/build_macos_app.sh` runs this end-to-end and smoke-tests `/health` + `SIGTERM`
  cleanup against the packaged `.app`.

## Windows gaps (repo-observable, not yet exercised)

1. **Binary name has no `.exe`.** `BACKEND_BINARY_NAME` in `main.rs:77` is the literal
   `"opencleaner-backend"`, joined verbatim in both `resolve_backend_binary()` (main.rs:81-83) and
   `resolve_resource_backend()` (main.rs:87-89). PyInstaller on Windows produces
   `opencleaner-backend.exe`, not an extensionless file. As written, neither resolver would find a
   Windows-built binary — `backend_binary_path()` would return `None` on Windows even if the exe
   were staged correctly, because `candidate.is_file()` would check for the wrong filename.

2. **`tauri.conf.json`'s `resources` entry is macOS-specific by content, not by platform gating.**
   `"resources": ["resources/opencleaner-backend"]` (tauri.conf.json:34) is a flat array with no
   per-platform variants. Tauri 1.x resource globs aren't OS-conditional here, so a Windows build
   using this same config would look for a file named exactly `opencleaner-backend` (no `.exe`)
   in the bundle resources — which won't exist if the Windows build produces
   `opencleaner-backend.exe`.

3. **`bundle.targets: ["app"]` is a macOS-only bundle target.** Tauri's `"app"` target is
   `.app`/macOS. A Windows build needs a Windows-appropriate target (e.g. `"msi"` or `"nsis"`) —
   not yet decided or added.

4. **`scripts/stage_tauri_sidecar.sh` is a Bash script.** It won't run under a plain Windows
   `cmd.exe`/PowerShell session (no WSL/Git-Bash assumed). It hardcodes the source path
   `backend/dist/opencleaner-backend` (no `.exe`) and destination
   `frontend/src-tauri/resources/opencleaner-backend` — both need a `.exe`-aware Windows
   equivalent, not just a shell-syntax port.

5. **`scripts/bundle_backend.sh` is also Bash**, and would need a Windows-native equivalent (or
   WSL/Git-Bash, which the audit's constraints exclude as a verification path since PyInstaller
   output must be built natively per target OS anyway). It also assumes `.venv/bin/activate`
   (POSIX venv layout); Windows venvs use `.venv\Scripts\activate`.

6. **Signal cleanup is Unix-only by explicit `#[cfg]` gating.** `main.rs:118` gates the
   SIGTERM-forwarding `terminate_child()` behind `#[cfg(unix)]`; the `#[cfg(not(unix))]` variant
   (main.rs:131-134) just calls `child.kill()` directly — no graceful-termination attempt, and no
   equivalent of the SIGTERM/SIGINT background-thread handler (`main.rs:200-214`, also
   `#[cfg(unix)]`-gated) exists for Windows. On Windows, `RunEvent::ExitRequested` (Tauri's
   windowing event loop) would still fire and kill the tracked child, but there is no
   Windows-side handling of the equivalent to a killed/force-quit parent process bypassing that
   event loop (e.g. `taskkill`, console close events) — this repo has no code addressing that
   case for Windows. Whether a plain `Child::kill()` on Windows fully tears down a PyInstaller
   `--onefile` bootloader's forked worker (as SIGKILL orphans it on macOS/Linux, per
   `docs/PACKAGING.md` "SIGTERM/SIGINT cleanup") is unknown — PyInstaller's Windows bootloader
   process model has not been inspected in this repo and cannot be verified without a Windows run.

7. **PyInstaller `--add-data` separator differs on Windows.** `scripts/bundle_backend.sh` passes
   `--add-data "sql/schema.sql:sql"` (colon-separated `SRC:DEST`). PyInstaller's Windows convention
   uses a semicolon (`SRC;DEST`) instead of a colon — a Windows build script must use
   `--add-data "sql/schema.sql;sql"` or the frozen binary will silently fail to bundle the schema
   file (the exact class of bug already fixed once for the module-import case, per
   `docs/PACKAGING.md`'s "Fixed" section).

## Required Windows build inputs (from repo docs only)

- Python 3.10+ (`backend/pyproject.toml:10`, `requires-python = ">=3.10"`), with the `packaging`
  extra (`pyinstaller>=6.0`, `backend/pyproject.toml:27`).
- Node 22 + npm (per `docs/MACOS_RELEASE_CHECKLIST.md` prerequisites; `.nvmrc`/`engines` pin
  applies equally to a Windows Node install).
- Rust/Cargo (via `rustup`), plus **MSVC build tools** — `docs/PACKAGING.md`'s existing "Windows
  build notes" section already names this; not independently verified here.
- No new Tauri Cargo features are known to be required beyond what's already enabled
  (`std::process::Command` only — no `shell-execute`/`shell-sidecar` allowlist entry is used
  today, and none is expected to be needed on Windows either, per how `main.rs` already spawns
  child processes directly).

## Required expected outputs

- `backend/dist/opencleaner-backend.exe` (PyInstaller Windows output).
- Staged Tauri resource: `frontend/src-tauri/resources/opencleaner-backend.exe` (name must match
  whatever `BACKEND_BINARY_NAME`/`tauri.conf.json`'s `resources` entry are updated to, once that
  Windows-aware change is made — not done in this audit).
- Packaged resource location inside the bundle: analogous to macOS's
  `Contents/Resources/resources/opencleaner-backend`, expected to be something like
  `resources/resources/opencleaner-backend.exe` relative to the installed app directory (exact
  Tauri 1.x Windows resource layout not verified here — must be confirmed on a real Windows build).

## Proposed future script names (not created in this audit)

- `scripts/bundle_backend_windows.ps1`
- `scripts/stage_tauri_sidecar_windows.ps1`
- `scripts/build_windows_app.ps1`

## Proposed verification runbook (for whoever runs this on real Windows)

1. `opencleaner-backend.exe --help` — direct frozen-binary sanity check (argparse usage, exit 0,
   no port bound), mirroring the macOS/Linux verification already done.
2. Direct frozen-binary `/health` check (bounded run, `OPENCLEANER_USE_MOCK=1`, isolated
   `OPENCLEANER_DATA_DIR`), mirroring `docs/PACKAGING.md`'s macOS verification.
3. Packaged app `/health` check — launch the installed/packaged `.exe` and confirm
   `GET 127.0.0.1:8742/health` returns `200` with `component: "opencleaner-backend"`.
4. Confirm no duplicate backend spawns when a backend is already listening on 8742 (mirrors the
   existing `decide()`/health-check logic, which is platform-agnostic Rust and should need no
   Windows-specific change).
5. Confirm cleanup on normal app exit (`RunEvent::ExitRequested` path) — does `child.kill()` alone
   fully terminate the PyInstaller bootloader and any forked/child worker process on Windows, or
   does it orphan a worker the way bare `SIGKILL` does on macOS/Linux? Unknown until tested.

## Explicitly unverified

- An actual Windows build (no Windows builder was available this session).
- Windows packaged spawn (resource resolution, `.exe` naming, bundle target) end-to-end.
- Windows child-process cleanup semantics (whether `Child::kill()` cleanly tears down a
  PyInstaller `--onefile` bootloader + forked worker, or orphans the worker as SIGKILL does on
  macOS/Linux).
- Installer/signing (MSI/NSIS packaging, code signing) — not addressed here at all.

## No Windows support is claimed

This audit changes no behavior and adds no Windows code paths. Windows remains blocked per the
platform build matrix in `docs/PACKAGING.md`.
