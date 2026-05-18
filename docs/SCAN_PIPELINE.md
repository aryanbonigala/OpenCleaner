# Scan reasoning pipeline

OpenCleaner processes inventory in a **fixed, deterministic order**. Each stage receives an immutable `ScanItem` and returns a new copy with allowed fields updated plus an appended **provenance** record.

## Flow

```text
scanner (ScoredItem)
    → normalize          (structure only)
    → rules              (bucket, protected, confidence)
    → intelligence       (intel snapshot, may tighten bucket)
    → ML                 (metrics ranks only)
    → [feedback nudge]   (optional usefulness tweak)
    → explanation        (headline / summary polish)
    → action_gating      (cleanup_eligible, performance_eligible)
```

Implementation: `backend/app/pipeline/reasoning.py`  
Orchestration: `backend/app/services/scan_service.py`

## Precedence

| Priority | Stage | May change `bucket`? | May enable deletion/suspend? |
| -------- | ----- | -------------------- | ---------------------------- |
| 1 (highest) | **Rules** | Yes | No — classification only |
| 2 | **Intelligence** | Only tighten / clarify (never below rules critical) | No |
| 3 | **ML** | **No** | No |
| 4 | **Explanation** | No | No |
| 5 (final) | **Action gating** | No | Sets eligibility flags only |

**Rules override everything.** Blocklist, critical process/service heuristics, and system paths win over intelligence and ML.

**Intelligence enriches** vendor/category text and may move `unknown` → `ask_user` on exact/alias matches. It **must not** downgrade `risky_system_critical` or promote to `safe_to_remove` / `probably_safe` alone.

**ML** only updates `metrics.*` rank fields and `ml_rank_score`. It does not authorize cleanup.

**Action gating** consults `protected_registry` and bucket policy to set `cleanup_eligible` / `performance_eligible`. Assisted cleanup and performance mode **must** respect these flags.

## Provenance philosophy

- Every automated decision is **explainable** from `provenance[]`.
- Stages **append**; they do not rewrite prior provenance.
- Exports use **sorted keys** and stable item ordering (`id`) — see `backend/app/pipeline/serialize.py`.

## Serialization

- API scan results: Pydantic `ScanResult` with `list[ScanItem]`.
- Export JSON: `export_canonical_payload()` — `scan_schema_version`, sorted items, JSON-safe types only.
- Persistence: `detail_json_for_storage()` embeds `canonical` + scanner facts for reload without re-running pipeline (unless legacy row).

## Future compatibility

- Prefer **additive** `ScanItem` fields and bump `SCAN_SCHEMA_VERSION` only when necessary.
- New pipeline stages should register a unique `stage` name and document whether they may touch `bucket` or action flags.
- Frontend should use `frontend/src/scanItem.ts` helpers instead of ad hoc `detail.*` access.

## Related docs

- [SCAN_SCHEMA.md](./SCAN_SCHEMA.md) — field reference
- [INTELLIGENCE_DATABASE.md](./INTELLIGENCE_DATABASE.md) — local encyclopedia
- [SECURITY.md](./SECURITY.md) — safety modes (if present)
