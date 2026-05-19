"""Default cleanup selection policy — must stay aligned with frontend/src/selection.ts."""

from __future__ import annotations

from app.models.enums import RiskBucket
from app.models.scan_item import ScanItem
from app.models.user_settings import UserSettings


def can_select_for_cleanup(item: ScanItem, settings: UserSettings) -> bool:
    if item.item_type.value != "file_or_folder":
        return False
    if item.protected:
        return False
    if item.bucket == RiskBucket.risky_system_critical:
        return False
    advanced = settings.is_advanced_risk()
    if item.bucket == RiskBucket.unknown and not advanced:
        return False
    if item.bucket == RiskBucket.ask_user and not advanced:
        return False
    if not item.cleanup_eligible and not advanced:
        return False
    return True


def default_selected_ids(items: list[ScanItem], settings: UserSettings) -> set[str]:
    ids: set[str] = set()
    for it in items:
        if not can_select_for_cleanup(it, settings):
            continue
        if it.bucket == RiskBucket.safe_to_remove:
            ids.add(it.id)
    return ids
