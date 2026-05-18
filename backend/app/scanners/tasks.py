from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from xml.parsers.expat import ExpatError

from app.models.schemas import ItemType, RiskBucket, ScoredItem
from app.platform.detect import OSFamily, detect_os


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _first_text_local(root: ET.Element, local_name: str) -> str | None:
    for el in root.iter():
        if _strip_ns(el.tag) == local_name and el.text and el.text.strip():
            return el.text.strip()
    return None


def _find_first_child_local(parent: ET.Element, local_name: str) -> ET.Element | None:
    for el in list(parent):
        if _strip_ns(el.tag) == local_name:
            return el
    return None


def _trigger_summary(root: ET.Element) -> str:
    parts: list[str] = []
    trig_el = _find_first_child_local(root, "Triggers")
    if trig_el is not None:
        for child in list(trig_el):
            tag = _strip_ns(child.tag)
            if tag.endswith("Trigger") and tag in (
                "BootTrigger",
                "LogonTrigger",
                "CalendarTrigger",
                "IdleTrigger",
                "EventTrigger",
                "TimeTrigger",
                "RegistrationTrigger",
            ):
                parts.append(tag.replace("Trigger", "").lower())
    return ", ".join(parts[:6]) if parts else ""


def _parse_task_xml_element(task_el: ET.Element, fallback_folder: str = "") -> ScoredItem:
    reg = _find_first_child_local(task_el, "RegistrationInfo")

    author = _first_text_local(reg, "Author") if reg is not None else None
    uri = _first_text_local(reg, "URI") if reg is not None else None
    uri = uri or ""

    settings = _find_first_child_local(task_el, "Settings")
    enabled_txt = ""
    if settings is not None:
        en = _find_first_child_local(settings, "Enabled")
        if en is not None and en.text:
            enabled_txt = en.text.strip().lower()
    if enabled_txt in ("true", "1"):
        status = "enabled"
    elif enabled_txt in ("false", "0"):
        status = "disabled"
    else:
        status = enabled_txt or "unknown"

    command = ""
    arguments = ""
    actions = _find_first_child_local(task_el, "Actions")
    if actions is not None:
        ex = _find_first_child_local(actions, "Exec")
        if ex is not None:
            c = _find_first_child_local(ex, "Command")
            a = _find_first_child_local(ex, "Arguments")
            command = (c.text or "").strip() if c is not None and c.text else ""
            arguments = (a.text or "").strip() if a is not None and a.text else ""

    task_name = uri.strip("\\").split("\\")[-1] if uri else ""
    if not task_name:
        task_name = command.rstrip("\\").split("\\")[-1] if command else "scheduled_task"

    trig = _trigger_summary(task_el)
    sid = f"task-xml-{fallback_folder}-{task_name}".replace(" ", "_")

    return ScoredItem(
        id=sid[:180],
        category="scheduled_tasks",
        item_type=ItemType.scheduled_task,
        name=task_name or "task",
        path=command or uri or None,
        detail={
            "folder": fallback_folder,
            "status": status,
            "author": author,
            "command": command,
            "arguments": arguments,
            "trigger_summary": trig,
            "source": "schtasks_xml",
        },
        rule_bucket=RiskBucket.unknown,
        confidence=0.62,
        reasoning="Parsed from Task Scheduler XML — verify actions before disabling.",
    )


def _parse_schtasks_xml_blob(text: str) -> list[ScoredItem]:
    items: list[ScoredItem] = []
    if not text or not text.strip():
        return items
    try:
        text = text.lstrip("\ufeff")
        root = ET.fromstring(text)
    except (ExpatError, ET.ParseError):
        return items

    tag = _strip_ns(root.tag)
    if tag == "Task":
        items.append(_parse_task_xml_element(root, ""))
        return items
    if tag == "Tasks":
        for child in root:
            if _strip_ns(child.tag) == "Task":
                items.append(_parse_task_xml_element(child, ""))
        return items

    for task_el in root.iter():
        if _strip_ns(task_el.tag) == "Task":
            items.append(_parse_task_xml_element(task_el, ""))
    return items


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
    for it in items:
        it.detail["source"] = it.detail.get("source") or "schtasks_list"
    return items


def _task_item_from_block(cur: dict[str, str]) -> ScoredItem:
    name = cur.get("task_name") or "unknown_task"
    folder = cur.get("folder") or ""
    status = cur.get("status") or cur.get("scheduled_task_state") or ""
    return ScoredItem(
        id=f"task-{folder}-{name}".replace(" ", "_")[:180],
        category="scheduled_tasks",
        item_type=ItemType.scheduled_task,
        name=name,
        path=cur.get("task_to_run"),
        detail={
            "folder": folder,
            "status": status,
            "author": cur.get("author"),
            "task_to_run": cur.get("task_to_run"),
            "command": cur.get("task_to_run"),
        },
        rule_bucket=RiskBucket.unknown,
        confidence=0.48,
        reasoning="Parsed from schtasks LIST output — prefer XML when available.",
    )


def _run_schtasks_xml() -> str | None:
    proc = subprocess.run(
        ["schtasks", "/query", "/xml"],
        capture_output=True,
        timeout=120,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,  # type: ignore[attr-defined]
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    raw: bytes = proc.stdout
    for enc in ("utf-16", "utf-16-le", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


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
        xml_blob = _run_schtasks_xml()
        if xml_blob:
            parsed = _parse_schtasks_xml_blob(xml_blob)
            if parsed:
                return parsed
    except Exception:
        pass

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


def parse_tasks_xml_for_tests(xml_text: str) -> list[ScoredItem]:
    """Test helper: parse fixture XML."""
    return _parse_schtasks_xml_blob(xml_text)
