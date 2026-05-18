from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Iterable

import psutil

from app.models.schemas import ItemType, RiskBucket, ScoredItem


def _gpu_heuristic(proc: psutil.Process, exe_name: str) -> bool:
    n = exe_name.lower()
    if any(k in n for k in ("obs64", "obs32", "chrome", "msedge", "firefox", "dwm", "game")):
        return True
    # Heuristic: very high CPU with certain names
    try:
        return proc.cpu_percent(interval=None) > 40 and "render" in n
    except Exception:
        return False


def scan_processes(limit: int = 220) -> list[ScoredItem]:
    out: list[ScoredItem] = []
    now = time.time()
    for p in list(psutil.process_iter(["pid", "name", "exe", "memory_info", "cpu_num"])):
        if len(out) >= limit:
            break
        try:
            info = p.info
            name = info.get("name") or f"pid_{info.get('pid')}"
            exe = info.get("exe") or ""
            mem = float((info.get("memory_info").rss or 0) / (1024 * 1024))  # type: ignore[union-attr]
            cpu = 0.0
            try:
                cpu = float(p.cpu_percent(interval=None))
            except Exception:
                cpu = 0.0
            gpu = _gpu_heuristic(p, name)
            suspended = False
            try:
                status = p.status()
                suspended = status == psutil.STATUS_STOPPED
            except Exception:
                pass

            out.append(
                ScoredItem(
                    id=f"proc-{info.get('pid')}",
                    category="processes",
                    item_type=ItemType.process,
                    name=name,
                    path=exe or None,
                    detail={
                        "pid": info.get("pid"),
                        "memory_mb": round(mem, 2),
                        "cpu_percent": round(cpu, 2),
                        "gpu_heavy": gpu,
                        "suspended": suspended,
                        "cpu_affinity_count": len(p.cpu_affinity()) if hasattr(p, "cpu_affinity") else None,
                        "num_threads": p.num_threads() if p else None,
                        "started_ts": p.create_time() if p else None,
                        "uptime_s": round(now - p.create_time(), 1) if p else None,
                    },
                    rule_bucket=RiskBucket.unknown,
                    confidence=0.45,
                    reasoning="Live process snapshot — rules engine refines risk.",
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return out
