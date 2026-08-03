from __future__ import annotations

from app.models.scan_item import (
    SCAN_SCHEMA_VERSION,
    ExplanationBlock,
    ItemMetrics,
    ScanItem,
    utc_now_iso,
)
from app.models.schemas import ScoredItem
from app.pipeline.adapters import _intel_from_detail


def normalize_scored_item(scored: ScoredItem, *, scan_version: int | None = None) -> ScanItem:
    """
    Convert raw scanner output (legacy ScoredItem) into canonical ScanItem.
    No classification — only structural normalization.
    """
    detail = dict(scored.detail or {})
    intel = _intel_from_detail(detail)
    vendor = intel.vendor if intel else None
    category = scored.category if scored.category != "mock" else (intel.category if intel else scored.category)
    subtype = str(detail.get("category_hint") or detail.get("source") or "") or None

    metrics = ItemMetrics(
        memory_mb=_f(detail.get("memory_mb")),
        cpu_percent=_f(detail.get("cpu_percent")),
        size_mb=_f(detail.get("size_mb")),
    )

    facts = {k: v for k, v in detail.items() if k != "intelligence"}

    display = str(detail.get("display_name") or scored.name)

    return ScanItem(
        id=scored.id,
        scan_version=scan_version or scored.detail.get("scan_version") or SCAN_SCHEMA_VERSION,
        item_type=scored.item_type,
        source=scored.category,
        subtype=subtype,
        display_name=display,
        raw_name=scored.name,
        path=scored.path,
        vendor=vendor,
        category=category,
        metrics=metrics,
        intelligence=intel,
        bucket=scored.rule_bucket,
        risk_level="unknown",
        protected=False,
        cleanup_eligible=False,
        performance_eligible=False,
        explanation=ExplanationBlock(summary=scored.reasoning or ""),
        timestamps={"normalized_at": utc_now_iso()},
        scanner_facts=facts,
        confidence=float(scored.confidence),
    )


def _f(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
