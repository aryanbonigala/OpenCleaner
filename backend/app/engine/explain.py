from __future__ import annotations

from app.models.schemas import ExplainRequest, ExplainResponse, ItemType
from app.engine.rules_engine import is_critical_process, is_critical_service


def explain_item(req: ExplainRequest) -> ExplainResponse:
    item = req.item
    n = item.name
    t = item.item_type
    path = item.path or ""
    intel = item.detail.get("intelligence") if isinstance(item.detail.get("intelligence"), dict) else {}

    what = f"This is a {t.value.replace('_', ' ')} named “{n}”"
    if path:
        what += f" located at `{path}`."
    else:
        what += "."

    if intel.get("vendor") or intel.get("category"):
        what += (
            f" Local intelligence labels this as {intel.get('vendor') or 'unknown vendor'}"
            f" ({intel.get('category') or 'general'})."
        )

    importance = "Importance depends on whether you rely on its vendor features actively."
    if t == ItemType.process:
        if is_critical_process(n):
            importance = (
                "Strong heuristic match for OS, security stack, or low-level drivers/anti-cheat — treat as critical."
            )
        elif intel.get("plain_english_description"):
            importance = str(intel["plain_english_description"])
        else:
            mem = item.detail.get("memory_mb")
            if mem:
                importance = f"It currently uses about {float(mem):.0f} MB of RAM; that may be normal for heavy apps."
    elif t == ItemType.service:
        if is_critical_service(n):
            importance = "Marked as high-risk service family (security/audio/network core). Do not disable casually."
        elif intel.get("plain_english_description"):
            importance = str(intel["plain_english_description"])
        else:
            st = item.detail.get("start_type")
            importance = f"Windows service (start type: {st or 'unknown'}); disabling can break dependent features."
    elif t == ItemType.startup_entry:
        importance = (
            str(intel["plain_english_description"])
            if intel.get("plain_english_description")
            else "Runs during logon; affects boot-to-usable time and background resource use."
        )
    elif t == ItemType.scheduled_task:
        importance = (
            str(intel["plain_english_description"])
            if intel.get("plain_english_description")
            else "Runs on a timer; may perform updates, maintenance, or vendor housekeeping."
        )
    elif t == ItemType.file_or_folder:
        hint = item.detail.get("category_hint")
        importance = f"Filesystem object; category hint: {hint or 'general'}."
    elif t in (ItemType.browser_profile,):
        importance = "Browser storage; clearing frees space but may sign you out of web sessions."
    elif t == ItemType.duplicate_group:
        importance = "Exact duplicate by hash; usually safe to keep one representative copy."
    elif t == ItemType.orphan_app:
        importance = "Leftover from partial uninstall; could still be referenced by another app."

    installer_guess = "Unknown installer — check digital signature or publisher in Properties → Details."
    lowpath = path.lower()
    if "microsoft" in lowpath or "windows" in lowpath:
        installer_guess = "Likely Microsoft / Windows component path."
    elif "steam" in lowpath:
        installer_guess = "Associated with Steam or a Steam library."
    elif "epic" in lowpath:
        installer_guess = "Associated with Epic Games Launcher or library."
    elif "mozilla" in lowpath or "chrome" in lowpath or "edge" in lowpath:
        installer_guess = "Browser vendor path."

    gaming = "Minimal direct gaming impact unless it competes for CPU/GPU during play."
    if item.rank_gaming_impact is not None and item.rank_gaming_impact > 55:
        gaming = "Elevated gaming-impact score — may cause frame pacing issues or input lag when active."
    if intel.get("gaming_impact") and not (item.rank_gaming_impact is not None and item.rank_gaming_impact > 55):
        gaming = f"Local intelligence rates gaming impact as “{intel.get('gaming_impact')}”."
    if item.detail.get("gpu_heavy"):
        gaming = "Flagged as potentially GPU-heavy — can reduce headroom for GPU-bound titles."

    startup = "Unlikely to affect boot unless it is a startup entry or boot service."
    if t in (ItemType.startup_entry, ItemType.service, ItemType.scheduled_task):
        startup = "Can affect cold boot, logon, or resume behavior depending on triggers and dependencies."
    if intel.get("startup_impact"):
        startup += f" Local intelligence rates startup impact as “{intel.get('startup_impact')}”."

    safe = "Use Assisted mode with quarantine for files; for services/startup, prefer disabling over deletion."
    if intel.get("known") is False and intel.get("rules_protect"):
        safe = "Rules mark this as protected / critical — do not stop, suspend, or delete without authoritative guidance."
    elif intel.get("known") is False:
        safe = "Unknown to the local intelligence database — assume not safe to change until you verify the publisher."
    elif intel.get("safe_to_stop") is False and t == ItemType.process:
        safe = "Local intelligence: stopping this process is not recommended."
    elif intel.get("safe_to_disable_startup") is False and t == ItemType.startup_entry:
        safe = "Local intelligence: disabling this startup entry is not recommended."
    if item.rule_bucket.value == "risky_system_critical":
        safe = "Not safe to remove/disable without deep research — high chance of breaking OS stability."
    elif item.rule_bucket.value == "safe_to_remove":
        safe = "Rules classify as low-permanence cache/temp — assisted cleanup with quarantine is appropriate."

    breaks = "Removing critical OS files or disabling core services can cause boot failures or security gaps."
    if intel.get("warning_if_changed"):
        breaks = f"{breaks} {intel.get('warning_if_changed')}"
    if t == ItemType.browser_profile:
        breaks = "May sign you out of websites and lose cached offline data for PWAs."
    if t == ItemType.startup_entry:
        breaks = "You may lose auto-start conveniences (cloud sync, peripherals utilities) until re-enabled."

    ml_note = (
        "Local ranking blends deterministic rules with a feature-based usefulness estimate; "
        "it never authorizes autonomous deletion."
    )
    if intel.get("recommended_action"):
        ml_note += f" Intelligence note: {intel.get('recommended_action')}"

    return ExplainResponse(
        what_it_does=what,
        importance=importance,
        installer_guess=installer_guess,
        gaming_impact=gaming,
        startup_impact=startup,
        safe_to_disable_or_remove=safe,
        what_could_break=breaks,
        local_ml_note=ml_note,
    )
