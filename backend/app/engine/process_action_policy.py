from __future__ import annotations

"""
Single source of truth for the `process_control` block.

Hard-deny decisions are delegated to `app.engine.protected_registry` — this module
must never carry its own copy of the protected patterns.

Two standing rules for this layer:

* When uncertain, classify `unknown` / `report_only`. Never `safe`.
* `safe_to_end` and `safe_to_disable_startup` are **never** granted here. There is no
  end or startup-disable flow yet; granting the flag before the guarded execution path
  exists would be the flag lying. Suspension is reversible, so `safe_to_suspend` may be
  granted — the actual suspend still passes `suspend_allowed_by_policy()` at action time.
"""

from app.engine.protected_registry import (
    is_browser_or_shell_executable,
    is_hard_protected_process,
    is_protected_windows_service,
)
from app.models.enums import ActionPolicy, ItemType, ProcessControlCategory, RiskBucket
from app.models.scan_item import PROCESS_CONTROL_ITEM_TYPES, IntelligenceSnapshot, ProcessControl, ScanItem

# Intelligence categories whose failure breaks the machine, the session, or a game's
# anti-cheat. Mirrors `_CRITICAL_INTEL_CATEGORIES` in intelligence_service plus the
# stacks the protected registry already guards by name.
_ESSENTIAL_INTEL_CATEGORIES: frozenset[str] = frozenset(
    {
        "Windows core",
        "Windows shell",
        "Windows graphics",
        "Security",
        "GPU driver",
        "Audio",
        "Anticheat",
    }
)

_GAMING_IMPACT_LEVELS: frozenset[str] = frozenset({"medium", "high", "critical"})

_SERVICE_REPORT_ONLY_NOTE = "services are report-only in Process Control MVP"
_STARTUP_REPORT_ONLY_NOTE = "no safe startup-disable flow exists yet — report only"
_TASK_REPORT_ONLY_NOTE = "scheduled tasks are report-only in Process Control MVP"
_SUSPEND_GATE_NOTE = "suspend still gated by protected_registry.suspend_allowed_by_policy at action time"


def _s(v: str | None) -> str:
    return str(v or "").strip().lower()


def _intel(item: ScanItem) -> IntelligenceSnapshot | None:
    intel = item.intelligence
    return intel if intel is not None and intel.applicable else None


def _names(item: ScanItem) -> tuple[str, ...]:
    """Names worth testing against the protected registry (startup rows carry the exe in `path`)."""
    return tuple(n for n in (item.raw_name, item.display_name, item.path) if n)


def _hard_protected(item: ScanItem) -> bool:
    return any(is_hard_protected_process(n) for n in _names(item))


def _intel_is_essential(intel: IntelligenceSnapshot | None) -> str | None:
    """Reason string when intelligence itself demands essential treatment, else None."""
    if intel is None or not intel.known:
        return None
    risk = _s(intel.risk_level)
    category = str(intel.category or "")
    if category in _ESSENTIAL_INTEL_CATEGORIES:
        return f"intelligence category {category}"
    if risk == "critical":
        return "intelligence risk_level critical"
    return None


def _impacts(item: ScanItem, intel: IntelligenceSnapshot | None) -> dict[str, str | None]:
    return {
        "fps_impact": _s(intel.gaming_impact) or None if intel else None,
        "memory_impact": _s(intel.memory_impact) or None if intel else None,
        "cpu_impact": None,
    }


def _block(
    item: ScanItem,
    *,
    category: ProcessControlCategory,
    reason: str,
    evidence: list[str],
    confidence: float,
) -> ProcessControl:
    intel = _intel(item)
    return ProcessControl(
        applicable=True,
        category=category,
        action_policy=ActionPolicy.blocked,
        blocked_reason=reason,
        user_visible_summary=(intel.plain_english_description if intel else None),
        confidence=confidence,
        evidence=evidence,
        **_impacts(item, intel),
    )


