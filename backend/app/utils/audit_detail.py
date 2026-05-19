from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.models.user_settings import LoggingMode


def _redact_path(path: str) -> str:
    p = Path(path)
    digest = hashlib.sha256(str(p).encode("utf-8")).hexdigest()[:12]
    return f"<path:{digest}:{p.name}>"


def sanitize_audit_detail(detail: dict[str, Any], mode: LoggingMode) -> dict[str, Any]:
    if mode == LoggingMode.normal:
        return detail
    if mode == LoggingMode.minimal:
        out: dict[str, Any] = {}
        for key in ("action", "item_id", "id", "scan_id", "decision", "mode", "preset"):
            if key in detail:
                out[key] = detail[key]
        if "reclaimed_bytes" in detail:
            out["reclaimed_bytes"] = detail["reclaimed_bytes"]
        if "items" in detail and isinstance(detail["items"], int):
            out["items"] = detail["items"]
        return out

    # redacted_paths
    return _redact_dict(detail)


def _redact_dict(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _redact_value(k, v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_dict(x) for x in obj]
    return obj


def _redact_value(key: str, value: Any) -> Any:
    if key in ("path", "original_path", "quarantine_path", "item") and isinstance(value, str):
        return _redact_path(value)
    if isinstance(value, (dict, list)):
        return _redact_dict(value)
    return value
