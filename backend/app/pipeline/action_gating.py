from __future__ import annotations

from app.engine.protected_registry import (
    is_hard_protected_process,
    is_protected_windows_service,
    suspend_allowed_by_policy,
)
from app.models.enums import ActionPolicy, ProcessControlCategory
from app.models.scan_item import ProvenanceRecord, ScanItem, utc_now_iso
from app.models.schemas import ItemType, RiskBucket

def apply_action_gating(item: ScanItem) -> ScanItem:
    """
    Final authority: cleanup_eligible / performance_eligible / protected flags.
    Does not change bucket (rules already decided).
    """
    protected = item.bucket == RiskBucket.risky_system_critical
    evidence: list[str] = []

    if item.item_type == ItemType.process and is_hard_protected_process(item.raw_name):
        protected = True
        evidence.append("hard_protected_process_registry")

    if item.item_type == ItemType.service and is_protected_windows_service(item.raw_name):
        protected = True
        evidence.append("protected_windows_service")

    if item.intelligence and item.intelligence.rules_protect:
        protected = True
        evidence.append("intelligence_rules_protect_stub")

    cleanup_eligible = False
    if item.item_type == ItemType.file_or_folder and not protected:
        if item.bucket == RiskBucket.safe_to_remove:
            cleanup_eligible = True
            evidence.append("bucket_safe_to_remove")
        elif item.bucket == RiskBucket.probably_safe:
            cleanup_eligible = True
            evidence.append("bucket_probably_safe_requires_confirm")

    performance_eligible = False
    if item.item_type == ItemType.process and not protected:
        ok, reason = suspend_allowed_by_policy(item.raw_name, explicit_target_basenames=frozenset())
        if ok:
            performance_eligible = True
            evidence.append(f"performance_policy:{reason}")
        else:
            evidence.append(f"performance_blocked:{reason}")

    # Gating may only tighten the classifier, never widen it: anything protected here is
    # blocked in process_control too, even if the classifier reached a softer verdict.
    pc = item.process_control
    if protected and pc.applicable and pc.action_policy is not ActionPolicy.blocked:
        pc = pc.model_copy(
            update={
                "category": ProcessControlCategory.essential,
                "action_policy": ActionPolicy.blocked,
                "safe_to_end": False,
                "safe_to_suspend": False,
                "safe_to_disable_startup": False,
                "blocked_reason": pc.blocked_reason or "Protected — no automated stop, suspend, or disable.",
                "evidence": [*pc.evidence, "action_gating:protected_clamp"],
            }
        )

    rec_warnings = list(item.recommendations.warnings)
    if protected:
        rec_warnings.append("Protected — no automated stop, suspend, or delete.")
    if item.bucket == RiskBucket.unknown and item.intelligence and not item.intelligence.known:
        rec_warnings.append("Unknown item — verify publisher before any change.")

    prov = ProvenanceRecord(
        stage="action_gating",
        decided_by="action_gating",
        evidence=evidence,
        confidence=item.confidence,
    )

    ts = dict(item.timestamps)
    ts["action_gated_at"] = utc_now_iso()

    return item.model_copy(
        update={
            "protected": protected,
            "cleanup_eligible": cleanup_eligible,
            "performance_eligible": performance_eligible,
            "process_control": pc,
            "recommendations": item.recommendations.model_copy(
                update={
                    "primary": item.recommendations.primary
                    or (item.intelligence.recommended_action if item.intelligence else None),
                    "warnings": rec_warnings,
                }
            ),
            "provenance": [*item.provenance, prov],
            "timestamps": ts,
        }
    )