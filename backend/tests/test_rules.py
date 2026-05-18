from __future__ import annotations

import pytest

from app.engine.rules_engine import classify_item
from app.models.schemas import ItemType, RiskBucket, ScoredItem


def test_rules_temp_cache_safe():
    item = ScoredItem(
        id="t1",
        category="temp",
        item_type=ItemType.file_or_folder,
        name="foo.tmp",
        path="C:\\Users\\x\\AppData\\Local\\Temp\\foo.tmp",
        detail={"category_hint": "temp_cache", "locked": False},
        rule_bucket=RiskBucket.unknown,
        confidence=0.5,
        reasoning="",
    )
    r = classify_item(item, [], [])
    assert r.bucket == RiskBucket.safe_to_remove


def test_rules_blocklist_wins():
    item = ScoredItem(
        id="b1",
        category="x",
        item_type=ItemType.process,
        name="notepad.exe",
        path="C:\\Windows\\notepad.exe",
        detail={},
        rule_bucket=RiskBucket.unknown,
        confidence=0.5,
        reasoning="",
    )
    r = classify_item(item, [], ["notepad.exe"])
    assert r.bucket == RiskBucket.risky_system_critical
