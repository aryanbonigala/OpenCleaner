from __future__ import annotations

import os
from pathlib import Path

from app.models.schemas import ItemType, RiskBucket, ScoredItem
from app.platform.detect import OSFamily, detect_os
from app.scanners import scan_limits as L
from app.utils.fs import bounded_walk, walk_deadline


def _browser_roots() -> list[tuple[str, Path]]:
    roots: list[tuple[str, Path]] = []
    home = Path.home()
    if detect_os() == OSFamily.windows:
        la = os.environ.get("LOCALAPPDATA")
        if la:
            base = Path(la)
            roots.extend(
                [
                    ("Chrome", base / "Google" / "Chrome" / "User Data"),
                    ("Edge", base / "Microsoft" / "Edge" / "User Data"),
                    ("Brave", base / "BraveSoftware" / "Brave-Browser" / "User Data"),
                ]
            )
    elif detect_os() == OSFamily.darwin:
        roots.extend(
            [
                ("Chrome", home / "Library" / "Caches" / "Google" / "Chrome"),
                ("Safari", home / "Library" / "Caches" / "com.apple.Safari"),
            ]
        )
    else:
        roots.append(("Chromium", home / ".cache" / "chromium"))
    return roots


def scan_browser_profiles() -> list[ScoredItem]:
    items: list[ScoredItem] = []
    for vendor, root in _browser_roots():
        if not root.exists():
            continue
        total = 0
        counted = 0

        def on_file(p: Path) -> None:
            nonlocal total, counted
            try:
                total += int(p.stat().st_size)
                counted += 1
            except OSError:
                pass

        stats, trunc = bounded_walk(
            root,
            max_files=L.BROWSER_ROOT_MAX_FILES,
            max_depth=L.BROWSER_ROOT_MAX_DEPTH,
            max_total_bytes=L.BROWSER_ROOT_MAX_TOTAL_BYTES,
            deadline=walk_deadline(L.BROWSER_ROOT_TIMEOUT_S),
            on_file=on_file,
        )
        size_mb = total / (1024 * 1024)
        items.append(
            ScoredItem(
                id=f"browser-{vendor}",
                category="browser_storage",
                item_type=ItemType.browser_profile,
                name=f"{vendor} profile/cache tree",
                path=str(root),
                detail={
                    "vendor": vendor,
                    "size_mb": round(float(size_mb), 2),
                    "files_counted": counted,
                    "scan_truncated": trunc,
                    "walk_files_seen": stats.files_seen,
                    "timed_out": stats.timed_out,
                    "bytes_accounted": stats.bytes_accounted,
                },
                rule_bucket=RiskBucket.unknown,
                confidence=0.55,
                reasoning="Capped walk size estimate — clearing should be explicit in Assisted mode.",
            )
        )
    return items
