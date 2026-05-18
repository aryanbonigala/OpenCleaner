from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.schemas import ItemType, RiskBucket, ScoredItem


@dataclass(frozen=True)
class RulesResult:
    bucket: RiskBucket
    confidence: float
    reasoning: str


CRITICAL_PROCESS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(csrss|smss|wininit|services|lsass|svchost|system|secure system)\.exe$", re.I),
    re.compile(r"^(winlogon|fontdrvhost|dwm|audiodg|sihost|taskhostw|regsvr32)\.exe$", re.I),
    re.compile(r"(?i)antimalware|defender|msmpeng|securityhealthservice"),
    re.compile(r"(?i)easyanti|battleye|vac|nprotect|xigncode"),
    re.compile(r"(?i)nvd?display|nvcontainer|nvidia|amdow|atieclxx|radeon"),
    re.compile(r"(?i)rtkaud|realtek|windows\.old"),
)


CRITICAL_SERVICE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)^(rpcss|samss|lsass|dcomlaunch|plugplay|schedule|windefend)$"),
    re.compile(r"(?i)audio|hidserv|wlan|bthserv|cryptsvc|wudf"),
)

CRITICAL_PATH_PREFIXES: tuple[str, ...] = (
    r"c:\windows\system32",
    r"c:\windows\syswow64",
    r"c:\windows\winsxs",
    r"c:\program files\windows defender",
)


def _norm_path(p: str | None) -> str:
    if not p:
        return ""
    return p.replace("/", "\\").lower()


def is_critical_process(name: str) -> bool:
    base = name.split("\\")[-1].split("/")[-1]
    return any(p.search(base) for p in CRITICAL_PROCESS_PATTERNS)


def is_critical_service(name: str) -> bool:
    return any(p.search(name.strip()) for p in CRITICAL_SERVICE_PATTERNS)


def is_critical_path(path: str | None) -> bool:
    np = _norm_path(path)
    return any(np.startswith(pref) for pref in CRITICAL_PATH_PREFIXES)


def classify_item(item: ScoredItem, allow_patterns: list[str], block_patterns: list[str]) -> RulesResult:
    """Deterministic rules layer — always runs before ML."""

    name_l = item.name.lower()
    path_l = (item.path or "").lower()

    for b in block_patterns:
        if b and (b.lower() in name_l or (bool(item.path) and b.lower() in path_l)):
            return RulesResult(
                RiskBucket.risky_system_critical,
                0.95,
                "User or policy blocklist marks this pattern as protected or intentionally retained.",
            )

    if item.item_type == ItemType.process and is_critical_process(item.name):
        return RulesResult(
            RiskBucket.risky_system_critical,
            0.98,
            "Heuristic match against core OS, security, anti-cheat, or audio/GPU driver stacks.",
        )

    if item.item_type == ItemType.service and is_critical_service(item.name):
        return RulesResult(
            RiskBucket.risky_system_critical,
            0.95,
            "Service name matches core Windows, networking, audio, or security subsystem.",
        )

    if item.item_type == ItemType.file_or_folder and is_critical_path(item.path):
        return RulesResult(
            RiskBucket.risky_system_critical,
            0.99,
            "Path is under a Windows system directory that must not be moved or deleted.",
        )

    for a in allow_patterns:
        if a and (a.lower() in name_l or (item.path and a.lower() in path_l)):
            return RulesResult(
                RiskBucket.ask_user,
                0.55,
                "Allowlist match — user has marked this as important; confirmation still recommended.",
            )

    if item.item_type == ItemType.startup_entry:
        if any(x in name_l for x in ("onedrive", "spotify", "discord", "steam", "epic")):
            return RulesResult(
                RiskBucket.ask_user,
                0.72,
                "Common user-facing auto-start; disabling may affect convenience but is usually reversible.",
            )
        if "windows" in path_l or "microsoft" in path_l:
            return RulesResult(
                RiskBucket.unknown,
                0.55,
                "Microsoft-signed or Windows-integrated start-up; disabling can affect updates or UX.",
            )

    if item.item_type == ItemType.file_or_folder and item.detail.get("category_hint") == "temp_cache":
        if item.detail.get("locked"):
            return RulesResult(
                RiskBucket.ask_user,
                0.68,
                "Temporary/cache path appears locked or in use; cleanup should be deferred or retried.",
            )
        return RulesResult(
            RiskBucket.safe_to_remove,
            0.86,
            "Ephemeral cache/temp paths are standard assisted-clean targets with low permanence risk.",
        )

    if item.item_type == ItemType.file_or_folder and item.detail.get("category_hint") == "installer_residual":
        return RulesResult(
            RiskBucket.probably_safe,
            0.74,
            "Looks like an installer/unpack residual under user-writable locations; verify before removal.",
        )

    if item.item_type == ItemType.duplicate_group:
        return RulesResult(
            RiskBucket.probably_safe,
            0.62,
            "Duplicate files detected by hash; keeping one canonical copy is usually sufficient.",
        )

    if item.item_type == ItemType.browser_profile:
        return RulesResult(
            RiskBucket.ask_user,
            0.60,
            "Browser cache can be large but clearing logs you out of some sites; confirm in assisted mode.",
        )

    if item.item_type == ItemType.orphan_app:
        return RulesResult(
            RiskBucket.ask_user,
            0.58,
            "Orphaned application remnants — could be shared libraries; assisted cleanup should quarantine.",
        )

    if item.item_type == ItemType.scheduled_task:
        if any(x in name_l for x in ("defender", "windows", "microsoft", "winsxs")):
            return RulesResult(
                RiskBucket.risky_system_critical,
                0.88,
                "Task name suggests OS maintenance or security scheduling; do not disable without research.",
            )
        return RulesResult(
            RiskBucket.unknown,
            0.50,
            "Scheduled task purpose varies; read the XML/action before changes.",
        )

    if item.item_type == ItemType.service:
        return RulesResult(
            RiskBucket.unknown,
            0.52,
            "Generic Windows service — impact depends on start mode and dependencies; use Explain This.",
        )

    if item.item_type == ItemType.process:
        mem_mb = float(item.detail.get("memory_mb") or 0)
        if mem_mb > 800:
            return RulesResult(
                RiskBucket.unknown,
                0.48,
                f"High memory footprint (~{mem_mb:.0f} MB) — may be useful (browser) or leaky; investigate before action.",
            )
        return RulesResult(
            RiskBucket.unknown,
            0.45,
            "User-mode process without strong heuristics — classification needs context.",
        )

    return RulesResult(
        RiskBucket.unknown,
        0.40,
        "No strong deterministic rule fired; ML-assisted ranking and user review recommended.",
    )


def merge_rules_into_item(item: ScoredItem, rules: RulesResult) -> ScoredItem:
    data = item.model_dump()
    data["rule_bucket"] = rules.bucket
    data["confidence"] = max(0.0, min(1.0, rules.confidence))
    data["reasoning"] = rules.reasoning
    return ScoredItem.model_validate(data)
