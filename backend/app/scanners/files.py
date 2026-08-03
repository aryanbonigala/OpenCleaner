from __future__ import annotations

import hashlib
import os
import time
from collections import defaultdict
from pathlib import Path

from app.models.schemas import ItemType, RiskBucket, ScoredItem
from app.platform.detect import OSFamily, detect_os
from app.scanners import scan_limits as L
from app.utils.fs import (
    bounded_walk,
    directory_contains_any_file,
    is_probably_locked,
    path_depth,
    sha256_file,
    try_file_size,
    walk_deadline,
)


def _user_special_dirs() -> dict[str, Path]:
    home = Path.home()
    out: dict[str, Path] = {"home": home}
    if detect_os() == OSFamily.windows:
        dl = Path.home() / "Downloads"
        desk = Path.home() / "Desktop"
        if os.environ.get("USERPROFILE"):
            up = Path(os.environ["USERPROFILE"])
            out["downloads"] = up / "Downloads"
            out["desktop"] = up / "Desktop"
        else:
            out["downloads"] = dl
            out["desktop"] = desk
        la = os.environ.get("LOCALAPPDATA")
        if la:
            out["temp"] = Path(la) / "Temp"
    elif detect_os() == OSFamily.darwin:
        out["downloads"] = home / "Downloads"
        out["desktop"] = home / "Desktop"
        out["temp"] = Path(os.environ.get("TMPDIR") or "/tmp")
    else:
        out["downloads"] = home / "Downloads"
        out["desktop"] = home / "Desktop"
        out["temp"] = Path(os.environ.get("TMPDIR") or "/tmp")
    return out


def scan_temp_and_cache() -> list[ScoredItem]:
    items: list[ScoredItem] = []
    dirs = _user_special_dirs()
    temp = dirs.get("temp")
    if not temp or not temp.exists():
        return items

    idx = 0

    def on_file(p: Path) -> None:
        nonlocal idx
        try:
            sz = try_file_size(p) or 0
            st = p.stat()
            items.append(
                ScoredItem(
                    id=f"temp-{p.name}-{idx}",
                    category="temp_cache",
                    item_type=ItemType.file_or_folder,
                    name=p.name,
                    path=str(p),
                    detail={
                        "category_hint": "temp_cache",
                        "size_mb": round(sz / (1024 * 1024), 3),
                        "path_depth": path_depth(p),
                        "locked": is_probably_locked(p),
                        "age_days": round((time.time() - st.st_mtime) / 86400, 1),
                    },
                    rule_bucket=RiskBucket.unknown,
                    confidence=0.5,
                    reasoning="Temp folder candidate — rules mark low risk when not locked.",
                )
            )
            idx += 1
        except OSError:
            pass

    stats, trunc = bounded_walk(
        temp,
        max_files=L.TEMP_MAX_FILES,
        max_depth=L.TEMP_MAX_DEPTH,
        max_total_bytes=L.TEMP_MAX_TOTAL_BYTES,
        deadline=walk_deadline(L.TEMP_TIMEOUT_S),
        on_file=on_file,
    )
    if trunc and items:
        items[-1].detail["scan_truncated"] = True
        items[-1].detail["walk_stats"] = {
            "files_seen": stats.files_seen,
            "timed_out": stats.timed_out,
            "bytes_accounted": stats.bytes_accounted,
        }
    return items


