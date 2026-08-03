# Tauri Sidecar Readiness Audit

Audited at commit `e5a24d3` ("Pin frontend Node version"). Scope: Tauri wrapper state, backend
sidecar packaging plan, dev vs packaged startup behavior, safety constraints. No product behavior
was changed to produce this audit.

## 1. Current Tauri state

- The scaffold is real: `frontend/src-tauri/{Cargo.toml,build.rs,src/main.rs,tauri.conf.json}` all
  exist and are internally consistent with the frontend build.
- `frontend/package.json` has a working `"tauri": "tauri"` script, so `npm run tauri dev` /
  `npm run tauri build` are invokable — **not verified this audit**, since the Rust toolchain has
  never built this crate locally (no `frontend/src-tauri/target/`). Running `npm run tauri build`
  was skipped per the audit's safety budget (Rust/Tauri deps not confirmed configured).
- `frontend/src-tauri/src/main.rs` is the unmodified Tauri template: 7 lines, `Builder::default().run(...)`,
  no custom commands, no lifecycle hooks, no sidecar logic.
- `Cargo.toml` enables only the `shell-open` Tauri feature (open URLs/files in the OS default
  app). No `shell-execute`, `shell-sidecar`, or `process-command-api` feature is enabled — **the
  Rust binary cannot currently spawn an arbitrary child process even if code were added**; the
  Cargo feature flags for that aren't turned on yet.
- `tauri.conf.json`: `devPath` → `http://localhost:1420` (matches Vite's `strictPort: true` on
  1420), `distDir` → `../dist`, `beforeDevCommand: "npm run dev"` (frontend only, does not touch
  the backend), `bundle.active: false` (bundling itself is not yet turned on), allowlist has only
  `shell.open: true`.
- `frontend npm run build` re-verified this audit: succeeds (`tsc --noEmit && vite build`, ~320ms).

## 2. Current backend sidecar state

- No backend binary exists anywhere in the repo or build output.
- `scripts/bundle_backend_stub.sh` is an explicit stub — it echoes an example PyInstaller
  invocation and exits 0; it does not build anything.
- `docs/PACKAGING.md` names the expected artifact: `opencleaner-backend.exe` (Windows) /
  `opencleaner-backend` (macOS/Linux, "future"), wrapping
  `uvicorn app.main:app --host 127.0.0.1 --port 8742`.
- No Rust-side sidecar spawn code exists anywhere (`grep -rn "spawn\|sidecar\|Command::new"
  frontend/src-tauri/` → zero matches). `docs/PACKAGING.md` §"Spawning sidecar" is explicitly
  labeled an outline.
- `backend/app/main.py` exposes `GET /health` returning `{status, component: "opencleaner-backend",
  version, api_version, stage, scan_in_progress}` — usable today as a readiness/liveness probe.
- Backend default port (`backend/app/config.py`: `port: int = 8742`) and CORS origins
  (`localhost:1420`, `127.0.0.1:1420`, `tauri://localhost`) are consistent with `vite.config.ts`
  and `tauri.conf.json`'s `devPath`.

## 3. Dev-mode behavior

- Current `beforeDevCommand` only starts Vite; the documented dev flow
  (`docs/PACKAGING.md` "Local development") is three manual terminals: backend
  (`./scripts/run_backend.sh`), frontend (`npm run dev`), optional Tauri shell (`npm run tauri
  dev`).
- **Recommendation: keep dev-mode backend startup manual.** Folding a long-running `uvicorn`
  process into `beforeDevCommand` (which Tauri expects to complete, not run forever) or into
  Rust startup for the *dev* path adds real complexity for no benefit — a developer already sees
  backend logs directly in its own terminal, and iteration speed doesn't depend on auto-start.
- Health-check readiness in dev mode: not needed today, since the developer controls backend
  startup directly and can see failures in that terminal. It becomes relevant only once the app
  window itself needs to know the backend is up (see next section and recommended task).

