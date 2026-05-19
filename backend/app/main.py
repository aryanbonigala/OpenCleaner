from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import PlainTextResponse

from app.actions.cleanup import assisted_cleanup
from app.actions.cleanup_preview import preview_cleanup_items
from app.actions.performance import (
    active_session,
    count_running_matches_hard_protected,
    planned_suspend_actions,
    session_snapshot,
    start_session,
    stop_session,
)
from app.actions.quarantine import list_quarantine, quarantine_storage_summary, restore_quarantine
from app.config import get_settings
from app.db import append_audit, db_conn, get_setting, init_db, set_setting
from app.engine.explain import explain_item
from app.models.schemas import (
    CleanupExecuteRequest,
    CleanupPreviewRequest,
    CleanupPreviewResponse,
    ExplainRequest,
    ExplainResponse,
    FeedbackRequest,
    ModeSetRequest,
    PermissionMode,
    PerformancePreviewRequest,
    PerformanceSessionRequest,
    ScanResult,
    UserSettingsPatch,
)
from app.models.user_settings import UserSettings
from app.services.settings_service import load_settings, reset_settings, save_settings
from app.services import scan_state
from app.version import API_VERSION, APP_VERSION
from app.models.scan_item import ScanItem
from app.pipeline.adapters import scored_from_scan_item
from app.engine.protected_registry import protected_pattern_count
from app.services.feedback_service import record_feedback
from app.services.scan_service import export_canonical_payload, latest_scan_from_db, run_full_scan


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="OpenCleaner AI", version=API_VERSION, lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "component": "opencleaner-backend",
        "version": APP_VERSION,
        "api_version": API_VERSION,
        "scan_in_progress": str(scan_state.is_scan_in_progress()).lower(),
    }


@app.get("/api/scan/status")
async def scan_status() -> dict[str, bool]:
    return {"scan_in_progress": scan_state.is_scan_in_progress()}


@app.get("/api/settings", response_model=UserSettings)
async def get_user_settings() -> UserSettings:
    return await load_settings()


