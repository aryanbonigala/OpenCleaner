# Scan schema (canonical ScanItem)

OpenCleaner standardizes every scanner row as a **`ScanItem`** (`backend/app/models/scan_item.py`). API responses, exports, and persisted `detail_json.canonical` blobs use this shape.

## Versioning

| Field | Meaning |
| ----- | ------- |
| `SCAN_SCHEMA_VERSION` (currently **1**) | Semantics of `ScanItem` fields |
| `scan_version` on each item | Copy of schema version at normalization time |
| `scan_schema_version` on `ScanSummary` | Report / API envelope version |

Bump `SCAN_SCHEMA_VERSION` when you make **breaking** field renames or change precedence guarantees. Additive fields are backward compatible.

## ScanItem fields

| Field | Description |
| ----- | ----------- |
| `id` | Stable row id from scanner |
| `scan_version` | Schema version stamp |
| `item_type` | `process`, `service`, `startup_entry`, `scheduled_task`, `file_or_folder`, … |
| `source` | Scanner module category (e.g. `processes`, `services`) |
| `subtype` | Optional hint (`temp_cache`, task source, …) |
| `display_name` | UI-friendly label |
| `raw_name` | Original identifier (exe name, service name, …) |
| `path` | Path or command when known |
| `vendor` / `category` | From intelligence or scanner |
| `metrics` | Numeric facts + ML rank scores (0–100) |
| `intelligence` | Snapshot from local Windows intelligence DB |
| `bucket` | Rules output (`safe_to_remove` … `risky_system_critical`) |
| `risk_level` | Qualitative string (intel or derived) |
| `protected` | Rules/registry: do not auto-change |
| `cleanup_eligible` | Action gating: assisted file quarantine allowed |
| `performance_eligible` | Action gating: suspend policy allows |
| `explanation` | `summary` (+ optional `headline`) |
| `recommendations` | `primary` action text + `warnings[]` |
| `provenance` | Append-only list of stage decisions |
| `timestamps` | ISO UTC markers per stage |
| `scanner_facts` | Raw scanner dict (minus embedded intelligence) |
| `confidence` | 0–1 rules/intelligence confidence |

## Provenance record

Each pipeline stage appends one record:

- `stage`: `rules` \| `intelligence` \| `ml` \| `explanation` \| `action_gating` \| `feedback`
- `decided_by`: engine name
- `evidence`: human-readable strings
- `matched_rule`, `matched_intelligence_entry`, `ml_score_source` (optional)
- `confidence` (optional)

Exports sort provenance by `(stage, decided_by)` for stable JSON.

## Legacy compatibility

- Scanners still emit **`ScoredItem`** internally; **`normalize_scored_item`** converts to `ScanItem`.
- DB rows store `detail_json` with a **`canonical`** key containing the full `ScanItem`.
- Legacy columns (`name`, `rule_bucket`, `reasoning`, …) mirror canonical fields for SQL/report tools.

## Guarantees

1. Unknown intelligence entries **never** imply `safe_to_delete`.
2. `risky_system_critical` **cannot** be downgraded by intelligence or ML.
3. ML updates **`metrics` ranks only** — not `bucket` or `explanation.summary` (except optional feedback nudge text).
4. **`action_gating`** is the only stage that sets `cleanup_eligible` / `performance_eligible`.

See also: [SCAN_PIPELINE.md](./SCAN_PIPELINE.md), [INTELLIGENCE_DATABASE.md](./INTELLIGENCE_DATABASE.md).
