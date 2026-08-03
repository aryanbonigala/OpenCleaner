from __future__ import annotations

import pytest

from app.engine.process_action_policy import classify_process_control
from app.engine.process_classifier import stage_process_control
from app.models.enums import ActionPolicy, ItemType, ProcessControlCategory, RiskBucket
from app.models.scan_item import IntelligenceSnapshot, ProcessControl, ScanItem
from app.models.schemas import ScoredItem
from app.pipeline.normalize import normalize_scored_item
from app.pipeline.reasoning import run_reasoning_pipeline


def make_item(
    item_type: ItemType = ItemType.process,
    name: str = "unknownthing.exe",
    *,
    bucket: RiskBucket = RiskBucket.unknown,
    intelligence: IntelligenceSnapshot | None = None,
    **overrides,
) -> ScanItem:
    data = {
        "id": f"{item_type.value}-1",
        "item_type": item_type,
        "source": "test",
        "display_name": name,
        "raw_name": name,
        "bucket": bucket,
        "intelligence": intelligence,
    }
    data.update(overrides)
    return ScanItem(**data)


def intel(**kw) -> IntelligenceSnapshot:
    base = {"known": True, "applicable": True, "confidence": 0.85}
    base.update(kw)
    return IntelligenceSnapshot(**base)


def assert_no_safe_actions(pc: ProcessControl) -> None:
    assert pc.safe_to_end is False
    assert pc.safe_to_suspend is False
    assert pc.safe_to_disable_startup is False


# --- essential / hard-protected -------------------------------------------------

@pytest.mark.parametrize("name", ["lsass.exe", "csrss.exe", "winlogon.exe", "services.exe"])
def test_hard_protected_process_is_essential_and_blocked(name: str) -> None:
    pc = classify_process_control(make_item(name=name))
    assert pc.category is ProcessControlCategory.essential
    assert pc.action_policy is ActionPolicy.blocked
    assert_no_safe_actions(pc)
    assert any("protected_registry" in e for e in pc.evidence)
    assert pc.blocked_reason
    assert pc.confidence >= 0.9


@pytest.mark.parametrize("name", ["MsMpEng.exe", "SecurityHealthService.exe", "CSFalconService.exe"])
def test_security_processes_are_blocked(name: str) -> None:
    pc = classify_process_control(make_item(name=name))
    assert pc.action_policy is ActionPolicy.blocked
    assert pc.category is ProcessControlCategory.essential


@pytest.mark.parametrize(
    "name",
    ["nvcontainer.exe", "NVDisplay.Container.exe", "audiodg.exe", "RtkAudUService64.exe", "wlanext.exe"],
)
def test_gpu_audio_network_processes_are_blocked(name: str) -> None:
    pc = classify_process_control(make_item(name=name))
    assert pc.action_policy is ActionPolicy.blocked
    assert pc.category is ProcessControlCategory.essential
    assert_no_safe_actions(pc)


@pytest.mark.parametrize("name", ["EasyAntiCheat.exe", "BEService.exe", "vgtray.exe"])
def test_anticheat_processes_are_blocked(name: str) -> None:
    pc = classify_process_control(make_item(name=name))
    assert pc.action_policy is ActionPolicy.blocked


def test_classifier_never_unblocks_a_hard_protected_name() -> None:
    """Intelligence claiming safe_to_stop cannot override the protected registry."""
    pc = classify_process_control(
        make_item(
            name="lsass.exe",
            intelligence=intel(safe_to_stop=True, risk_level="low", category="Updater"),
        )
    )
    assert pc.action_policy is ActionPolicy.blocked
    assert_no_safe_actions(pc)


def test_rules_critical_bucket_is_essential() -> None:
    pc = classify_process_control(
        make_item(name="somecustom.exe", bucket=RiskBucket.risky_system_critical)
    )
    assert pc.category is ProcessControlCategory.essential
    assert pc.action_policy is ActionPolicy.blocked


def test_intelligence_critical_category_is_essential() -> None:
    pc = classify_process_control(
        make_item(name="vendorgpu.exe", intelligence=intel(category="GPU driver", risk_level="medium"))
    )
    assert pc.category is ProcessControlCategory.essential
    assert pc.action_policy is ActionPolicy.blocked
    assert_no_safe_actions(pc)


def test_intelligence_high_risk_is_important_report_only() -> None:
    pc = classify_process_control(
        make_item(name="vendorvpn.exe", intelligence=intel(category="Networking", risk_level="high"))
    )
    assert pc.category is ProcessControlCategory.important
    assert pc.action_policy is ActionPolicy.report_only
    assert_no_safe_actions(pc)


# --- browsers / shell -----------------------------------------------------------

