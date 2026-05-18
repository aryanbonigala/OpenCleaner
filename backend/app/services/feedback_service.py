from __future__ import annotations

import hashlib

from app.db import db_conn
from app.models.schemas import ScoredItem


def fingerprint_item(item: ScoredItem) -> str:
    raw = f"{item.item_type.value}|{item.name}|{item.path or ''}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def record_feedback(item: ScoredItem, decision: str, weight: float = 1.0) -> None:
    fp = fingerprint_item(item)
    if decision not in ("keep", "remove", "ignore"):
        raise ValueError("invalid decision")
    async with await db_conn() as db:
        await db.execute(
            "INSERT INTO user_feedback (item_fingerprint, decision, weight) VALUES (?, ?, ?)",
            (fp, decision, float(weight)),
        )
        await db.commit()


async def feedback_nudge_for(item: ScoredItem) -> float:
    fp = fingerprint_item(item)
    async with await db_conn() as db:
        cur = await db.execute(
            """
            SELECT AVG(
              CASE decision
                WHEN 'remove' THEN -12.0
                WHEN 'keep' THEN 12.0
                ELSE 0.0
              END * weight
            ) FROM user_feedback WHERE item_fingerprint = ?
            """,
            (fp,),
        )
        row = await cur.fetchone()
        if row is None or row[0] is None:
            return 0.0
        return float(row[0])
