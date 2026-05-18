from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.actions.performance import planned_suspend_actions
from app.engine.protected_registry import suspend_allowed_by_policy
from app.models.schemas import PerformancePreset


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