def scan_downloads() -> list[ScoredItem]:
    items: list[ScoredItem] = []
    dl = _user_special_dirs().get("downloads")
    if not dl or not dl.exists():
        return items
    exts = {".msi", ".exe", ".dmg", ".pkg", ".zip", ".7z", ".tar", ".gz"}
    idx = 0

    def on_file(p: Path) -> None:
        nonlocal idx
        try:
            suf = p.suffix.lower()
            hint = "installer_residual" if suf in exts else "downloads_general"
            sz = try_file_size(p) or 0
            st = p.stat()
            items.append(
                ScoredItem(
                    id=f"dl-{p.name}-{idx}",
                    category="downloads",
                    item_type=ItemType.file_or_folder,
                    name=p.name,
                    path=str(p),
                    detail={
                        "category_hint": hint,
                        "size_mb": round(sz / (1024 * 1024), 3),
                        "path_depth": path_depth(p),
                        "age_days": round((time.time() - st.st_mtime) / 86400, 1),
                    },
                    rule_bucket=RiskBucket.unknown,
                    confidence=0.52,
                    reasoning="Downloads folder inventory — duplicates/old installers often reclaim space.",
                )
            )
            idx += 1
        except OSError:
            pass

    stats, trunc = bounded_walk(
        dl,
        max_files=L.DOWNLOADS_MAX_FILES,
        max_depth=L.DOWNLOADS_MAX_DEPTH,
        max_total_bytes=L.DOWNLOADS_MAX_TOTAL_BYTES,
        deadline=walk_deadline(L.DOWNLOADS_TIMEOUT_S),
        on_file=on_file,
    )
    if trunc and items:
        items[-1].detail["scan_truncated"] = True
        items[-1].detail["walk_stats"] = {
            "files_seen": stats.files_seen,
            "timed_out": stats.timed_out,
            "bytes_accounted": stats.bytes_accounted,
        }
    return items


def scan_desktop_clutter() -> list[ScoredItem]:
    items: list[ScoredItem] = []
    desk = _user_special_dirs().get("desktop")
    if not desk or not desk.exists():
        return items
    idx = 0

    def on_file(p: Path) -> None:
        nonlocal idx
        try:
            sz = try_file_size(p) or 0
            items.append(
                ScoredItem(
                    id=f"desk-{p.name}-{idx}",
                    category="desktop",
                    item_type=ItemType.file_or_folder,
                    name=p.name,
                    path=str(p),
                    detail={
                        "category_hint": "desktop_clutter",
                        "size_mb": round(sz / (1024 * 1024), 3),
                        "path_depth": path_depth(p),
                    },
                    rule_bucket=RiskBucket.ask_user,
                    confidence=0.58,
                    reasoning="Desktop files are user-visible — confirm moves instead of deletion.",
                )
            )
            idx += 1
        except OSError:
            pass

    stats, trunc = bounded_walk(
        desk,
        max_files=L.DESKTOP_MAX_FILES,
        max_depth=L.DESKTOP_MAX_DEPTH,
        max_total_bytes=L.DESKTOP_MAX_TOTAL_BYTES,
        deadline=walk_deadline(L.DESKTOP_TIMEOUT_S),
        on_file=on_file,
    )
    if trunc and items:
        items[-1].detail["scan_truncated"] = True
        items[-1].detail["walk_stats"] = {"timed_out": stats.timed_out}
    return items


def scan_large_unused_candidates() -> list[ScoredItem]:
    items: list[ScoredItem] = []
    home = Path.home()
    candidates: list[tuple[Path, int]] = []
    roots: list[Path] = []
    dl = _user_special_dirs().get("downloads")
    if dl:
        roots.append(dl)
    vids = home / "Videos"
    roots.append(vids if vids.exists() else home)

    for root in roots:
        if not root.exists():
            continue

        def on_file(p: Path) -> None:
            try:
                sz = int(p.stat().st_size)
            except OSError:
                return
            if sz >= L.LARGE_FILE_THRESHOLD_BYTES:
                candidates.append((p, sz))

        bounded_walk(
            root,
            max_files=L.LARGE_FILE_SCAN_MAX_FILES,
            max_depth=L.LARGE_FILE_SCAN_MAX_DEPTH,
            max_total_bytes=L.LARGE_FILE_SCAN_MAX_TOTAL_BYTES,
            deadline=walk_deadline(L.LARGE_FILE_SCAN_TIMEOUT_S),
            on_file=on_file,
        )

    candidates.sort(key=lambda x: x[1], reverse=True)
    for p, sz in candidates[:15]:
        items.append(
            ScoredItem(
                # blake2b, not the builtin str hash: that one is salted per process,
                # so the same file got a brand new id on every scan.
                id=f"large-{hashlib.blake2b(str(p).encode(), digest_size=6).hexdigest()}",
                category="large_files",
                item_type=ItemType.file_or_folder,
                name=p.name,
                path=str(p),
                detail={
                    "category_hint": "large_user_file",
                    "size_mb": round(sz / (1024 * 1024), 2),
                    "path_depth": path_depth(p),
                },
                rule_bucket=RiskBucket.ask_user,
                confidence=0.56,
                reasoning="Large user-media/installer candidate — never auto-delete; review purpose.",
            )
        )
    return items


