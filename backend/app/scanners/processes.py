from __future__ import annotations

import time

import psutil

from app.models.schemas import ItemType, RiskBucket, ScoredItem

# Only attrs psutil implements on every supported platform. `cpu_num` is Linux/FreeBSD-only
# and made `process_iter` raise ValueError on macOS/Windows, killing the whole scan.
_ITER_ATTRS = (
    "pid",
    "ppid",
    "name",
    "exe",
    "memory_info",
    "username",
    "create_time",
    "status",
    "num_threads",
)

_PROC_ERRORS = (
    psutil.NoSuchProcess,
    psutil.AccessDenied,
    psutil.ZombieProcess,
    ValueError,
    AttributeError,
    OSError,
)

# Fields no cross-platform psutil call can answer honestly. Reported as unknown rather
# than guessed — signature/elevation need per-OS APIs we are not pulling in here.
_UNAVAILABLE_FACTS = ("elevated", "integrity_level", "publisher", "signature_status")


def _gpu_heuristic(proc: psutil.Process, exe_name: str) -> bool:
    n = exe_name.lower()
    if any(k in n for k in ("obs64", "obs32", "chrome", "msedge", "firefox", "dwm", "game")):
        return True
    # Heuristic: very high CPU with certain names
    try:
        return proc.cpu_percent(interval=None) > 40 and "render" in n
    except _PROC_ERRORS:
        return False


def _basename(path: str) -> str:
    return (path or "").replace("/", "\\").split("\\")[-1].strip()


def _snapshot() -> list[tuple[psutil.Process, dict]]:
    """One guarded pass over the process table. A bad row is dropped, never the scan."""
    rows: list[tuple[psutil.Process, dict]] = []
    try:
        it = psutil.process_iter(list(_ITER_ATTRS))
    except _PROC_ERRORS:
        return rows
    while True:
        try:
            p = next(it)
        except StopIteration:
            break
        except _PROC_ERRORS:
            continue
        try:
            rows.append((p, dict(p.info)))
        except _PROC_ERRORS:
            continue
    return rows


def _call(fn, denied: list[str], field: str):
    """Best-effort optional fact; records the field name when the OS refuses."""
    try:
        return fn()
    except (psutil.AccessDenied, psutil.ZombieProcess):
        denied.append(field)
    except _PROC_ERRORS:
        denied.append(field)
    return None


def scan_processes(limit: int = 220) -> list[ScoredItem]:
    out: list[ScoredItem] = []
    now = time.time()
    rows = _snapshot()

    names_by_pid: dict[int, str] = {}
    children_by_ppid: dict[int, list[int]] = {}
    for _, info in rows:
        pid = info.get("pid")
        if pid is None:
            continue
        names_by_pid[int(pid)] = str(info.get("name") or "")
        ppid = info.get("ppid")
        if ppid is not None:
            children_by_ppid.setdefault(int(ppid), []).append(int(pid))

    for p, info in rows:
        if len(out) >= limit:
            break
        pid = info.get("pid")
        name = info.get("name") or f"pid_{pid}"
        exe = info.get("exe") or ""
        denied: list[str] = []

        mem_info = info.get("memory_info")
        if mem_info is None:
            denied.append("memory_info")
        mem = float(getattr(mem_info, "rss", 0) or 0) / (1024 * 1024)

        username = info.get("username")
        if username is None:
            denied.append("username")

        status = info.get("status")
        created = info.get("create_time")
        ppid = info.get("ppid")

        cpu = _call(lambda: float(p.cpu_percent(interval=None)), denied, "cpu_percent") or 0.0
        affinity = None
        if hasattr(p, "cpu_affinity"):
            aff = _call(p.cpu_affinity, denied, "cpu_affinity")  # type: ignore[attr-defined]
            affinity = len(aff) if aff is not None else None

        out.append(
            ScoredItem(
                id=f"proc-{pid}",
                category="processes",
                item_type=ItemType.process,
                name=str(name),
                path=exe or None,
                detail={
                    "pid": pid,
                    "memory_mb": round(mem, 2),
                    "cpu_percent": round(cpu, 2),
                    "gpu_heavy": _gpu_heuristic(p, str(name)),
                    "suspended": status == psutil.STATUS_STOPPED,
                    "cpu_affinity_count": affinity,
                    "num_threads": info.get("num_threads"),
                    "started_ts": created,
                    "uptime_s": round(now - created, 1) if created else None,
                    "ppid": ppid,
                    "parent_name": names_by_pid.get(int(ppid)) if ppid is not None else None,
                    "username": username,
                    "child_pids": children_by_ppid.get(int(pid), []) if pid is not None else [],
                    "executable_basename": _basename(exe) or str(name),
                    "status": status,
                    "access_denied_fields": denied,
                    # Honest unknowns — see _UNAVAILABLE_FACTS.
                    "elevated": None,
                    "integrity_level": None,
                    "publisher": None,
                    "signature_status": "unknown",
                    "unavailable_facts": list(_UNAVAILABLE_FACTS),
                    "unavailable_facts_reason": (
                        "requires platform-specific signature/token APIs not used by this scanner"
                    ),
                },
                rule_bucket=RiskBucket.unknown,
                confidence=0.45,
                reasoning="Live process snapshot — rules engine refines risk.",
            )
        )
    return out
