# Changelog

All notable changes to OpenCleaner are documented here.

## [0.4.2] — Settings and safety preferences (`v0.4.2_SettingsAndSafetyPreferences`)

### Added

- **User settings model** (`backend/app/models/user_settings.py`) with safe defaults and schema version.
- **Settings API**: `GET/PUT /api/settings`, `POST /api/settings/reset`.
- **Scanner toggles** — enable/disable file, browser, startup, task, and performance scanner groups per scan.
- **Cleanup mode** — `quarantine_only` (default) vs `manual_permanent_delete_only` for Recycle Bin options.
- **Risk visibility** — `basic` (default) vs `advanced`; advanced shows risky items but does not auto-select them.
- **Quarantine retention** — manual-only default; optional 7/14/30-day purge at scan start.
- **Logging mode** — `redacted_paths` (default), `normal`, or `minimal` for local audit entries.
- **Settings page** in the UI with reset-to-defaults and advanced-risk warning.

### Safety

- Settings cannot disable path protections or rules-engine blocks.
- Recycle Bin emptying rejected when `cleanup_mode` is `quarantine_only`.
- Unknown / ask-user cleanup blocked in basic risk visibility at preview and execute time.

See [docs/SETTINGS.md](docs/SETTINGS.md).

## [0.4.1] — Frontend UX Alpha (`v0.4.1_FrontendUXAlpha`)

### Added

- **End-to-end assisted flow in the UI**: dashboard → scan → review findings → cleanup preview → quarantine execute → summary → quarantine restore.
- **Frontend screens**: Dashboard, ScanProgress, ScanResults, FindingCard, FindingDetails, RiskBadge, CleanupReview, CleanupProgress, CleanupSummary, QuarantineManager, Settings, ErrorBanner, EmptyState.
- **`POST /api/cleanup/preview`**: dry-run with per-item status (`will_quarantine`, `blocked`, `skipped`), estimated bytes, and plain-English `why_safe_or_unsafe`.
- **`POST /api/cleanup/execute`**: requires a matching preview session; returns estimated vs confirmed reclaim sizes and blocked/skipped/failed counts.
- **`GET /api/scan/status`**: exposes whether a scan is in progress.
- **Health/version**: `/health` returns `version`, `api_version`, and `scan_in_progress`.
- **Scanner warnings** on scan summary when individual scanners partially fail.

### Safety

- Cleanup cannot run while a scan is running (HTTP 409).
- Cleanup execute requires a valid preview id; selected item ids must match preview exactly.
- Recycle Bin emptying requires `confirm_permanent_delete` after preview.
- Unknown / ask-user / non-cleanup-eligible items are blocked in preview unless medium-risk confirmation is enabled.
- Dangerous items are not selected by default in the UI (only `safe_to_remove`).

### Limitations (this release)

- Windows-focused scanners; non-Windows dev may use mock scan data.
- Assisted cleanup quarantines **files** only (not processes, services, or startup entries).
- Preview sessions expire after about one hour; re-preview if execute fails with “preview expired”.
- No cloud sync, telemetry, registry cleaning, or automatic service disabling.
- ML and intelligence inform ranking and copy only; they cannot override rules or action gating.

## [0.4.0] — Canonical scan model + reasoning pipeline

- Unified `ScanItem` schema, multi-stage pipeline, provenance, deterministic export.

## [0.3.0] — Windows Intelligence Database

- Local `windows_intelligence.json`, enrichment service, UI badges and filters.

## [0.2.0] — Safety and packaging hardening

- Bounded filesystem walks, task XML parsing, performance preview-first API, Safety Center summary.
