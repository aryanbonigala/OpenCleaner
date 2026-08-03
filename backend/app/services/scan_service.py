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
from app.services import scan_state
from app.services.settings_service import load_settings
from app.actions.quarantine_retention import apply_quarantine_retention
from app.models.user_settings import ScannerToggles


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


def _scanners_for_toggles(toggles: ScannerToggles) -> list[tuple[str, Any]]:
    scanners: list[tuple[str, Any]] = []
    if toggles.performance:
        scanners.append(("processes", scan_processes))
    if toggles.startup:
        scanners.extend([("services", scan_services), ("startup", scan_startup)])
    if toggles.tasks:
        scanners.append(("scheduled_tasks", scan_scheduled_tasks))
    if toggles.files:
        scanners.extend(
            [
                ("temp_and_cache", scan_temp_and_cache),
                ("downloads", scan_downloads),
                ("desktop_clutter", scan_desktop_clutter),
                ("duplicates", scan_duplicates_limited),
                ("large_unused", scan_large_unused_candidates),
                ("orphans", scan_orphans_lightweight),
            ]
        )
    if toggles.browser:
        scanners.append(("browser_profiles", scan_browser_profiles))
    return scanners


def _collect_raw_scored(toggles: ScannerToggles) -> tuple[list[ScoredItem], list[str]]:
    raw_items: list[ScoredItem] = []
    warnings: list[str] = []
    scanners = _scanners_for_toggles(toggles)
    if _env_use_mock():
        raw_items.extend(raw_to_scored(x) for x in load_mock_scan())
    else:
        if not scanners:
            warnings.append("All scanner groups are disabled in settings; enable at least one group.")
        for label, fn in scanners:
            try:
                raw_items.extend(fn())
            except Exception as exc:
                warnings.append(f"Scanner “{label}” did not complete: {exc}")
    if not raw_items and not _env_use_mock():
        raw_items.extend(raw_to_scored(x) for x in load_mock_scan())
        if not warnings:
            warnings.append("Live scanners returned no items; loaded sample dataset instead.")
    return raw_items, warnings


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
    if scan_state.is_scan_in_progress():
        raise RuntimeError("A scan is already in progress. Wait for it to finish before starting another.")
    scan_state.begin_scan()
    try:
        return await _run_full_scan_inner(mode)
    finally:
        scan_state.end_scan()


async def _run_full_scan_inner(mode: PermissionMode) -> ScanResult:
    prefs = await load_settings()
    await apply_quarantine_retention(prefs)
    allow, block = await _load_lists()
    scan_id = str(uuid.uuid4())
    platform = os_friendly_name()

    raw, warnings = _collect_raw_scored(prefs.scanner_toggles)
    finalized = await _finalize_items(raw, allow, block)

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
        scanner_warnings=warnings,
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


def assert_unique_scan_item_ids(items: list[ScanItem]) -> None:
    """Fail loudly if two items in one scan share an id.

    Ids are deterministic per item and repeat across scans by design (scan_items is
    keyed on (scan_id, id)), but within a single scan a collision means a scanner is
    minting under-scoped ids and would silently merge two real items.
    """
    seen: dict[str, ScanItem] = {}
    clashes: list[str] = []
    for it in items:
        first = seen.setdefault(it.id, it)
        if first is it:
            continue
        clashes.append(
            f"  id={it.id!r}\n"
            f"    A: type={first.item_type.value} source={first.source} "
            f"name={first.raw_name!r} display={first.display_name!r} path={first.path!r} "
            f"facts={first.scanner_facts}\n"
            f"    B: type={it.item_type.value} source={it.source} "
            f"name={it.raw_name!r} display={it.display_name!r} path={it.path!r} "
            f"facts={it.scanner_facts}"
        )
    if clashes:
        raise ValueError(
            f"Duplicate scan item ids within one scan ({len(clashes)}); "
            "a scanner is producing under-scoped ids:\n" + "\n".join(clashes)
        )


async def _persist_scan(
    scan_id: str, platform: str, mode: str, items: list[ScanItem], summary: ScanSummary
) -> None:
    assert_unique_scan_item_ids(items)
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
            # finished_at is second-resolution, so two scans a moment apart tie;
            # rowid breaks the tie in insertion order.
            "SELECT id, platform, mode, summary_json FROM scans "
            "ORDER BY finished_at DESC, rowid DESC LIMIT 1"
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
            scanner_warnings=list(summary_dict.get("scanner_warnings", [])),
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
