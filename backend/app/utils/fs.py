from __future__ import annotations

import hashlib
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator


@dataclass
class WalkResult:
    files_seen: int
    skipped_permission: int
    skipped_locked: int


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


def bounded_walk(
    root: Path,
    *,
    max_files: int,
    max_depth: int,
    on_file: Callable[[Path], None] | None = None,
) -> tuple[WalkResult, bool]:
    """
    BFS with symlink / cycle guard. Returns (stats, truncated).
    """
    result = WalkResult(0, 0, 0)
    if not root.exists():
        return result, False

    q: deque[tuple[Path, int, int]] = deque([(root.resolve(), 0, 0)])
    seen_inodes: set[tuple[int, int]] = set()
    truncated = False

    while q:
        current, depth, dev = q.popleft()
        if result.files_seen >= max_files:
            truncated = True
            break
        if depth > max_depth:
            continue

        try:
            st = current.lstat()
        except (PermissionError, OSError):
            result.skipped_permission += 1
            continue

        if st.st_ino and not current.is_symlink():
            key = (int(st.st_dev), int(st.st_ino))
            if key in seen_inodes:
                continue
            seen_inodes.add(key)

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
            if target.is_dir() and depth + 1 <= max_depth:
                q.append((target, depth + 1, dev))
            elif target.is_file():
                result.files_seen += 1
                if on_file:
                    try:
                        on_file(target)
                    except OSError:
                        result.skipped_locked += 1
            continue

        if current.is_file():
            result.files_seen += 1
            if on_file:
                try:
                    on_file(current)
                except OSError:
                    result.skipped_locked += 1
            continue

        if current.is_dir():
            for child in safe_iterdir(current):
                if result.files_seen >= max_files:
                    truncated = True
                    break
                q.append((child, depth + 1, dev))
            if truncated:
                break

    return result, truncated


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