def _report_only(
    item: ScanItem,
    *,
    category: ProcessControlCategory,
    evidence: list[str],
    confidence: float,
) -> ProcessControl:
    intel = _intel(item)
    return ProcessControl(
        applicable=True,
        category=category,
        action_policy=ActionPolicy.report_only,
        user_visible_summary=(intel.plain_english_description if intel else None),
        confidence=confidence,
        evidence=evidence,
        **_impacts(item, intel),
    )


def _classify_process(item: ScanItem) -> ProcessControl:
    intel = _intel(item)

    if _hard_protected(item):
        return _block(
            item,
            category=ProcessControlCategory.essential,
            reason=(
                "Hard-protected by the OS/security/driver registry — core Windows, security or "
                "anti-cheat, GPU driver, audio, networking, input, or servicing stack. Stopping it "
                "can break sign-in, sound, network, display, or flag a game's anti-cheat."
            ),
            evidence=["protected_registry:is_hard_protected_process"],
            confidence=0.97,
        )

    if item.bucket is RiskBucket.risky_system_critical:
        return _block(
            item,
            category=ProcessControlCategory.essential,
            reason="Rules engine classified this as system-critical.",
            evidence=["rules:risky_system_critical"],
            confidence=0.95,
        )

    if intel is not None and intel.rules_protect:
        return _block(
            item,
            category=ProcessControlCategory.essential,
            reason="Marked safety-critical by rules — no automated stop or suspend.",
            evidence=["intelligence:rules_protect"],
            confidence=0.9,
        )

    essential_reason = _intel_is_essential(intel)
    if essential_reason:
        return _block(
            item,
            category=ProcessControlCategory.essential,
            reason=(
                f"{essential_reason} — OS, security, anti-cheat, GPU driver, or audio stack. "
                "Not controllable from OpenCleaner."
            ),
            evidence=[f"intelligence:{essential_reason}"],
            confidence=0.9,
        )

    if is_browser_or_shell_executable(item.raw_name):
        pc = _report_only(
            item,
            category=ProcessControlCategory.important,
            evidence=["protected_registry:browser_or_shell_requires_explicit_selection"],
            confidence=0.8,
        )
        return pc.model_copy(
            update={
                "action_policy": ActionPolicy.explicit_selection_required,
                "blocked_reason": (
                    "Browsers and the Windows shell are never selected automatically — you must "
                    "name this process explicitly."
                ),
            }
        )

    if intel is not None and intel.known:
        risk = _s(intel.risk_level)
        gaming = _s(intel.gaming_impact) in _GAMING_IMPACT_LEVELS

        if risk == "high":
            return _report_only(
                item,
                category=ProcessControlCategory.important,
                evidence=["intelligence:risk_level=high"],
                confidence=0.85,
            )

        if intel.safe_to_stop is False:
            pc = _report_only(
                item,
                category=(
                    ProcessControlCategory.gaming_fps_impact if gaming else ProcessControlCategory.important
                ),
                evidence=["intelligence:safe_to_stop=false"],
                confidence=0.8,
            )
            return pc.model_copy(update={"action_policy": ActionPolicy.explicit_selection_required})

        if intel.safe_to_stop is True and risk in ("low", "medium"):
            pc = _report_only(
                item,
                category=(
                    ProcessControlCategory.gaming_fps_impact if gaming else ProcessControlCategory.non_essential
                ),
                evidence=[
                    f"intelligence:safe_to_stop=true,risk_level={risk or 'unknown'}",
                    _SUSPEND_GATE_NOTE,
                ],
                confidence=float(intel.confidence or 0.7),
            )
            return pc.model_copy(
                update={
                    "action_policy": (
                        ActionPolicy.explicit_selection_required if gaming and risk == "medium"
                        else ActionPolicy.preview_required
                    ),
                    "safe_to_suspend": True,
                }
            )

    return _report_only(
        item,
        category=ProcessControlCategory.unknown,
        evidence=["no_confident_signal:classified_unknown"],
        confidence=0.3,
    )


