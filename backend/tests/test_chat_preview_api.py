"""Read-only chat command preview — deterministic parser, no execution, no OS access."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import psutil
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import ActionPolicy, ItemType, PermissionMode, ProcessControlCategory, RiskBucket
from app.models.scan_item import ExplanationBlock, ProcessControl, ScanItem
from app.models.schemas import ScanResult, ScanSummary
from app.services import scan_state
from app.services.chat_preview import detect_intent

DISCLAIMER = "Preview only. No process was ended, suspended, or modified."


def _proc(
    item_id: str,
    pid: int,
    *,
    category: ProcessControlCategory,
    policy: ActionPolicy,
    safe_to_suspend: bool = False,
    item_type: ItemType = ItemType.process,
    blocked_reason: str | None = None,
    protected: bool = False,
    summary: str | None = None,
) -> ScanItem:
    return ScanItem(
        id=item_id,
        item_type=item_type,
        source="processes",
        display_name=item_id,
        raw_name=f"{item_id}.exe",
        path=rf"C:\Apps\{item_id}.exe",
        bucket=RiskBucket.unknown,
        protected=protected,
        scanner_facts={"pid": pid},
        explanation=ExplanationBlock(summary=f"{item_id} explanation"),
        process_control=ProcessControl(
            applicable=True,
            category=category,
            action_policy=policy,
            safe_to_suspend=safe_to_suspend,
            blocked_reason=blocked_reason,
            user_visible_summary=summary,
            evidence=["test:seeded"],
        ),
    )


ESSENTIAL = _proc(
    "lsass",
    4,
    category=ProcessControlCategory.essential,
    policy=ActionPolicy.blocked,
    blocked_reason="Hard-protected security stack.",
    protected=True,
)
UNKNOWN = _proc("abcxyz", 4410, category=ProcessControlCategory.unknown, policy=ActionPolicy.report_only)
SUSPENDABLE = _proc(
    "spotify",
    9134,
    category=ProcessControlCategory.non_essential,
    policy=ActionPolicy.preview_required,
    safe_to_suspend=True,
    summary="Music player — safe to pause.",
)
EXPLICIT = _proc(
    "discord",
    9140,
    category=ProcessControlCategory.gaming_fps_impact,
    policy=ActionPolicy.explicit_selection_required,
    safe_to_suspend=True,
)
SERVICE = _proc(
    "audiosrv",
    0,
    category=ProcessControlCategory.important,
    policy=ActionPolicy.report_only,
    item_type=ItemType.service,
)

ALL_ITEMS = [ESSENTIAL, UNKNOWN, SUSPENDABLE, EXPLICIT, SERVICE]


def _scan(items: list[ScanItem]) -> ScanResult:
    return ScanResult(
        summary=ScanSummary(
            scan_id="chat-scan-1",
            platform="win32",
            mode=PermissionMode.read_only,
            items_count=len(items),
            buckets={},
            generated_at="2026-01-01T00:00:00+00:00",
        ),
        items=items,
    )


@pytest.fixture
def client():
    scan_state.reset_for_tests()
    return TestClient(app)


def _with_scan(scan: ScanResult | None):
    return patch("app.main.latest_scan_from_db", new=AsyncMock(return_value=scan))


_DEFAULT_SCAN = object()  # sentinel: `scan=None` must be able to mean "no scan exists"


def _ask(client, message: str, *, confirm: bool = False, scan=_DEFAULT_SCAN):
    with _with_scan(_scan(ALL_ITEMS) if scan is _DEFAULT_SCAN else scan):
        r = client.post(
            "/api/chat/command-preview",
            json={"message": message, "confirm_explicit_selection": confirm},
        )
    assert r.status_code == 200, r.text
    return r.json()


# --- parser ------------------------------------------------------------------


@pytest.mark.parametrize(
    "message,intent",
    [
        ("What can I close before gaming?", "gaming_safety_preview"),
        ("Show FPS-impacting apps", "gaming_safety_preview"),
        ("my game is lagging", "gaming_safety_preview"),
        ("What can I safely suspend?", "safe_suspend_preview"),
        ("Explain Chrome", "explain_process"),
        ("why is chrome using so much memory", "explain_process"),
        ("Why is this locked?", "protected_inventory"),
        ("what is protected", "protected_inventory"),
        ("What is unknown?", "unknown_inventory"),
        ("hello there", "help"),
        ("", "help"),
    ],
)
def test_intent_routing_covers_the_documented_commands(message, intent):
    assert detect_intent(message) == intent


def test_generic_verbs_do_not_match_inside_longer_words():
    """Word-boundary matching: 'recommend' contains 'end', 'games' must not come from 'gamesomething'."""
    assert detect_intent("any recommendations for me") == "help"
    assert detect_intent("tell me about vendor signatures") == "explain_process"


# --- no scan -----------------------------------------------------------------


def test_no_scan_returns_helpful_message_not_an_error(client):
    body = _ask(client, "What can I close before gaming?", scan=None)
    assert body["intent"] == "gaming_safety_preview"
    assert "run a scan" in body["summary"].lower()
    assert body["items"] == [] and body["blocked"] == []
    assert body["preview"] is None
    assert [a["kind"] for a in body["actions"]] == ["run_scan"]
    assert body["disclaimer"] == DISCLAIMER


# --- gaming / safe-suspend ---------------------------------------------------


def test_gaming_returns_only_previewable_candidates(client):
    body = _ask(client, "What can I close before gaming?")
    assert body["intent"] == "gaming_safety_preview"
    # spotify (non-essential, safe_to_suspend) is the only one clearable without confirmation.
    assert [i["id"] for i in body["items"]] == ["spotify"]
    assert all(i["status"] == "would_allow" for i in body["items"])
    # Only FPS-impacting / non-essential are even considered candidates.
    assert {i["id"] for i in body["items"] + body["blocked"]} == {"spotify", "discord"}
    assert body["preview"]["preview_id"] is None
    assert body["disclaimer"] == DISCLAIMER


def test_safe_suspend_blocks_essential_unknown_and_report_only(client):
    body = _ask(client, "What can I safely suspend?")
    assert body["intent"] == "safe_suspend_preview"
    assert [i["id"] for i in body["items"]] == ["spotify"]
    blocked = {i["id"]: i for i in body["blocked"]}
    assert set(blocked) == {"lsass", "abcxyz", "discord", "audiosrv"}
    assert all(b["status"] == "blocked" for b in blocked.values())
    # Unknown and report-only are never offered an action.
    assert "report-only" in blocked["abcxyz"]["reason"].lower()
    assert "report-only" in blocked["audiosrv"]["reason"].lower()


def test_explicit_selection_requires_confirm_flag(client):
    without = _ask(client, "What can I close before gaming?")
    with_confirm = _ask(client, "What can I close before gaming?", confirm=True)

    assert "discord" in {i["id"] for i in without["blocked"]}
    assert any("explicit selection" in w.lower() for w in without["warnings"])
    assert "confirm_explicit_selection" in {a["kind"] for a in without["actions"]}

    assert {i["id"] for i in with_confirm["items"]} == {"spotify", "discord"}
    assert with_confirm["blocked"] == []


def test_confirmation_never_unlocks_essential_or_unknown(client):
    body = _ask(client, "What can I safely suspend?", confirm=True)
    allowed = {i["id"] for i in body["items"]}
    assert allowed == {"spotify", "discord"}
    assert "lsass" not in allowed and "abcxyz" not in allowed


# --- destructive wording -----------------------------------------------------


@pytest.mark.parametrize("message", ["kill lsass", "end all background apps", "shut down discord"])
def test_destructive_wording_stays_preview_only(client, message):
    body = _ask(client, message)
    assert body["intent"] in {"safe_suspend_preview", "gaming_safety_preview"}
    assert any("not implemented" in w.lower() for w in body["warnings"])
    assert body["disclaimer"] == DISCLAIMER
    assert body["preview"]["preview_id"] is None  # no execute token is ever minted
    # Generated prose must never claim something happened. The disclaimer and warnings are
    # excluded on purpose — they are negations ("No process *was ended*...").
    prose = " ".join(
        [body["summary"]]
        + [i["reason"] for i in body["items"] + body["blocked"]]
        + [a["label"] for a in body["actions"]]
    ).lower()
    for claim in ("was ended", "was suspended", "has been", "killed", "terminated", "we ended"):
        assert claim not in prose


def test_kill_request_for_essential_process_is_refused(client):
    body = _ask(client, "kill lsass", confirm=True)
    lsass = next(i for i in body["blocked"] if i["id"] == "lsass")
    assert lsass["status"] == "blocked"
    assert "lsass" not in {i["id"] for i in body["items"]}


# --- explain -----------------------------------------------------------------


def test_explain_by_pid(client):
    body = _ask(client, "explain 9134")
    assert body["intent"] == "explain_process"
    assert body["detail"]["id"] == "spotify"
    assert body["detail"]["pid"] == 9134
    assert body["detail"]["process_control"]["category"] == "non_essential"
    assert body["detail"]["evidence"] == ["test:seeded"]
    assert body["detail"]["scanner_facts"]["pid"] == 9134
    assert body["items"][0]["status"] == "informational"


def test_explain_by_name(client):
    body = _ask(client, "Explain spotify")
    assert body["detail"]["id"] == "spotify"
    assert body["summary"] == "Music player — safe to pause."
    assert body["items"] == [] or body["items"][0]["status"] == "informational"


def test_explain_by_raw_name_with_extension(client):
    assert _ask(client, "what is discord.exe")["detail"]["id"] == "discord"


def test_explain_surfaces_blocked_reason(client):
    body = _ask(client, "explain lsass")
    assert body["detail"]["blocked_reason"] == "Hard-protected security stack."
    assert body["items"] == [] or body["items"][0]["status"] == "informational"


def test_explain_matches_one_word_of_a_multi_word_display_name(client):
    """The documented example: "Explain Chrome" must resolve to "Google Chrome"."""
    chrome = _proc(
        "chrome-main",
        700,
        category=ProcessControlCategory.gaming_fps_impact,
        policy=ActionPolicy.preview_required,
    )
    chrome.display_name = "Google Chrome"
    helper = _proc(
        "chrome-helper",
        701,
        category=ProcessControlCategory.unknown,
        policy=ActionPolicy.report_only,
    )
    helper.display_name = "Google Chrome Helper (Renderer)"

    body = _ask(client, "Explain Chrome", scan=_scan([chrome, helper]))
    # Shorter name wins the tie — the main app, not a helper.
    assert body["detail"]["display_name"] == "Google Chrome"


def test_explain_unmatched_target_is_a_warning_not_a_crash(client):
    body = _ask(client, "explain notarealprocess")
    assert body["detail"] is None
    assert any("matched" in w.lower() for w in body["warnings"])
    assert body["disclaimer"] == DISCLAIMER


# --- inventories -------------------------------------------------------------


def test_unknown_inventory_is_informational_and_not_actionable(client):
    body = _ask(client, "What is unknown?")
    assert body["intent"] == "unknown_inventory"
    assert body["items"] == []  # nothing is ever offered for unknown items
    assert [i["id"] for i in body["blocked"]] == ["abcxyz"]
    assert body["blocked"][0]["status"] == "informational"


def test_protected_inventory_lists_locked_items(client):
    body = _ask(client, "Why is this locked?")
    assert body["intent"] == "protected_inventory"
    assert body["items"] == []
    assert [i["id"] for i in body["blocked"]] == ["lsass"]
    assert body["blocked"][0]["blocked_reason"] == "Hard-protected security stack."


def test_help_fallback_lists_examples(client):
    body = _ask(client, "hello")
    assert body["intent"] == "help"
    assert "Explain Chrome" in body["summary"]
    assert body["items"] == [] and body["blocked"] == []
    assert body["disclaimer"] == DISCLAIMER


# --- safety ------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "What can I close before gaming?",
        "What can I safely suspend?",
        "kill lsass",
        "explain 9134",
        "Why is this locked?",
        "What is unknown?",
        "hello",
    ],
)
def test_every_response_carries_the_preview_disclaimer(client, message):
    assert _ask(client, message)["disclaimer"] == DISCLAIMER


def test_endpoint_never_mutates_os_state(client, monkeypatch):
    def boom(*_a, **_kw):
        raise AssertionError("chat preview must not touch live processes")

    for name in ("kill", "terminate", "suspend", "resume"):
        monkeypatch.setattr(psutil.Process, name, boom, raising=False)
    monkeypatch.setattr(psutil, "process_iter", boom)

    for message in ("kill lsass", "What can I close before gaming?", "explain 9134", "shut down discord"):
        body = _ask(client, message, confirm=True)
        assert body["disclaimer"] == DISCLAIMER


def test_chat_preview_never_mints_an_execute_token(client):
    body = _ask(client, "What can I safely suspend?", confirm=True)
    assert "confirmation_token" not in body
    assert body["preview"]["preview_id"] is None
    assert all(a["endpoint"] != "/api/processes/end" for a in body["actions"])


def test_process_end_remains_not_implemented(client):
    r = client.post("/api/processes/end", json={})
    assert r.status_code == 501
    assert r.json()["detail"] == "Process execution is not implemented yet. Use preview endpoints only."
