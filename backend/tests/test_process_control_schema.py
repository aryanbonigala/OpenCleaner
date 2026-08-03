from __future__ import annotations

import pytest

from app.models.enums import ActionPolicy, ItemType, ProcessControlCategory, RiskBucket
from app.models.scan_item import (
    SCAN_SCHEMA_VERSION,
    CanonicalScanResult,
    CanonicalScanSummary,
    ProcessControl,
    ScanItem,
)
from app.models.schemas import PermissionMode
from app.pipeline.serialize import canonical_item_dict, serialize_scan_result_object
from app.services.selection_policy import can_select_for_cleanup
from app.services.settings_service import default_settings

PROCESS_CONTROL_TYPES = (
    ItemType.process,
    ItemType.service,
    ItemType.startup_entry,
    ItemType.scheduled_task,
)

OTHER_TYPES = (
    ItemType.file_or_folder,
    ItemType.browser_profile,
    ItemType.duplicate_group,
    ItemType.orphan_app,
)


def make_item(item_type: ItemType, **overrides) -> ScanItem:
    data = {
        "id": f"{item_type.value}-1",
        "item_type": item_type,
        "source": "test",
        "display_name": "Test item",
        "raw_name": "test.exe",
        "bucket": RiskBucket.unknown,
    }
    data.update(overrides)
    return ScanItem(**data)


def test_scan_schema_version_is_two() -> None:
    assert SCAN_SCHEMA_VERSION == 2


def test_scan_item_builds_without_explicit_process_control() -> None:
    item = make_item(ItemType.file_or_folder)
    assert isinstance(item.process_control, ProcessControl)


@pytest.mark.parametrize("item_type", PROCESS_CONTROL_TYPES + OTHER_TYPES)
def test_process_control_defaults_are_inert(item_type: ItemType) -> None:
    pc = make_item(item_type).process_control
    assert pc.safe_to_end is False
    assert pc.safe_to_suspend is False
    assert pc.safe_to_disable_startup is False
    assert pc.action_policy is ActionPolicy.report_only
    assert pc.blocked_reason is None
    assert pc.evidence == []


@pytest.mark.parametrize("item_type", PROCESS_CONTROL_TYPES)
def test_running_item_types_are_process_control_applicable(item_type: ItemType) -> None:
    pc = make_item(item_type).process_control
    assert pc.applicable is True
    assert pc.category is ProcessControlCategory.unknown


@pytest.mark.parametrize("item_type", OTHER_TYPES)
def test_other_item_types_are_not_applicable(item_type: ItemType) -> None:
    pc = make_item(item_type).process_control
    assert pc.applicable is False
    assert pc.category is ProcessControlCategory.not_applicable


def test_explicit_classification_is_not_overwritten() -> None:
    item = make_item(
        ItemType.process,
        process_control=ProcessControl(
            applicable=True,
            category=ProcessControlCategory.essential,
            action_policy=ActionPolicy.blocked,
            blocked_reason="security stack",
            evidence=["protected_registry"],
        ),
    )
    assert item.process_control.category is ProcessControlCategory.essential
    assert item.process_control.action_policy is ActionPolicy.blocked
    assert item.process_control.blocked_reason == "security stack"


def test_process_control_survives_model_copy_updates() -> None:
    """Pipeline stages use model_copy(update=...); classification must not be reset."""
    classified = make_item(
        ItemType.process,
        process_control=ProcessControl(
            applicable=True,
            category=ProcessControlCategory.non_essential,
            action_policy=ActionPolicy.preview_required,
        ),
    )
    gated = classified.model_copy(update={"protected": True})
    assert gated.process_control.category is ProcessControlCategory.non_essential
    assert gated.process_control.action_policy is ActionPolicy.preview_required


def test_serialized_item_always_includes_process_control() -> None:
    for item_type in PROCESS_CONTROL_TYPES + OTHER_TYPES:
        data = canonical_item_dict(make_item(item_type))
        assert "process_control" in data
        assert data["process_control"]["safe_to_end"] is False


def test_old_stored_payload_without_process_control_still_loads() -> None:
    """Schema-v1 canonical blobs live in scan_items.detail_json and must rehydrate."""
    legacy_payload = {
        "id": "proc-1",
        "scan_version": 1,
        "item_type": "process",
        "source": "processes",
        "display_name": "Legacy",
        "raw_name": "legacy.exe",
        "bucket": "unknown",
        "risk_level": "unknown",
        "protected": False,
        "cleanup_eligible": False,
        "performance_eligible": False,
        "confidence": 0.45,
    }
    item = ScanItem.model_validate(legacy_payload)
    assert item.scan_version == 1
    assert item.process_control.applicable is True
    assert item.process_control.category is ProcessControlCategory.unknown
    assert item.process_control.safe_to_end is False


def test_export_serialization_still_works() -> None:
    result = CanonicalScanResult(
        summary=CanonicalScanSummary(
            scan_id="scan-1",
            platform="test",
            mode=PermissionMode.read_only,
            items_count=2,
            buckets={"unknown": 2},
        ),
        items=[make_item(ItemType.process), make_item(ItemType.file_or_folder)],
    )
    payload = serialize_scan_result_object(result)
    assert payload["scan_schema_version"] == 2
    assert all("process_control" in it for it in payload["items"])


def test_cleanup_selection_behavior_unchanged() -> None:
    settings = default_settings()
    safe_file = make_item(
        ItemType.file_or_folder,
        bucket=RiskBucket.safe_to_remove,
        cleanup_eligible=True,
    )
    assert can_select_for_cleanup(safe_file, settings) is True
    # Process-control items remain outside the file cleanup path.
    assert can_select_for_cleanup(make_item(ItemType.process), settings) is False
