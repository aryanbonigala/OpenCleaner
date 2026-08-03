from __future__ import annotations

from enum import Enum


class PermissionMode(str, Enum):
    read_only = "read_only"
    assisted = "assisted"
    performance = "performance"


class PerformancePreset(str, Enum):
    max_fps = "max_fps"
    min_ram = "min_ram"
    streaming = "streaming"
    battery_saver = "battery_saver"


class ItemType(str, Enum):
    process = "process"
    service = "service"
    startup_entry = "startup_entry"
    scheduled_task = "scheduled_task"
    file_or_folder = "file_or_folder"
    browser_profile = "browser_profile"
    duplicate_group = "duplicate_group"
    orphan_app = "orphan_app"


class RiskBucket(str, Enum):
    safe_to_remove = "safe_to_remove"
    probably_safe = "probably_safe"
    ask_user = "ask_user"
    unknown = "unknown"
    risky_system_critical = "risky_system_critical"


class ProcessControlCategory(str, Enum):
    """How a running/scheduled item relates to keeping the machine usable."""

    essential = "essential"
    important = "important"
    non_essential = "non_essential"
    gaming_fps_impact = "gaming_fps_impact"
    unknown = "unknown"
    not_applicable = "not_applicable"


class ActionPolicy(str, Enum):
    """What the UI/API may offer for an item — never widened by ML or intelligence."""

    blocked = "blocked"
    report_only = "report_only"
    preview_required = "preview_required"
    explicit_selection_required = "explicit_selection_required"
    allowed_with_confirmation = "allowed_with_confirmation"
    unsupported = "unsupported"
