from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

SETTINGS_SCHEMA_VERSION = 1


class CleanupMode(str, Enum):
    quarantine_only = "quarantine_only"
    manual_permanent_delete_only = "manual_permanent_delete_only"


class RiskVisibility(str, Enum):
    basic = "basic"
    advanced = "advanced"


class QuarantineRetention(str, Enum):
    days_7 = "7_days"
    days_14 = "14_days"
    days_30 = "30_days"
    manual_only = "manual_only"


class LoggingMode(str, Enum):
    normal = "normal"
    redacted_paths = "redacted_paths"
    minimal = "minimal"


class ScannerToggles(BaseModel):
    files: bool = True
    browser: bool = True
    startup: bool = True
    tasks: bool = True
    performance: bool = True


class UserSettings(BaseModel):
    """Local safety preferences — cannot weaken core path protections."""

    settings_version: int = SETTINGS_SCHEMA_VERSION
    cleanup_mode: CleanupMode = CleanupMode.quarantine_only
    risk_visibility: RiskVisibility = RiskVisibility.basic
    scanner_toggles: ScannerToggles = Field(default_factory=ScannerToggles)
    quarantine_retention: QuarantineRetention = QuarantineRetention.manual_only
    logging_mode: LoggingMode = LoggingMode.redacted_paths

    def is_advanced_risk(self) -> bool:
        return self.risk_visibility == RiskVisibility.advanced

    def allows_permanent_delete(self) -> bool:
        return self.cleanup_mode == CleanupMode.manual_permanent_delete_only

    def retention_days(self) -> int | None:
        if self.quarantine_retention == QuarantineRetention.days_7:
            return 7
        if self.quarantine_retention == QuarantineRetention.days_14:
            return 14
        if self.quarantine_retention == QuarantineRetention.days_30:
            return 30
        return None
