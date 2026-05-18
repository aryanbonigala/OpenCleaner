from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CleanupPreviewSession:
    preview_id: str
    scan_id: str
    item_ids: list[str]
    confirm_medium_risk: bool
    include_recycle_bin: bool
    created_at: float
    estimated_bytes: int
    preview_payload: dict[str, Any]


_scan_in_progress: bool = False
_previews: dict[str, CleanupPreviewSession] = {}


def begin_scan() -> None:
    global _scan_in_progress
    if _scan_in_progress:
        raise RuntimeError("A scan is already running.")
    _scan_in_progress = True


def end_scan() -> None:
    global _scan_in_progress
    _scan_in_progress = False


def is_scan_in_progress() -> bool:
    return _scan_in_progress


def store_cleanup_preview(
    *,
    scan_id: str,
    item_ids: list[str],
    confirm_medium_risk: bool,
    include_recycle_bin: bool,
    estimated_bytes: int,
    preview_payload: dict[str, Any],
) -> str:
    preview_id = secrets.token_urlsafe(16)
    _previews[preview_id] = CleanupPreviewSession(
        preview_id=preview_id,
        scan_id=scan_id,
        item_ids=list(item_ids),
        confirm_medium_risk=confirm_medium_risk,
        include_recycle_bin=include_recycle_bin,
        created_at=time.time(),
        estimated_bytes=estimated_bytes,
        preview_payload=preview_payload,
    )
    _prune_old_previews()
    return preview_id


def get_cleanup_preview(preview_id: str) -> CleanupPreviewSession | None:
    return _previews.get(preview_id)


def consume_cleanup_preview(preview_id: str) -> CleanupPreviewSession | None:
    return _previews.pop(preview_id, None)


def _prune_old_previews(max_age_s: float = 3600.0) -> None:
    now = time.time()
    stale = [k for k, v in _previews.items() if now - v.created_at > max_age_s]
    for k in stale:
        _previews.pop(k, None)


def reset_for_tests() -> None:
    global _scan_in_progress
    _scan_in_progress = False
    _previews.clear()
