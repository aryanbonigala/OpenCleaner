from __future__ import annotations

import sys

import psutil

from app.models.schemas import ItemType, RiskBucket, ScoredItem
from app.platform.detect import OSFamily, detect_os


def _windows_services_psutil() -> list[ScoredItem]:
    items: list[ScoredItem] = []
    try:
        for s in psutil.win_service_iter():  # type: ignore[attr-defined]
            try:
                info = s.as_dict()
            except Exception:
                continue
            name = str(info.get("name") or "")
            display = str(info.get("display_name") or "")
            start_type = str(info.get("start_type") or "")
            items.append(
                ScoredItem(
                    id=f"svc-{name}",
                    category="services",
                    item_type=ItemType.service,
                    name=name,
                    path=None,
                    detail={
                        "display_name": display,
                        "start_type": start_type,
                        "status": info.get("status"),
                        "username": info.get("username"),
                    },
                    rule_bucket=RiskBucket.unknown,
                    confidence=0.5,
                    reasoning="Windows service — verify dependencies before changes.",
                )
            )
    except Exception:
        return items
    return items


def _generic_services_stub() -> list[ScoredItem]:
    return [
        ScoredItem(
            id="svc-stub-platform",
            category="services",
            item_type=ItemType.service,
            name="PlatformServiceScanPending",
            path=None,
            detail={
                "display_name": "Non-Windows services scan requires platform module",
                "start_type": "unknown",
            },
            rule_bucket=RiskBucket.unknown,
            confidence=0.3,
            reasoning="Place-holder on non-Windows until platform adapters ship.",
        )
    ]


def scan_services() -> list[ScoredItem]:
    if detect_os() == OSFamily.windows and sys.platform == "win32":
        return _windows_services_psutil()
    return _generic_services_stub()
