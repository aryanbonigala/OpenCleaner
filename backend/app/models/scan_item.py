from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ItemType, PermissionMode, RiskBucket

# Bump when canonical ScanItem field semantics change (not for data file entries).
SCAN_SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ProvenanceRecord(BaseModel):
    """Who decided what, with evidence — appended per pipeline stage (immutable history)."""

    stage: str
    decided_by: str
    evidence: list[str] = Field(default_factory=list)
    matched_rule: str | None = None
    matched_intelligence_entry: str | None = None
    ml_score_source: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ItemMetrics(BaseModel):
    memory_mb: float | None = None
    cpu_percent: float | None = None
    size_mb: float | None = None
    ml_rank_score: float | None = None
    rank_startup_impact: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_memory_impact: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_cpu_impact: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_gpu_impact: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_gaming_impact: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_deletion_risk: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_usefulness: float | None = Field(default=None, ge=0.0, le=100.0)


class IntelligenceSnapshot(BaseModel):
    known: bool = False
    applicable: bool = True
    match_kind: str | None = None
    name: str | None = None
    vendor: str | None = None
    category: str | None = None
    plain_english_description: str | None = None
    safe_to_stop: bool | None = None
    safe_to_disable_startup: bool | None = None
    safe_to_delete: bool | None = None
    gaming_impact: str | None = None
    memory_impact: str | None = None
    startup_impact: str | None = None
    risk_level: str | None = None
    confidence: float | None = None
    warning_if_changed: str | None = None
    recommended_action: str | None = None
    rules_protect: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class ExplanationBlock(BaseModel):
    summary: str = ""
    headline: str | None = None


class Recommendations(BaseModel):
    primary: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ScanItem(BaseModel):
    """Canonical scan row — sole shape exposed in API/export after v0.4."""

    id: str
    scan_version: int = SCAN_SCHEMA_VERSION
    item_type: ItemType
    source: str
    subtype: str | None = None
    display_name: str
    raw_name: str
    path: str | None = None
    vendor: str | None = None
    category: str | None = None
    metrics: ItemMetrics = Field(default_factory=ItemMetrics)
    intelligence: IntelligenceSnapshot | None = None
    bucket: RiskBucket = RiskBucket.unknown
    risk_level: str = "unknown"
    protected: bool = False
    cleanup_eligible: bool = False
    performance_eligible: bool = False
    explanation: ExplanationBlock = Field(default_factory=ExplanationBlock)
    recommendations: Recommendations = Field(default_factory=Recommendations)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    timestamps: dict[str, str] = Field(default_factory=dict)
    scanner_facts: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class CanonicalScanSummary(BaseModel):
    scan_id: str
    scan_schema_version: int = SCAN_SCHEMA_VERSION
    platform: str
    mode: PermissionMode
    items_count: int
    buckets: dict[str, int]
    disk_usage_sample: dict[str, Any] | None = None
    generated_at: str = Field(default_factory=utc_now_iso)


class CanonicalScanResult(BaseModel):
    summary: CanonicalScanSummary
    items: list[ScanItem]
