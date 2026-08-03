"""Scanner contract guardrails: scanners stay read-only, output stays canonical.

Turns the manual VERSION_API_CONTRACT_AUDIT findings ("scanners are read-only",
"scanner output normalizes into ScanItem") into automated checks so a future
scanner change can't silently regress either property.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.models.user_settings import ScannerToggles
from app.services import scan_service

SCANNERS_DIR = Path(__file__).parents[1] / "app" / "scanners"

# Case-insensitive substrings that have no legitimate reason to appear in a
# read-only scanner. Presence means a scanner started mutating the system.
FORBIDDEN_SUBSTRINGS = (
    "os.remove(",
    ".unlink(",
    "rmtree(",
    ".kill(",
    ".terminate(",
    ".suspend(",
    "rm -rf",
    "os.system(",
)

# subprocess.run/Popen argv lists a scanner is allowed to execute. Anything
# else (e.g. `schtasks /delete`, `taskkill`) fails the test — extend this
# allowlist deliberately, never widen FORBIDDEN_SUBSTRINGS to work around it.
ALLOWED_SUBPROCESS_ARGV = {
    ("schtasks", "/query", "/xml"),
    ("schtasks", "/query", "/fo", "LIST", "/v"),
}


def _subprocess_argv_calls(tree: ast.AST) -> list[list[str]]:
    calls: list[list[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_subprocess_call = (
            isinstance(func, ast.Attribute)
            and func.attr in ("run", "Popen", "call", "check_output")
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
        )
        if not is_subprocess_call or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.List) and all(isinstance(e, ast.Constant) for e in first.elts):
            calls.append([e.value for e in first.elts])
    return calls


def _scanner_files() -> list[Path]:
    return sorted(SCANNERS_DIR.glob("*.py"))


@pytest.mark.parametrize("path", _scanner_files(), ids=lambda p: p.name)
def test_scanner_source_has_no_destructive_calls(path: Path) -> None:
    text = path.read_text()
    lowered = text.lower()
    hits = [pat for pat in FORBIDDEN_SUBSTRINGS if pat in lowered]
    assert not hits, f"{path.name} contains destructive-looking call(s): {hits}"


@pytest.mark.parametrize("path", _scanner_files(), ids=lambda p: p.name)
def test_scanner_subprocess_calls_are_allowlisted(path: Path) -> None:
    tree = ast.parse(path.read_text(), filename=str(path))
    for argv in _subprocess_argv_calls(tree):
        assert tuple(argv) in ALLOWED_SUBPROCESS_ARGV, (
            f"{path.name} runs non-allowlisted subprocess command: {argv}"
        )


REQUIRED_SCAN_ITEM_FIELDS = (
    "id",
    "scan_version",
    "item_type",
    "source",
    "display_name",
    "bucket",
    "risk_level",
    "protected",
    "cleanup_eligible",
    "performance_eligible",
    "process_control",
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLEANER_DATA_DIR", str(tmp_path))
    assert get_settings().database_path == tmp_path / "opencleaner.db"
    yield tmp_path


def test_scan_items_normalize_into_canonical_scan_item_shape(monkeypatch):
    monkeypatch.setenv("OPENCLEANER_USE_MOCK", "1")
    with TestClient(app) as client:
        resp = client.post("/api/scan")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items, "mock scan produced no items to check"

    for item in items:
        missing = [f for f in REQUIRED_SCAN_ITEM_FIELDS if f not in item]
        assert not missing, f"item {item.get('id')!r} missing canonical field(s): {missing}"


def test_one_scanner_failure_does_not_abort_the_whole_scan(monkeypatch):
    def boom():
        raise RuntimeError("synthetic scanner failure")

    monkeypatch.setattr(scan_service, "scan_startup", boom)
    monkeypatch.setattr(scan_service, "scan_services", lambda: [])

    toggles = ScannerToggles(files=False, browser=False, startup=True, tasks=False, performance=False)
    raw, warnings = scan_service._collect_raw_scored(toggles)

    assert any("startup" in w and "did not complete" in w for w in warnings)
    # no live scanner produced items, but the exception didn't propagate — the
    # collector still ran its empty-result fallback instead of crashing.
    assert raw
