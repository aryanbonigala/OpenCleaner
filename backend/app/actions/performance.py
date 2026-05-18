from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

import psutil

from app.engine.rules_engine import is_critical_process
from app.models.schemas import PerformancePreset


@dataclass
class PerformanceSession:
    preset: PerformancePreset
    suspended_pids: list[int]
    prior_affinities: dict[int, list[int]]


_SESSION: PerformanceSession | None = None

_DEFAULT_SOFT_SUSPEND = {
    "onedrive.exe",
    "dropbox.exe",
    "googledrivefs.exe",
    "creative cloud.exe",
    "adobeipcbroker.exe",
    "epicwebhelper.exe",
    "steamwebhelper.exe",
}


def start_session(preset: PerformancePreset, target_procs: list[str]) -> PerformanceSession:
    global _SESSION
    if _SESSION is not None:
        stop_session()

    suspended: list[int] = []
    affinities: dict[int, list[int]] = {}

    explicit = {t.lower() for t in target_procs if t}
    if explicit:
        suspend_filter = explicit
    else:
        suspend_filter = set(_DEFAULT_SOFT_SUSPEND)

    for p in psutil.process_iter(["pid", "name"]):
        try:
            name = str(p.info.get("name") or "")
            pid = int(p.info.get("pid") or 0)
            if not pid or is_critical_process(name):
                continue
            base = name.split("\\")[-1].split("/")[-1].lower()
            if base not in suspend_filter:
                continue
            if preset == PerformancePreset.battery_saver:
                try:
                    if hasattr(p, "nice"):
                        p.nice(psutil.IDLE_PRIORITY_CLASS if sys.platform == "win32" else 19)  # type: ignore[attr-defined]
                except Exception:
                    pass
                continue

            # Suspend non-critical background where safe
            try:
                status = p.status()
                if status != psutil.STATUS_STOPPED:
                    p.suspend()
                    suspended.append(pid)
            except Exception:
                continue
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    _SESSION = PerformanceSession(preset=preset, suspended_pids=suspended, prior_affinities=affinities)

    if sys.platform == "win32":
        if preset == PerformancePreset.max_fps:
            _try_powercfg_high_performance()
        elif preset == PerformancePreset.battery_saver:
            _try_powercfg_battery()

    return _SESSION


def stop_session() -> None:
    global _SESSION
    if _SESSION is None:
        return
    for pid in _SESSION.suspended_pids:
        try:
            p = psutil.Process(pid)
            p.resume()
        except Exception:
            continue
    _SESSION = None


def active_session() -> PerformanceSession | None:
    return _SESSION


def _try_powercfg_high_performance() -> None:
    try:
        subprocess.run(
            ["powercfg", "/s", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"],
            check=False,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,  # type: ignore[attr-defined]
        )
    except Exception:
        return


def _try_powercfg_battery() -> None:
    try:
        subprocess.run(
            ["powercfg", "/s", "a1841308-3541-4fab-bc81-f71556f20b4a"],
            check=False,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,  # type: ignore[attr-defined]
        )
    except Exception:
        return
