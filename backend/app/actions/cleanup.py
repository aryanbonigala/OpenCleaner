from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.actions.quarantine import quarantine_path
from app.db import append_audit
from app.engine.rules_engine import is_critical_path
from app.models.schemas import PermissionMode, RiskBucket, ScoredItem


async def assisted_cleanup(
    mode: PermissionMode,
    items: list[ScoredItem],
    confirm_medium_risk: bool,
    include_recycle_bin: bool = False,
) -> dict:
    if mode != PermissionMode.assisted:
        raise PermissionError("Assisted cleanup requires assisted permission mode.")

    reclaimed_bytes = 0
    actions: list[dict] = []
    errors: list[str] = []

    for it in items:
        if it.item_type.value != "file_or_folder":
            actions.append({"id": it.id, "skipped": True, "reason": "not a file target"})
            continue
        if not it.path:
            actions.append({"id": it.id, "skipped": True, "reason": "missing path"})
            continue
        p = Path(it.path)
        if is_critical_path(str(p)):
            actions.append({"id": it.id, "skipped": True, "reason": "critical path"})
            continue

        allowed_buckets = {RiskBucket.safe_to_remove}
        if confirm_medium_risk:
            allowed_buckets.add(RiskBucket.probably_safe)

        hint = str(it.detail.get("category_hint") or "")
        low_risk_hints = {
            "temp_cache",
            "installer_residual",
            "downloads_general",
        }

        if it.rule_bucket not in allowed_buckets and not (
            confirm_medium_risk and hint in low_risk_hints
        ):
            actions.append(
                {
                    "id": it.id,
                    "skipped": True,
                    "reason": "risk bucket requires explicit confirmation",
                }
            )
            continue

        try:
            if p.is_file():
                size = p.stat().st_size
                meta = {"item_id": it.id, "bucket": it.rule_bucket.value, "hint": hint}
                qid = await quarantine_path(p, meta)
                reclaimed_bytes += size
                actions.append({"id": it.id, "quarantine_id": qid, "bytes": size})
            elif p.is_dir() and hint == "empty_startmenu_folder":
                # Remove empty dir without quarantine — low value
                if not any(p.iterdir()):
                    p.rmdir()
                    actions.append({"id": it.id, "removed_empty_dir": True})
                else:
                    actions.append({"id": it.id, "skipped": True, "reason": "dir not empty"})
            else:
                actions.append({"id": it.id, "skipped": True, "reason": "unsupported target type"})
        except OSError as e:
            errors.append(str(e))
            actions.append({"id": it.id, "error": str(e)})
            await append_audit(
                "cleanup_error",
                mode.value,
                {"item": it.id, "path": str(p), "error": str(e)},
                success=False,
                error=str(e),
            )

    if include_recycle_bin and sys.platform == "win32":
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                check=False,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,  # type: ignore[attr-defined]
            )
            actions.append({"recycle_bin": "cleared"})
        except Exception as e:
            errors.append(f"recycle_bin:{e}")

    await append_audit(
        "assisted_cleanup",
        mode.value,
        {"reclaimed_bytes": reclaimed_bytes, "actions": actions},
        success=len(errors) == 0,
        error="; ".join(errors) if errors else None,
    )

    return {
        "reclaimed_bytes": reclaimed_bytes,
        "reclaimed_mb": round(reclaimed_bytes / (1024 * 1024), 3),
        "actions": actions,
        "errors": errors,
    }
