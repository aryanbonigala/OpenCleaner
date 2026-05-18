from __future__ import annotations

import json
import os
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models.schemas import ItemType, RiskBucket, ScoredItem

_INTEL_TYPE_BY_ITEM: dict[ItemType, str] = {
    ItemType.process: "process",
    ItemType.service: "service",
    ItemType.startup_entry: "startup",
    ItemType.scheduled_task: "task",
}

_CAUTION: dict[RiskBucket, int] = {
    RiskBucket.safe_to_remove: 0,
    RiskBucket.probably_safe: 1,
    RiskBucket.ask_user: 2,
    RiskBucket.unknown: 3,
    RiskBucket.risky_system_critical: 4,
}

_CRITICAL_INTEL_CATEGORIES: frozenset[str] = frozenset(
    {
        "Anticheat",
        "Windows core",
        "Security",
        "GPU driver",
    }
)


def _data_path() -> Path:
    override = os.environ.get("OPENCLEANER_INTELLIGENCE_JSON")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "data" / "windows_intelligence.json"


def normalize_intel_key(s: str | None) -> str:
    if not s:
        return ""
    return str(s).strip().lower()


def _basename(p: str | None) -> str:
    if not p:
        return ""
    return str(p).replace("/", "\\").split("\\")[-1].strip()


@lru_cache(maxsize=1)
def _load_db() -> dict[str, Any]:
    path = _data_path()
    if not path.is_file():
        return {"schema_version": 0, "entries": []}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=16)