## 4. Packaged-app behavior (design, not implemented)

- **Spawn**: locate the sidecar binary via the running executable's directory or
  `tauri::api::path::resource_dir()`, per `docs/PACKAGING.md`'s outline, and launch with
  `std::process::Command`. Requires enabling a shell/process Cargo feature not currently on.
- **Kill on exit**: hook `RunEvent::ExitRequested` (or `on_window_event` /
  `CloseRequested`) and call `Child::kill()` on the spawned process. Not implemented; no
  lifecycle/cleanup code exists yet.
- **Port conflict on 8742**: before spawning, `GET /health` with a short timeout. If it already
  answers with `component: "opencleaner-backend"`, treat as already-running and skip spawn
  (idempotent, avoids double-spawn). If the port answers with something else, surface an error
  rather than silently spawning a second process or hanging.
- **Logs/errors**: redirect child stdout/stderr to a file under the existing
  `~/.opencleaner/logs/` directory (`backend/app/config.py:logs_dir`) rather than losing them,
  and surface spawn/health failures to the user via a dialog instead of a silent hang.

## 5. Safety constraints — confirmed

- `docs/PACKAGING.md`'s sidecar concept section describes starting the backend HTTP server only —
  nothing about invoking scan/cleanup/performance actions on startup.
- Even if the sidecar auto-starts, no mutation happens automatically: `backend/app/main.py`
  defaults `permission_mode` to `PermissionMode.read_only`, and cleanup/performance endpoints all
  require explicit, separately-authenticated frontend calls (preview → confirm → execute). Sidecar
  startup and product-action execution are architecturally decoupled already.
- No telemetry: `Settings.telemetry_enabled` defaults `False`.
- No cloud: backend binds `127.0.0.1` only; `cors_origins` is loopback/`tauri://localhost` only.
- **Confirmed**: default launch remains non-mutating regardless of how/whether the sidecar is
  wired.

## 6. Gaps / blockers

- No backend binary or working build script (`bundle_backend_stub.sh` is explicitly a stub).
- No Rust sidecar spawn code (`main.rs` is the unmodified template).
- No Cargo/Tauri feature or allowlist entry for process execution — only `shell-open` is enabled.
- No lifecycle cleanup (kill-on-exit) code.
- No health-wait loop anywhere (Rust or frontend).
- `bundle.active: false` — bundling itself isn't turned on, a prerequisite before "sidecar in
  bundle" is meaningful.
- Rust/Tauri build has never been verified to compile in this repo (no `target/` directory).

## 7. Recommended next implementation task

**Add a backend health-wait step to the Tauri app startup path, polling the existing `GET
/health` endpoint with a bounded retry/backoff, and show a simple "waiting for backend" /
"backend not reachable" state in the frontend until it succeeds or times out — with the backend
itself still started manually (`scripts/run_backend.sh`), exactly as today's dev workflow already
requires.**

No process spawning, no new Cargo/Tauri process-execution features, no bundling changes, no
PyInstaller work. Testable entirely in `npm run tauri dev`: start the backend manually and confirm
the app reaches "ready", then don't start it (or kill it) and confirm the app shows a clear
"backend not reachable" state instead of hanging or silently failing.

**Why this task first:** it is the smallest genuinely new piece of the sidecar story — every
future spawn design (dev or packaged) needs this same wait-for-health logic, so building and
proving it now, against the existing manual-start workflow, retires that risk without touching
Cargo features, Tauri allowlist/permissions, bundling, or backend binary packaging — all of which
are separately gated and higher-risk. It also gives the eventual "Rust spawns the sidecar" task a
tested readiness primitive to call instead of inventing one under bundling pressure.

## 8. Build baseline update (at `fa91e79`, "Add backend readiness gate")

- **Node** `v23.3.0` / **npm** `10.9.1` present. Note: `frontend/package.json` `engines` pins
  `node: ">=22 <23"` — the installed Node is outside that range, though `npm run build` still
  succeeded (not enforced by npm without `engine-strict`).
