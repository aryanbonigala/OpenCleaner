from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.actions.quarantine import list_quarantine
from app.db import append_audit, db_conn
from app.models.user_settings import UserSettings


async def apply_quarantine_retention(settings: UserSettings) -> dict[str, int]:
    """
    Remove quarantine DB rows (and files) older than retention policy.
    manual_only performs no automatic purge.
    """
    days = settings.retention_days()
    if days is None:
        return {"purged": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entries = await list_quarantine()
    purged = 0
    async with await db_conn() as db:
        for entry in entries:
            if entry.get("restored"):
                continue
            created_raw = str(entry.get("created_at", ""))
            try:
                created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if created > cutoff:
                continue
            qid = str(entry["id"])
            qpath = str(entry.get("quarantine_path", ""))
            await db.execute("DELETE FROM quarantine_entries WHERE id = ?", (qid,))
            if qpath:
                from pathlib import Path

                try:
                    Path(qpath).unlink(missing_ok=True)
                except OSError:
                    pass
            purged += 1
        await db.commit()

    if purged:
        await append_audit(
            "quarantine_retention_purge",
            "assisted",
            {"purged": purged, "retention_days": days},
            success=True,
        )
    return {"purged": purged}
