"""Read-only Process Control API — inventory, PID lookup, preview-end (no execution)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import psutil
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import ActionPolicy, ItemType, PermissionMode, ProcessControlCategory, RiskBucket
from app.models.scan_item import ProcessControl, ScanItem
from app.models.schemas import ScanResult, ScanSummary
from app.services import scan_state


def _proc(
    item_id: str,
    pid: int,
    *,
    category: ProcessControlCategory,
    policy: ActionPolicy,
    safe_to_suspend: bool = False,
    item_type: ItemType = ItemType.process,
    blocked_reason: str | None = None,
) -> ScanItem:
    return ScanItem(
        id=item_id,
        item_type=item_type,
        source="processes",
        display_name=item_id,
        raw_name=f"{item_id}.exe",
        path=rf"C:\Apps\{item_id}.exe",
        bucket=RiskBucket.unknown,
        scanner_facts={"pid": pid},
        process_control=ProcessControl(
            applicable=True,
            category=category,
            action_policy=policy,
            safe_to_suspend=safe_to_suspend,
            blocked_reason=blocked_reason,
            evidence=["test:seeded"],
        ),
    )


def _file_item(item_id: str) -> ScanItem:
    return ScanItem(
        id=item_id,
        item_type=ItemType.file_or_folder,
        source="filesystem",
        display_name="junk.tmp",
        raw_name="junk.tmp",
        path=r"C:\Temp\junk.tmp",
        bucket=RiskBucket.safe_to_remove,
    )


ESSENTIAL = _proc(
    "lsass",
    4,
    category=ProcessControlCategory.essential,
    policy=ActionPolicy.blocked,
    blocked_reason="Hard-protected security stack.",
)
UNKNOWN = _proc("abcxyz", 4410, category=ProcessControlCategory.unknown, policy=ActionPolicy.report_only)
SUSPENDABLE = _proc(
    "spotify",
    9134,
    category=ProcessControlCategory.non_essential,
    policy=ActionPolicy.preview_required,
    safe_to_suspend=True,
)
EXPLICIT = _proc(
    "discord",
    9140,
    category=ProcessControlCategory.gaming_fps_impact,
    policy=ActionPolicy.explicit_selection_required,
    safe_to_suspend=True,
)
SERVICE = _proc(
    "audiosrv",
    0,
    category=ProcessControlCategory.important,
    policy=ActionPolicy.report_only,
    item_type=ItemType.service,
)

ALL_ITEMS = [ESSENTIAL, UNKNOWN, SUSPENDABLE, EXPLICIT, SERVICE, _file_item("junk-1")]


def _scan(items: list[ScanItem]) -> ScanResult:
    return ScanResult(
        summary=ScanSummary(
            scan_id="proc-scan-1",
            platform="win32",
            mode=PermissionMode.read_only,
            items_count=len(items),
            buckets={},
            generated_at="2026-01-01T00:00:00+00:00",
            scanner_warnings=["services scanner partial"],
        ),
        items=items,
    )


@pytest.fixture
def client():
    scan_state.reset_for_tests()
    return TestClient(app)


def _with_scan(scan: ScanResult | None):
    return patch("app.main.latest_scan_from_db", new=AsyncMock(return_value=scan))


def test_inventory_without_scan_returns_message(client):
    with _with_scan(None):
        r = client.get("/api/processes")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["scan_id"] is None
    assert "run a scan" in body["message"].lower()


def test_inventory_excludes_non_process_item_types(client):
    with _with_scan(_scan(ALL_ITEMS)):
        r = client.get("/api/processes")
    body = r.json()
    types = {it["item_type"] for it in body["items"]}
    assert types <= {"process", "service", "startup_entry", "scheduled_task"}
    assert "junk-1" not in {it["id"] for it in body["items"]}
    assert body["items_count"] == 5
    assert body["warnings"] == ["services scanner partial"]


def test_inventory_groups_counts_by_process_control_category(client):
    with _with_scan(_scan(ALL_ITEMS)):
        r = client.get("/api/processes")
    assert r.json()["counts"] == {
        "essential": 1,
        "unknown": 1,
        "non_essential": 1,
        "gaming_fps_impact": 1,
        "important": 1,
    }


def test_process_detail_by_pid(client):
    with _with_scan(_scan(ALL_ITEMS)):
        r = client.get("/api/processes/9134")
    assert r.status_code == 200
    body = r.json()
    assert body["item"]["id"] == "spotify"
    assert body["process_control"]["category"] == "non_essential"
    assert body["scanner_facts"]["pid"] == 9134


def test_process_detail_missing_pid_is_404(client):
    with _with_scan(_scan(ALL_ITEMS)):
        r = client.get("/api/processes/999999")
    assert r.status_code == 404


def test_preview_end_blocks_essential(client):
    with _with_scan(_scan(ALL_ITEMS)):
        r = client.post("/api/processes/preview-end", json={"item_ids": ["lsass"]})
    row = r.json()["items"][0]
    assert row["status"] == "blocked"
    assert row["recommended_action"] == "blocked"


def test_preview_end_blocks_unknown_and_report_only(client):
    with _with_scan(_scan(ALL_ITEMS)):
        r = client.post("/api/processes/preview-end", json={"item_ids": ["abcxyz", "audiosrv"]})
    body = r.json()
    assert body["counts"]["blocked"] == 2
    assert body["counts"]["would_allow"] == 0


def test_preview_end_requires_explicit_confirmation(client):
    with _with_scan(_scan(ALL_ITEMS)):
        blocked = client.post("/api/processes/preview-end", json={"item_ids": ["discord"]}).json()
        allowed = client.post(
            "/api/processes/preview-end",
            json={"item_ids": ["discord"], "confirm_explicit_selection": True},
        ).json()
    assert blocked["items"][0]["status"] == "blocked"
    assert allowed["items"][0]["status"] == "would_allow"
    assert allowed["items"][0]["recommended_action"] == "suspend_preview_only"


def test_preview_end_skips_unknown_ids_and_reports_counts(client):
    with _with_scan(_scan(ALL_ITEMS)):
        r = client.post("/api/processes/preview-end", json={"item_ids": ["nope", "spotify", "lsass"]})
    body = r.json()
    assert body["preview_id"] is None
    assert body["counts"] == {"selected": 3, "would_allow": 1, "blocked": 1, "skipped": 1}
    assert body["disclaimer"] == "Preview only. No process was ended, suspended, or modified."


def test_preview_end_never_mutates_os_state(client, monkeypatch):
    def boom(*_a, **_kw):
        raise AssertionError("preview-end must not touch live processes")

    for name in ("kill", "terminate", "suspend", "resume"):
        monkeypatch.setattr(psutil.Process, name, boom, raising=False)
    monkeypatch.setattr(psutil, "process_iter", boom)

    with _with_scan(_scan(ALL_ITEMS)):
        r = client.post(
            "/api/processes/preview-end",
            json={"item_ids": [i.id for i in ALL_ITEMS], "confirm_explicit_selection": True},
        )
    assert r.status_code == 200
    assert r.json()["counts"]["would_allow"] == 2


def test_process_end_is_not_implemented(client):
    r = client.post("/api/processes/end", json={})
    assert r.status_code == 501
    assert r.json()["detail"] == "Process execution is not implemented yet. Use preview endpoints only."
