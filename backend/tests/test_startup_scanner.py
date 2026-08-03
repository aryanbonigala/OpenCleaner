from __future__ import annotations

from pathlib import Path

from app.platform.detect import OSFamily
from app.scanners import startup as startup_module


def test_darwin_launch_agents_ids_unique_across_scopes(tmp_path, monkeypatch) -> None:
    """
    Regression test: a plist with the same stem (e.g. a vendor's bundle id) installed in
    both a user LaunchAgents dir and a system LaunchAgents/LaunchDaemons dir previously
    produced two ScoredItems sharing id=f"launchd-{stem}", which crashed scan persistence
    on the scan_items.id UNIQUE constraint. The scope must now be part of the id.
    """
    fake_home = tmp_path / "home"
    system_agents = tmp_path / "sys" / "LaunchAgents"
    system_daemons = tmp_path / "sys" / "LaunchDaemons"
    user_agents = fake_home / "Library" / "LaunchAgents"
    for d in (user_agents, system_agents, system_daemons):
        d.mkdir(parents=True)
    (user_agents / "com.example.thing.plist").write_text("<plist/>", encoding="utf-8")
    (system_agents / "com.example.thing.plist").write_text("<plist/>", encoding="utf-8")

    real_path = Path

    class RedirectingPath:
        def __new__(cls, *args):
            if args and str(args[0]) == "/Library/LaunchAgents":
                return system_agents
            if args and str(args[0]) == "/Library/LaunchDaemons":
                return system_daemons
            return real_path(*args)

        @staticmethod
        def home():
            return fake_home

    monkeypatch.setattr(startup_module, "Path", RedirectingPath)
    monkeypatch.setattr(startup_module, "detect_os", lambda: OSFamily.darwin)

    items = startup_module.scan_startup()

    ids = [it.id for it in items]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"
    assert {it.id for it in items} == {
        "launchd-user-agents-com.example.thing",
        "launchd-system-agents-com.example.thing",
    }
