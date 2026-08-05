# macOS Local Pre-Release Checklist

A local, repeatable gate to run before cutting a macOS build. See
[`docs/PACKAGING.md`](PACKAGING.md) for how the sidecar/packaging pieces fit
together.

## Prerequisites

- macOS (Darwin).
- Node 22 on `PATH` (or via `nvm`, pinned in `.nvmrc`) and npm.
- Rust/Cargo available (via `rustup` or already on `PATH`).
- Python 3.10+.
- Port 8742 free (nothing else listening on it).

## Command

```bash
./scripts/build_macos_app.sh
```

## What it verifies

- Backend sidecar builds (`scripts/bundle_backend.sh`).
- The sidecar binary is staged as a Tauri resource.
- The Tauri `.app` builds.
- The packaged app's `/health` endpoint responds with
  `component: "opencleaner-backend"`.
- The app process cleans up on `SIGTERM` and port 8742 is free afterward.

## What it does not verify

- Code signing / notarization.
- DMG or other installer targets.
- Windows or Linux packaged spawn.
- `SIGKILL`, crash, or power-loss cleanup.

## Generated outputs (not committed)

`backend/dist/`, `backend/build/`, `frontend/src-tauri/resources/`, and
`frontend/src-tauri/target/` are all git-ignored build output — do not commit
them.

## Manual CI smoke

The `macOS Package Smoke` workflow
(`.github/workflows/macos-package-smoke.yml`) runs this same script on a
GitHub-hosted macOS runner. It is manual-only (`workflow_dispatch`) — it does
not run on push or PR, and there is no schedule.

To run it: GitHub → **Actions** → **macOS Package Smoke** → **Run workflow**.

It verifies the same things as the local command above. On failure, the
build/smoke logs are uploaded as a workflow artifact. It is not a
signing/notarization/DMG check, and it does not touch Windows or Linux
packaging.
