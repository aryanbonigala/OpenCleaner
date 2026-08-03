# OpenCleaner — Project Graph Facts

Compact, structured facts about OpenCleaner, written to be extracted into the
graphify knowledge graph and retrieved by future agents without rereading the repo.

**Rules for this file**
- One fact per bullet, one line where possible. No diffs, no logs, no pasted reports.
- Code is the source of truth. If a fact here disagrees with the code, the code wins
  and the fact gets corrected — see `docs/GRAPHIFY_WORKFLOW.md`.
- Never add secrets, API keys, tokens, personal data, or machine-specific paths.
- Superseded facts move to **Superseded facts** at the bottom rather than being deleted.

Last verified against commit `a3a31b2`.

---

## Project

- **OpenCleaner** — local-first desktop app for understanding and safely controlling
  what runs on your machine. Python/FastAPI backend, React/TypeScript frontend,
  local SQLite at `~/.opencleaner/opencleaner.db`. No cloud, no telemetry by default.

## ProductDirection

- Local-first process/task intelligence app.
- "Task Manager, but understandable, safe, beautiful, and chat-controlled."
- Pivot direction is recorded in `docs/PROCESS_CONTROL_PIVOT_PLAN.md`.
- The product previews and explains; it does not yet act on processes.

## Subsystem

- **backend scan pipeline** — collects scanners, normalizes, scores, persists one scan.
  Entry point `run_full_scan`. See `docs/SCAN_PIPELINE.md`.
- **process-control classifier** — assigns each process a category and an action policy.
- **process inventory API** — read-only process listing derived from the newest scan.
- **chat command preview API** — deterministic local parser over the newest scan.
- **frontend Process Control dashboard** — main UI surface for process review.
- **frontend Chat Preview UI** — "Ask OpenCleaner" panel; sends chat text to the chat command
  preview API and renders the response. Preview-only, no execution actions.
- **FPS Optimizer panel** — gaming-oriented view over FPS-impacting processes.
- **scan persistence / SQLite** — scans + scan_items tables, retention, schema migration.
- **file cleanup / quarantine** — reversible file actions, quarantine retention.
- **settings / permissions** — user preferences, permission mode, scanner toggles.
- **protected registry / action gating** — the safety floor; can only tighten, never widen.

## File

- `backend/app/services/scan_service.py` — scan orchestration, persistence, retention, latest-scan read.
- `backend/app/db.py` — SQLite connection lifecycle, schema init, settings, audit log.
- `backend/app/models/scan_item.py` — canonical `ScanItem`, `SCAN_SCHEMA_VERSION`.
- `backend/app/engine/process_action_policy.py` — final action policy per process. Safety-critical.
- `backend/app/engine/process_classifier.py` — process categorisation and evidence.
- `backend/app/services/process_inventory.py` — process inventory response building.
- `backend/app/services/chat_preview.py` — chat command preview construction.
- `backend/sql/schema.sql` — table definitions, composite keys, cascade rules.
- `backend/app/scanners/` — per-source scanners; each mints scan item ids.
- `frontend/src/App.tsx` — app shell and routing between panels.
- `frontend/src/api.ts` — typed client for all backend endpoints.
- `frontend/src/components/ProcessControlDashboard.tsx` — process control table/UI.
- `frontend/src/components/FpsOptimizerPanel.tsx` — FPS optimizer panel.
- `frontend/src/components/ChatPreviewPanel.tsx` — "Ask OpenCleaner" panel; owns chat state, calls `client.previewChatCommand`.
- `frontend/src/components/ChatCommandInput.tsx` — chat textarea, explicit-selection confirm checkbox, submit control.
- `frontend/src/components/ChatSuggestedPrompts.tsx` — canned prompt chips that submit preset chat messages.
- `frontend/src/components/ChatPreviewResponse.tsx` — renders chat preview response: summary, warnings, item lists, actions, disclaimer.
- `frontend/src/components/ChatPreviewItemList.tsx` — renders one labeled list of chat preview items by status.
- `docs/VERSION_API_CONTRACT_AUDIT.md` — v0.1.0/v0.1.1 backend/API contract audit; findings, gaps, next task.

