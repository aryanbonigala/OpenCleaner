"""Scan history retention.

Nothing used to delete from `scans`, so a local DB grew by a few hundred
`scan_items` rows every time the user pressed scan. `_persist_scan` now prunes to the
newest DEFAULT_SCAN_HISTORY_LIMIT scans and lets ON DELETE CASCADE take the items —
which only works because `db_conn()` turns foreign keys on per connection.
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import db_conn, init_db
from app.main import app
from app.models.enums import ItemType, RiskBucket
from app.models.scan_item import ScanItem
from app.models.schemas import PermissionMode, ScanSummary
from app.services.scan_service import (
    DEFAULT_SCAN_HISTORY_LIMIT,
    _persist_scan,
    latest_scan_from_db,
    prune_old_scans,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLEANER_DATA_DIR", str(tmp_path))
    assert get_settings().database_path == tmp_path / "opencleaner.db"
    yield tmp_path


def _item(item_id: str) -> ScanItem:
    return ScanItem(
        id=item_id,
        item_type=ItemType.file_or_folder,
        source="downloads",
        display_name=item_id,
        raw_name=f"{item_id}.bin",
        path=f"/tmp/{item_id}",
        bucket=RiskBucket.unknown,
        scanner_facts={},
    )


def _summary(scan_id: str) -> ScanSummary:
    return ScanSummary(
        scan_id=scan_id,
        platform="test",
        mode=PermissionMode.read_only,
        items_count=1,
        buckets={},
    )


async def _seed(scan_id: str, items: list[ScanItem] | None = None) -> None:
    items = [_item("dl-a")] if items is None else items
    await _persist_scan(scan_id, "test", "read_only", items, _summary(scan_id))


async def _scan_ids() -> list[str]:
    async with await db_conn() as db:
        cur = await db.execute("SELECT id FROM scans ORDER BY rowid")
        return [r[0] for r in await cur.fetchall()]


async def _item_scan_ids() -> set[str]:
    async with await db_conn() as db:
        cur = await db.execute("SELECT DISTINCT scan_id FROM scan_items")
        return {r[0] for r in await cur.fetchall()}


# --- foreign keys, the thing cascade depends on -----------------------------


def test_foreign_keys_are_on_for_every_connection():
    """schema.sql's PRAGMA only applied to init_db's own connection: it is per-connection."""

    async def go():
        await init_db()
        async with await db_conn() as db:
            cur = await db.execute("PRAGMA foreign_keys")
            return (await cur.fetchone())[0]

    assert asyncio.run(go()) == 1


def test_scan_items_cannot_reference_a_missing_scan():
    async def go():
        await init_db()
        async with await db_conn() as db:
            await db.execute(
                "INSERT INTO scan_items (id, scan_id, category, item_type, name, "
                "detail_json, rule_bucket, confidence, reasoning) "
                "VALUES ('x', 'no-such-scan', 'c', 'file_or_folder', 'n', '{}', "
                "'unknown', 0.5, 'r')"
            )
            await db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        asyncio.run(go())


# --- retention --------------------------------------------------------------


def test_only_the_newest_n_scans_survive():
    total = DEFAULT_SCAN_HISTORY_LIMIT + 7

    async def go():
        await init_db()
        for i in range(total):
            await _seed(f"scan-{i:03d}")
        return await _scan_ids()

    kept = asyncio.run(go())
    assert len(kept) == DEFAULT_SCAN_HISTORY_LIMIT
    assert kept == [f"scan-{i:03d}" for i in range(total - DEFAULT_SCAN_HISTORY_LIMIT, total)]


def test_items_of_pruned_scans_are_cascaded_away():
    total = DEFAULT_SCAN_HISTORY_LIMIT + 3

    async def go():
        await init_db()
        for i in range(total):
            await _seed(f"scan-{i:03d}", [_item("dl-a"), _item("dl-b")])
        return await _scan_ids(), await _item_scan_ids()

    kept, item_owners = asyncio.run(go())
    assert item_owners == set(kept)
    assert "scan-000" not in item_owners


def test_the_scan_just_persisted_is_never_pruned():
    async def go():
        await init_db()
        for i in range(DEFAULT_SCAN_HISTORY_LIMIT + 4):
            await _seed(f"scan-{i:03d}")
            # Assert after *every* insert, not just the last: a mis-ordered prune
            # would drop the newest scan the moment the window first fills up.
            assert f"scan-{i:03d}" in await _scan_ids()

    asyncio.run(go())


def test_latest_scan_from_db_still_returns_the_newest_after_pruning():
    newest = f"scan-{DEFAULT_SCAN_HISTORY_LIMIT + 5:03d}"

    async def go():
        await init_db()
        for i in range(DEFAULT_SCAN_HISTORY_LIMIT + 6):
            await _seed(f"scan-{i:03d}")
        return await latest_scan_from_db()

    result = asyncio.run(go())
    assert result is not None
    assert result.summary.scan_id == newest
    assert [i.id for i in result.items] == ["dl-a"]


def test_prune_reports_how_many_it_deleted_and_is_idempotent():
    async def go():
        await init_db()
        for i in range(6):
            await _seed(f"scan-{i:03d}")
        return await prune_old_scans(keep=4), await prune_old_scans(keep=4), await _scan_ids()

    first, second, kept = asyncio.run(go())
    assert (first, second) == (2, 0)
    assert kept == ["scan-002", "scan-003", "scan-004", "scan-005"]


def test_keep_below_one_is_rejected_rather_than_wiping_history():
    async def go():
        await init_db()
        await _seed("scan-000")
        with pytest.raises(ValueError, match="keep must be >= 1"):
            await prune_old_scans(keep=0)
        return await _scan_ids()

    assert asyncio.run(go()) == ["scan-000"]


# --- retention must not fire on a rejected scan -----------------------------


def test_duplicate_ids_abort_before_any_pruning_happens():
    """The guardrail raises before INSERT, so history must be left exactly as it was."""

    async def go():
        await init_db()
        for i in range(DEFAULT_SCAN_HISTORY_LIMIT + 2):
            await _seed(f"scan-{i:03d}")
        before = await _scan_ids()

        with pytest.raises(ValueError, match="Duplicate scan item ids"):
            await _seed("scan-bad", [_item("dl-a"), _item("dl-a")])

        return before, await _scan_ids()

    before, after = asyncio.run(go())
    assert after == before
    assert "scan-bad" not in after


# --- end to end -------------------------------------------------------------


def test_repeated_api_scans_succeed_under_retention(monkeypatch):
    monkeypatch.setenv("OPENCLEANER_USE_MOCK", "1")
    monkeypatch.setattr("app.services.scan_service.DEFAULT_SCAN_HISTORY_LIMIT", 3)

    with TestClient(app) as client:
        posted = [client.post("/api/scan") for _ in range(5)]
        latest = client.get("/api/scan/latest")

    assert [r.status_code for r in posted] == [200] * 5, [r.text for r in posted]
    newest = posted[-1].json()["summary"]["scan_id"]
    assert latest.json()["summary"]["scan_id"] == newest

    async def count():
        async with await db_conn() as db:
            cur = await db.execute("SELECT COUNT(*) FROM scans")
            return (await cur.fetchone())[0]

    assert asyncio.run(count()) == 3
