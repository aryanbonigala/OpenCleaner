# Process Control Pivot Plan

Status: planning document. Nothing in this file has been implemented yet.

This plan describes the **Process Control MVP**: turning OpenCleaner from a junk-file cleaner
into a chat-driven process/task intelligence and control center. It is written to be executed
by other agents without guessing — file paths, endpoint names, component names, field names,
and tests are spelled out.

Scope guardrail for anyone executing this plan: **do not expand file-deletion work.** The
existing cleanup/quarantine flow stays as-is and becomes a secondary surface.

---

## 1. New product goal

**OpenCleaner is a local-first task manager you can actually understand, plus a safety layer
that stops you from breaking your machine — driven by chat as much as by clicking.**

A normal user opens the app and can answer:

- What is running on my computer right now?
- What does each process / service / startup entry / scheduled task actually do?
- Is it essential, important, non-essential, FPS-relevant, or unknown?
- Is it safe to end, suspend, or disable — and what breaks if I do?
- What can I safely close before gaming?
- What am I never allowed to touch, and why?

### How this differs from a normal system cleaner

| Normal cleaner | OpenCleaner (after pivot) |
|---|---|
| Optimizes for bytes reclaimed | Optimizes for *understanding* and reversible control of running software |
| Deletes files (irreversible-ish) | Suspends/resumes processes (reversible), quarantines files (reversible) |
| Opaque "junk" categories | Per-item plain-English explanation with evidence and confidence |
| Marketing claims ("300% faster") | Measured facts: memory MB, CPU %, known FPS-relevant categories |
| One-shot "Clean" button | Preview → explain → confirm → act → log → undo |
| No refusal model | Hard-blocked classes (OS/security/GPU/audio/network/anti-cheat) that cannot be selected at all |

It also differs from Windows Task Manager in the direction users actually need: Task Manager
tells you `svchost.exe — 84 MB`, but never tells you whether closing it is safe, what it
belongs to, or what breaks.

### Why file cleanup becomes secondary

1. **The value is in the unknown, not the disk.** Users already know what a Downloads folder is;
   they do not know what `nvcontainer.exe` is. Explanation of running software is the scarce good.
2. **Reversibility is better on the process side.** Suspend/resume is fully reversible in-session;
   file deletion is only reversible while quarantine retention holds.
3. **The repo's differentiators already point that way.** `backend/app/engine/protected_registry.py`,
   `backend/data/windows_intelligence.json`, and `backend/app/actions/performance.py` are all
   process/service-shaped assets. The file scanners are the commodity part.
4. **Risk profile.** Expanding deletion increases blast radius; process control with hard
   protection gates and preview-first execution is safer to ship.

Cleanup is **kept**, not removed: same endpoints, same quarantine, demoted to a secondary
"Storage" area of the UI.

---

## 2. Current repo state

### Backend — scanners

| Path | What it does today | Notes for pivot |
|---|---|---|
| `backend/app/scanners/processes.py` | `scan_processes(limit=220)` via `psutil.process_iter`; emits `ScoredItem` with `detail = {pid, memory_mb, cpu_percent, gpu_heavy, suspended, cpu_affinity_count, num_threads, started_ts, uptime_s}` | **No `ppid`, no `username`, no signature/publisher, no elevation/integrity, no per-process grouping.** `_gpu_heuristic` is a crude name-match. |
| `backend/app/scanners/services.py` | Windows: `psutil.win_service_iter()` → `{display_name, start_type, status, username}`. Non-Windows: single stub item | No dependency graph (`sc qc` / `DependOnService`) — needed for dependency warnings. |
| `backend/app/scanners/startup.py` | Registry `Run` keys, Startup folders, macOS LaunchAgents | Reusable as-is. |
| `backend/app/scanners/tasks.py` | `schtasks /query /xml` with namespace-tolerant parse + LIST fallback; `parse_tasks_xml_for_tests` | Reusable as-is. |
| `backend/app/scanners/files.py`, `browser.py`, `scan_limits.py`, `mock_data.py` | Filesystem/browser inventory, bounded walks, mock dataset | Untouched by pivot; mock dataset needs process rows for non-Windows dev. |

### Backend — model, pipeline, engine

| Path | Role |
|---|---|
| `backend/app/models/scan_item.py` | Canonical `ScanItem` (+ `ItemMetrics`, `IntelligenceSnapshot`, `ExplanationBlock`, `Recommendations`, `ProvenanceRecord`), `SCAN_SCHEMA_VERSION = 1` |
| `backend/app/models/enums.py` | `PermissionMode`, `PerformancePreset`, `ItemType`, `RiskBucket` |
| `backend/app/models/schemas.py` | Legacy `ScoredItem` (scanner-facing), API request/response models |
| `backend/app/models/user_settings.py` | `UserSettings` (cleanup mode, risk visibility, scanner toggles, retention, logging) |
| `backend/app/pipeline/normalize.py` | `ScoredItem` → `ScanItem` |
| `backend/app/pipeline/reasoning.py` | `run_reasoning_pipeline`: rules → intelligence → ML (metrics only) → feedback nudge → explanation → `apply_action_gating` |
| `backend/app/pipeline/action_gating.py` | Final authority for `protected` / `cleanup_eligible` / `performance_eligible` |
| `backend/app/pipeline/adapters.py`, `serialize.py` | ScanItem↔ScoredItem adapters; deterministic export ordering |
| `backend/app/engine/rules_engine.py` | Deterministic buckets; `is_critical_process` delegates to protected registry |
| `backend/app/engine/protected_registry.py` | **Hard-deny patterns** (OS/session, AV, anti-cheat, GPU, audio, networking, input, servicing, `steam.exe`), `BROWSER_OR_SHELL_BASE_NAMES`, `DEFAULT_SOFT_SUSPEND_BASE_NAMES`, `_CORE_SERVICE_NAMES`, `suspend_allowed_by_policy()` |
| `backend/app/engine/explain.py` | `explain_item()` → 8-field `ExplainResponse` |
| `backend/app/engine/ml_ranker.py` | Local feature ranking; metrics only, never authorizes actions |

### Backend — services, actions, API

| Path | Role |
|---|---|
| `backend/app/services/scan_service.py` | Runs scanner set per `ScannerToggles`, finalizes items, persists, `latest_scan_from_db()`, `export_canonical_payload()` |
| `backend/app/services/intelligence_service.py` | Exact → alias → conservative fuzzy match against the local encyclopedia |
| `backend/app/services/selection_policy.py` | Backend mirror of frontend cleanup selection rules (`item_type == file_or_folder` only) |
| `backend/app/services/settings_service.py`, `scan_state.py`, `feedback_service.py` | Settings persistence, scan-in-progress lock, feedback nudges |
| `backend/app/actions/performance.py` | `planned_suspend_actions()` (preview, no mutation), `start_session(confirm_apply=True)`, `stop_session()` (resume), `session_snapshot()`, powercfg presets |
| `backend/app/actions/cleanup_preview.py`, `cleanup.py`, `quarantine.py`, `quarantine_retention.py` | File preview/execute/quarantine/retention |
| `backend/app/main.py` | All routes (see below) |
| `backend/app/db.py`, `backend/sql/schema.sql` | SQLite: `settings`, `allowlist`, `blocklist`, `scans`, `scan_items`, `quarantine_entries`, `audit_log`, `user_feedback`, `ml_model_meta` |
| `backend/data/windows_intelligence.json` | 49 entries (42 process / 5 service / 1 startup / 1 task); categories include Windows core, GPU driver, Security, Anticheat, Audio, Game launcher, Cloud sync, Browser, Browser helper |

