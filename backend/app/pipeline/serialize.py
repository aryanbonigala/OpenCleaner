from __future__ import annotations

import json
from typing import Any

from app.models.scan_item import SCAN_SCHEMA_VERSION, CanonicalScanResult, ScanItem


def _sort_provenance(item: ScanItem) -> ScanItem:
    """Provenance order is append-only; no reorder needed."""
    return item


def canonical_item_dict(item: ScanItem) -> dict[str, Any]:
    """Deterministic dict for one item (stable key order via model_dump)."""
    data = item.model_dump(mode="json")
    data["provenance"] = sorted(
        data.get("provenance") or [],
        key=lambda p: (p.get("stage", ""), p.get("decided_by", "")),
    )
    return data


def serialize_scan_result(result: CanonicalScanResult) -> str:
    """Deterministic JSON for exports and persistence."""
    payload = {
        "scan_schema_version": SCAN_SCHEMA_VERSION,
        "summary": result.summary.model_dump(mode="json"),
        "items": [canonical_item_dict(_sort_provenance(it)) for it in sorted(result.items, key=lambda x: x.id)],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def serialize_scan_result_object(result: CanonicalScanResult) -> dict[str, Any]:
    """Export-safe dict (no numpy / datetime objects)."""
    return json.loads(serialize_scan_result(result))


def detail_json_for_storage(item: ScanItem) -> str:
    """Embed canonical item in detail_json for DB backward compatibility."""
    wrapper = {
        "canonical": item.model_dump(mode="json"),
        **{k: v for k, v in item.scanner_facts.items()},
    }
    return json.dumps(wrapper, ensure_ascii=False, sort_keys=True)