@pytest.mark.parametrize("name", ["chrome.exe", "msedge.exe", "firefox.exe", "explorer.exe"])
def test_browser_and_shell_require_explicit_selection(name: str) -> None:
    pc = classify_process_control(
        make_item(name=name, intelligence=intel(category="Browser", risk_level="low", safe_to_stop=True))
    )
    assert pc.action_policy is ActionPolicy.explicit_selection_required
    assert pc.category is ProcessControlCategory.important
    assert_no_safe_actions(pc)


# --- unknown --------------------------------------------------------------------

def test_unknown_process_is_report_only_with_no_safe_actions() -> None:
    pc = classify_process_control(make_item(name="abcxyz12345.exe"))
    assert pc.category is ProcessControlCategory.unknown
    assert pc.action_policy is ActionPolicy.report_only
    assert_no_safe_actions(pc)
    assert pc.confidence <= 0.5


def test_known_but_unclassifiable_intelligence_stays_unknown() -> None:
    pc = classify_process_control(
        make_item(name="mystery.exe", intelligence=intel(risk_level="unknown", safe_to_stop=None))
    )
    assert pc.category is ProcessControlCategory.unknown
    assert_no_safe_actions(pc)


# --- non-essential / gaming -----------------------------------------------------

def test_known_low_risk_updater_is_non_essential_and_preview_required() -> None:
    pc = classify_process_control(
        make_item(
            name="GoogleUpdate.exe",
            intelligence=intel(category="Updater", risk_level="low", safe_to_stop=True, gaming_impact="low"),
        )
    )
    assert pc.category is ProcessControlCategory.non_essential
    assert pc.action_policy is ActionPolicy.preview_required
    assert pc.safe_to_suspend is True
    assert pc.safe_to_end is False
    assert pc.safe_to_disable_startup is False


def test_gaming_impact_helper_is_gaming_fps_impact() -> None:
    pc = classify_process_control(
        make_item(
            name="Discord.exe",
            intelligence=intel(
                category="Communication", risk_level="low", safe_to_stop=True, gaming_impact="medium"
            ),
        )
    )
    assert pc.category is ProcessControlCategory.gaming_fps_impact
    assert pc.action_policy is ActionPolicy.preview_required
    assert pc.safe_to_suspend is True
    assert pc.safe_to_end is False
    assert pc.fps_impact == "medium"


def test_safe_to_stop_false_helper_requires_explicit_selection() -> None:
    pc = classify_process_control(
        make_item(
            name="steamwebhelper.exe",
            intelligence=intel(
                category="Game launcher", risk_level="low", safe_to_stop=False, gaming_impact="medium"
            ),
        )
    )
    assert pc.category is ProcessControlCategory.gaming_fps_impact
    assert pc.action_policy is ActionPolicy.explicit_selection_required
    assert_no_safe_actions(pc)


# --- services / startup / tasks --------------------------------------------------

@pytest.mark.parametrize("name", ["WinDefend", "Audiosrv", "mpssvc", "Schedule"])
def test_protected_services_are_essential_blocked(name: str) -> None:
    pc = classify_process_control(make_item(ItemType.service, name=name))
    assert pc.category is ProcessControlCategory.essential
    assert pc.action_policy is ActionPolicy.blocked
    assert pc.safe_to_disable_startup is False


def test_other_services_are_report_only() -> None:
    pc = classify_process_control(make_item(ItemType.service, name="SomeVendorUpdaterSvc"))
    assert pc.action_policy is ActionPolicy.report_only
    assert pc.safe_to_disable_startup is False
    assert any("report-only" in e for e in pc.evidence)


def test_known_service_is_important_but_still_report_only() -> None:
    pc = classify_process_control(
        make_item(ItemType.service, name="VendorSvc", intelligence=intel(category="Vendor", risk_level="low"))
    )
    assert pc.category is ProcessControlCategory.important
    assert pc.action_policy is ActionPolicy.report_only
    assert_no_safe_actions(pc)


def test_startup_entry_stays_report_only_and_not_disableable() -> None:
    pc = classify_process_control(
        make_item(
            ItemType.startup_entry,
            name="OneDrive",
            intelligence=intel(category="Cloud sync", risk_level="low", safe_to_disable_startup=True),
        )
    )
    assert pc.category is ProcessControlCategory.non_essential
    assert pc.action_policy is ActionPolicy.report_only
    assert pc.safe_to_disable_startup is False


def test_startup_entry_pointing_at_protected_binary_is_blocked() -> None:
    pc = classify_process_control(
        make_item(ItemType.startup_entry, name="SecurityHealth", path=r"C:\Windows\System32\SecurityHealthSystray.exe")
    )
    assert pc.category is ProcessControlCategory.essential
    assert pc.action_policy is ActionPolicy.blocked


