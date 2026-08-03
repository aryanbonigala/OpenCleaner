# Packaging Readiness Audit

Audited at commit `1a8898b` ("Add performance suspend gating tests"). Scope: fresh-clone
setup, dev/build/test flow, local data/safety packaging, repo hygiene, release readiness.
No product behavior was changed to produce this audit.

## 1. Fresh clone setup

- Backend: `cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`,
  or just `./scripts/run_backend.sh` (creates the venv, installs, and runs uvicorn in one step).
- Frontend: `cd frontend && npm install`.
- Python version is pinned: `requires-python = ">=3.10"` in `backend/pyproject.toml`.
- Node version is **not** pinned anywhere (no `.nvmrc`, no `engines` field in `frontend/package.json`).
- Both installs are documented in README.md; no root-level command installs both at once (two
  independent projects, no root `package.json`/Makefile).

## 2. Dev run flow

- Backend: `uvicorn app.main:app --host 127.0.0.1 --port 8742` (or `scripts/run_backend.sh`).
- Frontend: `npm run dev` (Vite), fixed to port **1420** via `strictPort: true` in `vite.config.ts`.
- Optional Tauri shell: `npm run tauri dev` (requires a Rust toolchain, not verified by this audit).
- Ports/CORS are internally consistent: `backend/app/config.py` hardcodes
  `cors_origins = ["http://localhost:1420", "http://127.0.0.1:1420", "tauri://localhost"]`,
  matching `frontend/vite.config.ts`'s fixed port and `frontend/src-tauri/tauri.conf.json`'s
  `devPath`. This coupling is real but not spelled out anywhere in prose — a developer who
  changes the Vite port would silently break CORS with no comment pointing at the cause.
- No single script starts backend + frontend together; the documented flow is two manual
  terminal commands (plus a third, optional, for Tauri).

## 3. Build flow

- Frontend build verified working end-to-end this audit: `npm run build` (`tsc --noEmit && vite build`)
  succeeded from the existing `node_modules`, producing `dist/` in ~300ms.
- Backend has no build/package step beyond editable install. `docs/PACKAGING.md` documents a
  PyInstaller/Nuitka path to produce a `opencleaner-backend` sidecar binary for Windows, but
  `scripts/bundle_backend_stub.sh` is explicitly labeled "outline only" (edit paths before use) —
  not runnable as-is.
- A Tauri desktop wrapper already exists (`frontend/src-tauri/`), and `docs/PACKAGING.md`
  thoughtfully lays out the sidecar pattern (UI spawns/expects a local backend binary). The
  actual Rust-side sidecar spawn logic is documented as an "outline," not implemented.

## 4. Test flow

- Backend: `cd backend && PYTHONPATH=. pytest` (documented in README).
- Frontend: `cd frontend && npm run test` (`vitest run`, documented in README).
- This audit's one smoke pass: `OPENCLEANER_USE_MOCK=1 python -c "import app.main"` succeeded
  (clean import, no live OS calls), and the frontend build above succeeded. Full pytest/vitest
  suites were not run, per the audit's read-only/no-mutation scope.
- No standalone "safe smoke test" recipe is documented. `OPENCLEANER_USE_MOCK=1` is the closest
  thing — it forces the mock scan dataset instead of live process/service/filesystem access —
  but nothing in README names it as the go-to non-mutating verification step for a fresh clone.

## 5. Local data/safety

- Local data lives under `~/.opencleaner/` (SQLite db, quarantine, logs), default
  `Path.home() / ".opencleaner"` in `backend/app/config.py`.
- That path **is** overridable via `OPENCLEANER_DATA_DIR` (pydantic-settings
  `env_prefix="OPENCLEANER_"`), confirmed by reading `backend/app/config.py` — but this override
  is not mentioned in README.md or docs/PACKAGING.md, even though `OPENCLEANER_USE_MOCK` (the
  sibling env var) is documented.
- Destructive/mutation capabilities are otherwise well documented: README's "Safety model"
  section covers permission modes, preview-first cleanup/performance actions, quarantine +
  rollback, and the protected-process registry. This matches the guardrail work in recent
  commits (action safety contract, scanner contract, performance suspend gating).
- `/api/processes/end` remains intentionally unimplemented per prior context; not re-verified
  here (out of scope — action/process-control code was not touched).

## 6. Repo hygiene

- `.gitignore` covers `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `*.db`,
  `dist/`, `node_modules/`, `.DS_Store`, `target/`, **and** `graphify-out/`, `.claude/`, `.serena/`
  — generated files, local assistant/tool folders, and Graphify output are all correctly ignored.
- No `.github/workflows/` — no CI configured (expected; out of scope for this task).
- No root `pyproject.toml`/`package.json`/Makefile unifying backend and frontend — this is a
  structural fact, not a hygiene problem, but it's why there's no one-shot "clone and run" command.
- No stale version references were spotted in the files read for this audit; a full doc/version
  consistency sweep is out of this audit's budget (`docs/VERSION_API_CONTRACT_AUDIT.md` already
  exists as a separate, prior audit of that surface).

## 7. Release readiness

**Already good enough:**
- Safety model is clearly documented and enforced (protected registry, preview-first, quarantine + rollback, audit log).
- Backend imports cleanly in mock mode; frontend builds cleanly — both verified this audit.
- Ports/CORS are internally consistent across Vite, Tauri config, and backend settings.
- `.gitignore` is clean and correctly scoped, including local AI-tool folders.
- `docs/PACKAGING.md` already has a coherent sidecar packaging plan for Windows.

**Missing before a first safe local alpha:**
- No documented, non-mutating smoke-test recipe for verifying a fresh clone works.
- `OPENCLEANER_DATA_DIR` override exists in code but is undocumented.
- Node version is unpinned (Python version is pinned).
- Sidecar spawn wiring (Rust) and backend bundling (PyInstaller) are both outlines, not runnable — expected pre-alpha, not a blocker for local dev.

## Recommended next implementation task

**Add a "Safe smoke test" section to README.md** (after "Running tests") giving one
copy-pasteable, non-mutating command sequence — `OPENCLEANER_USE_MOCK=1` backend import/health
check plus `npm run build` — and document `OPENCLEANER_DATA_DIR` next to the existing
`OPENCLEANER_USE_MOCK` documentation.

**Why this task first:** it is the lowest-risk change available (README-only, no code, no new
dependencies, no port/CORS changes, nothing that touches scanner/action/performance behavior),
and it directly closes the biggest gap this audit found for a new contributor: there is
currently no documented way to verify the app is wired correctly on a fresh clone without either
touching real OS process/service state or guessing at an undocumented env var. It also gives the
next real packaging step (Tauri sidecar wiring) a safe, documented baseline to build from.
