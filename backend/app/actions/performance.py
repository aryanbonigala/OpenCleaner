from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

import psutil

from app.engine.protected_registry import (
    DEFAULT_SOFT_SUSPEND_BASE_NAMES,
    is_hard_protected_process,
    suspend_allowed_by_policy,
)
from app.models.schemas import PerformancePreset


@dataclass
class PerformanceSession:
    preset: PerformancePreset
    suspended_pids: list[int]
    prior_affinities: dict[int, list[int]]


_SESSION: PerformanceSession | None = None


def _norm_explicit(targets: list[str]) -> frozenset[str]:
    out: set[str] = set()
    for t in targets:
        b = (t or "").replace("/", "\\").split("\\")[-1].strip().lower()
        if b:
            out.add(b)
    return frozenset(out)


def planned_suspend_actions(
    preset: PerformancePreset,
    target_process_names: list[str],
) -> dict[str, object]:
    """
    Preview-only: which processes would be suspended and why others are skipped.
    Does not mutate system state.
    """
    explicit = _norm_explicit(target_process_names)
    would_suspend: list[dict[str, object]] = []
    skipped_protected: list[dict[str, str]] = []
    skipped_policy: list[dict[str, str]] = []

    for p in psutil.process_iter(["pid", "name"]):
        try:
            pid = int(p.info.get("pid") or 0)
            name = str(p.info.get("name") or "")
            if not pid or not name:
                continue
            base = name.replace("/", "\\").split("\\")[-1].lower()
            ok, reason = suspend_allowed_by_policy(name, explicit_target_basenames=explicit)
            if not ok:
                if is_hard_protected_process(name) or "browser" in reason or "shell" in reason:
                    skipped_protected.append({"pid": str(pid), "name": name, "reason": reason})
                else:
                    skipped_policy.append({"pid": str(pid), "name": name, "reason": reason})
                continue

            if explicit:
                if base not in explicit:
                    continue
            else:
                if base not in DEFAULT_SOFT_SUSPEND_BASE_NAMES:
                    continue

            would_suspend.append(
                {
                    "pid": pid,
                    "name": name,
                    "reason": "matches performance policy and preset target list",
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    power_note = (
        "Preset may attempt a local power profile switch on Windows (optional; may require elevation)."
    )

    return {
        "preset": preset.value,
        "explicit_targets": sorted(explicit),
        "would_suspend": would_suspend,
        "would_suspend_count": len(would_suspend),
        "skipped_protected_sample": skipped_protected[:40],
        "skipped_protected_count": len(skipped_protected),
        "skipped_policy_sample": skipped_policy[:20],
        "disclaimer": (
            "Preview only. No process was suspended. Review the list, then call /api/performance/start "
            "with confirm_apply=true if you accept the impact."
        ),
        "power_note": power_note,
    }


def count_running_matches_hard_protected() -> int:
    n = 0
    for p in psutil.process_iter(["name"]):
        try:
            name = str(p.info.get("name") or "")
            if name and is_hard_protected_process(name):
                n += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return n


def start_session(
    preset: PerformancePreset,
    target_procs: list[str],
    *,
    confirm_apply: bool,
) -> PerformanceSession:
    global _SESSION
    if not confirm_apply:
        raise ValueError("Performance session requires confirm_apply=true after reviewing preview.")

    if _SESSION is not None:
        stop_session()

    explicit = _norm_explicit(target_procs)
    suspended: list[int] = []
    affinities: dict[int, list[int]] = {}

    for p in psutil.process_iter(["pid", "name"]):
        try:
            name = str(p.info.get("name") or "")
            pid = int(p.info.get("pid") or 0)
            if not pid:
                continue
            ok, _reason = suspend_allowed_by_policy(name, explicit_target_basenames=explicit)
            if not ok:
                continue
            base = name.replace("/", "\\").split("\\")[-1].lower()
            if explicit:
                if base not in explicit:
                    continue
            else:
                if base not in DEFAULT_SOFT_SUSPEND_BASE_NAMES:
                    continue

            if preset == PerformancePreset.battery_saver:
                try:
                    if hasattr(p, "nice"):
                        p.nice(psutil.IDLE_PRIORITY_CLASS if sys.platform == "win32" else 19)  # type: ignore[attr-defined]
                except Exception:
                    pass
                continue

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


def session_snapshot() -> dict[str, object] | None:
    if _SESSION is None:
        return None
    return {
        "active": True,
        "preset": _SESSION.preset.value,
        "suspended_pids": list(_SESSION.suspended_pids),
        "suspended_count": len(_SESSION.suspended_pids),
    }


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
