from __future__ import annotations

import os
from pathlib import Path

from app.models.schemas import ItemType, RiskBucket, ScoredItem
from app.platform.detect import OSFamily, detect_os


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
        base = home / "Library" / "Caches"
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
        try:
            size_mb = sum(f.stat().st_size for f in root.rglob("*") if f.is_file()) / (1024 * 1024)
        except OSError:
            size_mb = 0.0
        items.append(
            ScoredItem(
                id=f"browser-{vendor}",
                category="browser_storage",
                item_type=ItemType.browser_profile,
                name=f"{vendor} profile/cache tree",
                path=str(root),
                detail={"vendor": vendor, "size_mb": round(float(size_mb), 2)},
                rule_bucket=RiskBucket.unknown,
                confidence=0.55,
                reasoning="Coarse folder size estimate — clearing should be explicit in Assisted mode.",
            )
        )
    return items
