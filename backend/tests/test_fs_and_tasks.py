from __future__ import annotations

import os
import time
from pathlib import Path

from app.scanners.tasks import parse_tasks_xml_for_tests
from app.utils.fs import bounded_walk, directory_contains_any_file, walk_deadline


def test_bounded_walk_respects_max_files(tmp_path: Path) -> None:
    d = tmp_path / "d"
    d.mkdir()
    for i in range(5):
        (d / f"f{i}.txt").write_text("x", encoding="utf-8")
    stats, trunc = bounded_walk(d, max_files=3, max_depth=5)
    assert stats.files_seen == 3
    assert trunc is True


def test_bounded_walk_respects_max_bytes(tmp_path: Path) -> None:
    d = tmp_path / "d"
    d.mkdir()
    (d / "a.bin").write_bytes(b"x" * 100)
    (d / "b.bin").write_bytes(b"y" * 100)
    stats, trunc = bounded_walk(d, max_files=10, max_depth=3, max_total_bytes=150)
    assert stats.bytes_accounted <= 150
    assert trunc is True


def test_bounded_walk_symlink_non_windows_skip(tmp_path: Path) -> None:
    """Symlink loop test only meaningful on POSIX; Windows needs admin for symlinks."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    if os.name == "posix":
        os.symlink("../a", b / "loop", target_is_directory=True)
        (a / "file.txt").write_text("hi", encoding="utf-8")
    stats, _trunc = bounded_walk(
        a,
        max_files=50,
        max_depth=10,
        deadline=walk_deadline(5.0),
    )
    assert isinstance(stats.files_seen, int)


def test_bounded_walk_timeout(tmp_path: Path) -> None:
    d = tmp_path / "d"
    d.mkdir()
    (d / "one").write_text("1", encoding="utf-8")
    deadline = time.monotonic() + 0.001
    _stats, _trunc = bounded_walk(d, max_files=100, max_depth=3, deadline=deadline)


def test_directory_contains_any_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    has, _, __ = directory_contains_any_file(
        empty,
        max_depth=4,
        max_files=5,
        max_total_bytes=10_000,
        timeout_seconds=3.0,
    )
    assert has is False

    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "x").write_text("z", encoding="utf-8")
    has2, _, __ = directory_contains_any_file(
        nonempty,
        max_depth=4,
        max_files=5,
        max_total_bytes=10_000,
        timeout_seconds=3.0,
    )
    assert has2 is True


def test_parse_tasks_xml_fixture() -> None:
    fx = Path(__file__).resolve().parent / "fixtures" / "sample_tasks.xml"
    items = parse_tasks_xml_for_tests(fx.read_text(encoding="utf-8"))
    assert len(items) == 2
    names = {it.name for it in items}
    assert "OpenCleanerDemoTask" in names
    demo = next(it for it in items if it.name == "OpenCleanerDemoTask")
    assert str(demo.detail.get("command", "")).endswith("notepad.exe")
    assert demo.detail.get("status") == "enabled"
