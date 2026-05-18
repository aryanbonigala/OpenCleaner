from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from app.config import get_settings
from app.db import db_conn
from app.utils.fs import sha256_file


async def quarantine_path(src: Path, meta: dict) -> str:
    settings = get_settings()
    settings.quarantine_dir.mkdir(parents=True, exist_ok=True)
    qid = str(uuid.uuid4())
    dst_dir = settings.quarantine_dir / qid
    dst_dir.mkdir(parents=True, exist_ok=True)

    dst = dst_dir / src.name
    shutil.move(str(src), str(dst))

    h = None
    try:
        h = sha256_file(dst)
    except OSError:
        h = None

    meta_path = dst_dir / "meta.json"
    payload = {
        "id": qid,
        "original_path": str(src),
        "quarantine_path": str(dst),
        "hash_sha256": h,
        "meta": meta,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async with await db_conn() as db:
        await db.execute(
            """
            INSERT INTO quarantine_entries (id, original_path, quarantine_path, hash_sha256, size_bytes, meta_json, restored)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (
                qid,
                str(src),
                str(dst),
                h,
                dst.stat().st_size if dst.exists() else None,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        await db.commit()
    return qid


async def restore_quarantine(qid: str) -> None:
    settings = get_settings()
    entry_dir = settings.quarantine_dir / qid
    meta_path = entry_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError("missing meta")
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    original = Path(str(payload["original_path"]))
    current = Path(str(payload["quarantine_path"]))
    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(current), str(original))

    async with await db_conn() as db:
        await db.execute(
            "UPDATE quarantine_entries SET restored = 1 WHERE id = ?",
            (qid,),
        )
        await db.commit()
    shutil.rmtree(entry_dir, ignore_errors=True)


async def list_quarantine() -> list[dict]:
    async with await db_conn() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, original_path, quarantine_path, size_bytes, restored, created_at FROM quarantine_entries ORDER BY id DESC LIMIT 200"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
