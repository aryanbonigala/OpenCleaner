from __future__ import annotations

import json
import os
import uuid
from typing import Any

import aiosqlite

from app.db import append_audit, db_conn
from app.engine.ml_ranker import optional_sklearn_blend, train_synthetic_calibrator_if_available
from app.engine.rules_engine import classify_item, merge_rules_into_item
from app.models.schemas import ItemType, PermissionMode, RiskBucket, ScoredItem, ScanResult, ScanSummary
from app.platform.detect import os_friendly_name
from app.scanners.browser import scan_browser_profiles
from app.scanners.files import (
    scan_desktop_clutter,
    scan_downloads,
    scan_duplicates_limited,
    scan_large_unused_candidates,
    scan_orphans_lightweight,
    scan_temp_and_cache,
)
from app.scanners.mock_data import load_mock_scan, raw_to_scored
from app.scanners.processes import scan_processes
from app.scanners.services import scan_services
from app.scanners.startup import scan_startup
from app.scanners.tasks import scan_scheduled_tasks
from app.services.feedback_service import feedback_nudge_for


_sklearn_model = train_synthetic_calibrator_if_available()


async def _load_lists() -> tuple[list[str], list[str]]:
    async with await db_conn() as db:
        db.row_factory = aiosqlite.Row
        allow: list[str] = []
        block: list[str] = []
        try:
            cur = await db.execute("SELECT pattern FROM allowlist")
            allow = [str(r[0]) for r in await cur.fetchall()]
        except Exception:
            allow = []
        try:
            cur = await db.execute("SELECT pattern FROM blocklist")
            block = [str(r[0]) for r in await cur.fetchall()]
        except Exception:
            block = []
    return allow, block


def _env_use_mock() -> bool:
    return os.environ.get("OPENCLEANER_USE_MOCK", "").lower() in ("1", "true", "yes")


async def run_full_scan(mode: PermissionMode) -> ScanResult:
    allow, block = await _load_lists()
    scan_id = str(uuid.uuid4())
    platform = os_friendly_name()

    raw_items: list[ScoredItem] = []

    if _env_use_mock():
        raw_items.extend(raw_to_scored(x) for x in load_mock_scan())
    else:
        try:
            raw_items.extend(scan_processes())
        except Exception:
            pass
        try:
            raw_items.extend(scan_services())
        except Exception:
            pass
        try:
            raw_items.extend(scan_startup())
        except Exception:
            pass
        try:
            raw_items.extend(scan_scheduled_tasks())
        except Exception:
            pass
        try:
            raw_items.extend(scan_temp_and_cache())
        except Exception:
            pass
        try:
            raw_items.extend(scan_downloads())
        except Exception:
            pass
        try:
            raw_items.extend(scan_desktop_clutter())
        except Exception:
            pass
        try:
            raw_items.extend(scan_browser_profiles())
        except Exception:
            pass
        try:
            raw_items.extend(scan_duplicates_limited())
        except Exception:
            pass
        try:
            raw_items.extend(scan_large_unused_candidates())
        except Exception:
            pass
        try:
            raw_items.extend(scan_orphans_lightweight())
        except Exception:
            pass

    if not raw_items and not _env_use_mock():
        raw_items.extend(raw_to_scored(x) for x in load_mock_scan())

    finalized: list[ScoredItem] = []
    for it in raw_items:
        rules = classify_item(it, allow, block)
        merged = merge_rules_into_item(it, rules)
        ranked = optional_sklearn_blend(merged, _sklearn_model)
        nudge = await feedback_nudge_for(ranked)
        if nudge != 0.0 and ranked.rank_usefulness is not None:
            ranked = ranked.model_copy(
                update={
                    "rank_usefulness": float(max(0.0, min(100.0, ranked.rank_usefulness + nudge))),
                    "reasoning": ranked.reasoning + f" (local feedback nudge {nudge:+.1f})",
                }
            )
        finalized.append(ranked)

    buckets: dict[str, int] = {}
    for it in finalized:
        buckets[it.rule_bucket.value] = buckets.get(it.rule_bucket.value, 0) + 1

    summary = ScanSummary(
        scan_id=scan_id,
        platform=platform,
        mode=mode,
        items_count=len(finalized),
        buckets=buckets,
        disk_usage_sample=_disk_snapshot(),
    )

    await _persist_scan(scan_id, platform, mode.value, finalized, summary)

    await append_audit(
        "scan_completed",
        mode.value,
        {"scan_id": scan_id, "items": len(finalized)},
        success=True,
    )

    return ScanResult(summary=summary, items=finalized)


