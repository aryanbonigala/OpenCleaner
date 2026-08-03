from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.actions import performance
from app.actions.performance import (
    active_session,
    planned_suspend_actions,
    start_session,
    stop_session,
)
from app.engine.protected_registry import (
    DEFAULT_SOFT_SUSPEND_BASE_NAMES,
    suspend_allowed_by_policy,
)
from app.models.schemas import PerformancePreset


@pytest.fixture(autouse=True)
def _reset_session():
    performance._SESSION = None
    yield
    performance._SESSION = None


class FakeProcess:
    """Stand-in for psutil.Process/Process-iter entries. Never touches the OS."""

    def __init__(self, pid: int, name: str, status: str = "running") -> None:
        self.info = {"pid": pid, "name": name}
        self.pid = pid
        self._status = status
        self.suspend_calls = 0
        self.resume_calls = 0

    def status(self) -> str:
        return self._status

    def suspend(self) -> None:
        self.suspend_calls += 1

    def resume(self) -> None:
        self.resume_calls += 1

    def nice(self, *_args, **_kwargs) -> None:
        pass


def test_suspend_denies_lsass() -> None:
    ok, reason = suspend_allowed_by_policy("lsass.exe", explicit_target_basenames=frozenset())
    assert ok is False
    assert "hard-protected" in reason


def test_suspend_denies_chrome_without_explicit() -> None:
    ok, reason = suspend_allowed_by_policy("chrome.exe", explicit_target_basenames=frozenset())
    assert ok is False
    assert "browser" in reason


def test_suspend_allows_chrome_when_explicit() -> None:
    ok, reason = suspend_allowed_by_policy(
        "chrome.exe", explicit_target_basenames=frozenset({"chrome.exe"})
    )
    assert ok is True


@patch("app.actions.performance.psutil.process_iter")
def test_planned_suspend_never_lists_lsass(mock_iter) -> None:
    mock_iter.return_value = [SimpleNamespace(info={"pid": 99, "name": "lsass.exe"})]

    out = planned_suspend_actions(PerformancePreset.max_fps, [])
    assert out["would_suspend_count"] == 0


@patch("app.actions.performance.psutil.process_iter")
def test_preview_does_not_mutate(mock_iter) -> None:
    onedrive = FakeProcess(111, "onedrive.exe")
    mock_iter.return_value = [onedrive]

    out = planned_suspend_actions(PerformancePreset.max_fps, [])

    assert onedrive.suspend_calls == 0
    assert onedrive.resume_calls == 0
    assert out["would_suspend_count"] == 1
    assert out["would_suspend"][0]["pid"] == 111
    assert active_session() is None


@patch("app.actions.performance.subprocess.run")
@patch("app.actions.performance.psutil.process_iter")
def test_confirm_apply_false_blocks_mutation(mock_iter, mock_run) -> None:
    with pytest.raises(ValueError):
        start_session(PerformancePreset.max_fps, [], confirm_apply=False)

    mock_iter.assert_not_called()
    mock_run.assert_not_called()
    assert active_session() is None


@patch("app.actions.performance.subprocess.run")
@patch("app.actions.performance.psutil.process_iter")
def test_policy_gating_blocks_protected_and_unknown_processes(mock_iter, mock_run) -> None:
    protected = FakeProcess(222, "lsass.exe")
    unknown = FakeProcess(333, "some_random_app.exe")
    mock_iter.return_value = [protected, unknown]

    session = start_session(PerformancePreset.max_fps, [], confirm_apply=True)

    assert protected.suspend_calls == 0
    assert unknown.suspend_calls == 0
    assert session.suspended_pids == []
    mock_run.assert_not_called()


@patch("app.actions.performance.psutil.process_iter")
def test_allowed_soft_target_suspends_only_when_confirmed(mock_iter) -> None:
    target_name = next(iter(DEFAULT_SOFT_SUSPEND_BASE_NAMES))
    allowed = FakeProcess(444, target_name)
    protected = FakeProcess(222, "lsass.exe")
    mock_iter.return_value = [allowed, protected]

    session = start_session(PerformancePreset.max_fps, [], confirm_apply=True)

    assert allowed.suspend_calls == 1
    assert protected.suspend_calls == 0
    assert session.suspended_pids == [444]


@patch("app.actions.performance.psutil.Process")
@patch("app.actions.performance.psutil.process_iter")
def test_stop_resumes_only_suspended_pids(mock_iter, mock_process_ctor) -> None:
    target_name = next(iter(DEFAULT_SOFT_SUSPEND_BASE_NAMES))
    allowed = FakeProcess(444, target_name)
    protected = FakeProcess(222, "lsass.exe")
    mock_iter.return_value = [allowed, protected]

    start_session(PerformancePreset.max_fps, [], confirm_apply=True)
    assert active_session() is not None

    mock_process_ctor.side_effect = lambda pid: {444: allowed, 222: protected}[pid]
    stop_session()

    assert allowed.resume_calls == 1
    assert protected.resume_calls == 0
    assert active_session() is None