def test_unknown_startup_entry_is_unknown() -> None:
    pc = classify_process_control(make_item(ItemType.startup_entry, name="RandoTray"))
    assert pc.category is ProcessControlCategory.unknown
    assert pc.action_policy is ActionPolicy.report_only
    assert_no_safe_actions(pc)


@pytest.mark.parametrize("name", [r"\Microsoft\Windows\UpdateOrchestrator\Reboot", "Windows Defender Scheduled Scan"])
def test_microsoft_scheduled_tasks_are_blocked(name: str) -> None:
    pc = classify_process_control(make_item(ItemType.scheduled_task, name=name))
    assert pc.category is ProcessControlCategory.essential
    assert pc.action_policy is ActionPolicy.blocked


def test_other_scheduled_tasks_are_report_only() -> None:
    pc = classify_process_control(make_item(ItemType.scheduled_task, name=r"\VendorApp\CheckUpdates"))
    assert pc.category is ProcessControlCategory.unknown
    assert pc.action_policy is ActionPolicy.report_only
    assert_no_safe_actions(pc)


# --- not applicable --------------------------------------------------------------

@pytest.mark.parametrize(
    "item_type",
    [ItemType.file_or_folder, ItemType.browser_profile, ItemType.duplicate_group, ItemType.orphan_app],
)
def test_non_process_item_types_are_not_applicable(item_type: ItemType) -> None:
    pc = classify_process_control(make_item(item_type, name="C:/tmp/x"))
    assert pc.applicable is False
    assert pc.category is ProcessControlCategory.not_applicable
    assert pc.action_policy is ActionPolicy.unsupported
    assert_no_safe_actions(pc)


# --- stage / pipeline behaviour ---------------------------------------------------

def test_stage_preserves_an_already_classified_block() -> None:
    preset = ProcessControl(
        applicable=True,
        category=ProcessControlCategory.non_essential,
        action_policy=ActionPolicy.preview_required,
        evidence=["set_by_an_earlier_stage"],
    )
    item = make_item(name="lsass.exe", process_control=preset)
    out = stage_process_control(item)
    assert out.process_control.category is ProcessControlCategory.non_essential
    assert out.provenance == []


def _scored(name: str, item_type: ItemType = ItemType.process, **detail) -> ScoredItem:
    return ScoredItem(
        id=f"x-{name}",
        category="processes" if item_type is ItemType.process else "test",
        item_type=item_type,
        name=name,
        path=None,
        detail={"memory_mb": 10.0, **detail},
        rule_bucket=RiskBucket.unknown,
        confidence=0.45,
        reasoning="scanner placeholder",
    )


def test_pipeline_populates_process_control_for_processes() -> None:
    out = run_reasoning_pipeline(normalize_scored_item(_scored("Discord.exe")), allow=[], block=[])
    pc = out.process_control
    assert pc.applicable is True
    assert pc.category is not ProcessControlCategory.not_applicable
    assert pc.evidence
    assert "process_control" in [p.stage for p in out.provenance]


def test_pipeline_blocks_protected_process_end_to_end() -> None:
    out = run_reasoning_pipeline(normalize_scored_item(_scored("lsass.exe")), allow=[], block=[])
    assert out.process_control.action_policy is ActionPolicy.blocked
    assert out.process_control.category is ProcessControlCategory.essential
    assert_no_safe_actions(out.process_control)
    assert out.protected is True


def test_action_gating_clamps_classifier_when_protected() -> None:
    """A softer classifier verdict must not survive a protected verdict from gating."""
    from app.pipeline.action_gating import apply_action_gating

    item = make_item(
        name="vendorhelper.exe",
        bucket=RiskBucket.risky_system_critical,
        process_control=ProcessControl(
            applicable=True,
            category=ProcessControlCategory.non_essential,
            action_policy=ActionPolicy.preview_required,
            safe_to_suspend=True,
            evidence=["stale_softer_verdict"],
        ),
    )
    out = apply_action_gating(item)
    assert out.process_control.action_policy is ActionPolicy.blocked
    assert out.process_control.category is ProcessControlCategory.essential
    assert_no_safe_actions(out.process_control)


def test_classifier_does_not_change_file_cleanup_eligibility() -> None:
    scored = _scored("Temp", ItemType.file_or_folder, category_hint="temp_cache", size_mb=12.0)
    scored = scored.model_copy(update={"category": "files", "path": r"C:\Users\x\AppData\Local\Temp\a"})
    out = run_reasoning_pipeline(normalize_scored_item(scored), allow=[], block=[])
    assert out.bucket is RiskBucket.safe_to_remove
    assert out.cleanup_eligible is True
    assert out.process_control.applicable is False
    assert out.process_control.category is ProcessControlCategory.not_applicable
