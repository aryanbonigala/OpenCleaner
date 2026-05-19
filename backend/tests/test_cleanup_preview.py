"""Cleanup preview and execute safety (v0.4.1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.actions.cleanup_preview import preview_cleanup_items
from app.main import app
from app.models.enums import ItemType, PermissionMode, RiskBucket
from app.models.scan_item import ScanItem
from app.models.schemas import ScanResult, ScanSummary
from app.services import scan_state
from app.services.settings_service import default_settings
from app.version import APP_VERSION


def _file_item(
    item_id: str,
    *,
    bucket: RiskBucket = RiskBucket.safe_to_remove,
    path: str = r"C:\Temp\junk.tmp",
    cleanup_eligible: bool = True,
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
        cleanup_eligible=cleanup_eligible,
        confidence=0.9,
        scanner_facts={"category_hint": "temp_cache"},
    )


def _scan_result(items: list[ScanItem]) -> ScanResult:
    buckets: dict[str, int] = {}
    for it in items:
        buckets[it.bucket.value] = buckets.get(it.bucket.value, 0) + 1
    return ScanResult(
        summary=ScanSummary(
            scan_id="test-scan-1",
            platform="win32",
            mode=PermissionMode.read_only,
            items_count=len(items),
            buckets=buckets,
        ),
        items=items,
    )


@pytest.fixture
def client():
    scan_state.reset_for_tests()
    return TestClient(app)


def test_health_exposes_version(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == APP_VERSION
    assert data["scan_in_progress"] == "false"


def test_cleanup_preview_requires_items(client):
    latest = _scan_result([_file_item("a")])
    with patch("app.main.latest_scan_from_db", new=AsyncMock(return_value=latest)):
        r = client.post("/api/cleanup/preview", json={"item_ids": []})
    assert r.status_code == 400


def test_cleanup_execute_without_preview_fails(client):
    with patch(
        "app.main.get_setting",
        new=AsyncMock(return_value=PermissionMode.assisted.value),
    ):
        r = client.post(
            "/api/cleanup/execute",
            json={
                "preview_id": "missing",
                "item_ids": ["a"],
                "confirm_medium_risk": False,
                "include_recycle_bin": False,
                "confirm_permanent_delete": False,
            },
        )
    assert r.status_code == 400
    assert "preview" in r.json()["detail"].lower()


def test_cleanup_blocked_while_scan_in_progress(client):
    latest = _scan_result([_file_item("a")])
    scan_state.begin_scan()
    try:
        with patch("app.main.latest_scan_from_db", new=AsyncMock(return_value=latest)):
            r = client.post("/api/cleanup/preview", json={"item_ids": ["a"]})
        assert r.status_code == 409
    finally:
        scan_state.end_scan()


def test_unknown_item_blocked_in_preview_unit():
    payload = preview_cleanup_items(
        [_file_item("unknown", bucket=RiskBucket.unknown)],
        confirm_medium_risk=False,
        include_recycle_bin=False,
    )
    assert payload["counts"]["blocked"] >= 1
    assert payload["items"][0]["status"] == "blocked"


def test_preview_endpoint_returns_preview_id(client):
    latest = _scan_result([_file_item("a")])
    with (
        patch("app.main.latest_scan_from_db", new=AsyncMock(return_value=latest)),
        patch("app.main.load_settings", new=AsyncMock(return_value=default_settings())),
    ):
        r = client.post("/api/cleanup/preview", json={"item_ids": ["a"]})
    assert r.status_code == 200
    body = r.json()
    assert body["preview_id"]
    assert body["scan_id"] == "test-scan-1"