def _indexes_for_type(intel_type: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """exact_key_norm -> entry, alias_norm -> entry (last wins on alias collision)."""
    exact: dict[str, dict[str, Any]] = {}
    alias_map: dict[str, dict[str, Any]] = {}
    for e in _load_db().get("entries", []):
        if str(e.get("type") or "") != intel_type:
            continue
        n = normalize_intel_key(str(e.get("name", "")))
        if n:
            exact[n] = e
        for a in e.get("aliases") or []:
            an = normalize_intel_key(str(a))
            if an:
                alias_map[an] = e
    return exact, alias_map


def _candidate_keys(item: ScoredItem, intel_type: str) -> list[str]:
    keys: list[str] = []
    if item.name:
        keys.append(normalize_intel_key(item.name))
        keys.append(normalize_intel_key(_basename(item.name)))
    if item.path:
        keys.append(normalize_intel_key(item.path))
        keys.append(normalize_intel_key(_basename(item.path)))
    dn = item.detail.get("display_name")
    if dn:
        keys.append(normalize_intel_key(str(dn)))
    # Scheduled task: common to store hierarchical path in name via scanners
    if intel_type == "task" and item.name and "\\" in item.name:
        keys.append(normalize_intel_key(item.name.replace("/", "\\")))
    # De-dupe preserving order
    out: list[str] = []
    seen: set[str] = set()
    for k in keys:
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def _fuzzy_match(
    candidates: list[str],
    exact: dict[str, dict[str, Any]],
    aliases: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    """Only return fuzzy hits when the matched encyclopedia row is low-risk (mis-id safe)."""
    best_entry: dict[str, Any] | None = None
    best_score = 0.0
    best_key = ""
    pool_keys = list(exact.keys()) + [normalize_intel_key(str(x.get("name", ""))) for x in exact.values()]
    pool_keys = list(dict.fromkeys(k for k in pool_keys if k))
    for cand in candidates:
        if not cand:
            continue
        for pk in pool_keys:
            if not pk:
                continue
            r = SequenceMatcher(a=cand, b=pk).ratio()
            if r > best_score:
                best_score = r
                best_key = pk
                best_entry = exact.get(pk) or aliases.get(pk)
    if best_entry is None or best_score < 0.92:
        return None, None
    rl = str(best_entry.get("risk_level") or "").lower()
    if rl != "low":
        return None, None
    if float(best_entry.get("confidence") or 0) < 0.82:
        return None, None
    return best_entry, f"fuzzy:{best_score:.2f}:{best_key}"


def lookup_intelligence_row(item: ScoredItem) -> tuple[dict[str, Any] | None, str | None]:
    """
    Return (entry_dict, match_kind) where match_kind is exact|alias|fuzzy:<...> or None.
    """
    itype = _INTEL_TYPE_BY_ITEM.get(item.item_type)
    if not itype:
        return None, None
    exact, aliases = _indexes_for_type(itype)
    cand_keys = _candidate_keys(item, itype)
    for k in cand_keys:
        if k in exact:
            return exact[k], "exact"
        if k in aliases:
            return aliases[k], "alias"
    ent, why = _fuzzy_match(cand_keys, exact, aliases)
    if ent is not None:
        return ent, why
    return None, None


def _intel_detail_public(entry: dict[str, Any], *, known: bool, match_kind: str | None) -> dict[str, Any]:
    return {
        "known": known,
        "match_kind": match_kind,
        "name": entry.get("name"),
        "aliases": entry.get("aliases") or [],
        "type": entry.get("type"),
        "vendor": entry.get("vendor"),
        "category": entry.get("category"),
        "plain_english_description": entry.get("plain_english_description"),
        "safe_to_stop": entry.get("safe_to_stop"),
        "safe_to_disable_startup": entry.get("safe_to_disable_startup"),
        "safe_to_delete": entry.get("safe_to_delete"),
        "gaming_impact": entry.get("gaming_impact"),
        "memory_impact": entry.get("memory_impact"),
        "startup_impact": entry.get("startup_impact"),
        "risk_level": entry.get("risk_level"),
        "confidence": entry.get("confidence"),
        "warning_if_changed": entry.get("warning_if_changed"),
        "recommended_action": entry.get("recommended_action"),
    }


def _unknown_intel_stub() -> dict[str, Any]:
    return {
        "known": False,
        "match_kind": None,
        "name": None,
        "aliases": [],
        "type": None,
        "vendor": None,
        "category": None,
        "plain_english_description": None,
        "safe_to_stop": None,
        "safe_to_disable_startup": None,
        "safe_to_delete": False,
        "gaming_impact": None,
        "memory_impact": None,
        "startup_impact": None,
        "risk_level": "unknown",
        "confidence": None,
        "warning_if_changed": "Not present in the local intelligence database.",
        "recommended_action": "Treat as unknown — verify publisher and purpose before stopping, disabling, or deleting anything.",
    }


def _rules_critical_stub() -> dict[str, Any]:
    return {
        "known": False,
        "match_kind": None,
        "rules_protect": True,
        "risk_level": "unknown",
        "safe_to_stop": False,
        "safe_to_disable_startup": False,
        "safe_to_delete": False,
        "warning_if_changed": "Marked safety-critical by rules — do not suspend, stop, or delete without research.",
        "recommended_action": "No automatic changes; treat as protected.",
    }


def _elevate_from_entry(entry: dict[str, Any]) -> RiskBucket | None:
    """If intelligence demands a stricter bucket, return it; else None."""
    rl = str(entry.get("risk_level") or "").lower()
    cat = str(entry.get("category") or "")
    if rl == "critical" and cat in _CRITICAL_INTEL_CATEGORIES:
        return RiskBucket.risky_system_critical
    if rl == "critical":
        return RiskBucket.ask_user
    if rl == "high" and cat in _CRITICAL_INTEL_CATEGORIES:
        return RiskBucket.risky_system_critical
    return None


def _apply_bucket_intel(
    item: ScoredItem,
    *,
    entry: dict[str, Any] | None,
    match_kind: str | None,
) -> tuple[RiskBucket, float, str]:
    """
    Rules already merged into item (non-risky path). Never promote to safe_to_remove / probably_safe
    from intelligence alone; may tighten classification or clarify unknown → ask_user.
    """
    bucket = item.rule_bucket
    conf = float(item.confidence)
    reasoning = item.reasoning

    if entry is None or not match_kind:
        return bucket, conf, reasoning

    elevated = _elevate_from_entry(entry)
    if elevated is not None and _CAUTION[elevated] > _CAUTION[bucket]:
        bucket = elevated
        conf = max(conf, float(entry.get("confidence") or 0.75))
        reasoning = f"{reasoning} | Intelligence ({match_kind}): {entry.get('plain_english_description') or entry.get('name')}"

    # Informative bump: unknown -> ask_user for exact/alias matches (cleanup eligibility unchanged).
    if match_kind in ("exact", "alias") and bucket == RiskBucket.unknown:
        bucket = RiskBucket.ask_user
        conf = max(conf, float(entry.get("confidence") or 0.65) * 0.92)
        if "Intelligence" not in reasoning:
            reasoning = f"{reasoning} | Intelligence: {entry.get('plain_english_description') or entry.get('name')}"

    return bucket, conf, reasoning


def apply_intelligence(item: ScoredItem) -> ScoredItem:
    itype = _INTEL_TYPE_BY_ITEM.get(item.item_type)
    detail = dict(item.detail or {})
    if not itype:
        detail["intelligence"] = {
            "known": False,
            "applicable": False,
            "recommended_action": "—",
            "note": "Intelligence database applies to processes, services, startup entries, and scheduled tasks.",
        }
        return item.model_copy(update={"detail": detail})

    entry, match_kind = lookup_intelligence_row(item)

    if item.rule_bucket == RiskBucket.risky_system_critical:
        if entry is not None:
            detail["intelligence"] = _intel_detail_public(entry, known=True, match_kind=match_kind)
        else:
            detail["intelligence"] = _rules_critical_stub()
        return item.model_copy(update={"detail": detail})

    if entry is None:
        detail["intelligence"] = _unknown_intel_stub()
        return item.model_copy(update={"detail": detail})

    detail["intelligence"] = _intel_detail_public(entry, known=True, match_kind=match_kind)

    new_bucket, new_conf, new_reasoning = _apply_bucket_intel(
        item,
        entry=entry,
        match_kind=match_kind,
    )

    # Never promote into cleanup-eligible buckets purely from intelligence.
    if item.rule_bucket not in (RiskBucket.safe_to_remove, RiskBucket.probably_safe):
        if new_bucket in (RiskBucket.safe_to_remove, RiskBucket.probably_safe):
            new_bucket = item.rule_bucket
            new_conf = item.confidence

    merged_reasoning = new_reasoning
    if entry and "Intelligence" not in merged_reasoning and match_kind in ("exact", "alias"):
        tail = entry.get("recommended_action") or entry.get("plain_english_description") or ""
        if tail:
            merged_reasoning = f"{merged_reasoning} | Intelligence: {tail}"

    return item.model_copy(
        update={
            "detail": detail,
            "rule_bucket": new_bucket,
            "confidence": float(max(0.0, min(1.0, new_conf))),
            "reasoning": merged_reasoning.strip(),
        }
    )


def reload_intelligence_cache_for_tests() -> None:
    """Clear loader cache (tests only)."""
    _load_db.cache_clear()
    _indexes_for_type.cache_clear()
