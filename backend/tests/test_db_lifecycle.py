"""SQLite connection lifecycle.

Regression guard for `RuntimeError: threads can only be started once`: `db_conn()`
must hand back an *unstarted* aiosqlite connection so that the `async with` at the
call site starts its worker thread exactly once and closes it on exit.
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import db_conn, get_setting, init_db, set_setting
from app.main import app


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point every get_settings() call at a throwaway data dir (local-only, no home writes)."""
    monkeypatch.setenv("OPENCLEANER_DATA_DIR", str(tmp_path))
    assert get_settings().database_path == tmp_path / "opencleaner.db"
    yield tmp_path


def _worker_threads() -> list[str]:
    return [t.name for t in threading.enumerate() if "_connection_worker_thread" in t.name]


def test_init_db_creates_schema_and_defaults():
    asyncio.run(init_db())
    assert get_settings().database_path.exists()
    assert asyncio.run(get_setting("permission_mode")) == "read_only"


def test_db_conn_usable_by_callers():
    async def go():
        await init_db()
        async with await db_conn() as db:
            cur = await db.execute("SELECT 1")
            assert await cur.fetchone() == (1,)

    asyncio.run(go())


def test_db_conn_repeated_use_does_not_restart_thread():
    """The original bug: the second `async with` re-started an already-started thread."""

    async def go():
        await init_db()
        for i in range(5):
            await set_setting("lifecycle_probe", str(i))
            assert await get_setting("lifecycle_probe") == str(i)

    asyncio.run(go())


def test_db_conn_does_not_leak_worker_threads():
    before = len(_worker_threads())

    async def go():
        await init_db()
        for _ in range(10):
            async with await db_conn() as db:
                await db.execute("SELECT 1")

    asyncio.run(go())
    # Each connection is closed by __aexit__; threads must not accumulate per call.
    assert len(_worker_threads()) - before < 10


def test_db_backed_endpoints_work_and_are_repeatable():
    """/api/settings, /api/scan/latest and /api/processes over a fresh, scan-less DB."""
    with TestClient(app) as client:  # lifespan runs init_db()
        assert client.get("/health").status_code == 200

        for _ in range(3):  # repeat: one call per endpoint would not catch a re-start bug
            settings_res = client.get("/api/settings")
            assert settings_res.status_code == 200, settings_res.text
            assert "cleanup_mode" in settings_res.json()

            latest = client.get("/api/scan/latest")
            assert latest.status_code == 200, latest.text
            assert latest.json() is None  # no scan recorded yet

            procs = client.get("/api/processes")
            assert procs.status_code == 200, procs.text
            assert procs.json()["items"] == []