## Decision

- `SCAN_SCHEMA_VERSION` is **2**; version 2 added the `process_control` block to `ScanItem`.
- `scan_items` row identity is **(scan_id, id)**. Item ids repeat across scans by design
  but must be unique within one scan.
- Duplicate item ids within one scan **fail loudly before any INSERT**
  (`assert_unique_scan_item_ids`). No `INSERT OR REPLACE`, no `INSERT OR IGNORE`, no silent drops.
- Latest scan is selected by `ORDER BY finished_at DESC, rowid DESC` — `finished_at` is
  second-resolution, so rowid breaks ties in insertion order.
- The DB retains the newest **25** scans; older `scans` rows are pruned after a successful
  `_persist_scan` commit, and `scan_items` follow via `ON DELETE CASCADE`.
- **Foreign keys are enabled per connection.** `PRAGMA foreign_keys` is per-connection and
  defaults to OFF, so `db_conn()` sets it when the connection starts. Without this the
  cascade silently did nothing.
- File-derived scan item ids are derived from a stable hash of the path
  (`stable_path_id`, blake2b over `os.fsencode(path)`), not from a sibling index.
- Scanner ids never use the builtin `hash()` — it is salted per process, so ids changed
  on every run.
- Process execution is **intentionally not implemented**; the execution endpoint returns 501.
- Chat command preview is deterministic, local, no LLM, no OS access, no execution,
  and issues no confirmation token.
- The Ask OpenCleaner UI calls `POST /api/chat/command-preview` through
  `client.previewChatCommand` and never calls `/api/processes/end`.

## SafetyInvariant

- Items classified `unknown` are **report-only**. Uncertainty never becomes "safe".
- `essential` and `blocked` items can never be selected for action.
- Browsers and the Windows shell require **explicit selection** — never chosen automatically.
- Services, startup entries and scheduled tasks are report-only for now.
- ML/intelligence signals may **narrow** an action policy but never widen it.
- The protected registry and action gating can only tighten safety, never loosen it.
- `safe_to_end` and `safe_to_disable_startup` are never granted by the action policy.
- No process kill/suspend/disable execution path exists anywhere in the codebase.
- Preview endpoints must never mutate OS state.
- Chat UI is preview-only; it displays backend warnings/disclaimers and provides no
  execute, kill, suspend, disable, or confirm-action button.

## KnownRisk

- SQLite does not shrink on delete; the DB file plateaus at its high-water mark without `VACUUM`.
- Scan rows written before the stable-id change keep old positional id formats until they
  age out of the 25-scan retention window; ids are not comparable across that boundary.
- `proc-{pid}` ids do not correlate across reboots, so process history cannot be traced over time.
- The Windows intelligence database is sparse compared with real machines.
- Full-repo `ruff check` has pre-existing unrelated errors (unused imports in
  `app/main.py`, `app/pipeline/*`, `app/engine/*`, some tests). Do not fix them incidentally.
- `stable_path_id` does not resolve symlinks by design; a moved file correctly gets a new id.
- `ScanSummary` has no per-scan `duration`/`status` field and `ScanResult` carries no
  `api_version` — flagged in `docs/VERSION_API_CONTRACT_AUDIT.md` as the next v0.1.0/v0.1.1 gap.

## Superseded facts

- ~~`scan_items` is keyed on `id` alone~~ — superseded by the composite key `(scan_id, id)`.
- ~~Large-file ids use the builtin `hash()`~~ — superseded by blake2b via `stable_path_id`.
- ~~File ids carry a sibling index suffix (`dl-report.pdf-3`)~~ — superseded by path-derived hashes.
