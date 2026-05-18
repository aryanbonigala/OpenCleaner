from __future__ import annotations

import json

import pytest

from app.engine.ml_ranker import optional_sklearn_blend, train_synthetic_calibrator_if_available
from app.engine.rules_engine import classify_item, merge_rules_into_item
from app.models.scan_item import ExplanationBlock, SCAN_SCHEMA_VERSION, ScanItem
from app.models.schemas import ItemType, RiskBucket, ScoredItem
from app.pipeline.adapters import scored_from_scan_item
from app.pipeline.normalize import normalize_scored_item
from app.pipeline.reasoning import run_reasoning_pipeline, stage_rules
from app.pipeline.serialize import serialize_scan_result, serialize_scan_result_object
from app.services.intelligence_service import apply_intelligence
from app.models.scan_item import CanonicalScanResult, CanonicalScanSummary
from app.models.schemas import PermissionMode


def _proc(name: str = "Discord.exe", **detail) -> ScoredItem:
    return ScoredItem(
        id="p-test",
        category="processes",
        item_type=ItemType.process,
        name=name,
        path="C:\\x\\" + name,
        detail={"memory_mb": 50.0, **detail},
        rule_bucket=RiskBucket.unknown,
        confidence=0.45,
        reasoning="scanner placeholder",
    )


def test_normalize_produces_canonical_shape() -> None:
    item = normalize_scored_item(_proc())
    assert item.scan_version == SCAN_SCHEMA_VERSION
    assert item.raw_name == "Discord.exe"
    assert item.display_name == "Discord.exe"
    assert item.source == "processes"
    assert "normalized_at" in item.timestamps


def test_pipeline_provenance_stages() -> None:
    base = normalize_scored_item(_proc())
    out = run_reasoning_pipeline(base, allow=[], block=[])
    stages = [p.stage for p in out.provenance]
    assert stages == ["rules", "intelligence", "ml", "explanation", "action_gating"]


def test_rules_precedence_over_intelligence_bucket() -> None:
    base = normalize_scored_item(
        ScoredItem(
            id="l1",
            category="processes",
            item_type=ItemType.process,
            name="lsass.exe",
            path=None,
            detail={},
            rule_bucket=RiskBucket.unknown,
            confidence=0.5,
            reasoning="",
        )
    )
    ruled = stage_rules(base, [], [])
    assert ruled.bucket == RiskBucket.risky_system_critical
    out = run_reasoning_pipeline(ruled, allow=[], block=[])
    assert out.bucket == RiskBucket.risky_system_critical
    assert out.protected is True


def test_intelligence_does_not_downgrade_risky() -> None:
    scored = ScoredItem(
        id="l2",
        category="processes",
        item_type=ItemType.process,
        name="lsass.exe",
        path=None,
        detail={},
        rule_bucket=RiskBucket.risky_system_critical,
        confidence=0.98,
        reasoning="protected",
    )
    enriched = apply_intelligence(scored)
    assert enriched.rule_bucket == RiskBucket.risky_system_critical


def test_ml_enrichment_does_not_change_bucket() -> None:
    item = ScanItem(
        id="m1",
        scan_version=SCAN_SCHEMA_VERSION,
        item_type=ItemType.process,
        source="processes",
        display_name="x",
        raw_name="x.exe",
        bucket=RiskBucket.ask_user,
        confidence=0.7,
        explanation=ExplanationBlock(summary="test"),
    )
    before = item.bucket
    scored = scored_from_scan_item(item)
    model = train_synthetic_calibrator_if_available()
    ranked = optional_sklearn_blend(scored, model)
    assert ranked.rule_bucket == before


def test_deterministic_serialization_stable() -> None:
    base = normalize_scored_item(_proc())
    a = run_reasoning_pipeline(base, allow=[], block=[])
    b = run_reasoning_pipeline(base, allow=[], block=[])
    # Clear timestamps for compare — they differ by second
    a_ts = a.model_copy(update={"timestamps": {}})
    b_ts = b.model_copy(update={"timestamps": {}})
    result_a = CanonicalScanResult(
        summary=CanonicalScanSummary(
            scan_id="s1",
            platform="test",
            mode=PermissionMode.read_only,
            items_count=1,
            buckets={a_ts.bucket.value: 1},
            generated_at="2000-01-01T00:00:00+00:00",
        ),
        items=[a_ts],
    )
    result_b = CanonicalScanResult(
        summary=CanonicalScanSummary(
            scan_id="s1",
            platform="test",
            mode=PermissionMode.read_only,
            items_count=1,
            buckets={b_ts.bucket.value: 1},
            generated_at="2000-01-01T00:00:00+00:00",
        ),
        items=[b_ts],
    )
    s1 = serialize_scan_result(result_a)
    s2 = serialize_scan_result(result_b)
    assert s1 == s2
    obj = serialize_scan_result_object(result_a)
    json.dumps(obj)  # export-safe


def test_unknown_not_cleanup_eligible() -> None:
    base = normalize_scored_item(
        ScoredItem(
            id="u1",
            category="processes",
            item_type=ItemType.process,
            name="UnknownProc999.exe",
            path=None,
            detail={},
            rule_bucket=RiskBucket.unknown,
            confidence=0.4,
            reasoning="",
        )
    )
    out = run_reasoning_pipeline(base, allow=[], block=[])
    assert out.cleanup_eligible is False
    assert out.intelligence is not None
    assert out.intelligence.known is False
