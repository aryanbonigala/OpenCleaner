from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import ItemType, PermissionMode, PerformancePreset, RiskBucket
from app.models.scan_item import SCAN_SCHEMA_VERSION, ScanItem

# Re-export enums for backward compatibility
__all__ = [
    "ItemType",
    "PermissionMode",
    "PerformancePreset",
    "RiskBucket",
    "ScoredItem",
    "ScanItem",
    "SCAN_SCHEMA_VERSION",
]


class ScoredItem(BaseModel):
    """Legacy scanner / engine row — prefer ScanItem at API boundaries."""

    id: str
    category: str
    item_type: ItemType
    name: str
    path: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)

    rule_bucket: RiskBucket
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

    ml_rank_score: float | None = None
    rank_startup_impact: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_memory_impact: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_cpu_impact: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_gpu_impact: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_gaming_impact: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_deletion_risk: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_usefulness: float | None = Field(default=None, ge=0.0, le=100.0)


class ExplainRequest(BaseModel):
    item: ScanItem


class ExplainResponse(BaseModel):
    what_it_does: str
    importance: str
    installer_guess: str
    gaming_impact: str
    startup_impact: str
    safe_to_disable_or_remove: str
    what_could_break: str
    local_ml_note: str


class ScanSummary(BaseModel):
    scan_id: str
    scan_schema_version: int = SCAN_SCHEMA_VERSION
    platform: str
    mode: PermissionMode
    items_count: int
    buckets: dict[str, int]
    disk_usage_sample: dict[str, Any] | None = None
    generated_at: str | None = None


class ScanResult(BaseModel):
    summary: ScanSummary
    items: list[ScanItem]


class CleanupPreviewRequest(BaseModel):
    item_ids: list[str]
    confirm_medium_risk: bool = False


class CleanupExecuteRequest(BaseModel):
    item_ids: list[str]
    confirm_medium_risk: bool = False
    include_recycle_bin: bool = False


class QuarantineEntry(BaseModel):
    id: str
    original_path: str
    quarantine_path: str
    size_bytes: int | None = None
    restored: bool
    created_at: str


class PerformancePreviewRequest(BaseModel):
    preset: PerformancePreset
    target_process_names: list[str] = Field(default_factory=list)


class PerformanceSessionRequest(BaseModel):
    preset: PerformancePreset
    target_process_names: list[str] = Field(default_factory=list)
    confirm_apply: bool = False


class FeedbackRequest(BaseModel):
    item: dict[str, Any]
    decision: Literal["keep", "remove", "ignore"]
    weight: float = 1.0


class ModeSetRequest(BaseModel):
    mode: PermissionMode