@app.put("/api/settings", response_model=UserSettings)
async def put_user_settings(patch: UserSettingsPatch) -> UserSettings:
    payload = patch.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No settings fields provided.")
    try:
        return await save_settings(payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.post("/api/settings/reset", response_model=UserSettings)
async def post_settings_reset() -> UserSettings:
    return await reset_settings()


@app.get("/api/mode")
async def get_mode() -> dict[str, str]:
    m = await get_setting("permission_mode", PermissionMode.read_only.value)
    return {"mode": str(m)}


@app.post("/api/mode")
async def set_mode(req: ModeSetRequest) -> dict[str, str]:
    await set_setting("permission_mode", req.mode.value)
    await append_audit("mode_change", req.mode.value, {"mode": req.mode.value}, success=True)
    return {"mode": req.mode.value}


@app.post("/api/scan", response_model=ScanResult)
async def scan() -> ScanResult:
    if scan_state.is_scan_in_progress():
        raise HTTPException(status_code=409, detail="A scan is already running. Please wait for it to finish.")
    mode_raw = await get_setting("permission_mode", PermissionMode.read_only.value)
    mode = PermissionMode(str(mode_raw))
    try:
        return await run_full_scan(mode)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@app.get("/api/scan/latest", response_model=ScanResult | None)
async def scan_latest() -> ScanResult | None:
    return await latest_scan_from_db()


class ExplainBody(BaseModel):
    item: dict[str, Any]


@app.post("/api/explain", response_model=ExplainResponse)
async def explain(body: ExplainBody) -> ExplainResponse:
    item = ScanItem.model_validate(body.item)
    return explain_item(ExplainRequest(item=item))


@app.post("/api/feedback")
async def feedback(req: FeedbackRequest) -> dict[str, Any]:
    item = ScanItem.model_validate(req.item)
    await record_feedback(item, req.decision, req.weight)
    await append_audit(
        "user_feedback",
        (await get_setting("permission_mode", PermissionMode.read_only.value)) or "read_only",
        {"decision": req.decision, "item_id": item.id},
        success=True,
    )
    return {"ok": True}


@app.get("/api/metrics")
async def metrics() -> dict[str, Any]:
    try:
        import psutil  # noqa: WPS433

        cpu = psutil.cpu_percent(interval=0.2)
        vm = psutil.virtual_memory()
        return {
            "cpu_percent": cpu,
            "memory": {
                "total_gb": round(vm.total / (1024**3), 2),
                "used_gb": round(vm.used / (1024**3), 2),
                "percent": vm.percent,
            },
        }
    except Exception:
        return {"cpu_percent": 0, "memory": {"total_gb": 0, "used_gb": 0, "percent": 0}}


@app.post("/api/cleanup/preview", response_model=CleanupPreviewResponse)
async def cleanup_preview(req: CleanupPreviewRequest) -> CleanupPreviewResponse:
    if scan_state.is_scan_in_progress():
        raise HTTPException(
            status_code=409,
            detail="Cannot preview cleanup while a scan is running. Wait for the scan to finish.",
        )
    latest = await latest_scan_from_db()
    if latest is None:
        raise HTTPException(status_code=400, detail="No scan available. Run a scan first.")
    if not req.item_ids:
        raise HTTPException(status_code=400, detail="Select at least one item to preview cleanup.")
    prefs = await load_settings()
    if req.include_recycle_bin and not prefs.allows_permanent_delete():
        raise HTTPException(
            status_code=400,
            detail="Recycle Bin emptying requires cleanup mode “manual permanent delete only”.",
        )
    selected = [it for it in latest.items if it.id in set(req.item_ids)]
    if len(selected) != len(set(req.item_ids)):
        raise HTTPException(status_code=400, detail="Some selected item IDs were not found in the latest scan.")
    payload = preview_cleanup_items(
        selected,
        confirm_medium_risk=req.confirm_medium_risk,
        include_recycle_bin=req.include_recycle_bin,
        settings=prefs,
    )
    preview_id = scan_state.store_cleanup_preview(
        scan_id=latest.summary.scan_id,
        item_ids=list(req.item_ids),
        confirm_medium_risk=req.confirm_medium_risk,
        include_recycle_bin=req.include_recycle_bin,
        estimated_bytes=int(payload["estimated_bytes"]),
        preview_payload=payload,
    )
    return CleanupPreviewResponse(
        preview_id=preview_id,
        scan_id=latest.summary.scan_id,
        estimated_bytes=int(payload["estimated_bytes"]),
        estimated_mb=float(payload["estimated_mb"]),
        counts=dict(payload["counts"]),
        items=list(payload["items"]),
        include_recycle_bin=req.include_recycle_bin,
        recycle_bin_note=payload.get("recycle_bin_note"),
        confirm_medium_risk=req.confirm_medium_risk,
        disclaimer=str(payload["disclaimer"]),
    )


@app.post("/api/cleanup/execute")
async def cleanup_execute(req: CleanupExecuteRequest) -> dict[str, Any]:
    if scan_state.is_scan_in_progress():
        raise HTTPException(
            status_code=409,
            detail="Cannot run cleanup while a scan is in progress.",
        )
    mode_raw = await get_setting("permission_mode", PermissionMode.read_only.value)
    mode = PermissionMode(str(mode_raw))
    if mode != PermissionMode.assisted:
        raise HTTPException(
            status_code=403,
            detail="Switch to Assisted cleanup mode in Settings before quarantining files.",
        )
    session = scan_state.consume_cleanup_preview(req.preview_id)
    if session is None:
        raise HTTPException(
            status_code=400,
            detail="Cleanup preview expired or missing. Run preview again before executing.",
        )
    if set(req.item_ids) != set(session.item_ids):
        raise HTTPException(
            status_code=400,
            detail="Selected items must match the previewed set exactly.",
        )
    if req.confirm_medium_risk != session.confirm_medium_risk:
        raise HTTPException(status_code=400, detail="Medium-risk confirmation flag does not match preview.")
    if req.include_recycle_bin != session.include_recycle_bin:
        raise HTTPException(status_code=400, detail="Recycle Bin option does not match preview.")
    prefs = await load_settings()
    if req.include_recycle_bin and not prefs.allows_permanent_delete():
        raise HTTPException(
            status_code=400,
            detail="Recycle Bin emptying is disabled while cleanup mode is quarantine-only.",
        )
    if req.include_recycle_bin and not req.confirm_permanent_delete:
        raise HTTPException(
            status_code=400,
            detail="Emptying the Recycle Bin is permanent. Set confirm_permanent_delete=true after reviewing preview.",
        )
    latest = await latest_scan_from_db()
    if latest is None or latest.summary.scan_id != session.scan_id:
        raise HTTPException(status_code=400, detail="Latest scan no longer matches this preview. Scan again.")
    selected = [it for it in latest.items if it.id in set(req.item_ids)]
    result = await assisted_cleanup(
        mode,
        selected,
        req.confirm_medium_risk,
        include_recycle_bin=req.include_recycle_bin,
        settings=prefs,
    )
    quarantined = sum(1 for a in result.get("actions", []) if a.get("quarantine_id"))
    skipped = sum(1 for a in result.get("actions", []) if a.get("skipped"))
    failed = sum(1 for a in result.get("actions", []) if a.get("error"))
    result["summary"] = {
        "preview_id": req.preview_id,
        "estimated_bytes": session.estimated_bytes,
        "confirmed_bytes": result.get("reclaimed_bytes", 0),
        "estimated_mb": round(session.estimated_bytes / (1024 * 1024), 3),
        "confirmed_mb": result.get("reclaimed_mb", 0),
        "quarantined": quarantined,
        "skipped": skipped,
        "failed": failed,
        "blocked": int(session.preview_payload.get("counts", {}).get("blocked", 0)),
    }
    return result


@app.get("/api/quarantine")
async def quarantine_list() -> dict[str, Any]:
    return {"entries": await list_quarantine()}


class RestoreBody(BaseModel):
    id: str


@app.post("/api/quarantine/restore")
async def quarantine_restore(body: RestoreBody) -> dict[str, Any]:
    try:
        await restore_quarantine(body.id)
        await append_audit("quarantine_restore", "assisted", {"id": body.id}, success=True)
        return {"restored": True}
    except Exception as e:
        await append_audit(
            "quarantine_restore_failed", "assisted", {"id": body.id}, success=False, error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/safety/summary")
async def safety_summary() -> dict[str, Any]:
    mode_raw = await get_setting("permission_mode", PermissionMode.read_only.value)
    q = await quarantine_storage_summary()
    rollback = session_snapshot()
    protected_running = 0
    try:
        protected_running = count_running_matches_hard_protected()
    except Exception:
        protected_running = 0
    last_actions: list[dict[str, Any]] = []
    async with await db_conn() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT action, mode, detail_json, success, error, created_at
            FROM audit_log
            WHERE action IN ('assisted_cleanup', 'performance_start', 'performance_stop', 'cleanup_error', 'quarantine_restore')
            ORDER BY id DESC LIMIT 12
            """
        )
        rows = await cur.fetchall()
        last_actions = [dict(r) for r in rows]

    return {
        "permission_mode": str(mode_raw),
        "quarantine": q,
        "performance_session": rollback,
        "protected_registry_rules": protected_pattern_count(),
        "running_processes_matching_protection": protected_running,
        "recent_actions": last_actions,
        "telemetry": await get_setting("telemetry", "false"),
    }


@app.post("/api/performance/preview")
async def perf_preview(req: PerformancePreviewRequest) -> dict[str, Any]:
    mode_raw = await get_setting("permission_mode", PermissionMode.read_only.value)
    if PermissionMode(str(mode_raw)) != PermissionMode.performance:
        raise HTTPException(status_code=403, detail="performance mode required for preview")
    return planned_suspend_actions(req.preset, req.target_process_names)


@app.post("/api/performance/start")
async def perf_start(req: PerformanceSessionRequest) -> dict[str, Any]:
    mode_raw = await get_setting("permission_mode", PermissionMode.read_only.value)
    if PermissionMode(str(mode_raw)) != PermissionMode.performance:
        raise HTTPException(status_code=403, detail="performance mode required")
    if not req.confirm_apply:
        raise HTTPException(
            status_code=400,
            detail="Preview required: call POST /api/performance/preview first, then start with confirm_apply=true.",
        )
    try:
        sess = start_session(req.preset, req.target_process_names, confirm_apply=req.confirm_apply)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await append_audit(
        "performance_start",
        PermissionMode.performance.value,
        {"preset": req.preset.value, "suspended": sess.suspended_pids},
        success=True,
    )
    return {"suspended_pids": sess.suspended_pids, "preset": sess.preset.value}


@app.post("/api/performance/stop")
async def perf_stop() -> dict[str, Any]:
    sess = active_session()
    pids = sess.suspended_pids if sess else []
    stop_session()
    await append_audit(
        "performance_stop",
        PermissionMode.performance.value,
        {"resumed": pids},
        success=True,
    )
    return {"resumed": pids}


@app.get("/api/export/report", response_model=None)
async def export_report(fmt: str = "json") -> Any:
    latest = await latest_scan_from_db()
    if latest is None:
        raise HTTPException(status_code=400, detail="no scan")

    if fmt == "json":
        return export_canonical_payload(latest)

    if fmt == "md":
        lines: list[str] = []
        lines.append("# OpenCleaner AI report\n\n")
        lines.append(f"- Scan ID: `{latest.summary.scan_id}`\n")
        lines.append(f"- Platform: {latest.summary.platform}\n")
        lines.append(f"- Items: {latest.summary.items_count}\n\n")
        lines.append("\n## Bucket counts\n\n")
        for k, v in latest.summary.buckets.items():
            lines.append(f"- **{k}**: {v}\n")
        lines.append("\n## Notable items\n\n")
        for it in sorted(latest.items, key=lambda x: x.metrics.rank_deletion_risk or 0, reverse=True)[:40]:
            prov = ", ".join(p.stage for p in it.provenance[-3:]) if it.provenance else "—"
            lines.append(
                f"- `{it.display_name}` ({it.item_type.value}) — {it.bucket.value} — "
                f"{it.explanation.summary} [provenance: {prov}]\n"
            )
        return PlainTextResponse("".join(lines), media_type="text/markdown")

    raise HTTPException(status_code=404, detail="format")


@app.get("/api/audit")
async def audit(limit: int = 100) -> dict[str, Any]:
    async with await db_conn() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT id, action, mode, detail_json, success, error, created_at
            FROM audit_log ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        )
        rows = await cur.fetchall()
        return {"entries": [dict(r) for r in rows]}
