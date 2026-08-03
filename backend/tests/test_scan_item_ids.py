"""Scan item id identity.

Regression guard for `sqlite3.IntegrityError: UNIQUE constraint failed: scan_items.id`
on POST /api/scan. Scanner ids are deterministic per item ("proc-421",
"dl-report.pdf-3"), so the *second* scan of the same machine re-inserted ids the first
scan had already stored: on this repo's dev box 320 of 328 fresh ids collided with
previously persisted rows. Row identity is (scan_id, id); duplicates *within* one scan
are still a scanner bug and must fail loudly before any INSERT.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import scanners
from app.config import get_settings
from app.db import db_conn, init_db
from app.main import app
from app.models.enums import ItemType, RiskBucket
from app.models.scan_item import ScanItem
from app.models.schemas import PermissionMode, ScanSummary
from app.services.scan_service import _persist_scan, assert_unique_scan_item_ids


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLEANER_DATA_DIR", str(tmp_path))
    assert get_settings().database_path == tmp_path / "opencleaner.db"
    yield tmp_path


def _item(item_id: str, **overrides) -> ScanItem:
    data = {
        "id": item_id,
        "item_type": ItemType.process,
        "source": "processes",
        "display_name": item_id,
        "raw_name": f"{item_id}.exe",
        "path": f"/usr/bin/{item_id}",
        "bucket": RiskBucket.unknown,
        "scanner_facts": {"pid": 421},
    }
    data.update(overrides)
    return ScanItem(**data)


def _summary(scan_id: str) -> ScanSummary:
    return ScanSummary(
        scan_id=scan_id,
        platform="test",
        mode=PermissionMode.read_only,
        items_count=1,
        buckets={},
    )


async def _seed_scan(scan_id: str, items: list[ScanItem]) -> None:
    await _persist_scan(scan_id, "test", "read_only", items, _summary(scan_id))


# --- the reproduced failure -------------------------------------------------


def test_same_item_ids_persist_across_two_scans():
    """Two back-to-back scans of an unchanged machine reuse every item id."""
    items = [_item("proc-421"), _item("dl-report.pdf-3", item_type=ItemType.file_or_folder)]

    async def go():
        await init_db()
        await _seed_scan("scan-one", items)
        await _seed_scan("scan-two", items)
        async with await db_conn() as db:
            cur = await db.execute("SELECT scan_id, id FROM scan_items ORDER BY scan_id, id")
            return await cur.fetchall()

    rows = asyncio.run(go())
    assert rows == [
        ("scan-one", "dl-report.pdf-3"),
        ("scan-one", "proc-421"),
        ("scan-two", "dl-report.pdf-3"),
        ("scan-two", "proc-421"),
    ]


def test_same_id_twice_within_one_scan_still_rejected():
    async def go():
        await init_db()
        await _seed_scan("scan-one", [_item("proc-421")])
        async with await db_conn() as db:
            await db.execute(
                "INSERT INTO scan_items (id, scan_id, category, item_type, name, "
                "detail_json, rule_bucket, confidence, reasoning) "
                "VALUES ('proc-421', 'scan-one', 'processes', 'process', 'x', '{}', "
                "'unknown', 0.5, 'x')"
            )

    with pytest.raises(sqlite3.IntegrityError):
        asyncio.run(go())


def test_legacy_single_column_pk_is_migrated_and_rows_kept(isolated_db):
    """A DB created before the fix keeps its rows and gains the composite key."""
    db_path = isolated_db / "opencleaner.db"
    legacy = sqlite3.connect(db_path)
    legacy.executescript(
        """
        CREATE TABLE scans (id TEXT PRIMARY KEY, platform TEXT NOT NULL,
          mode TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
          summary_json TEXT, error TEXT);
        CREATE TABLE scan_items (
          id TEXT PRIMARY KEY,
          scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
          category TEXT NOT NULL, item_type TEXT NOT NULL, name TEXT NOT NULL,
          path TEXT, detail_json TEXT NOT NULL, rule_bucket TEXT NOT NULL,
          ml_score REAL, confidence REAL NOT NULL, reasoning TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now')));
        INSERT INTO scans (id, platform, mode, started_at)
          VALUES ('old-scan', 'test', 'read_only', '2026-01-01T00:00:00Z');
        INSERT INTO scan_items (id, scan_id, category, item_type, name, detail_json,
          rule_bucket, confidence, reasoning)
          VALUES ('proc-421', 'old-scan', 'processes', 'process', 'old', '{}',
                  'unknown', 0.5, 'seeded');
        """
    )
    legacy.commit()
    legacy.close()

    async def go():
        await init_db()
        await _seed_scan("new-scan", [_item("proc-421")])

    asyncio.run(go())

    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT scan_id, id, name FROM scan_items ORDER BY scan_id").fetchall()
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    con.close()
    assert rows == [("new-scan", "proc-421", "proc-421.exe"), ("old-scan", "proc-421", "old")]
    assert "scan_items_legacy" not in tables


# --- the guardrail ----------------------------------------------------------


def test_guardrail_passes_on_unique_ids():
    assert_unique_scan_item_ids([_item("proc-1"), _item("proc-2"), _item("svc-sshd")])


def test_guardrail_reports_duplicates_with_context():
    a = _item("launchd-com.example.thing", path="/Library/LaunchAgents/x.plist")
    b = _item(
        "launchd-com.example.thing",
        item_type=ItemType.startup_entry,
        source="startup",
        path="/Users/me/Library/LaunchAgents/x.plist",
        raw_name="com.example.thing",
    )
    with pytest.raises(ValueError) as exc:
        assert_unique_scan_item_ids([a, _item("proc-9"), b])
    msg = str(exc.value)
    assert "launchd-com.example.thing" in msg
    assert "/Library/LaunchAgents/x.plist" in msg
    assert "/Users/me/Library/LaunchAgents/x.plist" in msg
    assert "startup_entry" in msg and "startup" in msg
    assert "proc-9" not in msg


def test_persist_scan_rejects_duplicates_before_touching_the_db():
    async def go():
        await init_db()
        with pytest.raises(ValueError, match="Duplicate scan item ids"):
            await _seed_scan("scan-one", [_item("proc-421"), _item("proc-421")])
        async with await db_conn() as db:
            cur = await db.execute("SELECT COUNT(*) FROM scans")
            scans = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM scan_items")
            return scans, (await cur.fetchone())[0]

    assert asyncio.run(go()) == (0, 0)


# --- determinism ------------------------------------------------------------


def test_no_scanner_builds_ids_from_the_salted_builtin_hash():
    """`hash()` on a str is salted per process, so `large-{hash(path)}` gave the same
    file a brand new id on every scan — ids must come from a stable digest."""
    offenders = [
        p.name
        for p in Path(scanners.__file__).parent.glob("*.py")
        if re.search(r"(?<![\w.])hash\(", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


# --- end to end -------------------------------------------------------------


def test_two_consecutive_scans_over_the_api_both_succeed(monkeypatch):
    monkeypatch.setenv("OPENCLEANER_USE_MOCK", "1")
    with TestClient(app) as client:
        first = client.post("/api/scan")
        second = client.post("/api/scan")
        latest = client.get("/api/scan/latest")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["summary"]["scan_id"] != second.json()["summary"]["scan_id"]
    assert latest.json()["summary"]["scan_id"] == second.json()["summary"]["scan_id"]
    assert latest.json()["items"]