def scan_duplicates_limited() -> list[ScoredItem]:
    dl = _user_special_dirs().get("downloads")
    if not dl or not dl.exists():
        return []

    collected: list[Path] = []

    def on_file(p: Path) -> None:
        collected.append(p)

    bounded_walk(
        dl,
        max_files=L.DOWNLOADS_MAX_FILES,
        max_depth=1,
        max_total_bytes=L.DOWNLOADS_MAX_TOTAL_BYTES,
        deadline=walk_deadline(L.DOWNLOADS_TIMEOUT_S),
        on_file=on_file,
    )

    by_size: dict[int, list[Path]] = defaultdict(list)
    for p in collected:
        try:
            if p.is_file():
                by_size[p.stat().st_size].append(p)
        except OSError:
            continue

    items: list[ScoredItem] = []
    for size, paths in by_size.items():
        if len(paths) < 2 or size < 1024:
            continue
        if size > L.MAX_DUPLICATE_FILE_SIZE_TO_HASH_BYTES:
            continue
        hashes: dict[str, list[Path]] = defaultdict(list)
        for p in paths[:8]:
            try:
                h = sha256_file(p, max_bytes=L.MAX_DUPLICATE_HASH_BYTES)
                hashes[h].append(p)
            except OSError:
                continue
        for h, group in hashes.items():
            if len(group) < 2:
                continue
            items.append(
                ScoredItem(
                    id=f"dup-{h[:12]}",
                    category="duplicates",
                    item_type=ItemType.duplicate_group,
                    name=f"{group[0].name} (+{len(group)-1} copies)",
                    path=str(group[0]),
                    detail={
                        "duplicate_count": len(group),
                        "hash_prefix": h[:16],
                        "paths": [str(x) for x in group],
                        "size_mb": round(size / (1024 * 1024), 3),
                        "hash_bytes_capped": L.MAX_DUPLICATE_HASH_BYTES,
                    },
                    rule_bucket=RiskBucket.unknown,
                    confidence=0.6,
                    reasoning="Exact duplicate content detected via capped hash — keep one copy.",
                )
            )
    return items


def scan_orphans_lightweight() -> list[ScoredItem]:
    if detect_os() != OSFamily.windows or os.name != "nt":
        return []
    items: list[ScoredItem] = []
    pd = os.environ.get("PROGRAMDATA")
    if not pd:
        return items
    root = Path(pd) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    if not root.exists():
        return items
    try:
        for d in root.iterdir():
            if not d.is_dir():
                continue
            try:
                has_file, _, _ = directory_contains_any_file(
                    d,
                    max_depth=L.ORPHAN_DIR_CHECK_MAX_DEPTH,
                    max_files=L.ORPHAN_DIR_CHECK_MAX_FILES,
                    max_total_bytes=L.ORPHAN_DIR_CHECK_MAX_TOTAL_BYTES,
                    timeout_seconds=L.ORPHAN_DIR_CHECK_TIMEOUT_S,
                )
            except OSError:
                has_file = True
            if not has_file:
                items.append(
                    ScoredItem(
                        id=f"orphan-{d.name}",
                        category="orphans",
                        item_type=ItemType.orphan_app,
                        name=d.name,
                        path=str(d),
                        detail={"category_hint": "empty_startmenu_folder"},
                        rule_bucket=RiskBucket.unknown,
                        confidence=0.45,
                        reasoning="Empty start-menu folder — possible uninstall remnant.",
                    )
                )
    except OSError:
        return items
    return items
