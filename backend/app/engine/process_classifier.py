from __future__ import annotations

"""
Pipeline-facing wrapper around `process_action_policy`.

Runs after rules + intelligence, before action gating. It only writes
`process_control` (plus provenance) — buckets, `cleanup_eligible`, and
`performance_eligible` stay where they were decided.
"""

from app.engine.process_action_policy import classify_process_control
from app.models.scan_item import ProvenanceRecord, ScanItem, utc_now_iso


def _already_classified(item: ScanItem) -> bool:
    """Only the classifier writes `evidence` — a non-empty list means someone decided already."""
    return bool(item.process_control.evidence)


def stage_process_control(item: ScanItem) -> ScanItem:
    if _already_classified(item):
        return item

    pc = classify_process_control(item)
    rec = ProvenanceRecord(
        stage="process_control",
        decided_by="process_action_policy",
        evidence=[f"category:{pc.category.value}", f"policy:{pc.action_policy.value}", *pc.evidence],
        confidence=pc.confidence,
    )
    return item.model_copy(
        update={
            "process_control": pc,
            "provenance": [*item.provenance, rec],
            "timestamps": {**item.timestamps, "process_control_at": utc_now_iso()},
        }
    )
