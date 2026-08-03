"""
Deterministic, local chat command preview over the latest scan.

No LLM, no network, no OS access: every answer comes from keyword matching over the
message plus `ScanItem`s the pipeline already classified. Action decisions are delegated
wholesale to `process_inventory.preview_end_processes`, so chat can never be more
permissive than the REST API. There is no execution path here and no confirmation token —
a token would imply an execute endpoint that does not exist.
"""

from __future__ import annotations

import re
from typing import Any

from app.models.enums import ActionPolicy, ProcessControlCategory
from app.models.scan_item import ScanItem
from app.models.schemas import ScanResult
from app.services.process_inventory import (
    NO_SCAN_MESSAGE,
    PREVIEW_DISCLAIMER,
    get_process_item_by_pid,
    pid_of,
    preview_end_processes,
    process_items_from_scan,
)

GAMING_SAFETY_PREVIEW = "gaming_safety_preview"
SAFE_SUSPEND_PREVIEW = "safe_suspend_preview"
EXPLAIN_PROCESS = "explain_process"
UNKNOWN_INVENTORY = "unknown_inventory"
PROTECTED_INVENTORY = "protected_inventory"
HELP = "help"

EXECUTION_NOT_IMPLEMENTED = (
    "Execution is not implemented. This endpoint only previews what would be offered — "
    "nothing was ended, suspended, disabled, or removed."
)

_GAMING = (
    "gaming", "game", "games", "fps", "lag", "laggy", "lagging", "stutter",
    "performance", "frame rate", "framerate", "before gaming",
)
_SAFE_SUSPEND = (
    "safe", "safely", "suspend", "close", "end", "pause", "quit", "free up", "background",
    # Stop-verbs route here too, so "kill chrome" gets the real policy verdict plus a
    # refusal warning rather than falling through to generic help. The intent label
    # grants nothing — every row still goes through preview_end_processes.
    "kill", "terminate", "shut down", "shutdown",
)
_UNKNOWN = ("unknown", "unrecognized", "unrecognised", "unidentified", "not sure")
_PROTECTED = (
    "locked", "lock", "blocked", "protected", "off limits", "never touch",
    "can't touch", "cannot touch", "untouchable",
)
_EXPLAIN = ("explain", "what is", "what's", "whats", "why", "tell me about", "describe", "who is")

# Wording that asks for mutation. Never changes what we do — only adds a refusal warning.
_DESTRUCTIVE = (
    "kill", "end", "disable", "remove", "shut down", "shutdown", "terminate",
    "force quit", "uninstall", "delete", "stop",
)

_HELP_EXAMPLES = [
    "What can I close before gaming?",
    "What can I safely suspend?",
    "Explain Chrome",
    "Why is this locked?",
    "What is unknown?",
    "Show FPS-impacting apps",
]


def _has(message: str, phrases: tuple[str, ...]) -> bool:
    """Word-boundary match, so 'recommend' never counts as 'end'."""
    return any(re.search(rf"\b{re.escape(p)}\b", message) for p in phrases)


def detect_intent(message: str) -> str:
    """
    First match wins, most specific first.

    Ordering is load-bearing: the concrete nouns ("unknown", "locked") are checked before
    the generic explain verbs, otherwise "what is unknown?" and "why is this locked?" both
    collapse into explain_process.
    """
    m = message.lower()
    if _has(m, _GAMING):
        return GAMING_SAFETY_PREVIEW
    if _has(m, _SAFE_SUSPEND):
        return SAFE_SUSPEND_PREVIEW
    if _has(m, _UNKNOWN):
        return UNKNOWN_INVENTORY
    if _has(m, _PROTECTED):
        return PROTECTED_INVENTORY
    if _has(m, _EXPLAIN):
        return EXPLAIN_PROCESS
    return HELP


def _action(kind: str, label: str, endpoint: str | None = None, item_ids: list[str] | None = None) -> dict[str, Any]:
    return {"kind": kind, "label": label, "endpoint": endpoint, "item_ids": item_ids or []}


def _row(item: ScanItem, *, status: str, reason: str) -> dict[str, Any]:
    pc = item.process_control
    return {
        "id": item.id,
        "display_name": item.display_name,
        "pid": pid_of(item),
        "item_type": item.item_type,
        "category": pc.category,
        "action_policy": pc.action_policy,
        "status": status,
        "reason": reason,
        "fps_impact": pc.fps_impact,
        "user_visible_summary": pc.user_visible_summary,
        "blocked_reason": pc.blocked_reason,
    }


