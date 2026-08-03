# Version / API Contract Audit — v0.1.0 CoreScanMVPFreeze & v0.1.1 APIContractLock

Audited against commit `018f09b`. Read-only audit; no code changed.

**Update:** the "Recommended next implementation task" below has been implemented.
`ScanResult` now carries `api_version` (defaults to `API_VERSION`), and `ScanSummary`
now carries `started_at`, `finished_at`, `duration_ms`, and `status`
(`"success" | "partial_success" | "failed"`, derived from `scanner_warnings`;
`"failed"` remains reserved — no code path returns a `ScanResult` on total scan
failure). See `backend/tests/test_scan_response_contract.py`.

**Update 2:** the v0.1.1 schema-drift gap below has been closed.
`backend/tests/test_scan_response_contract.py::test_scan_response_shape_matches_frontend_contract`
pins the exact top-level `ScanResult` keys, the `summary` keys, and representative
`items[0]` keys (plus contract-critical field types) against what
`frontend/src/api.ts` declares; `test_frontend_api_ts_declares_contract_fields` is a
narrow text smoke that fails if `api.ts` drops one of those field names. Removing or
renaming a contract-critical field now fails a test instead of only manual review.

## Findings

1. **Central version constant** — Yes. `backend/app/version.py` defines `APP_VERSION`
   (`"0.4.2_SettingsAndSafetyPreferences"`) and `API_VERSION` (`"0.4.2"`), imported into
   `main.py` and used for both the FastAPI app title/version and `/health`.
2. **`/health` endpoint** — Exists (`main.py:81`). Returns `status`, `component`, `version`
   (APP_VERSION), `api_version` (API_VERSION), and `scan_in_progress`. No explicit
   `"stage"` field, but the descriptive `version` string doubles as a stage label
   (`0.4.2_SettingsAndSafetyPreferences`).
3. **Scan response shape** — `ScanResult` (`schemas.py`) = `{summary, items}`.
   `ScanSummary` includes `scan_id`, `scan_schema_version`, `platform`, `mode`,
   `items_count`, `buckets`, `disk_usage_sample`, `generated_at`, `scanner_warnings`.
   No top-level API version field on the scan response itself and no `duration`/
   `status` field — `generated_at` exists but there's no scan start/finish timing or
   explicit success/failure status per scan.
4. **Normalized scanner outer shape** — Yes. Every scanner returns `list[ScoredItem]`;
   these get normalized to canonical `ScanItem` (schema version 2) via
   `normalize_scored_item` + `run_reasoning_pipeline` before persistence/API exposure.
   One canonical shape at the API boundary.
5. **Scanner read-only status** — Confirmed read-only. `files.py`, `browser.py`,
   `startup.py` only call `os.stat`/`Path` walks/hashing. `tasks.py` only shells out to
   `schtasks /query` (query, not mutate). Grep for
   `os.remove|os.unlink|shutil.rmtree|.kill(|.terminate(|.suspend(|subprocess.run|Popen`
   across `backend/app/scanners/` found only the two read-only `schtasks /query` calls.
   No mutation path exists inside any scanner.
6. **Per-scanner error isolation** — Yes. `scan_service._collect_raw_scored` wraps each
   scanner call in its own `try/except Exception`, appending a `warnings` entry per
   failed scanner (`f"Scanner "{label}" did not complete: {exc}"`) rather than aborting
   the whole scan.
7. **Frontend/backend schema drift** — `frontend/src/api.ts` mirrors `ScanItem`,
   `ScanSummary`, `ProcessControl`, etc. field-for-field against `schemas.py` /
   `scan_item.py`. No drift found in the reviewed surface. One gap: `api.ts`'s
   `client.health()` return type doesn't declare a `component` or `stage`-shaped field
   (only `status/version/api_version/scan_in_progress`), which is a harmless
   under-typing, not a runtime mismatch.

## Already stronger than roadmap expectations

- Composite `(scan_id, id)` primary key + `assert_unique_scan_item_ids` fail loudly on
  id collisions before any INSERT — solid contract guarantee not usually expected this
  early.
- `scan_schema_version` (`SCAN_SCHEMA_VERSION = 2`) is already versioned independently
  of `API_VERSION`/`APP_VERSION` — three separate version axes exist (app, api, scan
  schema), which is ahead of a typical MVP freeze.
- Scanner error isolation and per-scanner warnings surfaced through `ScanSummary.
  scanner_warnings` already implemented.
- Cleanup preview/execute path already enforces preview-must-match-execute (item_ids,
  confirm flags, scan_id) — beyond MVP scope but demonstrates the safety pattern is
  established.

## Gaps for v0.1.0 CoreScanMVPFreeze

- No per-scan `duration` (start/end timing) or explicit scan `status` field
  (success/partial/failed) on `ScanSummary` — only `scanner_warnings` (list) and
  `generated_at` (a single timestamp, not start+end).
- `/health` has no distinct `stage` field separate from the free-text version string;
  if the roadmap wants a machine-parseable stage (e.g. `"CoreScanMVPFreeze"`), it isn't
  present as its own field today.

## Gaps for v0.1.1 APIContractLock

- No API version is embedded in the scan/response payload itself (only in `/health`
  and the FastAPI app object) — contract-locking a versioned response schema would
  want `api_version` (or similar) on `ScanResult`/`ScanSummary` too, not just `/health`.
- ~~No visible contract test that pins the exact `ScanItem`/`ScanResult` JSON shape
  against `frontend/src/api.ts` (i.e., no schema-drift CI check) — drift today is
  caught by manual review only.~~ Closed — see Update 2 above.

## Scanner mutation/read-only concerns

None. All scanner paths reviewed (`files.py`, `browser.py`, `startup.py`, `tasks.py`)
are read-only; grep across the scanners directory found no delete/kill/write calls.

## Frontend/backend API drift concerns

None material. `api.ts` types track `schemas.py`/`scan_item.py` closely; the one minor
gap is `client.health()`'s narrower return type, which is not a contract break.

## Recommended next implementation task

Add `duration_ms` (or `started_at`/`finished_at`) and a `status` field
(`"ok" | "partial" | "failed"`) to `ScanSummary`, derived from existing
`scan_state`/`_run_full_scan_inner` timing and `scanner_warnings`, and surface
`api_version` on `ScanResult` itself (not just `/health`). This is the smallest
change that closes both the v0.1.0 "scan responses include duration/status" gap and
the v0.1.1 "API contract lock" gap (versioned response schema), without touching
scanners, cleanup, or quarantine.

Why: it's additive (no existing field removed or renamed), bounded to
`ScanSummary`/`run_full_scan`/`api.ts` types, and directly targets the two concrete
gaps found above rather than speculative future-proofing.
