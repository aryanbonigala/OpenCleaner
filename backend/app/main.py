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
from app.actions.performance import active_session, start_session, stop_session
from app.actions.quarantine import list_quarantine, restore_quarantine
from app.config import get_settings
from app.db import append_audit, db_conn, get_setting, init_db, set_setting
from app.engine.explain import explain_item
from app.models.schemas import (
    CleanupExecuteRequest,
    ExplainRequest,
    ExplainResponse,
    FeedbackRequest,
    ModeSetRequest,
    PermissionMode,
    PerformanceSessionRequest,
    ScanResult,
    ScoredItem,
)
from app.services.feedback_service import record_feedback
from app.services.scan_service import latest_scan_from_db, run_full_scan


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="OpenCleaner AI", version="0.1.0", lifespan=lifespan)

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
    return {"status": "ok", "component": "opencleaner-backend"}


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
    mode_raw = await get_setting("permission_mode", PermissionMode.read_only.value)
    mode = PermissionMode(str(mode_raw))
    return await run_full_scan(mode)


@app.get("/api/scan/latest", response_model=ScanResult | None)
async def scan_latest() -> ScanResult | None:
    return await latest_scan_from_db()


class ExplainBody(BaseModel):
    item: dict[str, Any]


@app.post("/api/explain", response_model=ExplainResponse)
async def explain(body: ExplainBody) -> ExplainResponse:
    item = ScoredItem.model_validate(body.item)
    return explain_item(ExplainRequest(item=item))


@app.post("/api/feedback")
async def feedback(req: FeedbackRequest) -> dict[str, Any]:
    item = ScoredItem.model_validate(req.item)
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


@app.post("/api/cleanup/execute")
async def cleanup_execute(req: CleanupExecuteRequest) -> dict[str, Any]:
    mode_raw = await get_setting("permission_mode", PermissionMode.read_only.value)
    mode = PermissionMode(str(mode_raw))
    latest = await latest_scan_from_db()
    if latest is None:
        raise HTTPException(status_code=400, detail="no scan available — run scan first")
    selected = [it for it in latest.items if it.id in set(req.item_ids)]
    return await assisted_cleanup(
        mode, selected, req.confirm_medium_risk, include_recycle_bin=req.include_recycle_bin
    )


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


@app.post("/api/performance/start")
async def perf_start(req: PerformanceSessionRequest) -> dict[str, Any]:
    mode_raw = await get_setting("permission_mode", PermissionMode.read_only.value)
    if PermissionMode(str(mode_raw)) != PermissionMode.performance:
        raise HTTPException(status_code=403, detail="performance mode required")
    sess = start_session(req.preset, req.target_process_names)
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
        return json.loads(latest.model_dump_json())

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
        for it in sorted(latest.items, key=lambda x: x.rank_deletion_risk or 0, reverse=True)[:40]:
            lines.append(
                f"- `{it.name}` ({it.item_type.value}) — {it.rule_bucket.value} — {it.reasoning}\n"
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