Existing routes in `backend/app/main.py`:

```
GET  /health                    GET  /api/scan/status        GET/PUT /api/settings
POST /api/settings/reset        GET/POST /api/mode           POST /api/scan
GET  /api/scan/latest           POST /api/explain            POST /api/feedback
GET  /api/metrics               POST /api/cleanup/preview    POST /api/cleanup/execute
GET  /api/quarantine            POST /api/quarantine/restore GET  /api/safety/summary
POST /api/performance/preview   POST /api/performance/start  POST /api/performance/stop
GET  /api/export/report         GET  /api/audit
```

### Frontend

| Path | Role |
|---|---|
| `frontend/src/App.tsx` | Single stateful shell; `View = dashboard \| results \| cleanup_review \| cleanup_summary \| quarantine \| settings` |
| `frontend/src/api.ts` | Typed client + all API types (`ScanItem`, `RiskBucket`, `ExplainResponse`, settings, cleanup, performance) |
| `frontend/src/scanItem.ts` | Field helpers with legacy fallbacks (`itemBucket`, `knownLabel`, `rankGaming`, …) |
| `frontend/src/selection.ts` (+ `selection.test.ts`) | Cleanup selection rules — file-only, mirrors backend `selection_policy.py` |
| `frontend/src/components/Dashboard.tsx` | Cleanup-first copy: "review … move selected files to quarantine" |
| `frontend/src/components/ScanResults.tsx` | Filters default to **files only** (`filter = "files"`, `showCleanupOnly = true`) — processes are effectively invisible |
| `frontend/src/components/FindingCard.tsx`, `FindingDetails.tsx`, `RiskBadge.tsx` | Per-item card, side detail with Explain fields, bucket badge |
| `frontend/src/components/CleanupReview.tsx`, `CleanupProgress.tsx`, `CleanupSummary.tsx`, `QuarantineManager.tsx` | Cleanup flow |
| `frontend/src/components/Settings.tsx` | Settings page |
| `frontend/src/styles.css` | All styling (~9 KB, dark theme) |
| `frontend/package.json` | React 18 + Vite 5 + Tauri 1.6 + recharts + vitest |

### Docs

`README.md` (version-sectioned: v0.4.2 / v0.4.1 / v0.4 / v0.3 / v0.2 + "Roadmap (short)"),
`CHANGELOG.md`, `docs/SCAN_SCHEMA.md`, `docs/SCAN_PIPELINE.md`, `docs/INTELLIGENCE_DATABASE.md`,
`docs/SETTINGS.md`, `docs/PACKAGING.md`, `docs/UI_MOCK_LAYOUT.txt`.

### Safety center

`GET /api/safety/summary` in `backend/app/main.py` returns permission mode, quarantine stats,
performance session snapshot, `protected_pattern_count()`, count of running processes matching
protection, recent audit entries. There is **no frontend page** consuming it today.

---

## 3. What can be reused

Reuse these; do not rewrite.

| Asset | Path | Why it survives the pivot |
|---|---|---|
| Process scanner | `backend/app/scanners/processes.py` | Correct psutil iteration + exception handling; only needs **added fields** (ppid, username, exe signature, integrity) |
| Service scanner | `backend/app/scanners/services.py` | Works; add dependency query later, read-only |
| Startup scanner | `backend/app/scanners/startup.py` | Complete for MVP |
| Task scanner | `backend/app/scanners/tasks.py` | XML parsing + fallback already hardened |
| Canonical model | `backend/app/models/scan_item.py` | Additive fields only (§13) |
| Protected registry | `backend/app/engine/protected_registry.py` | **The core safety asset.** All new gates must call it, never re-implement patterns |
| Action gating | `backend/app/pipeline/action_gating.py` | Extend to also decide `safe_to_end` / `safe_to_suspend` / `action_policy` |
| Intelligence service + DB | `backend/app/services/intelligence_service.py`, `backend/data/windows_intelligence.json` | Vendor/category/impact/warning text feeds `user_visible_summary` and FPS panel |
| Performance preview/start/stop | `backend/app/actions/performance.py` | Preview-first + confirm_apply + rollback is exactly the pattern chat needs |
| Explanation endpoint | `POST /api/explain` + `backend/app/engine/explain.py` | Powers "Explain this process" panel and chat answers |
| Reasoning pipeline | `backend/app/pipeline/reasoning.py` | Stage order and provenance already give us `evidence` + `confidence` for free |
| Audit log | `audit_log` table + `append_audit()` in `backend/app/db.py` | Required logging for every process action |
| Frontend detail components | `frontend/src/components/FindingDetails.tsx`, `RiskBadge.tsx` | Rename/retarget rather than rebuild |
| Settings + permission modes | `backend/app/models/user_settings.py`, `backend/app/services/settings_service.py`, `PermissionMode` | `performance` mode already gates process mutation |
| Frontend selection scaffolding | `frontend/src/selection.ts` + its vitest file | Pattern to copy for process selection (`processSelection.ts`) |

---

## 4. What must be refactored

