from __future__ import annotations

from pathlib import Path

from app.engine.rules_engine import is_critical_path
from app.models.enums import RiskBucket
from app.models.scan_item import ScanItem
from app.models.user_settings import UserSettings


def _file_size_bytes(it: ScanItem) -> int:
    if not it.path:
        return 0
    p = Path(it.path)
    try:
        if p.is_file():
            return int(p.stat().st_size)
    except OSError:
        return 0
    return 0


def preview_cleanup_items(
    items: list[ScanItem],
    *,
    confirm_medium_risk: bool,
    include_recycle_bin: bool,
    settings: UserSettings | None = None,
) -> dict:
    prefs = settings or UserSettings()
    advanced = prefs.is_advanced_risk()
    """
    Dry-run: classify each selected item without mutating disk.
    """
    rows: list[dict] = []
    estimated_bytes = 0
    will_quarantine = 0
    skipped = 0
    blocked = 0

    allowed_buckets = {RiskBucket.safe_to_remove}
    if confirm_medium_risk:
        allowed_buckets.add(RiskBucket.probably_safe)

    low_risk_hints = {"temp_cache", "installer_residual", "downloads_general"}

    for it in items:
        size = _file_size_bytes(it)
        hint = str(it.subtype or it.scanner_facts.get("category_hint") or "")
        row = {
            "id": it.id,
            "display_name": it.display_name,
            "path": it.path,
            "bucket": it.bucket.value,
            "subtype": hint or None,
            "estimated_bytes": size,
            "status": "skipped",
            "reason": "",
            "why_safe_or_unsafe": item_safety_blurb(it),
        }

        if it.item_type.value != "file_or_folder":
            row["status"] = "blocked"
            row["reason"] = "Only files can be quarantined in assisted cleanup."
            blocked += 1
        elif it.protected or it.bucket == RiskBucket.risky_system_critical:
            row["status"] = "blocked"
            row["reason"] = "Protected or critical — cannot be selected for automated cleanup."
            blocked += 1
        elif it.bucket == RiskBucket.unknown and (not advanced or not confirm_medium_risk):
            row["status"] = "blocked"
            row["reason"] = (
                "Unknown risk — enable Advanced risk visibility in Settings and confirm medium-risk."
                if not advanced
                else "Unknown risk — confirm medium-risk to include."
            )
            blocked += 1
        elif it.bucket == RiskBucket.ask_user and (not advanced or not confirm_medium_risk):
            row["status"] = "blocked"
            row["reason"] = (
                "Needs your review — enable Advanced risk visibility in Settings first."
                if not advanced
                else "Needs your review — confirm medium-risk to include."
            )
            blocked += 1
        elif not it.cleanup_eligible and not confirm_medium_risk:
            row["status"] = "blocked"
            row["reason"] = "Action gating: not marked cleanup-eligible."
            blocked += 1
        elif not it.path:
            row["status"] = "skipped"
            row["reason"] = "Missing file path."
            skipped += 1
        elif is_critical_path(str(it.path)):
            row["status"] = "blocked"
            row["reason"] = "Path is under a protected system directory."
            blocked += 1
        elif it.bucket not in allowed_buckets and not (confirm_medium_risk and hint in low_risk_hints):
            row["status"] = "blocked"
            row["reason"] = f"Risk bucket “{it.bucket.value}” requires explicit medium-risk confirmation."
            blocked += 1
        else:
            p = Path(it.path)
            if p.is_file():
                row["status"] = "will_quarantine"
                row["reason"] = "Will move to local quarantine (reversible)."
                estimated_bytes += size
                will_quarantine += 1
            elif p.is_dir() and hint == "empty_startmenu_folder":
                row["status"] = "will_quarantine"
                row["reason"] = "Empty folder may be removed without quarantine."
                will_quarantine += 1
            else:
                row["status"] = "skipped"
                row["reason"] = "Unsupported target (not a regular file)."
                skipped += 1

        rows.append(row)

    recycle_note = None
    if include_recycle_bin:
        if not prefs.allows_permanent_delete():
            recycle_note = "Recycle Bin emptying is disabled while cleanup mode is quarantine-only."
        else:
            recycle_note = (
                "Recycle Bin will be emptied if you confirm permanent delete — "
                "this is not reversible from quarantine."
            )

    return {
        "items": rows,
        "estimated_bytes": estimated_bytes,
        "estimated_mb": round(estimated_bytes / (1024 * 1024), 3),
        "counts": {
            "selected": len(items),
            "will_quarantine": will_quarantine,
            "skipped": skipped,
            "blocked": blocked,
        },
        "include_recycle_bin": include_recycle_bin,
        "recycle_bin_note": recycle_note,
        "confirm_medium_risk": confirm_medium_risk,
        "disclaimer": "Preview only — no files were changed. Run execute after reviewing this list.",
    }


def item_safety_blurb(it: ScanItem) -> str:
    if it.protected or it.bucket == RiskBucket.risky_system_critical:
        return "Unsafe to change automatically — OS, security, or driver related."
    if it.cleanup_eligible and it.bucket == RiskBucket.safe_to_remove:
        return "Low permanence risk — typical cache/temp style target; still review the path."
    if it.bucket == RiskBucket.probably_safe:
        return "Probably safe with review — confirm you recognize the file."
    if it.bucket == RiskBucket.unknown:
        return "Unknown — verify publisher and purpose before any change."
    if it.intelligence and it.intelligence.plain_english_description:
        return str(it.intelligence.plain_english_description)
    return it.explanation.summary or "No additional context."
