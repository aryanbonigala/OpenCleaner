from __future__ import annotations

import json
import os
import uuid
from typing import Any

import aiosqlite

from app.db import append_audit, db_conn
from app.models.scan_item import SCAN_SCHEMA_VERSION, ScanItem, utc_now_iso
from app.models.schemas import ItemType, PermissionMode, RiskBucket, ScoredItem, ScanResult, ScanSummary
from app.pipeline.normalize import normalize_scored_item
from app.pipeline.reasoning import run_reasoning_pipeline, scan_item_from_stored_payload
from app.pipeline.serialize import detail_json_for_storage, serialize_scan_result_object
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


def _collect_raw_scored() -> list[ScoredItem]:
    raw_items: list[ScoredItem] = []
    if _env_use_mock():
        raw_items.extend(raw_to_scored(x) for x in load_mock_scan())
    else:
        for fn in (
            scan_processes,
            scan_services,
            scan_startup,
            scan_scheduled_tasks,
            scan_temp_and_cache,
            scan_downloads,
            scan_desktop_clutter,
            scan_browser_profiles,
            scan_duplicates_limited,
            scan_large_unused_candidates,
            scan_orphans_lightweight,
        ):
            try:
                raw_items.extend(fn())
            except Exception:
                pass
    if not raw_items and not _env_use_mock():
        raw_items.extend(raw_to_scored(x) for x in load_mock_scan())
    return raw_items


async def _finalize_items(raw_items: list[ScoredItem], allow: list[str], block: list[str]) -> list[ScanItem]:
    finalized: list[ScanItem] = []
    for raw in raw_items:
        base = normalize_scored_item(raw)
        nudge = await feedback_nudge_for(
            ScoredItem(
                id=base.id,
                category=base.source,
                item_type=base.item_type,
                name=base.raw_name,
                path=base.path,
                detail=base.scanner_facts,
                rule_bucket=base.bucket,
                confidence=base.confidence,
                reasoning=base.explanation.summary,
            )
        )
        item = run_reasoning_pipeline(base, allow=allow, block=block, feedback_nudge=nudge)
        finalized.append(item)
    return finalized


async def run_full_scan(mode: PermissionMode) -> ScanResult:
    allow, block = await _load_lists()
    scan_id = str(uuid.uuid4())
    platform = os_friendly_name()

    finalized = await _finalize_items(_collect_raw_scored(), allow, block)

    buckets: dict[str, int] = {}
    for it in finalized:
        buckets[it.bucket.value] = buckets.get(it.bucket.value, 0) + 1

    summary = ScanSummary(
        scan_id=scan_id,
        scan_schema_version=SCAN_SCHEMA_VERSION,
        platform=platform,
        mode=mode,
        items_count=len(finalized),
        buckets=buckets,
        disk_usage_sample=_disk_snapshot(),
        generated_at=utc_now_iso(),
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


async def _persist_scan(
    scan_id: str, platform: str, mode: str, items: list[ScanItem], summary: ScanSummary
) -> None:
    async with await db_conn() as db:
        await db.execute(
            """
            INSERT INTO scans (id, platform, mode, started_at, finished_at, summary_json)
            VALUES (?, ?, ?, datetime('now'), datetime('now'), ?)
            """,
            (scan_id, platform, mode, summary.model_dump_json()),
        )
        for it in items:
            detail_json = detail_json_for_storage(it)
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
                    it.source,
                    it.item_type.value,
                    it.raw_name,
                    it.path,
                    detail_json,
                    it.bucket.value,
                    float(it.metrics.ml_rank_score or 0.0),
                    float(it.confidence),
                    it.explanation.summary,
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
        allow, block = await _load_lists()
        restored: list[ScanItem] = []
        for r in rows:
            detail = json.loads(str(r["detail_json"] or "{}"))
            payload = {
                "id": str(r["id"]),
                "category": str(r["category"]),
                "item_type": ItemType(str(r["item_type"])),
                "name": str(r["name"]),
                "path": str(r["path"]) if r["path"] else None,
                "detail": detail,
                "rule_bucket": RiskBucket(str(r["rule_bucket"])),
                "ml_score": float(r["ml_score"] or 0.0),
                "confidence": float(r["confidence"]),
                "reasoning": str(r["reasoning"]),
            }
            restored.append(scan_item_from_stored_payload(payload, allow=allow, block=block))

        buckets: dict[str, int] = {}
        for it in restored:
            buckets[it.bucket.value] = buckets.get(it.bucket.value, 0) + 1

        summary = ScanSummary(
            scan_id=scan_id,
            scan_schema_version=int(summary_dict.get("scan_schema_version", SCAN_SCHEMA_VERSION)),
            platform=platform or str(summary_dict.get("platform", "unknown")),
            mode=mode,
            items_count=len(restored),
            buckets=buckets or dict(summary_dict.get("buckets", {})),
            disk_usage_sample=summary_dict.get("disk_usage_sample"),
            generated_at=summary_dict.get("generated_at"),
        )
        return ScanResult(summary=summary, items=restored)


def export_canonical_payload(result: ScanResult) -> dict[str, Any]:
    from app.models.scan_item import CanonicalScanResult, CanonicalScanSummary

    canonical = CanonicalScanResult(
        summary=CanonicalScanSummary(
            scan_id=result.summary.scan_id,
            platform=result.summary.platform,
            mode=result.summary.mode,
            items_count=result.summary.items_count,
            buckets=result.summary.buckets,
            disk_usage_sample=result.summary.disk_usage_sample,
            generated_at=result.summary.generated_at or utc_now_iso(),
        ),
        items=result.items,
    )
    return serialize_scan_result_object(canonical)