| Area | Path | Problem | Change |
|---|---|---|---|
| README positioning | `README.md` | Titled around cleaning; v0.2–v0.4.2 sections + "Roadmap (short)" dominate | Rewrite as current-state doc (what it is, architecture, run, safety model, capabilities, limitations, dev setup, testing). No version sections. |
| Changelog vs README duplication | `README.md`, `CHANGELOG.md` | History lives in both | History only in `CHANGELOG.md` |
| Dashboard copy | `frontend/src/components/Dashboard.tsx` | "move selected files to a local quarantine folder" is the headline promise | Becomes system overview (what's running, essential vs non-essential counts, FPS-impacting count) |
| Findings language | `frontend/src/components/FindingCard.tsx`, `ScanResults.tsx`, `App.tsx` | "findings", "cleanup-eligible" framing for all item types | Process surfaces use "running items", "safe to end", "do not touch" |
| Default filtering | `frontend/src/components/ScanResults.tsx` (`filter` default `"files"`, `showCleanupOnly` default `true`) | Processes/services/tasks are filtered out of the default view | Process dashboard becomes the default view; file results move under a "Storage" tab with the same components |
| Cleanup-first navigation | `frontend/src/App.tsx` (`View` union, `<nav>`) | Nav order is dashboard → results → quarantine → settings | Nav becomes System / Processes / Performance / Chat / Storage / Safety / Settings |
| Selection logic | `frontend/src/selection.ts`, `backend/app/services/selection_policy.py` | Hard-codes `item_type === "file_or_folder"` | Keep for files; add sibling process-selection modules rather than overloading these |
| Scanner toggles semantics | `backend/app/services/scan_service.py::_scanners_for_toggles` | Processes are gated behind `toggles.performance`; services+startup share `toggles.startup` | Add explicit `processes` and `services` toggles (additive, default `true`) |
| Risk vocabulary | `backend/app/models/enums.py::RiskBucket` | `safe_to_remove` / `risky_system_critical` is deletion-shaped language for a process UI | Keep `RiskBucket` as-is for storage compatibility; add `ProcessControlCategory` (§10) and map |
| `_gpu_heuristic` | `backend/app/scanners/processes.py` | Name substring match ("chrome", "game") produces false GPU-heavy flags | Demote to a low-confidence hint; FPS panel must rely on intelligence categories first |
| Version-heavy docs | `docs/SCAN_SCHEMA.md`, `docs/SCAN_PIPELINE.md`, `docs/INTELLIGENCE_DATABASE.md`, `docs/SETTINGS.md` | Reference "v0.4+" style milestones in prose | Strip milestone prose; keep schema version **constants** (`SCAN_SCHEMA_VERSION`, `SETTINGS_SCHEMA_VERSION`, intelligence `schema_version`) — they are load-bearing |
| File cleaner prominence | `frontend/src/App.tsx` initial view, `Dashboard.tsx` CTA | "Run scan" implies file scan | "Scan system" produces the process inventory first; storage findings are one tab |

Not refactored (deliberately): cleanup preview/execute/quarantine internals, bounded walk utilities,
ML ranker, quarantine retention.

---

## 5. What is missing

### Backend

1. ~~Process-control metadata block on `ScanItem`~~ — **shipped**: `ScanItem.process_control`
   (`applicable`, `category`, `action_policy`, `safe_to_end`, `safe_to_suspend`,
   `safe_to_disable_startup`, `blocked_reason`, `user_visible_summary`, `fps_impact`,
   `memory_impact`, `cpu_impact`, `confidence`, `evidence`) with inert defaults.
2. A dedicated classifier module — today classification is spread across rules engine + intelligence
   + action gating with a deletion-oriented vocabulary.
3. Process inventory endpoint (`GET /api/processes`) — the UI can only get processes as a side effect
   of a full scan.
4. Process action preview/execute endpoints (end/suspend/resume) separate from performance sessions.
5. Process grouping (parent/child rollup: `chrome.exe` × 14 → one row) — requires `ppid` collection.
6. Process tree / parent-child info: `ppid`, `parent_name`, `children_pids`.
7. Publisher/signature info: Windows Authenticode publisher where available.
8. Integrity / elevation info: whether the process runs elevated / at System integrity (best-effort;
   many will be `unknown` without admin).
9. Service dependency data (`DependOnService` / dependents) for dependency warnings — read-only.
10. FPS optimization recommendation builder (which non-essential items are worth suspending before gaming,
    with expected memory freed — no fabricated FPS numbers).
11. Chat command parser (intent extraction, deterministic, local, no cloud).
12. Chat safety response layer (refusals, "will not touch" lists, confirmation tokens).
13. Confirmation-token store for chat execution (short-lived, single-use, bound to a preview).
14. Audit entries for process actions (`process_end`, `process_suspend`, `process_resume`, `chat_execute`).

### Frontend

15. Process dashboard, process table/cards, process detail panel (currently only file-shaped views).
16. Essential / important / non-essential / FPS / unknown grouping UI.
17. FPS optimizer panel (performance endpoints exist but have **no UI**).
18. Chat command panel with preview → confirm → execute.
19. Safety badges: `SafetyBadge`, `ProtectedItemLock` ("Do not touch" / "Safe to end").
20. Process selection module + tests (`processSelection.ts`).
21. Safety Center page consuming `GET /api/safety/summary`.
22. Live metrics refresh (poll `GET /api/metrics` / `GET /api/processes`) for a "live" system overview.
23. Visual design pass: current `styles.css` is functional-dark, not the intended premium/futuristic feel.

---

## 6. Backend architecture changes

### 6.1 New enum — `backend/app/models/enums.py`

Shipped in `backend/app/models/enums.py`:

```python
class ProcessControlCategory(str, Enum):
    essential = "essential"
    important = "important"
    non_essential = "non_essential"
    gaming_fps_impact = "gaming_fps_impact"
    unknown = "unknown"
    not_applicable = "not_applicable"     # files, browser profiles, duplicates, orphans


class ActionPolicy(str, Enum):
    blocked = "blocked"                                   # hard-protected; never selectable
    report_only = "report_only"                           # display only (default; services/tasks in MVP)
    preview_required = "preview_required"
    explicit_selection_required = "explicit_selection_required"   # browsers/shell/unknown
    allowed_with_confirmation = "allowed_with_confirmation"
    unsupported = "unsupported"
```

`RiskBucket` is **not** renamed (persisted in `scan_items.rule_bucket`, exported in reports).

### 6.2 New fields on `ScanItem` — `backend/app/models/scan_item.py`

All additive, all defaulted, so existing consumers keep working. Shipped:

```python
class ProcessControl(BaseModel):
    applicable: bool = False
    category: ProcessControlCategory = ProcessControlCategory.not_applicable
    action_policy: ActionPolicy = ActionPolicy.report_only
    safe_to_end: bool = False
    safe_to_suspend: bool = False
    safe_to_disable_startup: bool = False
    blocked_reason: str | None = None
    user_visible_summary: str | None = None
    fps_impact: str | None = None       # none | low | medium | high
    memory_impact: str | None = None    # low | medium | high
    cpu_impact: str | None = None       # low | medium | high
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
```

and on `ScanItem`:

```python
process_control: ProcessControl = Field(default_factory=ProcessControl)
```

A `model_validator(mode="after")` sets `applicable=True` + `category=unknown` for
`process` / `service` / `startup_entry` / `scheduled_task` items and leaves an already-classified
block untouched. `SCAN_SCHEMA_VERSION` is now `2`.

Still to add in a later phase (grouping work, §5 item 5): `group_key: str | None`,
`is_group_parent: bool` — either on `ProcessControl` or on the inventory row model.

New scanner facts (kept in `ScanItem.scanner_facts`, no schema change needed):
`ppid`, `parent_name`, `username`, `elevated`, `integrity_level`, `signature_status`,
`signature_publisher`, `child_pids`, `service_depends_on`, `service_dependents`.

### 6.3 New modules

| New file | Contents |
|---|---|
| `backend/app/engine/process_classifier.py` | `classify_process_control(item: ScanItem) -> ProcessControl`. Order: hard-protected registry → intelligence category → intelligence booleans → heuristics → `unknown`. Never returns `safe_to_end=True` for unknown items. |
| `backend/app/engine/process_action_policy.py` | `end_allowed(item)`, `suspend_allowed(item)`, `resume_allowed(item)` → `(bool, reason)`; all delegate to `protected_registry` for hard denies. Single source of truth used by API **and** chat. |
| `backend/app/actions/process_actions.py` | `preview_process_action(pids, action)`, `execute_process_action(preview_id, pids, action, confirm)`; suspend/resume preferred; `end` via `psutil.Process.terminate()` then bounded wait, never `kill()` in MVP. |
| `backend/app/services/process_inventory.py` | Live snapshot (no DB write): scan processes → normalize → classify → group. Used by `GET /api/processes`. |
| `backend/app/services/fps_advisor.py` | `build_fps_plan(items)` → recommended suspend list + total memory that would be freed + explicit "will not touch" list. |
| `backend/app/chat/intent_parser.py` | Deterministic keyword/regex intent extraction → `ChatIntent {intent, targets, scope}`. Intents: `explain_item`, `what_can_i_close`, `optimize_fps`, `why_slow`, `never_touch`, `close_non_essential`, `unsupported`. |
| `backend/app/chat/responder.py` | Intent + inventory → `ChatPreview` (allowed actions, blocked actions with reasons, confirmation token). Never executes. |
| `backend/app/chat/confirmation.py` | In-memory token store: `issue(preview) -> token`, `consume(token) -> preview | None`; TTL 5 min, single use. Mirrors the existing cleanup `preview_id` pattern. |

Pipeline change in `backend/app/pipeline/reasoning.py`: add `stage_process_control` **after**
`stage_intelligence` and **before** `apply_action_gating`; `apply_action_gating` remains the final
authority and may only downgrade (never upgrade) `safe_to_*` flags.

### 6.4 Endpoints (new)

```
GET  /api/processes                 # live inventory, grouped, classified
GET  /api/processes/{pid}           # single process detail + explanation
POST /api/processes/preview-end     # preview end/suspend/resume; never mutates
POST /api/processes/end             # execute; requires preview_id + confirm
POST /api/performance/plan          # FPS plan (recommendations + will-not-touch)
POST /api/chat/command-preview      # NL in → preview + confirmation_token
POST /api/chat/execute-confirmed    # confirmation_token + explicit confirm → execute
```

Existing endpoints kept: `/api/performance/preview|start|stop` (session-level suspend),
`/api/cleanup/*`, `/api/quarantine/*`, `/api/explain`, `/api/safety/summary`, `/api/audit`.
**No cleanup endpoint is removed.** `/api/processes/end` is scoped to individual PIDs;
`/api/performance/start` remains the batch preset path.

Mode gating: `POST /api/processes/end`, `/api/processes/preview-end` (execute path), and
`/api/chat/execute-confirmed` require `PermissionMode.performance`, matching how
`perf_start` already gates. All `GET` endpoints and previews work in `read_only`.

---

## 7. Frontend architecture changes

New/changed components:

| Path | Role |
|---|---|
| `frontend/src/components/ProcessDashboard.tsx` | Default view: live overview (CPU/RAM), category counts, entry to all process surfaces |
| `frontend/src/components/ProcessTable.tsx` | Dense sortable table: name, category, memory, CPU, safety badge, action |
| `frontend/src/components/ProcessCard.tsx` | Grouped card view (one card per `group_key`, e.g. Chrome ×14) |
| `frontend/src/components/ProcessDetails.tsx` | Side panel: "Explain this process" (reuses `POST /api/explain`), evidence, what could break, publisher, parent/child |
| `frontend/src/components/ProcessGroupSection.tsx` | Essential / Important / Non-essential / FPS / Unknown sections |
| `frontend/src/components/FpsOptimizerPanel.tsx` | Plan from `POST /api/performance/plan`; preview → start → stop (resume) |
| `frontend/src/components/ChatCommandPanel.tsx` | Chat input, response, allowed/blocked lists, confirm-to-execute |
| `frontend/src/components/SafetyBadge.tsx` | "Safe to end" / "Confirm first" / "Do not touch" / "Unknown" |
| `frontend/src/components/ProtectedItemLock.tsx` | Lock icon + reason tooltip for `action_policy == blocked` |
| `frontend/src/components/SystemOverview.tsx` | Live CPU/RAM strip, polls `GET /api/metrics` |
| `frontend/src/components/SafetyCenter.tsx` | Consumes `GET /api/safety/summary` + `GET /api/audit` |
| `frontend/src/processSelection.ts` (+ `.test.ts`) | Selection rules for processes; mirrors backend `process_action_policy.py` |
| `frontend/src/processItem.ts` | Helpers over `process_control` with safe fallbacks (same pattern as `scanItem.ts`) |
| `frontend/src/api.ts` | New types (`ProcessControl`, `ProcessRow`, `ProcessPreview`, `ChatPreview`, `FpsPlan`) + client methods |
| `frontend/src/App.tsx` | `View` becomes `system \| processes \| performance \| chat \| storage \| safety \| settings`; default `system` |
| `frontend/src/styles.css` | Design pass (see below) |

Kept and demoted (unchanged code, moved under the Storage tab): `ScanResults.tsx`,
`FindingCard.tsx`, `CleanupReview.tsx`, `CleanupProgress.tsx`, `CleanupSummary.tsx`,
`QuarantineManager.tsx`. `FindingDetails.tsx` is generalized into `ProcessDetails.tsx` by
extracting its Explain-rendering block; the file stays for storage items.

Visual direction (enforced in review, not just aspirational):

- Dark, high-contrast, single accent; typography-led hierarchy; generous spacing; no gradients-as-decoration.
- Numbers are measured facts (MB, %, counts). **No** "boost 300%", no gauges implying speed gains.
- Motion: ≤150 ms transitions on state change only; no looping animation.
- Danger is quiet, not red-everywhere: blocked items are visually *locked*, not alarming.
- Accessibility: badge meaning never conveyed by color alone; every badge has text.

---

## 8. New UI flow

```
Open app
  → System overview loads (GET /api/processes, GET /api/metrics)
  → Items grouped: Essential · Important · Non-essential · FPS-impacting · Unknown
  → User either clicks an item OR types in the chat panel
       ├─ click  → ProcessDetails: what it is, who made it, impact, what breaks, evidence, confidence
       └─ chat   → POST /api/chat/command-preview → answer + allowed actions + blocked actions
  → Any action shows a PREVIEW first (POST /api/processes/preview-end or /api/performance/plan)
       ├─ blocked items are listed with blocked_reason and cannot be selected
       └─ unknown items are shown but unchecked by default
  → User confirms explicitly (checkbox + button, both required)
  → Execute (POST /api/processes/end or /api/chat/execute-confirmed or /api/performance/start)
  → Result written to audit_log; UI shows what happened and what was skipped
  → Undo: suspended items resume via POST /api/performance/stop or /api/processes/end {action:"resume"}
           (ended processes cannot be undone — the UI must say so *before* the confirm click)
```

---

## 9. Chat interface direction

Chat is a **planner with a refusal model**, not an executor.

Supported example inputs and expected behavior:

| Input | Intent | Response |
|---|---|---|
| "What can I close before gaming?" | `what_can_i_close` | Lists non-essential + gaming-impact items with memory freed; produces a preview; nothing runs |
| "Why is my computer slow?" | `why_slow` | Top memory/CPU consumers with categories and plain-English notes; no action offered for essential items |
| "What is this process?" | `explain_item` | Calls the same explanation path as `POST /api/explain` |
| "Close everything non-essential." | `close_non_essential` | Preview with allowed list + blocked list + unknown items **excluded**; requires confirmation token |
| "Optimize for FPS." | `optimize_fps` | FPS plan preview (suspend, not end); explicit "will not touch" list |
| "What should I never touch?" | `never_touch` | Essential/blocked inventory with reasons; no actions at all |
| "Kill lsass.exe" | any | Hard refusal with reason, no preview, no token |

Hard rules:

1. Chat never mutates state. Execution only via `POST /api/chat/execute-confirmed` with a valid,
   unexpired, single-use confirmation token issued by a preview.
2. Every preview includes `will_not_touch: [{name, reason}]`.
3. Essential/protected items are refused, never merely deselected.
4. Unknown items are never included in a bulk action; they are listed as "needs your review".
5. Confirmation is a separate user act (explicit UI confirm), not a phrase in the chat message —
   "yes do it" in the same turn does not authorize execution.
6. Unrecognized intent → say so plainly and offer the manual surface. No guessing.
7. The parser is local and deterministic (`backend/app/chat/intent_parser.py`). If an LLM is added
   later it may only *rank/word* results; the allowed/blocked decision stays in
   `process_action_policy.py`.

---

## 10. Process classification model

| Category | Meaning | Selectable? |
|---|---|---|
| `essential` | OS core, security/AV, anti-cheat, GPU driver, audio, networking, input stack | Never |
| `important` | Usually leave running; stopping breaks useful functionality (sync clients mid-sync, VPN, peripheral utilities, main game client) | Explicit selection + confirmation |
| `non_essential` | Generally safe to suspend/close (updaters, helper trays, launcher web helpers) | Default-selectable in previews |
| `gaming_fps_impact` | Affects FPS/frametime/memory: overlays, recorders, sync, launchers, browsers | Explicit selection; suspend preferred |
| `unknown` | Not enough confidence | Never auto-selected, never in bulk actions |
| `not_applicable` | Files, browser profiles, duplicates, orphans — no process control | No process action |

Mapping from the existing `RiskBucket` (kept for storage/report compatibility):

| Source signal | → category |
|---|---|
| `is_hard_protected_process()` / `is_protected_windows_service()` true | `essential` |
| `RiskBucket.risky_system_critical` | `essential` |
| Intelligence category ∈ {Windows core, Security, Anticheat, GPU driver, Audio} | `essential` |
| Intelligence `safe_to_stop == False` (and not essential) | `important` |
| Intelligence category ∈ {Game launcher, Browser, Browser helper, Media, Cloud sync} or intelligence `gaming_impact` ∈ {medium, high} | `gaming_fps_impact` |
| Intelligence `safe_to_stop == True` + `RiskBucket.safe_to_remove/probably_safe` | `non_essential` |
| Intelligence `known == False` or `RiskBucket.unknown` | `unknown` |

`gaming_fps_impact` overlays rather than replaces: an item can be `gaming_fps_impact` **and** treated as
`important` for safety. Implementation: category is the safety bucket; `fps_impact` is the separate
field used by the FPS panel. When in doubt, classify **more** conservatively.

---

## 11. Safety gates

Enforced in `backend/app/engine/process_action_policy.py` and mirrored (not re-derived) in
`frontend/src/processSelection.ts`:

1. `essential` / `action_policy == blocked` items cannot be selected for end/suspend/disable — API returns
   `blocked` in preview and `403` if forced.
2. `unknown` items are never selected by default and never included in bulk/chat actions.
3. Browser and shell processes (`BROWSER_OR_SHELL_BASE_NAMES`) require explicit per-item selection —
   reuse `suspend_allowed_by_policy(..., explicit_target_basenames=...)`.
4. Security, anti-cheat, GPU driver, audio, networking, and core OS processes are hard-blocked via
   `is_hard_protected_process()`. New code must not maintain a second pattern list.
5. Every end/suspend/disable requires a preview first; execute without a matching `preview_id` → `400`.
6. **Services: report-only in this MVP.** No start-type changes, no stop/disable. `/api/processes/*`
   rejects `item_type == service`. Same for scheduled tasks and startup entries (read + explain only).
7. No new file-deletion capability in this work.
8. No automatic process killing from chat, ever — token + explicit confirm required.
9. Every attempted and completed action is written to `audit_log` (including refusals, with reason).
10. Suspend/resume is preferred over end. The UI offers "Suspend" as the primary action and "End" as
    secondary with an explicit "this cannot be undone" warning.
11. Preview results expire (5 min for chat tokens, 15 min for process previews) and are single-use.
12. Elevation failures degrade gracefully: item is marked `blocked_reason: "requires elevation"`,
    never silently retried.

---

## 12. API changes

### `GET /api/processes`

Response:

```json
{
  "generated_at": "2026-01-01T00:00:00+00:00",
  "platform": "Windows 11",
  "totals": {"processes": 214, "groups": 96,
             "essential": 41, "important": 22, "non_essential": 18,
             "gaming_fps_impact": 9, "unknown": 6},
  "system": {"cpu_percent": 12.4, "memory": {"total_gb": 32.0, "used_gb": 13.1, "percent": 41.0}},
  "items": [
    {
      "id": "proc-9134",
      "pid": 9134,
      "ppid": 812,
      "parent_name": "explorer.exe",
      "display_name": "Discord",
      "raw_name": "Discord.exe",
      "path": "C:\\Users\\x\\AppData\\Local\\Discord\\app-1.0\\Discord.exe",
      "vendor": "Discord Inc.",
      "signature_status": "signed",
      "signature_publisher": "Discord Inc.",
      "elevated": false,
      "integrity_level": "medium",
      "group_key": "discord.exe",
      "is_group_parent": true,
      "group_child_count": 4,
      "metrics": {"memory_mb": 512.4, "cpu_percent": 1.2},
      "process_control": {
        "applicable": true,
        "category": "gaming_fps_impact",
        "safe_to_end": true,
        "safe_to_suspend": true,
        "safe_to_disable_startup": true,
        "action_policy": "allowed_with_confirmation",
        "blocked_reason": null,
        "user_visible_summary": "Chat and voice app. Its overlay can cost a few FPS in games.",
        "fps_impact": "medium",
        "memory_impact": "high",
        "cpu_impact": "low",
        "confidence": 0.86,
        "evidence": ["intelligence:Discord", "category:Communication", "metrics:memory_mb=512"]
      }
    }
  ]
}
```

### `GET /api/processes/{pid}`

`{ "item": <ProcessRow>, "explanation": <ExplainResponse>, "children": [<ProcessRow>], "warnings": [] }`

### `POST /api/processes/preview-end`

Request: `{ "action": "suspend" | "resume" | "end", "pids": [9134, 9140], "explicit_targets": ["discord.exe"] }`

Response:

```json
{
  "preview_id": "pp_5f2c…",
  "action": "suspend",
  "expires_at": "2026-01-01T00:15:00+00:00",
  "allowed": [{"pid": 9134, "name": "Discord.exe", "reason": "non-essential, explicitly selected",
               "reversible": true, "memory_mb": 512.4}],
  "blocked": [{"pid": 812, "name": "nvcontainer.exe",
               "blocked_reason": "hard-protected (GPU driver stack)"}],
  "needs_review": [{"pid": 4410, "name": "abcxyz.exe", "reason": "unknown item — not auto-selected"}],
  "estimated_memory_freed_mb": 512.4,
  "disclaimer": "Preview only. Nothing has been changed."
}
```

### `POST /api/processes/end`

Request: `{ "preview_id": "pp_5f2c…", "action": "suspend", "pids": [9134], "confirm": true }`
(`pids` must match the preview's `allowed` set exactly; otherwise `400`.)

Response: `{ "action": "suspend", "succeeded": [9134], "failed": [], "skipped": [], "audit_id": 412, "reversible": true }`

### `POST /api/performance/plan`

Request: `{ "preset": "max_fps", "include_browsers": false }`
Response: `{ "plan_id": "fp_…", "recommended": [ … ], "will_not_touch": [{"name":"EasyAntiCheat.exe","reason":"anti-cheat — blocked"}], "estimated_memory_freed_mb": 1840.0, "notes": ["Suspend is reversible via Stop."] }`

### `POST /api/chat/command-preview`

Request: `{ "message": "what can I close before gaming?" }`

Response:

```json
{
  "intent": "what_can_i_close",
  "answer": "You can safely suspend 6 background apps, freeing about 1.8 GB. I will not touch anti-cheat, GPU, audio, or security software.",
  "allowed_actions": [{"action": "suspend", "pid": 9134, "name": "Discord.exe", "reason": "non-essential overlay"}],
  "blocked_actions": [{"name": "EasyAntiCheat.exe", "reason": "anti-cheat — ending it can flag or crash your game"}],
  "needs_review": [{"name": "abcxyz.exe", "reason": "unknown publisher"}],
  "requires_confirmation": true,
  "confirmation_token": "ct_9ab…",
  "expires_at": "2026-01-01T00:05:00+00:00",
  "executed": false
}
```

Refusal case: `{"intent": "unsupported", "answer": "I won't end lsass.exe — Windows sign-in and security depend on it.", "allowed_actions": [], "requires_confirmation": false, "confirmation_token": null, "executed": false}`

### `POST /api/chat/execute-confirmed`

Request: `{ "confirmation_token": "ct_9ab…", "confirm": true, "pids": [9134] }`
Response: same shape as `/api/processes/end` plus `"intent"`. Token invalid/expired/reused → `400`.

---

## 13. Data model changes

Additive-first. Existing consumers (`frontend/src/scanItem.ts`, `docs/SCAN_SCHEMA.md`,
`/api/export/report`, stored `scan_items.detail_json`) must keep working.

1. **`ScanItem.process_control: ProcessControl`** (defaulted) — **shipped**. Old stored payloads
   deserialize unchanged and get inert defaults (`scan_item_from_stored_payload` in
   `backend/app/pipeline/reasoning.py` needed no migration).
2. **`SCAN_SCHEMA_VERSION: 1 → 2`** in `backend/app/models/scan_item.py` — **shipped**. Readers
   should treat a missing or default `process_control` as "not classified".
3. **`ScannerToggles`**: add `processes: bool = True`, `services: bool = True`.
   `SETTINGS_SCHEMA_VERSION: 1 → 2`; `settings_service.load_settings()` fills defaults for
   rows written under version 1 (no destructive migration).
4. **SQLite**: no table changes required — `scan_items.detail_json` carries the new block.
   Add one optional index if process filtering gets slow:
   `CREATE INDEX IF NOT EXISTS idx_scan_items_name ON scan_items(name);`
5. **Audit actions** (new values in the existing `audit_log.action` text column, no DDL):
   `process_preview`, `process_suspend`, `process_resume`, `process_end`, `process_action_blocked`,
   `chat_preview`, `chat_execute`, `chat_refused`.
6. **Intelligence DB** (`backend/data/windows_intelligence.json`): optional per-entry
   `process_control_category` (values from `ProcessControlCategory`) and `fps_impact` fields;
   `schema_version: 1 → 2`.
   `intelligence_service.py` must tolerate both (absent → derive from category map in §10).
7. **No renames.** `RiskBucket`, `cleanup_eligible`, and `performance_eligible` keep their names.
   If a later phase wants `performance_eligible` → `suspend_eligible`, that requires: emit both keys
   for one release, update `frontend/src/api.ts` + `scanItem.ts` fallbacks, update
   `docs/SCAN_SCHEMA.md`, then drop the old key — out of scope for this MVP.

---

## 14. Tests needed

### Backend — `backend/tests/`

| File | Test |
|---|---|
| `test_process_classifier.py` | `test_essential_process_blocked` — `lsass.exe` → `essential`, `action_policy == blocked`, `safe_to_end is False` |
| | `test_security_process_blocked` — `MsMpEng.exe` blocked |
| | `test_gpu_audio_network_processes_blocked` — `nvcontainer.exe`, `audiodg.exe`, `wlanext.exe` all blocked |
| | `test_anticheat_blocked` — `EasyAntiCheat.exe` blocked |
| | `test_unknown_process_not_auto_selectable` — unknown → `unknown`, `safe_to_end is False`, excluded from default selection |
| | `test_known_non_essential_is_suspendable` — e.g. `OneDrive.exe` → `safe_to_suspend is True` |
| | `test_classifier_never_upgrades_protected_item` — intelligence claiming `safe_to_stop=True` cannot unblock a hard-protected name |
| `test_process_actions.py` | `test_browser_requires_explicit_selection` — `chrome.exe` blocked without explicit target, allowed with |
| | `test_process_end_requires_preview` — execute without `preview_id` → 400 |
| | `test_process_execute_rejects_pid_not_in_preview` → 400 |
| | `test_preview_does_not_mutate_state` — `psutil.Process.suspend` patched, asserted never called |
| | `test_preview_expires` — expired `preview_id` → 400 |
| | `test_service_disable_is_report_only` — service target → 400/`report_only` |
| | `test_action_requires_performance_mode` — `read_only` mode execute → 403 |
| | `test_every_action_is_audited` — audit row written for success, failure, and refusal |
| `test_performance_guard.py` (extend existing) | `test_performance_preview_does_not_mutate_state`; `test_fps_plan_excludes_protected` |
| `test_chat_commands.py` | `test_chat_preview_refuses_dangerous_action` — "kill lsass" → no token, `executed is False` |
| | `test_chat_does_not_execute_without_confirmation` — preview never suspends |
| | `test_chat_token_single_use` — reuse → 400 |
| | `test_chat_token_expiry` → 400 |
| | `test_chat_excludes_unknown_from_bulk` — "close everything non-essential" leaves unknown in `needs_review` |
| | `test_chat_lists_will_not_touch` — non-empty blocked list on gaming intent |
| | `test_chat_unsupported_intent_is_honest` — no fabricated action |
| `test_process_inventory.py` | `test_inventory_groups_by_group_key`; `test_inventory_has_no_side_effects`; `test_inventory_handles_access_denied` |
| `test_pipeline.py` (extend) | `test_process_control_block_present_for_processes`; `test_missing_process_control_deserializes` (schema v1 payload) |

### Frontend — `frontend/src/`

| File | Test |
|---|---|
| `ProcessDashboard.test.tsx` | renders category sections with counts from a fixture |
| `processSelection.test.ts` | essential item not selectable; unknown not selected by default; browser needs explicit selection; blocked reason surfaced |
| `SafetyBadge.test.tsx` | badge text matches `action_policy` (not color-only) |
| `ProtectedItemLock.test.tsx` | lock renders with `blocked_reason` text for essential items |
| `FpsOptimizerPanel.test.tsx` | shows recommendations and a non-empty "will not touch" list; start disabled until preview loaded |
| `ChatCommandPanel.test.tsx` | preview shows allowed + blocked; execute button disabled until confirm checkbox checked; refusal renders with no execute button |
| `ProcessTable.test.tsx` | protected row's checkbox is disabled |

Existing tests must keep passing unchanged: `test_pipeline.py`, `test_intelligence.py`,
`test_cleanup_preview.py`, `test_user_settings.py`, `test_rules.py`, `test_fs_and_tasks.py`,
`frontend/src/selection.test.ts`.

Note: the frontend currently has vitest but no DOM testing library. Phase E adds
`@testing-library/react` + `jsdom` as devDependencies (required for component tests).

---

## 15. Manual QA checklist (Windows)

Environment matrix: run the full list twice — once as a **standard user**, once as **administrator**.

Preconditions to have running: Chrome or Edge (with helper processes), Discord, Steam,
OneDrive, a game launcher (Epic/Battle.net), a security/AV product, GPU driver processes
(`nvcontainer.exe` / AMD equivalents), Windows audio (`audiodg.exe`), and one deliberately
unknown test process (a renamed copy of a harmless console app).

- [ ] App starts; system overview shows CPU/RAM and a non-zero process count
- [ ] Every category section is populated; counts sum to the total
- [ ] Chrome/Edge helper processes are grouped under one parent row
- [ ] Discord shows as gaming-impact with an overlay note
- [ ] Steam client shows as protected/essential (matches `^steam\.exe$` rule)
- [ ] OneDrive shows as non-essential/important with a sync warning
- [ ] AV/security process shows a lock badge and cannot be checked
- [ ] GPU driver process shows a lock badge and cannot be checked
- [ ] Audio service/process shows a lock badge and cannot be checked
- [ ] Unknown test process appears in Unknown, unchecked, and is excluded from bulk actions
- [ ] Clicking any item opens the detail panel with explanation, publisher, evidence, confidence
- [ ] Attempting to end a protected process (via table and via chat) is refused with a clear reason
- [ ] Preview for a safe process lists it under allowed with expected memory freed
- [ ] Execute is disabled until the confirm checkbox is ticked
- [ ] Suspend a safe process → app reflects suspended state → Resume restores it → app is usable again
- [ ] End a safe process → warning says it cannot be undone before the click
- [ ] FPS panel plan lists recommendations and a non-empty "will not touch" list
- [ ] FPS start → game/app still launches and audio still works → stop resumes everything
- [ ] Chat: "what can I close before gaming?" returns a preview, changes nothing
- [ ] Chat: "close everything non-essential" excludes unknown items
- [ ] Chat: "kill lsass.exe" refuses with an explanation and offers no execute button
- [ ] Standard user: elevation-required actions show "requires elevation", never a silent failure
- [ ] Audit log (`GET /api/audit` / Safety Center) contains every attempt, including refusals
- [ ] Storage tab still runs the existing file scan/preview/quarantine/restore flow
- [ ] Kill the backend mid-suspend, restart it: suspended PIDs are reported so the user can resume

---

## 16. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **False-positive classification** (safe label on something important) | Conservative default: `unknown` unless intelligence or rules match. Show `confidence` + `evidence` in the UI. Prefer suspend over end. |
| **Breaking audio / network / GPU / security** | Hard-deny list in `protected_registry.py` is the single gate; new code calls it rather than duplicating. Tests assert each family stays blocked. |
| **Killing anti-cheat → game crash or account flag** | Anti-cheat patterns are hard-blocked, refused in chat, and called out by name in the FPS panel's "will not touch" list. |
| **Malware masquerading as a legitimate process name** | Never claim safety from name alone: show path, publisher/signature status, and mark unsigned/odd-path items as `unknown`. OpenCleaner explicitly is not an AV — say so in the UI. |
| **Permissions / elevation** | Best-effort collection; missing data → `unknown` and `blocked_reason: "requires elevation"`. No silent retries, no auto-elevation prompts. |
| **Users misunderstanding "safe"** | Badge text is action-scoped ("Safe to suspend — reversible"), never a bare "Safe". Ending shows an explicit irreversibility warning. |
| **Chat overreach** | Deterministic local intent parser; policy decisions live in `process_action_policy.py`, not in the parser; token + explicit UI confirm required; unsupported intents say so. |
| **UI making dangerous actions too easy** | Suspend is primary, End is secondary; bulk actions exclude unknown; blocked items are non-interactive; two-step confirm on every mutation. |
| **Preview/execute drift** (system changed between preview and execute) | Re-validate PIDs *and* process names at execute time; a PID whose name changed is skipped and reported. |
| **Scope creep back into file deletion** | This plan adds no deletion capability; Phase gates below do not touch `cleanup.py` / `quarantine.py`. |

---

## 17. Phased implementation checklist

No version numbers. Phases are ordered; parallelism is noted per phase.

### Phase A — Repo cleanup and documentation pivot

- **Files:** `README.md`, `CHANGELOG.md`, `docs/SCAN_SCHEMA.md`, `docs/SCAN_PIPELINE.md`,
  `docs/INTELLIGENCE_DATABASE.md`, `docs/SETTINGS.md`, new `docs/PRODUCT_DIRECTION.md`,
  new `docs/SAFETY_MODEL.md`
- **Deliverables:** README rewritten as current-state (what it is, problem, architecture, run,
  safety model, capabilities, limitations, dev setup, testing); all `v0.x` sections and the
  "Roadmap (short)" block removed; history consolidated in `CHANGELOG.md`; version *constants*
  (`SCAN_SCHEMA_VERSION`, `SETTINGS_SCHEMA_VERSION`, `backend/app/version.py`, intelligence
  `schema_version`, `/health` fields) left untouched
- **Tests:** none (docs only); `pytest` and `npm run build` must still pass
- **Gate:** no `v0.` heading remains in `README.md`/`docs/` (`grep -rn "^## v0\." README.md docs/`);
  every path referenced in README exists
- **Parallel:** yes — independent of all code phases

### Phase B — Backend process-control schema — **done**

Shipped: enums + `ProcessControl` block + `SCAN_SCHEMA_VERSION = 2` + mirrored TS types +
`backend/tests/test_process_control_schema.py`. Scanner toggles (`processes`, `services`) and
`SETTINGS_SCHEMA_VERSION` are **not** done — they move into Phase C or D.

- **Files:** `backend/app/models/enums.py`, `backend/app/models/scan_item.py`,
  `backend/app/models/user_settings.py`, `backend/app/pipeline/serialize.py`,
  `frontend/src/api.ts` (types only), `docs/SCAN_SCHEMA.md`
- **Deliverables:** `ProcessControlCategory`, `ActionPolicy`, `ProcessControl`,
  `ScanItem.process_control`, `SCAN_SCHEMA_VERSION = 2`, new scanner toggles,
  `SETTINGS_SCHEMA_VERSION = 2` with default-filling load
- **Tests:** `test_pipeline.py::test_missing_process_control_deserializes`;
  `test_user_settings.py` extended for new toggle defaults
- **Gate:** full existing suite green; a schema-v1 stored payload still loads
- **Parallel:** with Phase A

### Phase C — Process classification and protected gates

- **Files:** new `backend/app/engine/process_classifier.py`, new
  `backend/app/engine/process_action_policy.py`, `backend/app/pipeline/reasoning.py`,
  `backend/app/pipeline/action_gating.py`, `backend/app/scanners/processes.py`
  (add `ppid`, `parent_name`, `username`, `elevated`, `integrity_level`, `signature_status`,
  `signature_publisher`, `child_pids`), `backend/data/windows_intelligence.json` (optional new fields)
- **Deliverables:** classification for every process/service/startup/task item; policy functions used
  by everything downstream; `blocked_reason` populated
- **Tests:** all of `test_process_classifier.py`
- **Gate:** every essential family (OS, security, anti-cheat, GPU, audio, network, input) blocked in
  tests; unknown never `safe_to_end`
- **Parallel:** depends on B; scanner-field work can run alongside classifier work

### Phase D — Process-control API (inventory + preview)

- **Files:** new `backend/app/services/process_inventory.py`, new
  `backend/app/actions/process_actions.py` (preview path only), `backend/app/main.py`,
  `backend/app/models/schemas.py`
- **Deliverables:** `GET /api/processes`, `GET /api/processes/{pid}`, `POST /api/processes/preview-end`
  (preview only — execute returns 501 until Phase H)
- **Tests:** `test_process_inventory.py`; preview tests in `test_process_actions.py`
- **Gate:** preview provably mutates nothing (patched psutil asserts); protected items always land in `blocked`
- **Parallel:** depends on C

### Phase E — Frontend process dashboard

- **Files:** `frontend/src/App.tsx`, `frontend/src/api.ts`, new `frontend/src/processItem.ts`,
  new `frontend/src/processSelection.ts`, new components `ProcessDashboard.tsx`, `ProcessTable.tsx`,
  `ProcessCard.tsx`, `ProcessDetails.tsx`, `ProcessGroupSection.tsx`, `SystemOverview.tsx`,
  `SafetyBadge.tsx`, `ProtectedItemLock.tsx`, `frontend/src/styles.css`,
  `frontend/package.json` (add `@testing-library/react`, `jsdom`)
- **Deliverables:** default view is the process dashboard; storage/cleanup moved to a Storage tab with
  existing components untouched; design pass per §7
- **Tests:** `ProcessDashboard.test.tsx`, `processSelection.test.ts`, `SafetyBadge.test.tsx`,
  `ProtectedItemLock.test.tsx`, `ProcessTable.test.tsx`
- **Gate:** `npm run build` (tsc) + `npm run test` green; existing cleanup flow still reachable and working
- **Parallel:** can start against a fixture once D's response shape is frozen; UI-design work parallel to logic

### Phase F — FPS optimization panel

- **Files:** new `backend/app/services/fps_advisor.py`, `backend/app/main.py`
  (`POST /api/performance/plan`), new `frontend/src/components/FpsOptimizerPanel.tsx`,
  `frontend/src/api.ts`
- **Deliverables:** plan endpoint + panel wired to existing `/api/performance/preview|start|stop`;
  "will not touch" list always shown; no fabricated FPS gain numbers
- **Tests:** `test_performance_guard.py::test_fps_plan_excludes_protected`; `FpsOptimizerPanel.test.tsx`
- **Gate:** manual QA "FPS start → audio/game fine → stop resumes"
- **Parallel:** depends on D + E

### Phase G — Chat command preview

- **Files:** new `backend/app/chat/intent_parser.py`, `responder.py`, `confirmation.py`,
  `backend/app/main.py` (`POST /api/chat/command-preview`), new
  `frontend/src/components/ChatCommandPanel.tsx`, `frontend/src/api.ts`
- **Deliverables:** all six example intents + refusal path; preview-only (no execute endpoint yet)
- **Tests:** `test_chat_commands.py` (preview/refusal/unknown-exclusion cases); `ChatCommandPanel.test.tsx`
- **Gate:** no code path from chat reaches `psutil` mutation methods (assert via patched psutil in tests)
- **Parallel:** depends on D; independent of F

### Phase H — Safe execute and rollback

- **Files:** `backend/app/actions/process_actions.py` (execute path), `backend/app/main.py`
  (`POST /api/processes/end`, `POST /api/chat/execute-confirmed`), `backend/app/db.py`
  (audit action names), `frontend/src/components/ProcessTable.tsx`, `ChatCommandPanel.tsx`,
  new `frontend/src/components/SafetyCenter.tsx`
- **Deliverables:** preview-bound execution, resume/undo for suspends, irreversibility warning for end,
  audit rows for every attempt and refusal, Safety Center page over `/api/safety/summary` + `/api/audit`
- **Tests:** remaining `test_process_actions.py` + `test_chat_commands.py` execution/token tests
- **Gate:** execute impossible without preview/token; every action audited; `read_only` mode returns 403
- **Parallel:** depends on D, G

### Phase I — Testing and manual QA

- **Files:** `backend/tests/*`, `frontend/src/*.test.tsx`, `docs/PROCESS_CONTROL_ARCHITECTURE.md`
  (final as-built notes), `CHANGELOG.md`
- **Deliverables:** full suites green; §15 checklist executed on a real Windows machine (standard +
  admin); architecture doc reflecting what actually shipped
- **Tests:** whole suite, both stacks
- **Gate:** every §15 box ticked or explicitly waived with a reason recorded in the doc
- **Parallel:** no — final phase
