"""Moat / quality signals derivable from data (framework §1). The qualitative
parts (brand, switching costs, network effects) need human judgment and are
flagged as manual. What data CAN show: sustained high ROIC, stable/rising gross
margin (pricing power), and low revenue volatility (demand durability)."""
from __future__ import annotations

import numpy as np

from .data import CompanyData
from .forensic import _at, _safe_div


def _series_pct(num, den, n):
    out = []
    for i in range(n):
        v = _safe_div(_at(num, i), _at(den, i))
        out.append(np.nan if np.isnan(v) else v * 100)
    return [x for x in out if not np.isnan(x)]


def run_moat(c: CompanyData, roic_series=None) -> dict:
    n = min(c.n_periods, 5)
    gm = _series_pct(c.gross(), c.rev(), n)
    om = _series_pct(c.ebit(), c.rev(), n)

    # pricing power: gross margin level + stability (low std) + trend
    gm_level = round(np.mean(gm), 1) if gm else None
    gm_stability = round(np.std(gm), 2) if len(gm) >= 3 else None
    gm_trend = _trend(gm)

    # demand durability: revenue growth volatility (std of YoY growth)
    rev = c.rev()
    yoys = []
    for i in range(min(n - 1, 4)):
        v = _safe_div(_at(rev, i), _at(rev, i + 1)) - 1
        if not np.isnan(v):
            yoys.append(v * 100)
    rev_vol = round(np.std(yoys), 1) if len(yoys) >= 3 else None

    # sustained-ROIC moat evidence
    roic_clean = [x for x in (roic_series or []) if x is not None]
    roic_min = min(roic_clean) if roic_clean else None
    sustained_high_roic = (roic_min is not None and roic_min > 12)

    signals = []
    if sustained_high_roic:
        signals.append(f"Sustained ROIC (min {roic_min}% over period) — evidence of a moat")
    if gm_level and gm_level > 50 and (gm_stability is not None and gm_stability < 3):
        signals.append(f"High, stable gross margin ({gm_level}%, ±{gm_stability}) — pricing power")
    if gm_trend == "rising":
        signals.append("Gross margin rising — strengthening pricing power")
    if rev_vol is not None and rev_vol < 8:
        signals.append(f"Low revenue volatility (±{rev_vol}%) — durable demand")

    weak = []
    if gm_trend == "falling":
        weak.append("Gross margin declining — eroding pricing power / competition")
    if roic_min is not None and roic_min < 0:
        weak.append("ROIC went negative in the period — no consistent moat")

    return {
        "gross_margin_avg_pct": gm_level, "gross_margin_stability": gm_stability,
        "gross_margin_trend": gm_trend, "revenue_volatility_pct": rev_vol,
        "sustained_high_roic": sustained_high_roic, "roic_floor_pct": roic_min,
        "moat_signals": signals, "weak_signals": weak,
        "manual_review_needed": ["brand strength", "switching costs", "network effects",
                                 "customer/supplier concentration", "regulatory moat"],
        "note": "data shows pricing power (margins) & durability (ROIC/rev stability); "
                "qualitative moat sources need human review",
    }


def _trend(vals):
    v = [x for x in vals if x is not None]
    if len(v) < 2:
        return "n/a"
    return "rising" if v[0] > v[-1] * 1.03 else ("falling" if v[0] < v[-1] * 0.97 else "flat")
