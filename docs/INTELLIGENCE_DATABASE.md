# Windows Intelligence Database

OpenCleaner ships a **local, open-source** “encyclopedia” JSON file that explains common Windows processes, services, startup entries, scheduled tasks, launchers, updaters, and related background apps. It is **not** a remote reputation service, **does not** phone home, and **must not** be treated as permission to delete files automatically.

- **Data file**: `backend/data/windows_intelligence.json`
- **Loader / matching**: `backend/app/services/intelligence_service.py`

## Schema (per entry)

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `name` | string | Canonical match key (e.g. `steam.exe`, `windefend`, `OneDrive`) |
| `aliases` | string[] | Alternate names (e.g. display names, friendly labels) |
| `type` | `"process"` \| `"service"` \| `"startup"` \| `"task"` | Which scanner rows this applies to |
| `vendor` | string | Publisher / vendor |
| `category` | string | High-level grouping (e.g. `Game launcher`, `Anticheat`) |
| `plain_english_description` | string | User-facing explanation |
| `safe_to_stop` | boolean | Process-oriented: kill via Task Manager, etc. |
| `safe_to_disable_startup` | boolean | Startup-oriented: disabling auto-run |
| `safe_to_delete` | boolean | **Informational only** — cleanup still honors rules + Assisted mode |
| `gaming_impact` | string | Qualitative (`low` … `critical`, `variable`, etc.) |
| `memory_impact` | string | Qualitative |
| `startup_impact` | string | Qualitative |
| `risk_level` | string | Qualitative severity for policy (`low` … `critical`) |
| `confidence` | number | 0–1 weight for the entry (informative) |
| `warning_if_changed` | string | What might break if the user intervenes |
| `recommended_action` | string | Conservative guidance |

Top-level document:

- `schema_version`: integer — bump when field meanings change
- `description`: human-readable policy blurb
- `entries`: array of rows

## How entries are matched

1. **Exact** match on normalized name keys (case-insensitive), including executable basenames and scheduled task names.
2. **Alias** match on `aliases` (e.g. service **display name** vs. short service name).
3. **Fuzzy** match **only** when the candidate encyclopedia row is **low** `risk_level` and high `confidence` — mis-identification must be unlikely to brick the system.

Unmatched rows receive a conservative **`known: false`** intelligence stub. **Unknown never implies “safe”.**

## Safety policy

1. **Rules engine wins** for `risky_system_critical` and path-based protections. Intelligence **enriches** these rows but does not downgrade them.
2. Intelligence **never** promotes items into `safe_to_remove` or `probably_safe` on its own.
3. **ML ranking** adjusts usefulness scores only; it shares the same “no autonomous deletion” guarantee as before.
4. Prefer **false negatives** (unknown) over false positives (calling something “safe” when it is not).

## Contributing entries

1. Edit `backend/data/windows_intelligence.json` (keep valid JSON — no trailing commas).
2. Prefer **well-known** names; add **aliases** for common display strings.
3. For `risk_level`, be honest: gaming clients and anticheat often warrant `high` / `critical`.
4. Do not set `safe_to_delete: true` for anything under `%WINDIR%`, drivers, security, or anticheat.
5. Run `PYTHONPATH=. pytest` from `backend/` and smoke-test the UI after substantive additions.

## Example entry

```json
{
  "name": "steam.exe",
  "aliases": ["Steam Client"],
  "type": "process",
  "vendor": "Valve",
  "category": "Game launcher",
  "plain_english_description": "Main Steam client — library, downloads, and game launches.",
  "safe_to_stop": false,
  "safe_to_disable_startup": false,
  "safe_to_delete": false,
  "gaming_impact": "critical",
  "memory_impact": "medium",
  "startup_impact": "medium",
  "risk_level": "medium",
  "confidence": 0.92,
  "warning_if_changed": "Closing exits Steam overlay and may interrupt downloads.",
  "recommended_action": "Close from Steam UI; avoid Task Manager unless frozen."
}
```

For questions about packaging paths or CI stubs, see `docs/PACKAGING.md` and the main `README.md`.
