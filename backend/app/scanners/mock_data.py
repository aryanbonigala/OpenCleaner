from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from app.models.schemas import ItemType, RiskBucket, ScoredItem
from app.platform.detect import os_friendly_name


def load_mock_scan(json_path: Path | None = None) -> list[dict[str, Any]]:
    base = json_path or Path(__file__).resolve().parent.parent.parent / "data" / "sample_scan.json"
    if not base.exists():
        return []
    data = json.loads(base.read_text(encoding="utf-8"))
    return list(data.get("items", []))


def raw_to_scored(raw: dict[str, Any]) -> ScoredItem:
    return ScoredItem(
        id=str(raw.get("id") or uuid.uuid4()),
        category=str(raw.get("category") or "mock"),
        item_type=ItemType(str(raw.get("item_type") or "process")),
        name=str(raw.get("name") or "unknown"),
        path=raw.get("path"),
        detail=dict(raw.get("detail") or {}),
        rule_bucket=RiskBucket(str(raw.get("rule_bucket") or "unknown")),
        confidence=float(raw.get("confidence") or 0.5),
        reasoning=str(raw.get("reasoning") or "Mock dataset entry."),
    )


def platform_label() -> str:
    return os_friendly_name()
