from __future__ import annotations

import os
import time
from collections import defaultdict
from pathlib import Path

from app.models.schemas import ItemType, RiskBucket, ScoredItem
from app.platform.detect import OSFamily, detect_os
from app.utils.fs import is_probably_locked, path_depth, sha256_file, try_file_size


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
            temp = Path(la) / "Temp"
            out["temp"] = temp
    elif detect_os() == OSFamily.darwin:
        out["downloads"] = home / "Downloads"
        out["desktop"] = home / "Desktop"
        out["temp"] = Path(os.environ.get("TMPDIR") or "/tmp")
    else:
        out["downloads"] = home / "Downloads"
        out["desktop"] = home / "Desktop"
        out["temp"] = Path(os.environ.get("TMPDIR") or "/tmp")
    return out


def scan_temp_and_cache(max_files: int = 400) -> list[ScoredItem]:
    items: list[ScoredItem] = []
    dirs = _user_special_dirs()
    temp = dirs.get("temp")
    if temp and temp.exists():
        count = 0
        for p in temp.iterdir() if temp.is_dir() else []:
            if count >= max_files:
                break
            try:
                if p.is_file():
                    sz = try_file_size(p) or 0
                    items.append(
                        ScoredItem(
                            id=f"temp-{p.name}-{count}",
                            category="temp_cache",
                            item_type=ItemType.file_or_folder,
                            name=p.name,
                            path=str(p),
                            detail={
                                "category_hint": "temp_cache",
                                "size_mb": round(sz / (1024 * 1024), 3),
                                "path_depth": path_depth(p),
                                "locked": is_probably_locked(p),
                                "age_days": round((time.time() - p.stat().st_mtime) / 86400, 1),
                            },
                            rule_bucket=RiskBucket.unknown,
                            confidence=0.5,
                            reasoning="Temp folder candidate — rules mark low risk when not locked.",
                        )
                    )
                    count += 1
            except OSError:
                continue
    return items


def scan_downloads(max_files: int = 260) -> list[ScoredItem]:
    items: list[ScoredItem] = []
    dl = _user_special_dirs().get("downloads")
    if not dl or not dl.exists():
        return items

    exts = {".msi", ".exe", ".dmg", ".pkg", ".zip", ".7z", ".tar", ".gz"}
    count = 0
    for p in dl.iterdir():
        if count >= max_files:
            break
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        hint = "installer_residual" if suf in exts else "downloads_general"
        try:
            sz = try_file_size(p) or 0
            items.append(
                ScoredItem(
                    id=f"dl-{p.name}-{count}",
                    category="downloads",
                    item_type=ItemType.file_or_folder,
                    name=p.name,
                    path=str(p),
                    detail={
                        "category_hint": hint,
                        "size_mb": round(sz / (1024 * 1024), 3),
                        "path_depth": path_depth(p),
                        "age_days": round((time.time() - p.stat().st_mtime) / 86400, 1),
                    },
                    rule_bucket=RiskBucket.unknown,
                    confidence=0.52,
                    reasoning="Downloads folder inventory — duplicates/old installers often reclaim space.",
                )
            )
            count += 1
        except OSError:
            continue
    return items


def scan_desktop_clutter(max_files: int = 200) -> list[ScoredItem]:
    items: list[ScoredItem] = []
    desk = _user_special_dirs().get("desktop")
    if not desk or not desk.exists():
        return items
    count = 0
    for p in desk.iterdir():
        if count >= max_files:
            break
        try:
            if p.is_file():
                sz = try_file_size(p) or 0
                items.append(
                    ScoredItem(
                        id=f"desk-{p.name}-{count}",
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
                count += 1
        except OSError:
            continue
    return items


def scan_large_unused_candidates(max_subtree_files: int = 80) -> list[ScoredItem]:
    """Find a few large files under downloads/videos as heuristic 'large unused' candidates."""
    items: list[ScoredItem] = []
    home = Path.home()
    candidates: list[tuple[Path, int]] = []

    scan_roots: list[Path] = []
    dl = _user_special_dirs().get("downloads")
    if dl:
        scan_roots.append(dl)
    vids = home / "Videos"
    scan_roots.append(vids if vids.exists() else home)

    for root in scan_roots:
        if not root.exists():
            continue
        try:
            scanned = 0
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                try:
                    sz = p.stat().st_size
                except OSError:
                    continue
                if sz > 750 * 1024 * 1024:
                    candidates.append((p, sz))
                scanned += 1
                if scanned >= max_subtree_files:
                    break
        except OSError:
            continue

    candidates.sort(key=lambda x: x[1], reverse=True)
    for p, sz in candidates[:15]:
        items.append(
            ScoredItem(
                id=f"large-{hash(str(p)) & 0xFFFFFFFF}",
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
    """
    Duplicate detection with size bucketing + partial hash; capped work for safety.
    """
    dl = _user_special_dirs().get("downloads")
    if not dl or not dl.exists():
        return []

    by_size: dict[int, list[Path]] = defaultdict(list)
    try:
        for p in dl.iterdir():
            if p.is_file():
                try:
                    by_size[p.stat().st_size].append(p)
                except OSError:
                    continue
    except OSError:
        return []

    items: list[ScoredItem] = []
    for size, paths in by_size.items():
        if len(paths) < 2 or size < 1024:
            continue
        hashes: dict[str, list[Path]] = defaultdict(list)
        for p in paths[:6]:
            try:
                h = sha256_file(p, max_bytes=2 * 1024 * 1024)
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
                    },
                    rule_bucket=RiskBucket.unknown,
                    confidence=0.6,
                    reasoning="Exact duplicate content detected via hashed prefix — keep one copy.",
                )
            )
    return items


def scan_orphans_lightweight() -> list[ScoredItem]:
    """
    Heuristic 'orphan' detection: empty directories under Start Menu Programs.
    Non-Windows returns empty.
    """
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
            if d.is_dir():
                try:
                    any_files = any(d.rglob("*"))
                except OSError:
                    any_files = True
                if not any_files:
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
