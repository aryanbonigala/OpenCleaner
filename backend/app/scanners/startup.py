from __future__ import annotations

import os
import sys
from pathlib import Path

from app.models.schemas import ItemType, RiskBucket, ScoredItem
from app.platform.detect import OSFamily, detect_os
from app.scanners import scan_limits as L
from app.utils.fs import bounded_walk, stable_path_id, walk_deadline


def _win_startup_registry() -> list[ScoredItem]:
    items: list[ScoredItem] = []
    try:
        import winreg  # type: ignore
    except Exception:
        return items

    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
    ]

    for hive, sub in keys:
        try:
            with winreg.OpenKey(hive, sub) as k:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(k, i)
                        i += 1
                        items.append(
                            ScoredItem(
                                id=f"startup-reg-{hive}-{name}",
                                category="startup",
                                item_type=ItemType.startup_entry,
                                name=name,
                                path=str(value),
                                detail={"location": sub, "hive": str(hive), "startup": True},
                                rule_bucket=RiskBucket.unknown,
                                confidence=0.55,
                                reasoning="Registry Run key entry.",
                            )
                        )
                    except OSError:
                        break
        except OSError:
            continue

    return items


def _win_startup_folders() -> list[ScoredItem]:
    items: list[ScoredItem] = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("PROGRAMDATA")
    candidates: list[Path] = []
    if appdata:
        candidates.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")
    if programdata:
        candidates.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")

    for folder in candidates:
        if not folder.exists():
            continue

        def on_file(p: Path) -> None:
            items.append(
                ScoredItem(
                    # Keyed on the full path, not the name: the same shortcut in both
                    # the per-user and all-users Startup folders is two real entries.
                    id=stable_path_id("startup-folder", p),
                    category="startup",
                    item_type=ItemType.startup_entry,
                    name=p.name,
                    path=str(p),
                    detail={"location": "StartupFolder", "startup": True},
                    rule_bucket=RiskBucket.unknown,
                    confidence=0.55,
                    reasoning="Shell Startup folder shortcut or script.",
                )
            )

        bounded_walk(
            folder,
            max_files=L.STARTUP_FOLDER_MAX_FILES,
            max_depth=L.STARTUP_FOLDER_MAX_DEPTH,
            max_total_bytes=L.STARTUP_FOLDER_MAX_BYTES,
            deadline=walk_deadline(L.STARTUP_FOLDER_TIMEOUT_S),
            on_file=on_file,
        )
    return items


def _darwin_launch_agents() -> list[ScoredItem]:
    """
    Architecture-ready: enumerate user LaunchAgents / LaunchDaemons (read-only metadata).
    """
    items: list[ScoredItem] = []
    home = Path.home()
    dirs = [
        (home / "Library" / "LaunchAgents", "user-agents"),
        (Path("/Library/LaunchAgents"), "system-agents"),
        (Path("/Library/LaunchDaemons"), "system-daemons"),
    ]
    for d, scope in dirs:
        if not d.exists():
            continue

        def on_file(p: Path, scope: str = scope) -> None:
            # The same plist stem (e.g. a vendor's bundle id) can legitimately appear in more
            # than one of these directories at once — the scope keeps `id` unique per location
            # instead of colliding on the scan_items.id primary key.
            if p.suffix.lower() != ".plist":
                return
            items.append(
                ScoredItem(
                    id=f"launchd-{scope}-{p.stem}",
                    category="startup",
                    item_type=ItemType.startup_entry,
                    name=p.stem,
                    path=str(p),
                    detail={"location": "launchd", "startup": True, "platform": "darwin"},
                    rule_bucket=RiskBucket.unknown,
                    confidence=0.5,
                    reasoning="macOS launchd plist — review Label/ProgramArguments before changes.",
                )
            )

        bounded_walk(
            d,
            max_files=L.STARTUP_FOLDER_MAX_FILES,
            max_depth=2,
            max_total_bytes=L.STARTUP_FOLDER_MAX_BYTES,
            deadline=walk_deadline(L.STARTUP_FOLDER_TIMEOUT_S),
            on_file=on_file,
        )
    return items


def scan_startup() -> list[ScoredItem]:
    if detect_os() == OSFamily.windows and sys.platform == "win32":
        return _win_startup_registry() + _win_startup_folders()
    if detect_os() == OSFamily.darwin:
        return _darwin_launch_agents()
    return [
        ScoredItem(
            id="startup-linux-stub",
            category="startup",
            item_type=ItemType.startup_entry,
            name="systemd/user units",
            path=None,
            detail={
                "platform": "linux",
                "note": "Future: enumerate systemd user units (.config/systemd/user).",
            },
            rule_bucket=RiskBucket.unknown,
            confidence=0.35,
            reasoning="Linux autostart enumeration scheduled for future adapter.",
        )
    ]
