from __future__ import annotations

import math
import random
from typing import Any

import numpy as np

from app.models.schemas import ItemType, RiskBucket, ScoredItem


FEATURE_VERSION = 3


def _safe_log1p(x: float) -> float:
    return float(math.log1p(max(0.0, x)))


def features_from_item(item: ScoredItem) -> np.ndarray:
    """32-dim dense feature vector — deterministic, versioned."""
    d = item.detail
    it = item.item_type.value
    type_onehot = {
        "process": [1, 0, 0, 0, 0, 0, 0, 0],
        "service": [0, 1, 0, 0, 0, 0, 0, 0],
        "startup_entry": [0, 0, 1, 0, 0, 0, 0, 0],
        "scheduled_task": [0, 0, 0, 1, 0, 0, 0, 0],
        "file_or_folder": [0, 0, 0, 0, 1, 0, 0, 0],
        "browser_profile": [0, 0, 0, 0, 0, 1, 0, 0],
        "duplicate_group": [0, 0, 0, 0, 0, 0, 1, 0],
        "orphan_app": [0, 0, 0, 0, 0, 0, 0, 1],
    }.get(it, [0, 0, 0, 0, 0, 0, 0, 0])

    mem_mb = float(d.get("memory_mb") or 0.0)
    cpu_pct = float(d.get("cpu_percent") or 0.0)
    gpu_flag = 1.0 if d.get("gpu_heavy") else 0.0
    startup = 1.0 if d.get("startup") else 0.0
    svc_manual = 1.0 if str(d.get("start_type") or "").lower() in ("manual", "demand start") else 0.0
    svc_auto = 1.0 if str(d.get("start_type") or "").lower() in ("auto", "automatic") else 0.0

    size_mb = float(d.get("size_mb") or 0.0)
    depth = float(str(d.get("path_depth") or "0"))
    is_temp = 1.0 if d.get("category_hint") == "temp_cache" else 0.0
    dup_count = float(d.get("duplicate_count") or 0.0)
    age_days = float(d.get("age_days") or 0.0)

    name_len = float(len(item.name or ""))
    path_len = float(len(item.path or ""))

    bucket_ord = float(
        [
            "safe_to_remove",
            "probably_safe",
            "ask_user",
            "unknown",
            "risky_system_critical",
        ].index(item.rule_bucket.value)
    )

    vec = np.array(
        type_onehot
        + [
            _safe_log1p(mem_mb),
            _safe_log1p(cpu_pct),
            gpu_flag,
            startup,
            svc_manual,
            svc_auto,
            _safe_log1p(size_mb),
            _safe_log1p(depth),
            is_temp,
            _safe_log1p(dup_count),
            _safe_log1p(age_days),
            _safe_log1p(name_len),
            _safe_log1p(path_len),
            bucket_ord,
            float(item.confidence),
        ],
        dtype=np.float32,
    )
    # Pad / trim to 32
    target = 32
    if vec.shape[0] < target:
        vec = np.pad(vec, (0, target - vec.shape[0]))
    elif vec.shape[0] > target:
        vec = vec[:target]
    return vec


