from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.engine.explain import explain_item
from app.engine.ml_ranker import optional_sklearn_blend, train_synthetic_calibrator_if_available
from app.engine.protected_registry import suspend_allowed_by_policy
from app.engine.rules_engine import classify_item, merge_rules_into_item
from app.models.schemas import ExplainRequest, ItemType, RiskBucket, ScoredItem
from app.pipeline.normalize import normalize_scored_item
from app.pipeline.reasoning import run_reasoning_pipeline, stage_intelligence, stage_rules
from app.services.intelligence_service import reload_intelligence_cache_for_tests


@pytest.fixture()
def intelligence_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "windows_intelligence.json"


@pytest.fixture(autouse=True)
def _reset_intel_cache(monkeypatch, intelligence_path: Path) -> None:
    monkeypatch.setenv("OPENCLEANER_INTELLIGENCE_JSON", str(intelligence_path))
    reload_intelligence_cache_for_tests()
    yield
    reload_intelligence_cache_for_tests()


def _model() -> object | None:
    return train_synthetic_calibrator_if_available()


def _pipeline_after_rules(scored: ScoredItem, allow: list[str], block: list[str]):
    base = normalize_scored_item(scored)
    ruled = stage_rules(base, allow, block)
    return stage_intelligence(ruled)


def test_intelligence_exact_name_match(intelligence_path: Path) -> None:
    db = json.loads(intelligence_path.read_text(encoding="utf-8"))
    assert any(e.get("name", "").lower() == "discord.exe" for e in db["entries"])
    item = ScoredItem(
        id="p1",
        category="proc",
        item_type=ItemType.process,
        name="Discord.exe",
        path=r"C:\Program Files\Discord\Discord.exe",
        detail={"memory_mb": 120.0},
        rule_bucket=RiskBucket.unknown,
        confidence=0.45,
        reasoning="User-mode process without strong heuristics — classification needs context.",
    )
    out = _pipeline_after_rules(item, [], [])
    assert out.intelligence is not None
    assert out.intelligence.known is True
    assert out.intelligence.match_kind == "exact"
    assert out.bucket == RiskBucket.ask_user
    assert "Discord" in out.explanation.summary or "Intelligence" in out.explanation.summary


def test_intelligence_alias_match_on_display_name(intelligence_path: Path) -> None:
    db = json.loads(intelligence_path.read_text(encoding="utf-8"))
    assert any("Windows Defender Antivirus" in (e.get("aliases") or []) for e in db["entries"])
    item = ScoredItem(
        id="s1",
        category="services",
        item_type=ItemType.service,
        name="SomeRandomSvcName",
        path=None,
        detail={"display_name": "Windows Defender Antivirus", "start_type": "auto"},
        rule_bucket=RiskBucket.unknown,
        confidence=0.52,
        reasoning="Generic Windows service — impact depends on start mode and dependencies; use Explain This.",
    )
    out = _pipeline_after_rules(item, [], [])
    assert out.intelligence is not None
    assert out.intelligence.known is True
    assert out.intelligence.match_kind == "alias"
    assert out.intelligence.vendor == "Microsoft"


def test_unknown_item_not_marked_safe_by_intelligence() -> None:
    item = ScoredItem(
        id="u1",
        category="proc",
        item_type=ItemType.process,
        name="TotallyUnknownVendorProcess999.exe",
        path=None,
        detail={},
        rule_bucket=RiskBucket.unknown,
        confidence=0.4,
        reasoning="Generic unknown.",
    )
    out = _pipeline_after_rules(item, [], [])
    assert out.intelligence is not None
    assert out.intelligence.known is False
    assert out.intelligence.safe_to_delete is False
    assert out.intelligence.safe_to_stop is None
    assert out.bucket == RiskBucket.unknown


def test_rules_protected_bucket_preserved_and_enriched() -> None:
    item = ScoredItem(
        id="l1",
        category="proc",
        item_type=ItemType.process,
        name="lsass.exe",
        path=None,
        detail={},
        rule_bucket=RiskBucket.unknown,
        confidence=0.5,
        reasoning="",
    )
    rules = classify_item(item, [], [])
    merged = merge_rules_into_item(item, rules)
    assert merged.rule_bucket == RiskBucket.risky_system_critical
    out = _pipeline_after_rules(item, [], [])
    assert out.bucket == RiskBucket.risky_system_critical
    assert out.intelligence is not None
    assert out.intelligence.known is True
    assert out.intelligence.name == "lsass.exe"
    assert out.intelligence.risk_level == "critical"


def test_protected_process_cannot_be_suspended() -> None:
    ok, reason = suspend_allowed_by_policy("lsass.exe", explicit_target_basenames=frozenset({"lsass.exe"}))
    assert ok is False
    assert "protected" in reason.lower()


def test_intelligence_improves_explain_text() -> None:
    item = ScoredItem(
        id="d1",
        category="proc",
        item_type=ItemType.process,
        name="Discord.exe",
        path=None,
        detail={},
        rule_bucket=RiskBucket.unknown,
        confidence=0.5,
        reasoning="",
    )
    out = run_reasoning_pipeline(normalize_scored_item(item), allow=[], block=[])
    ex = explain_item(ExplainRequest(item=out))
    assert "Discord" in ex.importance
    assert "voice" in ex.importance.lower() or "chat" in ex.importance.lower()


def test_rules_blocklist_overrides_benign_intelligence_hypothesis() -> None:
    item = ScoredItem(
        id="bl1",
        category="proc",
        item_type=ItemType.process,
        name="notepad.exe",
        path=r"C:\Windows\notepad.exe",
        detail={},
        rule_bucket=RiskBucket.unknown,
        confidence=0.5,
        reasoning="",
    )
    out = _pipeline_after_rules(item, [], ["notepad.exe"])
    assert out.bucket == RiskBucket.risky_system_critical


def test_ml_does_not_change_rule_bucket_for_risky_items() -> None:
    item = ScoredItem(
        id="m1",
        category="proc",
        item_type=ItemType.process,
        name="lsass.exe",
        path=None,
        detail={"memory_mb": 10.0},
        rule_bucket=RiskBucket.risky_system_critical,
        confidence=0.98,
        reasoning="protected",
    )
    ranked = optional_sklearn_blend(item, _model())
    assert ranked.rule_bucket == RiskBucket.risky_system_critical
