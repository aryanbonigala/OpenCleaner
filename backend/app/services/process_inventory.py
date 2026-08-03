from __future__ import annotations

"""
Read-only view over the latest classified scan.

Nothing here touches the OS: no psutil calls, no process handles, no disk writes.
It reads `ScanItem`s that the pipeline already classified and reshapes them for the
UI/chat layers. `preview_end_processes` decides what *would* be allowed later — it
never executes, and there is no execute endpoint to pair with it yet.
"""

from typing import Any

from app.models.enums import ActionPolicy, ItemType, ProcessControlCategory
from app.models.scan_item import PROCESS_CONTROL_ITEM_TYPES, ScanItem
from app.models.schemas import ScanResult

NO_SCAN_MESSAGE = "No scan available yet. Run a scan first (POST /api/scan)."
PREVIEW_DISCLAIMER = "Preview only. No process was ended, suspended, or modified."


def process_items_from_scan(scan: ScanResult) -> list[ScanItem]:
    """Process/service/startup/task rows only — files, browsers, duplicates, orphans are dropped."""
    return [
        it
        for it in scan.items
        if it.item_type in PROCESS_CONTROL_ITEM_TYPES
        and it.process_control.category is not ProcessControlCategory.not_applicable
    ]


def pid_of(item: ScanItem) -> int | None:
    raw = item.scanner_facts.get("pid")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def get_process_item_by_pid(scan: ScanResult, pid: int) -> ScanItem | None:
    for it in scan.items:
        if it.item_type is ItemType.process and pid_of(it) == pid:
            return it
    return None


def get_process_inventory(latest_scan: ScanResult | None) -> dict[str, Any]:
    if latest_scan is None:
        return {
            "scan_id": None,
            "generated_at": None,
            "platform": None,
            "items_count": 0,
            "counts": {},
            "items": [],
            "warnings": [],
            "message": NO_SCAN_MESSAGE,
        }

    items = process_items_from_scan(latest_scan)
    counts: dict[str, int] = {}
    for it in items:
        key = it.process_control.category.value
        counts[key] = counts.get(key, 0) + 1

    return {
        "scan_id": latest_scan.summary.scan_id,
        "generated_at": latest_scan.summary.generated_at,
        "platform": latest_scan.summary.platform,
        "items_count": len(items),
        "counts": counts,
        "items": items,
        "warnings": list(latest_scan.summary.scanner_warnings),
        "message": None,
    }


def _preview_row(item: ScanItem, *, confirm_explicit_selection: bool) -> dict[str, Any]:
    pc = item.process_control

    def out(status: str, action: str, reason: str) -> dict[str, Any]:
        return {
            "id": item.id,
            "display_name": item.display_name,
            "pid": pid_of(item),
            "status": status,
            "recommended_action": action,
            "reason": reason,
            "process_control": pc,
        }

    if item.item_type is not ItemType.process:
        return out(
            "blocked",
            "report_only",
            f"“{item.item_type.value}” items are report-only — no control flow exists for them yet.",
        )
    if pc.category is ProcessControlCategory.essential:
        return out("blocked", "blocked", pc.blocked_reason or "Essential — never selectable.")
    if pc.action_policy is ActionPolicy.blocked:
        return out("blocked", "blocked", pc.blocked_reason or "Blocked by process-control policy.")
    if pc.category is ProcessControlCategory.unknown or pc.action_policy in (
        ActionPolicy.report_only,
        ActionPolicy.unsupported,
    ):
        return out("blocked", "report_only", "Unclassified or report-only — not offered for any action.")
    if pc.action_policy is ActionPolicy.explicit_selection_required and not confirm_explicit_selection:
        return out(
            "blocked",
            "report_only",
            "Requires explicit selection — resend with confirm_explicit_selection=true.",
        )
    if not pc.safe_to_suspend:
        # safe_to_end is never granted by the classifier, so suspend is the only reversible
        # candidate. Without it there is nothing to preview.
        return out("blocked", "report_only", "No reversible action is classified safe for this process.")
    return out(
        "would_allow",
        "suspend_preview_only",
        "Would be offered as a reversible suspend once execution exists. Nothing ran.",
    )


def preview_end_processes(
    scan: ScanResult,
    item_ids: list[str],
    *,
    confirm_explicit_selection: bool = False,
) -> dict[str, Any]:
    by_id = {it.id: it for it in scan.items}
    rows: list[dict[str, Any]] = []

    for item_id in item_ids:
        item = by_id.get(item_id)
        if item is None:
            rows.append(
                {
                    "id": item_id,
                    "display_name": item_id,
                    "pid": None,
                    "status": "skipped",
                    "recommended_action": "report_only",
                    "reason": "Not found in the latest scan.",
                    "process_control": None,
                }
            )
            continue
        rows.append(_preview_row(item, confirm_explicit_selection=confirm_explicit_selection))

    return {
        "preview_id": None,  # no execute endpoint exists yet — a token would promise one
        "counts": {
            "selected": len(item_ids),
            "would_allow": sum(1 for r in rows if r["status"] == "would_allow"),
            "blocked": sum(1 for r in rows if r["status"] == "blocked"),
            "skipped": sum(1 for r in rows if r["status"] == "skipped"),
        },
        "items": rows,
        "disclaimer": PREVIEW_DISCLAIMER,
    }
