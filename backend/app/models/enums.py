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