def _names_of(item: ScanItem) -> list[str]:
    names = {item.display_name, item.raw_name}
    if "." in item.raw_name:
        names.add(item.raw_name.rsplit(".", 1)[0])
    if item.path:
        base = re.split(r"[\\/]", item.path)[-1]
        names.add(base)
        if "." in base:
            names.add(base.rsplit(".", 1)[0])
    # 3-char floor: shorter names produce false hits on ordinary words.
    return [n.lower() for n in names if n and len(n) >= 3]


_STOPWORDS = {
    "explain", "what", "whats", "why", "who", "is", "are", "was", "the", "this", "that",
    "my", "our", "you", "your", "about", "tell", "describe", "show", "can", "should",
    "does", "did", "much", "many", "using", "use", "uses", "and", "for", "with", "please",
    "process", "processes", "app", "apps", "application", "program", "task", "service",
    "doing", "there", "here", "now", "all", "any", "some", "more", "most",
}


def _message_tokens(message: str) -> list[str]:
    """Words that could plausibly name a process — fillers and intent verbs removed."""
    words = re.findall(r"[a-z0-9._+-]+", message.lower())
    return [w for w in words if len(w) >= 3 and w not in _STOPWORDS]


def _find_target(scan: ScanResult, message: str) -> ScanItem | None:
    """
    PID first (explicit), then the best name match in either direction.

    Both directions are needed: "Explain Google Chrome" contains the whole item name,
    while "Explain Chrome" only carries one word of it. Ranked so a whole-name hit beats
    a single-token hit, and a shorter item name wins ties — "chrome" should resolve to
    "Google Chrome", not "Google Chrome Helper (Renderer)".
    """
    m = message.lower()
    for raw in re.findall(r"\d+", m):
        try:
            item = get_process_item_by_pid(scan, int(raw))
        except ValueError:  # integer far outside PID range
            continue
        if item is not None:
            return item

    tokens = _message_tokens(message)
    best: ScanItem | None = None
    best_score = (0, 0, 0)
    for item in process_items_from_scan(scan):
        for name in _names_of(item):
            if re.search(rf"\b{re.escape(name)}\b", m) or name in tokens:
                score = (2, len(name), -len(name))
            else:
                hits = [t for t in tokens if re.search(rf"\b{re.escape(t)}\b", name)]
                if not hits:
                    continue
                score = (1, max(len(t) for t in hits), -len(name))
            if score > best_score:
                best, best_score = item, score
    return best


