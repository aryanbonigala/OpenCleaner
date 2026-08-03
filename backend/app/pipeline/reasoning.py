from __future__ import annotations

from typing import Any

from app.engine.ml_ranker import optional_sklearn_blend, train_synthetic_calibrator_if_available
from app.engine.process_classifier import stage_process_control
from app.engine.rules_engine import classify_item, merge_rules_into_item
from app.models.scan_item import (
    ExplanationBlock,
    IntelligenceSnapshot,
    ProvenanceRecord,
    Recommendations,
    ScanItem,
    utc_now_iso,
)
from app.models.schemas import ItemType, RiskBucket, ScoredItem
from app.pipeline.action_gating import apply_action_gating
from app.pipeline.adapters import apply_ml_metrics_only, apply_scored_engine_fields, scored_from_scan_item
from app.services.intelligence_service import apply_intelligence

_sklearn_model = train_synthetic_calibrator_if_available()


def _append_provenance(
    item: ScanItem,
    *,
    stage: str,
    decided_by: str,
    evidence: list[str],
    confidence: float | None = None,
    matched_rule: str | None = None,
    matched_intelligence_entry: str | None = None,
    ml_score_source: str | None = None,
) -> ScanItem:
    rec = ProvenanceRecord(
        stage=stage,
        decided_by=decided_by,
        evidence=evidence,
        matched_rule=matched_rule,
        matched_intelligence_entry=matched_intelligence_entry,
        ml_score_source=ml_score_source,
        confidence=confidence,
    )
    return item.model_copy(update={"provenance": [*item.provenance, rec]})


def stage_rules(item: ScanItem, allow: list[str], block: list[str]) -> ScanItem:
    scored = scored_from_scan_item(item)
    rules = classify_item(scored, allow, block)
    merged = merge_rules_into_item(scored, rules)
    updated = apply_scored_engine_fields(item, merged)
    protected = merged.rule_bucket == RiskBucket.risky_system_critical
    return _append_provenance(
        updated.model_copy(update={"protected": protected}),
        stage="rules",
        decided_by="rules_engine",
        evidence=[rules.reasoning],
        confidence=rules.confidence,
        matched_rule=rules.bucket.value,
    )


def stage_intelligence(item: ScanItem) -> ScanItem:
    before_bucket = item.bucket
    scored = scored_from_scan_item(item)
    enriched = apply_intelligence(scored)
    updated = apply_scored_engine_fields(item, enriched)

    intel_raw = enriched.detail.get("intelligence") if isinstance(enriched.detail.get("intelligence"), dict) else {}
    match_kind = intel_raw.get("match_kind")
    entry_name = intel_raw.get("name")

    evidence = ["intelligence_enrichment"]
    if match_kind:
        evidence.append(f"match:{match_kind}")
    if updated.bucket != before_bucket and before_bucket != RiskBucket.risky_system_critical:
        evidence.append(f"bucket:{before_bucket.value}->{updated.bucket.value}")

    rec_primary = None
    warnings: list[str] = []
    if updated.intelligence:
        rec_primary = updated.intelligence.recommended_action
        if updated.intelligence.warning_if_changed:
            warnings.append(str(updated.intelligence.warning_if_changed))

    return _append_provenance(
        updated.model_copy(
            update={
                "recommendations": Recommendations(primary=rec_primary, warnings=warnings),
                "timestamps": {**updated.timestamps, "intelligence_at": utc_now_iso()},
            }
        ),
        stage="intelligence",
        decided_by="intelligence_service",
        evidence=evidence,
        confidence=updated.confidence,
        matched_intelligence_entry=str(entry_name) if entry_name else None,
    )