def _classify_service(item: ScanItem) -> ProcessControl:
    if is_protected_windows_service(item.raw_name) or item.bucket is RiskBucket.risky_system_critical:
        return _block(
            item,
            category=ProcessControlCategory.essential,
            reason="Protected Windows service (core OS, security, networking, audio, or scheduling).",
            evidence=["protected_registry:is_protected_windows_service", _SERVICE_REPORT_ONLY_NOTE],
            confidence=0.95,
        )

    intel = _intel(item)
    if _intel_is_essential(intel):
        return _block(
            item,
            category=ProcessControlCategory.essential,
            reason="Intelligence marks this service as part of a critical stack.",
            evidence=["intelligence:essential_category", _SERVICE_REPORT_ONLY_NOTE],
            confidence=0.9,
        )

    known = intel is not None and intel.known
    return _report_only(
        item,
        category=ProcessControlCategory.important if known else ProcessControlCategory.unknown,
        evidence=[
            "intelligence:known_service" if known else "no_confident_signal:classified_unknown",
            _SERVICE_REPORT_ONLY_NOTE,
        ],
        confidence=0.6 if known else 0.3,
    )


def _classify_startup_entry(item: ScanItem) -> ProcessControl:
    if _hard_protected(item) or item.bucket is RiskBucket.risky_system_critical:
        return _block(
            item,
            category=ProcessControlCategory.essential,
            reason="Startup entry points at a hard-protected OS, security, or driver binary.",
            evidence=["protected_registry:is_hard_protected_process", _STARTUP_REPORT_ONLY_NOTE],
            confidence=0.93,
        )

    intel = _intel(item)
    if _intel_is_essential(intel):
        return _block(
            item,
            category=ProcessControlCategory.essential,
            reason="Intelligence marks this startup entry as part of a critical stack.",
            evidence=["intelligence:essential_category", _STARTUP_REPORT_ONLY_NOTE],
            confidence=0.9,
        )

    if intel is not None and intel.known and _s(intel.risk_level) == "low":
        return _report_only(
            item,
            category=ProcessControlCategory.non_essential,
            evidence=["intelligence:known_low_risk_startup", _STARTUP_REPORT_ONLY_NOTE],
            confidence=float(intel.confidence or 0.7),
        )

    return _report_only(
        item,
        category=ProcessControlCategory.unknown,
        evidence=["no_confident_signal:classified_unknown", _STARTUP_REPORT_ONLY_NOTE],
        confidence=0.3,
    )


def _classify_scheduled_task(item: ScanItem) -> ProcessControl:
    intel = _intel(item)
    name = f"{item.raw_name} {item.display_name}".lower()
    microsoft = any(k in name for k in ("microsoft", "windows", "defender", "security", "winsxs"))

    if item.bucket is RiskBucket.risky_system_critical or microsoft or _intel_is_essential(intel):
        return _block(
            item,
            category=ProcessControlCategory.essential,
            reason="Microsoft/Windows or security scheduled task — disabling can break updates or protection.",
            evidence=["rules:os_or_security_task", _TASK_REPORT_ONLY_NOTE],
            confidence=0.88,
        )

    known = intel is not None and intel.known
    return _report_only(
        item,
        category=ProcessControlCategory.important if known else ProcessControlCategory.unknown,
        evidence=[
            "intelligence:known_task" if known else "no_confident_signal:classified_unknown",
            _TASK_REPORT_ONLY_NOTE,
        ],
        confidence=0.6 if known else 0.3,
    )


_BY_ITEM_TYPE = {
    ItemType.process: _classify_process,
    ItemType.service: _classify_service,
    ItemType.startup_entry: _classify_startup_entry,
    ItemType.scheduled_task: _classify_scheduled_task,
}


def classify_process_control(item: ScanItem) -> ProcessControl:
    """Map a canonical `ScanItem` onto its `process_control` block. Pure, no I/O."""
    if item.item_type not in PROCESS_CONTROL_ITEM_TYPES:
        return ProcessControl(
            applicable=False,
            category=ProcessControlCategory.not_applicable,
            action_policy=ActionPolicy.unsupported,
            evidence=[f"item_type:{item.item_type.value}:process_control_not_applicable"],
            confidence=1.0,
        )
    return _BY_ITEM_TYPE[item.item_type](item)
