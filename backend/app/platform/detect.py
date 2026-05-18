from __future__ import annotations

import platform
import sys
from enum import Enum


class OSFamily(str, Enum):
    windows = "windows"
    darwin = "darwin"
    linux = "linux"
    unknown = "unknown"


def detect_os() -> OSFamily:
    name = sys.platform
    if name == "win32":
        return OSFamily.windows
    if name == "darwin":
        return OSFamily.darwin
    if name.startswith("linux"):
        return OSFamily.linux
    return OSFamily.unknown


def os_friendly_name() -> str:
    return f"{platform.system()} {platform.release()} ({platform.machine()})"
