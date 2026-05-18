from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from app.config import Settings, get_settings


async def init_db(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.quarantine_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
    async with aiosqlite.connect(settings.database_path) as db:
        if schema_path.exists():
            sql = schema_path.read_text(encoding="utf-8")
            await db.executescript(sql)
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('permission_mode', 'read_only')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('telemetry', 'false')"
        )
        await db.commit()


async def db_conn(settings: Settings | None = None) -> aiosqlite.Connection:
    settings = settings or get_settings()
    return await aiosqlite.connect(settings.database_path)


async def get_setting(key: str, default: str | None = None) -> str | None:
    async with await db_conn() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cur.fetchone()
        if row is None:
            return default
        return str(row["value"])


async def set_setting(key: str, value: str) -> None:
    async with await db_conn() as db:
        await db.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
            """,
            (key, value),
        )
        await db.commit()


async def append_audit(
    action: str,
    mode: str,
    detail: dict[str, Any],
    success: bool = True,
    error: str | None = None,
    actor: str = "local_ui",
) -> None:
    async with await db_conn() as db:
        await db.execute(
            """
            INSERT INTO audit_log (action, mode, actor, detail_json, success, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (action, mode, actor, json.dumps(detail, ensure_ascii=False), int(success), error),
        )
        await db.commit()