def _preview_intent(
    scan: ScanResult,
    *,
    categories: set[ProcessControlCategory] | None,
    confirm_explicit_selection: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Run the real policy engine over the candidate set and split its verdicts."""
    candidates = [
        it
        for it in process_items_from_scan(scan)
        if categories is None or it.process_control.category in categories
    ]
    preview = preview_end_processes(
        scan,
        [it.id for it in candidates],
        confirm_explicit_selection=confirm_explicit_selection,
    )
    by_id = {it.id: it for it in candidates}

    allowed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for row in preview["items"]:
        item = by_id[row["id"]]
        if row["status"] == "would_allow":
            allowed.append(_row(item, status="would_allow", reason=row["reason"]))
        else:
            blocked.append(_row(item, status="blocked", reason=row["reason"]))
    return allowed, blocked, preview


def _needs_confirmation(scan: ScanResult, candidates_only: set[ProcessControlCategory] | None) -> bool:
    return any(
        it.process_control.action_policy is ActionPolicy.explicit_selection_required
        and (candidates_only is None or it.process_control.category in candidates_only)
        for it in process_items_from_scan(scan)
    )


def build_chat_preview(
    message: str,
    latest_scan: ScanResult | None,
    *,
    confirm_explicit_selection: bool = False,
) -> dict[str, Any]:
    """Read-only. Returns the response payload for POST /api/chat/command-preview."""
    intent = detect_intent(message)
    warnings: list[str] = []
    if _has(message.lower(), _DESTRUCTIVE):
        warnings.append(EXECUTION_NOT_IMPLEMENTED)

    base: dict[str, Any] = {
        "intent": intent,
        "message": message,
        "items": [],
        "blocked": [],
        "preview": None,
        "detail": None,
        "actions": [],
        "warnings": warnings,
        "disclaimer": PREVIEW_DISCLAIMER,
    }

    if latest_scan is None:
        return {
            **base,
            "summary": NO_SCAN_MESSAGE,
            "actions": [_action("run_scan", "Run a scan first", "POST /api/scan")],
        }

    if intent in (GAMING_SAFETY_PREVIEW, SAFE_SUSPEND_PREVIEW):
        categories = (
            {ProcessControlCategory.gaming_fps_impact, ProcessControlCategory.non_essential}
            if intent == GAMING_SAFETY_PREVIEW
            else None
        )
        allowed, blocked, preview = _preview_intent(
            latest_scan,
            categories=categories,
            confirm_explicit_selection=confirm_explicit_selection,
        )
        scope = "FPS-impacting and non-essential" if categories else "process-control"
        summary = (
            f"{len(allowed)} of {len(allowed) + len(blocked)} {scope} items would be offered as a "
            f"reversible suspend. {len(blocked)} are held back as essential, protected, unknown, or "
            "report-only. Nothing ran."
        )
        actions: list[dict[str, Any]] = []
        if allowed:
            actions.append(
                _action(
                    "review_preview",
                    "Review this preview in full",
                    "POST /api/processes/preview-end",
                    [r["id"] for r in allowed],
                )
            )
        if not confirm_explicit_selection and _needs_confirmation(latest_scan, categories):
            warnings.append(
                "Some items require explicit selection — resend with confirm_explicit_selection=true "
                "to see them previewed."
            )
            actions.append(
                _action("confirm_explicit_selection", "Resend with confirm_explicit_selection=true")
            )
        return {**base, "summary": summary, "items": allowed, "blocked": blocked, "preview": preview, "actions": actions}

    if intent == EXPLAIN_PROCESS:
        target = _find_target(latest_scan, message)
        if target is None:
            warnings.append("No process in the latest scan matched that name or PID.")
            return {
                **base,
                "summary": (
                    "Could not match that to anything in the latest scan. Try a process name "
                    "(\"Explain Chrome\") or a PID."
                ),
                "actions": [_action("none", "Browse the inventory", "GET /api/processes")],
            }
        pc = target.process_control
        pid = pid_of(target)
        return {
            **base,
            "summary": pc.user_visible_summary or target.explanation.summary or f"{target.display_name} — no summary recorded.",
            "items": [_row(target, status="informational", reason="Explanation only — no action was offered.")],
            "detail": {
                "id": target.id,
                "display_name": target.display_name,
                "pid": pid,
                "process_control": pc.model_dump(mode="json"),
                "explanation": target.explanation.model_dump(mode="json"),
                "scanner_facts": target.scanner_facts,
                "evidence": list(pc.evidence),
                "blocked_reason": pc.blocked_reason,
            },
            "actions": [
                _action("open_process_detail", f"Open {target.display_name}", f"GET /api/processes/{pid}")
            ]
            if pid is not None
            else [],
        }

    if intent == UNKNOWN_INVENTORY:
        rows = [
            _row(
                it,
                status="informational",
                reason="Unclassified — never offered for any action and excluded from bulk previews.",
            )
            for it in process_items_from_scan(latest_scan)
            if it.process_control.category is ProcessControlCategory.unknown
        ]
        return {
            **base,
            "summary": (
                f"{len(rows)} item(s) are unclassified. Unknown items are always excluded from "
                "actions — they stay informational until they can be identified."
            ),
            "blocked": rows,
            "actions": [_action("none", "Browse the inventory", "GET /api/processes")],
        }

    if intent == PROTECTED_INVENTORY:
        rows = [
            _row(
                it,
                status="informational",
                reason=it.process_control.blocked_reason or "Protected by process-control policy.",
            )
            for it in process_items_from_scan(latest_scan)
            if it.protected
            or it.process_control.category is ProcessControlCategory.essential
            or it.process_control.action_policy is ActionPolicy.blocked
        ]
        return {
            **base,
            "summary": (
                f"{len(rows)} item(s) are locked. These are essential or hard-protected — the backend "
                "will not offer an action for them, with or without confirmation."
            ),
            "blocked": rows,
            "actions": [_action("none", "See the safety summary", "GET /api/safety/summary")],
        }

    return {
        **base,
        "summary": "Preview-only assistant. Try: " + "; ".join(f"“{e}”" for e in _HELP_EXAMPLES),
        "actions": [_action("none", "Browse the inventory", "GET /api/processes")],
    }