def stage_ml(item: ScanItem, model: Any | None = None) -> ScanItem:
    scored = scored_from_scan_item(item)
    ranked = optional_sklearn_blend(scored, model if model is not None else _sklearn_model)
    updated = apply_ml_metrics_only(item, ranked)
    source = "sklearn_blend" if model is not None else "heuristic_ml_ranker"
    return _append_provenance(
        updated.model_copy(update={"timestamps": {**updated.timestamps, "ml_at": utc_now_iso()}}),
        stage="ml",
        decided_by="ml_ranker",
        evidence=["ranking_only_no_bucket_change"],
        ml_score_source=source,
        confidence=updated.confidence,
    )


def stage_explanation(item: ScanItem) -> ScanItem:
    headline_parts: list[str] = []
    if item.vendor:
        headline_parts.append(item.vendor)
    if item.category:
        headline_parts.append(item.category)
    headline = " · ".join(headline_parts) if headline_parts else None

    summary = item.explanation.summary
    if item.intelligence and item.intelligence.plain_english_description and "Intelligence" not in summary:
        if item.bucket != RiskBucket.risky_system_critical:
            pass  # summary already merged during intelligence stage

    expl = ExplanationBlock(summary=summary, headline=headline)
    return _append_provenance(
        item.model_copy(
            update={
                "explanation": expl,
                "timestamps": {**item.timestamps, "explained_at": utc_now_iso()},
            }
        ),
        stage="explanation",
        decided_by="explanation_synthesis",
        evidence=["synthesized_from_rules_intelligence_ml"],
        confidence=item.confidence,
    )


def run_reasoning_pipeline(
    item: ScanItem,
    *,
    allow: list[str],
    block: list[str],
    ml_model: Any | None = None,
    feedback_nudge: float = 0.0,
) -> ScanItem:
    """
    Deterministic stage order:
    rules → intelligence → ML (metrics only) → explanation → process control → action gating
    """
    out = stage_rules(item, allow, block)
    out = stage_intelligence(out)
    out = stage_ml(out, ml_model)

    if feedback_nudge != 0.0 and out.metrics.rank_usefulness is not None:
        new_use = float(max(0.0, min(100.0, out.metrics.rank_usefulness + feedback_nudge)))
        metrics = out.metrics.model_copy(update={"rank_usefulness": new_use})
        out = out.model_copy(
            update={
                "metrics": metrics,
                "explanation": ExplanationBlock(
                    summary=out.explanation.summary + f" (local feedback nudge {feedback_nudge:+.1f})",
                    headline=out.explanation.headline,
                ),
            }
        )
        out = _append_provenance(
            out,
            stage="feedback",
            decided_by="feedback_service",
            evidence=[f"nudge:{feedback_nudge:+.1f}"],
        )

    out = stage_explanation(out)
    out = stage_process_control(out)
    out = apply_action_gating(out)
    return out


def scan_item_from_stored_payload(
    row: dict[str, Any],
    *,
    allow: list[str],
    block: list[str],
) -> ScanItem:
    """Rehydrate from DB: prefer embedded canonical JSON, else legacy columns."""
    detail = row.get("detail") or {}
    if isinstance(detail, str):
        import json

        detail = json.loads(detail)
    canonical = detail.get("canonical") if isinstance(detail, dict) else None
    if isinstance(canonical, dict):
        return ScanItem.model_validate(canonical)

    legacy = ScoredItem(
        id=str(row["id"]),
        category=str(row.get("category") or "unknown"),
        item_type=ItemType(str(row["item_type"])),
        name=str(row.get("name") or ""),
        path=row.get("path"),
        detail={k: v for k, v in detail.items() if k != "canonical"} if isinstance(detail, dict) else {},
        rule_bucket=row.get("rule_bucket", RiskBucket.unknown),
        confidence=float(row.get("confidence") or 0.5),
        reasoning=str(row.get("reasoning") or ""),
        ml_rank_score=float(row["ml_score"]) if row.get("ml_score") is not None else None,
    )
    from app.pipeline.normalize import normalize_scored_item

    base = normalize_scored_item(legacy)
    return run_reasoning_pipeline(base, allow=allow, block=block)