def heuristic_ml_scores(item: ScoredItem) -> dict[str, float]:
    """
    Lightweight, fully local 'ML' layer: convex blend of features.
    sklearn path can replace internals, but public outputs remain identical keys.
    """
    f = features_from_item(item)
    mem = float(f[8])
    cpu = float(f[9])
    gpu = float(f[10])

    # usefulness proxy: correlates negatively with resource use for background junk
    usefulness = 100.0 * (1.0 / (1.0 + 0.35 * mem + 0.25 * cpu + 0.45 * gpu))
    if item.item_type == ItemType.startup_entry:
        usefulness -= 12.0

    startup_impact = min(100.0, 18.0 + 22.0 * float(f[12]) + 10.0 * float(f[13]))
    memory_impact = min(100.0, 12.0 + 35.0 * mem)
    cpu_impact = min(100.0, 10.0 + 40.0 * cpu)
    gpu_impact = min(100.0, 55.0 * gpu + 8.0 * mem * gpu)

    gaming = min(100.0, 0.45 * cpu_impact + 0.55 * gpu_impact + 0.15 * memory_impact)

    deletion_risk = {
        "safe_to_remove": 12.0,
        "probably_safe": 28.0,
        "ask_user": 48.0,
        "unknown": 62.0,
        "risky_system_critical": 94.0,
    }[item.rule_bucket.value]

    ml_rank = float(np.clip(np.tanh(usefulness / 90.0 - 0.35), -1.0, 1.0))

    return {
        "ml_rank_score": ml_rank,
        "rank_usefulness": float(np.clip(usefulness, 0.0, 100.0)),
        "rank_startup_impact": float(np.clip(startup_impact, 0.0, 100.0)),
        "rank_memory_impact": float(np.clip(memory_impact, 0.0, 100.0)),
        "rank_cpu_impact": float(np.clip(cpu_impact, 0.0, 100.0)),
        "rank_gpu_impact": float(np.clip(gpu_impact, 0.0, 100.0)),
        "rank_gaming_impact": float(np.clip(gaming, 0.0, 100.0)),
        "rank_deletion_risk": float(np.clip(deletion_risk, 0.0, 100.0)),
    }


def apply_ml_ranking(item: ScoredItem) -> ScoredItem:
    s = heuristic_ml_scores(item)
    merged = item.model_dump()
    merged.update(s)
    return ScoredItem.model_validate(merged)


def train_synthetic_calibrator_if_available() -> Any | None:
    """
    Optional: train sklearn regressor on synthetic data mirroring rules+features.
    Not required at runtime — heuristic path is always available.
    """
    try:
        from sklearn.ensemble import GradientBoostingRegressor
    except Exception:  # pragma: no cover
        return None

    rng = np.random.default_rng(42)
    types = list(ItemType)
    buckets = list(RiskBucket)
    xs: list[np.ndarray] = []
    ys: list[float] = []
    for _ in range(800):
        fake = ScoredItem(
            id="syn",
            category="synthetic",
            item_type=random.choice(types),
            name="proc" + str(int(rng.integers(0, 1000))),
            path="C:\\Users\\x\\AppData\\Local\\Temp\\t.dat",
            detail={
                "memory_mb": float(rng.random() * 1200),
                "cpu_percent": float(rng.random() * 80),
                "gpu_heavy": bool(rng.random() > 0.85),
                "startup": bool(rng.random() > 0.7),
                "start_type": random.choice(["auto", "manual", "disabled"]),
                "size_mb": float(rng.random() * 9000),
                "path_depth": float(rng.integers(2, 10)),
                "category_hint": random.choice(["temp_cache", "installer_residual", None]),
                "duplicate_count": float(rng.integers(0, 8)),
                "age_days": float(rng.integers(0, 900)),
            },
            rule_bucket=random.choice(buckets),
            confidence=float(rng.random()),
            reasoning="synthetic",
        )
        vec = features_from_item(fake)
        xs.append(vec)
        ys.append(heuristic_ml_scores(fake)["rank_usefulness"])

    x = np.stack(xs, axis=0)
    y = np.array(ys, dtype=np.float64)
    model = GradientBoostingRegressor(random_state=42, max_depth=3, n_estimators=60, learning_rate=0.08)
    model.fit(x, y)
    return model


def optional_sklearn_blend(item: ScoredItem, model: Any | None) -> ScoredItem:
    base = heuristic_ml_scores(item)
    if model is None:
        merged = item.model_dump()
        merged.update(base)
        return ScoredItem.model_validate(merged)
    vec = features_from_item(item).reshape(1, -1)
    pred = float(model.predict(vec)[0])
    blended_usefulness = 0.65 * base["rank_usefulness"] + 0.35 * np.clip(pred, 0.0, 100.0)
    base["rank_usefulness"] = float(blended_usefulness)
    base["ml_rank_score"] = float(np.clip(np.tanh(blended_usefulness / 90.0 - 0.35), -1.0, 1.0))
    merged = item.model_dump()
    merged.update(base)
    return ScoredItem.model_validate(merged)
