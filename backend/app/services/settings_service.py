from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.db import get_setting, set_setting
from app.models.user_settings import (
    SETTINGS_SCHEMA_VERSION,
    CleanupMode,
    LoggingMode,
    QuarantineRetention,
    RiskVisibility,
    ScannerToggles,
    UserSettings,
)

_SETTINGS_KEY = "user_preferences_v1"


def default_settings() -> UserSettings:
    return UserSettings()


def _coerce_legacy(raw: dict[str, Any]) -> dict[str, Any]:
    """Migrate stored blobs from older shapes when possible."""
    version = int(raw.get("settings_version", 0))
    if version >= SETTINGS_SCHEMA_VERSION:
        return raw
    out = default_settings().model_dump()
    for key in ("cleanup_mode", "risk_visibility", "quarantine_retention", "logging_mode"):
        if key in raw:
            out[key] = raw[key]
    if "scanner_toggles" in raw and isinstance(raw["scanner_toggles"], dict):
        out["scanner_toggles"] = {**out["scanner_toggles"], **raw["scanner_toggles"]}
    out["settings_version"] = SETTINGS_SCHEMA_VERSION
    return out


def validate_settings_payload(data: dict[str, Any]) -> UserSettings:
    try:
        merged = _coerce_legacy(data) if data.get("settings_version", 0) < SETTINGS_SCHEMA_VERSION else data
        settings = UserSettings.model_validate(merged)
    except ValidationError as e:
        raise ValueError(f"Invalid settings: {e}") from e
    _assert_safe_invariants(settings)
    return settings


def _assert_safe_invariants(settings: UserSettings) -> None:
    """Settings must not declare bypass of core safety (no such fields today)."""
    if settings.cleanup_mode not in CleanupMode:
        raise ValueError("Invalid cleanup_mode")
    if settings.risk_visibility not in RiskVisibility:
        raise ValueError("Invalid risk_visibility")
    toggles = settings.scanner_toggles
    for name in ("files", "browser", "startup", "tasks", "performance"):
        if not isinstance(getattr(toggles, name), bool):
            raise ValueError(f"scanner_toggles.{name} must be boolean")


async def load_settings() -> UserSettings:
    raw = await get_setting(_SETTINGS_KEY)
    if not raw:
        return default_settings()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return default_settings()
    if not isinstance(data, dict):
        return default_settings()
    try:
        return validate_settings_payload(data)
    except ValueError:
        return default_settings()


async def save_settings(patch: dict[str, Any]) -> UserSettings:
    current = await load_settings()
    merged = current.model_dump()
    for key, value in patch.items():
        if key == "scanner_toggles" and isinstance(value, dict):
            merged["scanner_toggles"] = {**merged.get("scanner_toggles", {}), **value}
        elif key in merged or key == "settings_version":
            merged[key] = value
    merged["settings_version"] = SETTINGS_SCHEMA_VERSION
    settings = validate_settings_payload(merged)
    await set_setting(_SETTINGS_KEY, settings.model_dump_json())
    return settings


async def reset_settings() -> UserSettings:
    settings = default_settings()
    await set_setting(_SETTINGS_KEY, settings.model_dump_json())
    return settings
