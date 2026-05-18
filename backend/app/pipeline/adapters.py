from __future__ import annotations

from typing import Any

from app.models.scan_item import (
    ExplanationBlock,
    IntelligenceSnapshot,
    ItemMetrics,
    Recommendations,
    ScanItem,
)
from app.models.schemas import ItemType, RiskBucket, ScoredItem


def _intel_from_detail(detail: dict[str, Any]) -> IntelligenceSnapshot | None:
    raw = detail.get("intelligence")
    if not isinstance(raw, dict):
        return None
    known = raw.get("known")
    snap = IntelligenceSnapshot(
        known=bool(known) if known is not None else False,
        applicable=raw.get("applicable", True) is not False,
        match_kind=raw.get("match_kind"),
        name=raw.get("name"),
        vendor=raw.get("vendor"),
        category=raw.get("category"),
        plain_english_description=raw.get("plain_english_description"),
        safe_to_stop=raw.get("safe_to_stop"),
        safe_to_disable_startup=raw.get("safe_to_disable_startup"),
        safe_to_delete=raw.get("safe_to_delete"),
        gaming_impact=raw.get("gaming_impact"),
        memory_impact=raw.get("memory_impact"),
        startup_impact=raw.get("startup_impact"),
        risk_level=raw.get("risk_level"),
        confidence=raw.get("confidence"),
        warning_if_changed=raw.get("warning_if_changed"),
        recommended_action=raw.get("recommended_action"),
        rules_protect=bool(raw.get("rules_protect")),
    )
    extra = {k: v for k, v in raw.items() if k not in snap.model_dump()}
    if extra:
        snap.extra = extra
    return snap


def scored_from_scan_item(item: ScanItem) -> ScoredItem:
    """Adapter for rules / intelligence / ML engines (legacy ScoredItem input)."""
    detail = dict(item.scanner_facts)
    if item.intelligence is not None:
        intel_dump = item.intelligence.model_dump()
        intel_dump.pop("extra", None)
        if item.intelligence.extra:
            intel_dump.update(item.intelligence.extra)
        detail["intelligence"] = intel_dump
    return ScoredItem(
        id=item.id,
        category=item.source,
        item_type=item.item_type,
        name=item.raw_name,
        path=item.path,
        detail=detail,
        rule_bucket=item.bucket,
        confidence=item.confidence,
        reasoning=item.explanation.summary,
        ml_rank_score=item.metrics.ml_rank_score,
        rank_startup_impact=item.metrics.rank_startup_impact,
        rank_memory_impact=item.metrics.rank_memory_impact,
        rank_cpu_impact=item.metrics.rank_cpu_impact,
        rank_gpu_impact=item.metrics.rank_gpu_impact,
        rank_gaming_impact=item.metrics.rank_gaming_impact,
        rank_deletion_risk=item.metrics.rank_deletion_risk,
        rank_usefulness=item.metrics.rank_usefulness,
    )


def _risk_level_from_intel(intel: IntelligenceSnapshot | None, bucket: RiskBucket) -> str:
    if intel and intel.risk_level:
        return str(intel.risk_level).lower()
    if bucket == RiskBucket.risky_system_critical:
        return "critical"
    if bucket == RiskBucket.unknown:
        return "unknown"
    return "medium"


def apply_ml_metrics_only(item: ScanItem, scored: ScoredItem) -> ScanItem:
    """ML stage may only update ranking metrics — never bucket or explanation."""
    return item.model_copy(
        update={
            "metrics": item.metrics.model_copy(
                update={
                    "ml_rank_score": scored.ml_rank_score,
                    "rank_startup_impact": scored.rank_startup_impact,
                    "rank_memory_impact": scored.rank_memory_impact,
                    "rank_cpu_impact": scored.rank_cpu_impact,
                    "rank_gpu_impact": scored.rank_gpu_impact,
                    "rank_gaming_impact": scored.rank_gaming_impact,
                    "rank_deletion_risk": scored.rank_deletion_risk,
                    "rank_usefulness": scored.rank_usefulness,
                }
            ),
        }
    )


def apply_scored_engine_fields(item: ScanItem, scored: ScoredItem) -> ScanItem:
    """Merge engine outputs back into canonical item (does not touch provenance)."""
    intel = _intel_from_detail(scored.detail)
    vendor = item.vendor
    category = item.category
    if intel:
        vendor = vendor or intel.vendor
        category = category or intel.category

    metrics = item.metrics.model_copy(
        update={
            "memory_mb": scored.detail.get("memory_mb", item.metrics.memory_mb),
            "cpu_percent": scored.detail.get("cpu_percent", item.metrics.cpu_percent),
            "size_mb": scored.detail.get("size_mb", item.metrics.size_mb),
            "ml_rank_score": scored.ml_rank_score,
            "rank_startup_impact": scored.rank_startup_impact,
            "rank_memory_impact": scored.rank_memory_impact,
            "rank_cpu_impact": scored.rank_cpu_impact,
            "rank_gpu_impact": scored.rank_gpu_impact,
            "rank_gaming_impact": scored.rank_gaming_impact,
            "rank_deletion_risk": scored.rank_deletion_risk,
            "rank_usefulness": scored.rank_usefulness,
        }
    )

    facts = {k: v for k, v in scored.detail.items() if k != "intelligence"}

    return item.model_copy(
        update={
            "bucket": scored.rule_bucket,
            "confidence": scored.confidence,
            "explanation": ExplanationBlock(summary=scored.reasoning, headline=item.explanation.headline),
            "intelligence": intel if intel is not None else item.intelligence,
            "vendor": vendor,
            "category": category,
            "risk_level": _risk_level_from_intel(intel, scored.rule_bucket),
            "metrics": metrics,
            "scanner_facts": facts,
        }
    )
