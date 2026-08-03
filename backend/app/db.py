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
        from app.services.settings_service import default_settings

        defaults = default_settings().model_dump_json()
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('user_preferences_v1', ?)",
            (defaults,),
        )
        await db.commit()


async def db_conn(settings: Settings | None = None) -> aiosqlite.Connection:
    """Return an *unstarted* connection; callers own its lifecycle.

    Must not be awaited into a live connection here: `aiosqlite.Connection.__aenter__`
    awaits the connection itself, which starts its worker thread. Pre-awaiting would
    start that thread once here and again at the call site, raising
    "RuntimeError: threads can only be started once" and leaking the worker.

    Always use as: `async with await db_conn() as db:` — `__aexit__` closes it.
    """
    settings = settings or get_settings()
    return aiosqlite.connect(settings.database_path)


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
    from app.services.settings_service import load_settings
    from app.utils.audit_detail import sanitize_audit_detail

    prefs = await load_settings()
    safe_detail = sanitize_audit_detail(detail, prefs.logging_mode)
    async with await db_conn() as db:
        await db.execute(
            """
            INSERT INTO audit_log (action, mode, actor, detail_json, success, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (action, mode, actor, json.dumps(safe_detail, ensure_ascii=False), int(success), error),
        )
        await db.commit()
