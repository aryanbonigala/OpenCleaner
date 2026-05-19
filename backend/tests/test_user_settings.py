"""User settings persistence, validation, and safety enforcement (v0.4.2)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.actions.cleanup_preview import preview_cleanup_items
from app.engine.rules_engine import is_critical_path
from app.main import app
from app.models.enums import ItemType, RiskBucket
from app.models.scan_item import ScanItem
from app.models.user_settings import CleanupMode, RiskVisibility, UserSettings
from app.services.selection_policy import default_selected_ids
from app.services.settings_service import default_settings, load_settings, reset_settings, save_settings


def _file_item(
    item_id: str,
    *,
    bucket: RiskBucket = RiskBucket.safe_to_remove,
    path: str = r"C:\Temp\junk.tmp",
) -> ScanItem:
    return ScanItem(
        id=item_id,
        item_type=ItemType.file_or_folder,
        source="filesystem",
        display_name="junk.tmp",
        raw_name="junk.tmp",
        path=path,
        bucket=bucket,
        risk_level="low",
        cleanup_eligible=True,
        confidence=0.9,
        scanner_facts={"category_hint": "temp_cache"},
    )


@pytest.fixture
def client():
    return TestClient(app)


def test_default_settings_are_safe():
    s = default_settings()
    assert s.cleanup_mode == CleanupMode.quarantine_only
    assert s.risk_visibility == RiskVisibility.basic
    assert s.scanner_toggles.files is True
    assert s.scanner_toggles.browser is True
    assert s.scanner_toggles.startup is True
    assert s.scanner_toggles.tasks is True
    assert s.scanner_toggles.performance is True
    assert s.retention_days() is None


def test_settings_persist(settings_memory_store):
    asyncio.run(save_settings({"risk_visibility": "advanced", "cleanup_mode": "quarantine_only"}))
    loaded = asyncio.run(load_settings())
    assert loaded.risk_visibility == RiskVisibility.advanced
    assert loaded.cleanup_mode == CleanupMode.quarantine_only


def test_settings_validation_rejects_invalid_values(settings_memory_store):
    with pytest.raises(ValueError):
        asyncio.run(save_settings({"cleanup_mode": "delete_everything"}))


def test_reset_settings_restores_safe_defaults(settings_memory_store):
    asyncio.run(save_settings({"risk_visibility": "advanced"}))
    asyncio.run(reset_settings())
    loaded = asyncio.run(load_settings())
    assert loaded.risk_visibility == RiskVisibility.basic
    assert loaded.cleanup_mode == CleanupMode.quarantine_only


def test_advanced_mode_does_not_auto_select_dangerous_items():
    items = [
        _file_item("safe", bucket=RiskBucket.safe_to_remove),
        _file_item("unknown", bucket=RiskBucket.unknown),
        _file_item("critical", bucket=RiskBucket.risky_system_critical),
    ]
    basic = default_settings()
    advanced = UserSettings(risk_visibility=RiskVisibility.advanced)
    assert default_selected_ids(items, basic) == {"safe"}
    assert default_selected_ids(items, advanced) == {"safe"}


def test_settings_cannot_disable_blocked_path_protection():
    critical = r"C:\Windows\System32\kernel32.dll"
    assert is_critical_path(critical)
    item = _file_item("c1", path=critical, bucket=RiskBucket.safe_to_remove)
    payload = preview_cleanup_items(
        [item],
        confirm_medium_risk=True,
        include_recycle_bin=False,
        settings=UserSettings(risk_visibility=RiskVisibility.advanced),
    )
    assert payload["items"][0]["status"] == "blocked"


def test_quarantine_only_blocks_recycle_bin_in_api(client, settings_memory_store):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.json()["cleanup_mode"] == "quarantine_only"
    with patch("app.main.latest_scan_from_db", new=AsyncMock(return_value=None)):
        r2 = client.post(
            "/api/cleanup/preview",
            json={"item_ids": ["a"], "confirm_medium_risk": False, "include_recycle_bin": True},
        )
    assert r2.status_code == 400


def test_settings_api_reset(client, settings_memory_store):
    client.put("/api/settings", json={"risk_visibility": "advanced"})
    r = client.post("/api/settings/reset")
    assert r.status_code == 200
    assert r.json()["risk_visibility"] == "basic"