def _disk_snapshot() -> dict[str, Any]:
    try:
        import psutil  # noqa: WPS433

        parts = []
        for p in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(p.mountpoint)
                parts.append(
                    {
                        "mount": p.mountpoint,
                        "device": p.device,
                        "fstype": p.fstype,
                        "percent": u.percent,
                        "free_gb": round(u.free / (1024**3), 2),
                        "total_gb": round(u.total / (1024**3), 2),
                    }
                )
            except Exception:
                continue
        return {"partitions": parts}
    except Exception:
        return {"partitions": []}


async def _persist_scan(scan_id: str, platform: str, mode: str, items: list[ScoredItem], summary: ScanSummary) -> None:
    async with await db_conn() as db:
        await db.execute(
            """
            INSERT INTO scans (id, platform, mode, started_at, finished_at, summary_json)
            VALUES (?, ?, ?, datetime('now'), datetime('now'), ?)
            """,
            (scan_id, platform, mode, summary.model_dump_json()),
        )
        for it in items:
            detail_json = json.dumps(it.detail, ensure_ascii=False)
            await db.execute(
                """
                INSERT INTO scan_items (
                  id, scan_id, category, item_type, name, path, detail_json,
                  rule_bucket, ml_score, confidence, reasoning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    it.id,
                    scan_id,
                    it.category,
                    it.item_type.value,
                    it.name,
                    it.path,
                    detail_json,
                    it.rule_bucket.value,
                    float(it.ml_rank_score or 0.0),
                    float(it.confidence),
                    it.reasoning,
                ),
            )
        await db.commit()


async def latest_scan_from_db() -> ScanResult | None:
    async with await db_conn() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, platform, mode, summary_json FROM scans ORDER BY finished_at DESC LIMIT 1"
        )
        row = await cur.fetchone()
        if row is None:
            return None
        scan_id = str(row["id"])
        platform = str(row["platform"])
        mode = PermissionMode(str(row["mode"]))
        summary_dict = json.loads(str(row["summary_json"] or "{}"))
        cur2 = await db.execute(
            """
            SELECT category, item_type, name, path, detail_json, rule_bucket, ml_score, confidence, reasoning, id
            FROM scan_items WHERE scan_id = ?
            """,
            (scan_id,),
        )
        rows = await cur2.fetchall()
        items: list[ScoredItem] = []
        for r in rows:
            detail = json.loads(str(r["detail_json"] or "{}"))
            items.append(
                ScoredItem(
                    id=str(r["id"]),
                    category=str(r["category"]),
                    item_type=ItemType(str(r["item_type"])),
                    name=str(r["name"]),
                    path=str(r["path"]) if r["path"] else None,
                    detail=detail,
                    rule_bucket=RiskBucket(str(r["rule_bucket"])),
                    ml_rank_score=float(r["ml_score"] or 0.0),
                    confidence=float(r["confidence"]),
                    reasoning=str(r["reasoning"]),
                )
            )
        allow, block = await _load_lists()
        restored: list[ScoredItem] = []
        for it in items:
            rules = classify_item(it, allow, block)
            merged = merge_rules_into_item(it, rules)
            restored.append(optional_sklearn_blend(merged, _sklearn_model))
        summary = ScanSummary(
            scan_id=scan_id,
            platform=platform or str(summary_dict.get("platform", "unknown")),
            mode=mode,
            items_count=len(restored),
            buckets=dict(summary_dict.get("buckets", {})),
            disk_usage_sample=summary_dict.get("disk_usage_sample"),
        )
        return ScanResult(summary=summary, items=restored)
