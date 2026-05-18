from __future__ import annotations

import hashlib
import os
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class WalkStats:
    files_seen: int = 0
    skipped_permission: int = 0
    skipped_locked: int = 0
    dirs_visited: int = 0
    bytes_accounted: int = 0
    timed_out: bool = False
    symlink_loops_skipped: int = 0


def sha256_file(path: Path, max_bytes: int | None = None, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    read = 0
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
            read += len(b)
            if max_bytes is not None and read >= max_bytes:
                break
    return h.hexdigest()


def path_depth(p: Path) -> int:
    return len(p.parts)


def safe_iterdir(path: Path) -> list[Path]:
    try:
        return sorted(path.iterdir(), key=lambda x: x.name.lower())
    except (PermissionError, OSError):
        return []


def _inode_key(st: os.stat_result) -> tuple[int, int] | None:
    ino = int(getattr(st, "st_ino", 0) or 0)
    dev = int(getattr(st, "st_dev", 0) or 0)
    if ino == 0:
        return None
    return (dev, ino)


def _deadline_from_timeout(timeout_seconds: float | None) -> float | None:
    if timeout_seconds is None or timeout_seconds <= 0:
        return None
    return time.monotonic() + timeout_seconds


def walk_deadline(timeout_seconds: float | None) -> float | None:
    """Monotonic deadline for bounded_walk, or None if no limit."""
    return _deadline_from_timeout(timeout_seconds)


def _timed_out(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() > deadline


def bounded_walk(
    root: Path,
    *,
    max_files: int,
    max_depth: int,
    max_total_bytes: int = 2**63,
    deadline: float | None = None,
    on_file: Callable[[Path], None] | None = None,
) -> tuple[WalkStats, bool]:
    """
    BFS directory walk with caps. Symlink-aware; (dev,ino) cycle detection when available.
    Returns (stats, truncated) where truncated means a cap (files, depth, bytes, time) was hit.
    """
    stats = WalkStats()
    truncated = False

    if not root.exists():
        return stats, False

    try:
        root_rp = root.resolve()
    except (OSError, RuntimeError):
        root_rp = root

    q: deque[tuple[Path, int]] = deque([(root_rp, 0)])
    seen_dirs: set[tuple[int, int] | str] = set()

    while q:
        if _timed_out(deadline):
            stats.timed_out = True
            truncated = True
            break
        if stats.files_seen >= max_files:
            truncated = True
            break
        if stats.bytes_accounted >= max_total_bytes:
            truncated = True
            break

        current, depth = q.popleft()
        if depth > max_depth:
            continue

        try:
            st = current.lstat()
        except (PermissionError, OSError):
            stats.skipped_permission += 1
            continue

        inode_key = _inode_key(st)
        if current.is_dir() and not current.is_symlink():
            dk: tuple[int, int] | str = inode_key if inode_key is not None else str(current)
            if dk in seen_dirs:
                stats.symlink_loops_skipped += 1
                continue
            seen_dirs.add(dk)

        if current.is_symlink():
            try:
                target = current.resolve()
            except (OSError, RuntimeError):
                continue
            try:
                if not target.exists():
                    continue
            except OSError:
                continue
            tst = None
            tk = None
            try:
                tst = target.lstat()
                tk = _inode_key(tst)
            except OSError:
                tst = None
                tk = None
            if target.is_dir():
                if tk is not None and tk in seen_dirs:
                    stats.symlink_loops_skipped += 1
                    continue
                if depth + 1 <= max_depth:
                    if tk is not None:
                        seen_dirs.add(tk)
                    q.append((target, depth + 1))
                continue
            if target.is_file():
                if stats.files_seen >= max_files:
                    truncated = True
                    break
                try:
                    sz = int(tst.st_size) if tst is not None else int(target.stat().st_size)
                except OSError:
                    stats.skipped_permission += 1
                    continue
                if stats.bytes_accounted + sz > max_total_bytes:
                    truncated = True
                    break
                stats.files_seen += 1
                stats.bytes_accounted += sz
                if on_file:
                    try:
                        on_file(target)
                    except OSError:
                        stats.skipped_locked += 1
            continue

        if current.is_file():
            if stats.files_seen >= max_files:
                truncated = True
                break
            try:
                sz = int(st.st_size)
            except OSError:
                stats.skipped_permission += 1
                continue
            if stats.bytes_accounted + sz > max_total_bytes:
                truncated = True
                break
            stats.files_seen += 1
            stats.bytes_accounted += sz
            if on_file:
                try:
                    on_file(current)
                except OSError:
                    stats.skipped_locked += 1
            continue

        if current.is_dir():
            stats.dirs_visited += 1
            for child in safe_iterdir(current):
                if _timed_out(deadline):
                    stats.timed_out = True
                    truncated = True
                    break
                if stats.files_seen >= max_files:
                    truncated = True
                    break
                q.append((child, depth + 1))
            if stats.timed_out or (truncated and stats.files_seen >= max_files):
                break

    return stats, truncated


def directory_contains_any_file(
    dir_path: Path,
    *,
    max_depth: int,
    max_files: int,
    max_total_bytes: int,
    timeout_seconds: float | None,
) -> tuple[bool, WalkStats, bool]:
    """True if any file exists under dir_path within limits."""

    found = False

    def on_file(_: Path) -> None:
        nonlocal found
        found = True

    dl = walk_deadline(timeout_seconds)
    stats, trunc = bounded_walk(
        dir_path,
        max_files=max(1, max_files),
        max_depth=max_depth,
        max_total_bytes=max_total_bytes,
        deadline=dl,
        on_file=on_file,
    )
    return found, stats, trunc


def try_file_size(path: Path) -> int | None:
    try:
        return int(path.stat().st_size)
    except OSError:
        return None


def is_probably_locked(path: Path) -> bool:
    if os.name == "nt":
        try:
            with path.open("a"):
                pass
            return False
        except OSError:
            return True
    try:
        with path.open("rb"):
            return False
    except OSError:
        return True