- **Rust/Cargo: not installed** on this machine (`rustc`, `cargo` → command not found). This is
  the blocker for verifying the Tauri scaffold compiles.
- **`frontend/npm run build`**: succeeds (`tsc --noEmit && vite build`, ~343ms) — still passes
  after the backend readiness-gate change.
- **`npm run tauri -- --version`**: succeeds — `tauri-cli 1.6.3` is available (the CLI is a
  JS/npm wrapper and reports its version without invoking `rustc`).
- **`npm run tauri build`**: not run. Skipped per stop condition — it requires `cargo`/`rustc` to
  compile the Rust crate, which are absent, so it would fail immediately on missing toolchain
  rather than surface a build-config blocker.
- **Net**: Tauri scaffold compile status is still unverified in this repo, not because of a config
  or code problem, but because no Rust toolchain is installed on the machine that ran this audit.

## 9. Build verification update (at `a8e0e56`, "Document Tauri build baseline")

- **Node** `v22.23.2` / **npm** `10.9.8` — aligned to the `.nvmrc`/`engines` pin via `nvm use`.
- **Rust**: installed via official rustup (`https://sh.rustup.rs`, stable channel, user-level
  under `~/.rustup`/`~/.cargo`, no sudo/Homebrew). `rustc 1.97.1`, `cargo 1.97.1`,
  `rustup 1.29.0`, active toolchain `stable-aarch64-apple-darwin`.
- **`frontend/npm run build`**: succeeds (`tsc --noEmit && vite build`, ~330ms).
- **`npm run tauri -- --version`**: succeeds — `tauri-cli 1.6.3`.
- **`npm run tauri build`**: succeeds. Release profile compiled clean in ~41s, produced
  `frontend/src-tauri/target/release/OpenCleaner AI` (unsigned dev binary). No bundle artifact
  was produced, consistent with `bundle.active: false`. One harmless
  future-incompatibility warning from a transitive dependency (`block v0.1.6`); no errors.
- **Net**: the Tauri scaffold compiles cleanly end-to-end. The Rust-toolchain blocker from the
  prior baseline is resolved. Sidecar spawning remains unimplemented (out of scope here) — see
  §6/§7 above, which are otherwise unaffected by this update.

## 10. `block v0.1.6` future-incompatibility warning — triaged, deferred (at `d13def1`)

- **Dependency path**: `opencleaner_ai` → `tauri v1.8.3` → `tauri-runtime-wry v0.14.11` →
  `wry v0.24.12` → `tao v0.16.11` → `cocoa v0.24.1` → `block v0.1.6`. `block` is a transitive
  macOS Cocoa/Objective-C FFI dependency pulled in by Tauri's own runtime stack, not a direct
  dependency of this crate.
