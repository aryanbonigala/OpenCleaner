from __future__ import annotations

import psutil
import pytest

from app.models.schemas import ItemType
from app.scanners import processes as scanner


class FakeMem:
    rss = 64 * 1024 * 1024


class FakeProc:
    def __init__(self, pid: int, name: str, *, ppid: int = 1, raising: bool = False):
        self._raising = raising
        self.info = {
            "pid": pid,
            "ppid": ppid,
            "name": name,
            "exe": f"C:\\apps\\{name}",
            "memory_info": FakeMem(),
            "username": None if raising else "tester",
            "create_time": 1_700_000_000.0,
            "status": psutil.STATUS_RUNNING,
            "num_threads": 4,
        }

    def cpu_percent(self, interval=None):
        if self._raising:
            raise psutil.AccessDenied(self.info["pid"])
        return 3.5


def _patch_iter(monkeypatch, procs):
    def fake_iter(attrs=None):
        # psutil raises ValueError for attrs it does not implement — assert we only ask for good ones.
        assert set(attrs or []) <= set(scanner._ITER_ATTRS)
        return iter(procs)

    monkeypatch.setattr(scanner.psutil, "process_iter", fake_iter)


def test_iter_attrs_are_portable() -> None:
    """`cpu_num` is Linux-only and made process_iter raise on macOS/Windows."""
    assert "cpu_num" not in scanner._ITER_ATTRS
    valid = set(psutil.Process().as_dict().keys())
    assert set(scanner._ITER_ATTRS) <= valid


def test_scan_processes_returns_rows_on_this_platform() -> None:
    rows = scan = scanner.scan_processes(limit=5)
    assert rows, "live scan returned no processes"
    assert all(r.item_type is ItemType.process for r in scan)
    assert all("pid" in r.detail for r in rows)


def test_one_inaccessible_process_does_not_kill_the_scan(monkeypatch) -> None:
    _patch_iter(monkeypatch, [FakeProc(10, "ok.exe"), FakeProc(11, "denied.exe", raising=True)])
    rows = scanner.scan_processes()
    assert len(rows) == 2
    denied = next(r for r in rows if r.name == "denied.exe")
    assert denied.detail["cpu_percent"] == 0.0
    assert "username" in denied.detail["access_denied_fields"]
    assert "cpu_percent" in denied.detail["access_denied_fields"]


def test_process_iter_failure_returns_empty_not_exception(monkeypatch) -> None:
    def boom(attrs=None):
        raise ValueError("invalid attr name 'cpu_num'")

    monkeypatch.setattr(scanner.psutil, "process_iter", boom)
    assert scanner.scan_processes() == []


def test_expected_detail_fields_present(monkeypatch) -> None:
    _patch_iter(monkeypatch, [FakeProc(100, "parent.exe", ppid=1), FakeProc(101, "child.exe", ppid=100)])
    rows = {r.name: r.detail for r in scanner.scan_processes()}

    preserved = (
        "pid", "memory_mb", "cpu_percent", "gpu_heavy", "suspended",
        "cpu_affinity_count", "num_threads", "started_ts", "uptime_s",
    )
    added = (
        "ppid", "parent_name", "username", "child_pids", "executable_basename",
        "access_denied_fields", "elevated", "integrity_level", "publisher", "signature_status",
    )
    for field in preserved + added:
        assert field in rows["parent.exe"], field

    assert rows["child.exe"]["parent_name"] == "parent.exe"
    assert rows["parent.exe"]["child_pids"] == [101]
    assert rows["parent.exe"]["executable_basename"] == "parent.exe"
    assert rows["parent.exe"]["memory_mb"] == pytest.approx(64.0)


def test_unprovable_facts_are_reported_as_unknown(monkeypatch) -> None:
    _patch_iter(monkeypatch, [FakeProc(200, "app.exe")])
    d = scanner.scan_processes()[0].detail
    assert d["elevated"] is None
    assert d["integrity_level"] is None
    assert d["publisher"] is None
    assert d["signature_status"] == "unknown"
    assert d["unavailable_facts_reason"]


def test_limit_is_respected(monkeypatch) -> None:
    _patch_iter(monkeypatch, [FakeProc(i, f"p{i}.exe") for i in range(50)])
    assert len(scanner.scan_processes(limit=7)) == 7
