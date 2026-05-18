from __future__ import annotations

import re
import subprocess
import sys
from typing import Any

from app.models.schemas import ItemType, RiskBucket, ScoredItem
from app.platform.detect import OSFamily, detect_os


def _parse_schtasks_list(output: str) -> list[ScoredItem]:
    items: list[ScoredItem] = []
    cur: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip("\r")
        if not line:
            continue
        if line.lower().startswith("folder:"):
            if cur.get("task_name"):
                items.append(_task_item_from_block(cur))
            cur = {"folder": line.split(":", 1)[1].strip()}
            continue
        if line.lower().startswith("taskname:"):
            if cur.get("task_name"):
                items.append(_task_item_from_block(cur))
            cur = {"task_name": line.split(":", 1)[1].strip()}
            continue
        m = re.match(r"^([^:]+):\s*(.*)$", line)
        if m:
            k = m.group(1).strip().lower().replace(" ", "_")
            cur[k] = m.group(2).strip()

    if cur.get("task_name"):
        items.append(_task_item_from_block(cur))
    return items


def _task_item_from_block(cur: dict[str, str]) -> ScoredItem:
    name = cur.get("task_name") or "unknown_task"
    folder = cur.get("folder") or ""
    status = cur.get("status") or cur.get("scheduled_task_state") or ""
    return ScoredItem(
        id=f"task-{folder}-{name}".replace(" ", "_"),
        category="scheduled_tasks",
        item_type=ItemType.scheduled_task,
        name=name,
        path=None,
        detail={
            "folder": folder,
            "status": status,
            "author": cur.get("author"),
            "task_to_run": cur.get("task_to_run"),
        },
        rule_bucket=RiskBucket.unknown,
        confidence=0.48,
        reasoning="Parsed from schtasks output — review Task Scheduler for full XML.",
    )


def scan_scheduled_tasks() -> list[ScoredItem]:
    if not (detect_os() == OSFamily.windows and sys.platform == "win32"):
        return [
            ScoredItem(
                id="tasks-nonwin-stub",
                category="scheduled_tasks",
                item_type=ItemType.scheduled_task,
                name="Cron/system timers",
                path=None,
                detail={"note": "Non-Windows cron/launchd adapters ship incrementally."},
                rule_bucket=RiskBucket.unknown,
                confidence=0.35,
                reasoning="Placeholder until platform scheduler scanner is enabled.",
            )
        ]

    try:
        proc = subprocess.run(
            ["schtasks", "/query", "/fo", "LIST", "/v"],
            capture_output=True,
            text=True,
            timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,  # type: ignore[attr-defined]
        )
        if proc.returncode != 0:
            return []
        return _parse_schtasks_list(proc.stdout or "")
    except Exception:
        return []