- **Warning**: `static of uninhabited type` on `block`'s `_NSConcreteStackBlock` static
  (`cargo report future-incompatibilities`, rustc issue
  [#74840](https://github.com/rust-lang/rust/issues/74840)) — accepted today, will become a hard
  error in a future Rust release.
- **Checked for a fix**: `cargo update -p block --dry-run` locks 0 packages (already at the
  latest compatible version); `cargo search block` confirms `0.1.6` is the only version of the
  `block` crate ever published on crates.io. No lockfile-only or minor/patch update exists.
- **Classification: no safe fix without a Tauri/Wry/Tao major upgrade.** Resolving this requires
  `cocoa`/`tao`/`wry` upstream to migrate off the abandoned `block` crate (e.g. to `block2`),
  which in this dependency graph is tied to a newer `wry`/`tao` release line pulled in only by a
  Tauri 2.x major bump — out of scope per this task's constraints (no Tauri major upgrade, no
  product-code changes).
- **Deferred**: no `Cargo.toml`/`Cargo.lock` change made. The warning is harmless today (lint, not
  a build error) and re-check when a Tauri 2.x migration is otherwise warranted.

## 11. macOS dev-checkout spawn prototype implemented (at this commit)

- Implements §4's design: `frontend/src-tauri/src/main.rs` now spawns
  `backend/dist/opencleaner-backend` (dev-checkout path, resolved from
  `CARGO_MANIFEST_DIR`) on startup if `GET 127.0.0.1:8742/health` isn't
  already responding; stores the `Child` in managed state; kills only that
  child on `RunEvent::ExitRequested`. No new Cargo dependency — health check
  uses a raw `TcpStream` HTTP/1.1 request, no Tauri shell/process-execution
  feature or allowlist entry was enabled (`std::process::Command` only, per
  Cargo.toml unchanged). See `docs/PACKAGING.md` "macOS dev-checkout spawn
  prototype" for full behavior.
- Also added `frontend/src-tauri/icons/icon.png` (small placeholder PNG):
  `tauri::generate_context!()` panics at compile time without an icon file
  present at the conventional path, regardless of `bundle.active` — this was
  true on the unmodified template too (verified by stashing the sidecar diff
  and re-running `cargo check`), so it's a pre-existing gap unrelated to
  spawn logic, fixed here only because it blocked `cargo check`/`tauri
  build` from running at all.
- **Verified**: `cargo check`, `cargo test` (2 unit tests: binary path
  resolution, already-running-vs-spawn decision), `npm run build`, `npm run
  tauri build` — all pass. Runtime smoke (running the built release binary
  directly, not `tauri dev`): confirmed no double-spawn when a real backend
  (`scripts/run_backend.sh`) is already listening on 8742, and confirmed
  that backend is left running after the Tauri process exits. Confirmed the
  bounded health-wait does not hang when the child dies immediately (see
  gap below) — it times out and logs, and the frontend readiness gate still
  reports "backend not reachable" independently.
- **Fixed (this task)**: `backend/dist/opencleaner-backend` previously
  failed at actual startup — `uvicorn.run("app.main:app", ...)` could not
  import `app.main` inside the frozen binary (`ERROR: Could not import
  module "app.main"`). `backend/app/sidecar.py` now passes the imported
  FastAPI `app` object to `uvicorn.run()` instead of the module-path string.
  A second, previously-undiscovered gap then surfaced: `app/db.py` reads
  `sql/schema.sql` relative to `__file__`, which PyInstaller does not bundle
  by default, so `init_db` found no schema and every DB query failed.
  `scripts/bundle_backend.sh` now adds `--add-data "sql/schema.sql:sql"`.
  Verified: `pytest tests/test_sidecar_entrypoint.py -q` (4 passed,
  including a new "importing sidecar never imports app.main" test), the
  safe import smoke (`OPENCLEANER_USE_MOCK=1 python -c "import app.sidecar;
  import app.main"`), a direct run of the rebuilt frozen binary (bounded,
  isolated `OPENCLEANER_DATA_DIR`) returning `200 OK` with
  `component: "opencleaner-backend"` from `GET /health`, and a full Tauri
  release-binary spawn smoke — the frozen binary came up under the Rust
  spawn logic and `/health` was reachable end-to-end.
- **New gap found during this task's Tauri spawn smoke — unverified/likely
  broken**: sending the Tauri release binary a plain `SIGTERM` (simulating a
  killed/force-quit process, as opposed to a GUI-driven window close) did
  **not** terminate the spawned backend child; it was left running and had
  to be cleaned up manually. Tauri's `RunEvent::ExitRequested` appears to be
  driven by the windowing event loop (window close / OS "Quit"), not by
  process-level signals, so a hard kill of the parent orphans the child.
  This was flagged as unverified in the entry above (§11) before this task;
  it is now reproduced and confirmed as a real gap, not just an untested
  path. Out of scope to fix here — would need a `SIGTERM`/`SIGINT` handler
  in `main.rs` that also kills the tracked child, which is Rust spawn-logic
  work, not backend packaging.
