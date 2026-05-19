# Settings and safety preferences (v0.4.2)

OpenCleaner stores **local** user preferences in SQLite (`settings.user_preferences_v1`). There is no cloud sync and no telemetry.

## Settings reference

| Setting | Values | Default | What it does |
|---------|--------|---------|--------------|
| **cleanup_mode** | `quarantine_only`, `manual_permanent_delete_only` | `quarantine_only` | Controls whether Recycle Bin emptying can be requested. Quarantine-only never allows permanent delete paths. |
| **risk_visibility** | `basic`, `advanced` | `basic` | Basic hides unknown / ask-user / critical items from the findings list. Advanced shows them but never auto-selects them. |
| **scanner_toggles** | booleans per group | all `true` | Enables or disables scanner groups on the next scan. |
| **quarantine_retention** | `manual_only`, `7_days`, `14_days`, `30_days` | `manual_only` | When not manual, expired quarantine rows are purged at scan start. |
| **logging_mode** | `normal`, `redacted_paths`, `minimal` | `redacted_paths` | Controls detail written to the local audit log. |

### Scanner groups

| Toggle | Scanners included |
|--------|-------------------|
| `files` | Temp/cache, downloads, desktop clutter, duplicates, large files, orphans |
| `browser` | Browser profile sizing |
| `startup` | Services, startup entries |
| `tasks` | Scheduled tasks |
| `performance` | Running processes |

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/settings` | Load current preferences |
| `PUT` | `/api/settings` | Partial update (validated) |
| `POST` | `/api/settings/reset` | Restore safe defaults |

## Safety limits (cannot be changed in settings)

- **Protected paths** — `is_critical_path()` and the rules engine always block system directories.
- **No auto-select** — only `safe_to_remove` files are selected by default; advanced visibility does not change that.
- **Preview before execute** — cleanup still requires a matching preview session.
- **ML / intelligence** — cannot authorize deletion or override critical buckets.
- **No telemetry** — logging stays on disk only.

## Migration

`settings_version` inside the JSON blob is currently `1`. Older shapes are coerced to defaults on load when invalid.
