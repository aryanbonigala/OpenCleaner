"""Action-safety contract guardrails: mutation-capable calls stay bounded.

Mirrors test_scanner_contract.py's pattern but for the action/mutation
boundary (backend/app/actions, pipeline, services, engine, main.py). Turns
the current, reviewed mutation surface into automated checks so a future
change can't silently add an unreviewed destructive or process-control call.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

APP_DIR = Path(__file__).parents[1] / "app"
ACTION_SCOPE_DIRS = ("actions", "pipeline", "services", "engine")

# Case-insensitive substrings that have no legitimate reason to appear in this
# scope unless a file/line is explicitly allowlisted below. Presence outside
# the allowlist means an unreviewed destructive call was added.
FORBIDDEN_SUBSTRINGS = (
    "os.remove(",
    ".unlink(",
    "shutil.rmtree(",
    "shutil.move(",
    ".rename(",
    ".kill(",
    ".terminate(",
    ".suspend(",
    "taskkill",
    "rm -rf",
    "os.system(",
)

# file -> forbidden substrings that file is allowed to contain, because the
# call is part of an already-implemented, reviewed, gated mutation path.
# Narrow this by function/line, not by disabling the whole file, if a file
# ever needs more than its currently-reviewed calls.
MUTATION_ALLOWLIST: dict[str, tuple[str, ...]] = {
    # quarantine move/restore/delete — the approved cleanup mutation path.
    "actions/quarantine.py": ("shutil.move(", "shutil.rmtree("),
    # retention purge of already-quarantined files past the policy window.
    "actions/quarantine_retention.py": (".unlink(",),
    # performance/game-boost session: suspends non-protected processes, but
    # only behind permission_mode == performance AND confirm_apply AND
    # protected_registry policy checks (see engine/protected_registry.py).
    # This is a distinct, already-implemented feature from process control
    # (kill/terminate a user-selected process via /api/processes/end), which
    # remains unimplemented — see test_processes_end_stays_unimplemented below.
    "actions/performance.py": (".suspend(",),
}

# subprocess.run/Popen argv lists this scope is allowed to execute. Anything
# else fails the test — extend this allowlist deliberately, never widen
# FORBIDDEN_SUBSTRINGS or MUTATION_ALLOWLIST to work around it.
ALLOWED_SUBPROCESS_ARGV = {
    ("powershell", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"),
    ("powercfg", "/s", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"),
    ("powercfg", "/s", "a1841308-3541-4fab-bc81-f71556f20b4a"),
}

# Preview-only modules/endpoints: must never contain a mutation-capable call,
# no allowlist exceptions permitted here.
NO_MUTATION_FILES = (
    "actions/cleanup_preview.py",
    "services/chat_preview.py",
)


def _action_scope_files() -> list[Path]:
    files = [APP_DIR / "main.py"]
    for d in ACTION_SCOPE_DIRS:
        files.extend(sorted((APP_DIR / d).glob("*.py")))
    return files


def _rel(path: Path) -> str:
    return str(path.relative_to(APP_DIR))


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


@pytest.mark.parametrize("path", _action_scope_files(), ids=_rel)
def test_action_scope_mutation_calls_are_allowlisted(path: Path) -> None:
    text = path.read_text()
    allowed = MUTATION_ALLOWLIST.get(_rel(path), ())
    hits = [pat for pat in FORBIDDEN_SUBSTRINGS if pat in text and pat not in allowed]
    assert not hits, f"{_rel(path)} contains non-allowlisted mutation call(s): {hits}"


@pytest.mark.parametrize("path", _action_scope_files(), ids=_rel)
def test_action_scope_subprocess_calls_are_allowlisted(path: Path) -> None:
    tree = ast.parse(path.read_text(), filename=str(path))
    for argv in _subprocess_argv_calls(tree):
        assert tuple(argv) in ALLOWED_SUBPROCESS_ARGV, (
            f"{_rel(path)} runs non-allowlisted subprocess command: {argv}"
        )


@pytest.mark.parametrize("relpath", NO_MUTATION_FILES)
def test_preview_modules_have_no_mutation_calls(relpath: str) -> None:
    text = (APP_DIR / relpath).read_text()
    hits = [pat for pat in FORBIDDEN_SUBSTRINGS if pat in text]
    assert not hits, f"{relpath} is preview-only but contains: {hits}"


def test_processes_end_stays_unimplemented() -> None:
    with TestClient(app) as client:
        resp = client.post("/api/processes/end")
    assert resp.status_code == 501
    assert "not implemented" in resp.json()["detail"].lower()


def test_no_process_kill_terminate_outside_allowlisted_performance_suspend() -> None:
    """Process kill/terminate is disallowed everywhere; suspend is allowed
    only in the reviewed, gated performance session path."""
    for path in _action_scope_files():
        text = path.read_text()
        rel = _rel(path)
        allowed = MUTATION_ALLOWLIST.get(rel, ())
        for pat in (".kill(", ".terminate(", "taskkill"):
            assert pat not in text, f"{rel} contains disallowed process-control call: {pat}"
        if ".suspend(" in text:
            assert ".suspend(" in allowed, f"{rel} contains unreviewed process suspend call"
