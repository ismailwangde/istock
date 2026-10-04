"""Inference-time scoring for brain v2.

score = sigmoid(intercept + Σ wᵢ × xᵢ) × 100

Verdict thresholds (global, locked):
    score ≥ 80   STRONG BUY
    score ≥ 65   BUY
    score ≥ 55   LEAN BUY
    score ≥ 45   HOLD
    score ≥ 35   LEAN SELL
    score ≥ 20   SELL
    score <  20  AVOID

High-VIX guardrail: when daily VIX close > 22.0, downgrade any actionable
verdict by one tier.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from istock.features.spec import N_FEATURES
from istock.model.weights import WeightSet


HIGH_VIX_THRESHOLD: float = 22.0

_VIX_DOWNGRADE_MAP = {
    "STRONG BUY": "BUY",
    "BUY": "LEAN BUY",
    "LEAN BUY": "HOLD",
}

VERDICT_THRESHOLDS = (
    (80, "STRONG BUY"),
    (65, "BUY"),
    (55, "LEAN BUY"),
    (45, "HOLD"),
    (35, "LEAN SELL"),
    (20, "SELL"),
    (0,  "AVOID"),
)


# Non-directional quality bands. The tool shows these instead of a BUY/SELL
# verdict: they describe how the name SCORES on the measured signals, never a
# prediction that it will go up or down. (Short-horizon direction is unpredictable
# — see NEXT_STEPS.md; the honest product informs, it does not recommend.)
QUALITY_BANDS = (
    (80, "Excellent"),
    (65, "Strong"),
    (55, "Solid"),
    (45, "Average"),
    (35, "Mixed"),
    (20, "Weak"),
    (0,  "Poor"),
)


def quality_band_from_score(score_value: float) -> str:
    """0-100 score → non-directional quality band (Excellent…Poor). NOT a trade call."""
    for cutoff, label in QUALITY_BANDS:
        if score_value >= cutoff:
            return label
    return QUALITY_BANDS[-1][1]


def score(features: np.ndarray, ws: WeightSet) -> float:
    """Apply `ws` to `features` (length-36 binary vector) → 0-100 score."""
    if features.shape != (N_FEATURES,):
        raise ValueError(f"features.shape={features.shape}, expected ({N_FEATURES},)")
    if ws.coefficients.shape != (N_FEATURES,):
        raise ValueError(f"ws.coefficients.shape={ws.coefficients.shape}, expected ({N_FEATURES},)")
    logit = float(ws.intercept) + float(np.dot(ws.coefficients, features.astype(float)))
    if logit >= 0:
        p = 1.0 / (1.0 + np.exp(-logit))
    else:
        ex = np.exp(logit)
        p = ex / (1.0 + ex)
    return float(p * 100.0)


def verdict_from_score(score_value: float, current_vix: Optional[float] = None) -> str:
    """Map 0-100 score → verdict label. Applies VIX guardrail if current_vix provided."""
    verdict = _bucket_by_threshold(score_value)
    if current_vix is not None and current_vix > HIGH_VIX_THRESHOLD:
        verdict = apply_vix_guardrail(verdict, current_vix)
    return verdict


def _bucket_by_threshold(score_value: float) -> str:
    for cutoff, label in VERDICT_THRESHOLDS:
        if score_value >= cutoff:
            return label
    return VERDICT_THRESHOLDS[-1][1]


def apply_vix_guardrail(verdict: str, current_vix: float) -> str:
    """Downgrade an actionable verdict one tier when VIX > 22.0."""
    if current_vix <= HIGH_VIX_THRESHOLD:
        return verdict
    return _VIX_DOWNGRADE_MAP.get(verdict, verdict)
