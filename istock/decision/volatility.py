"""Volatility / expected-range helpers for the Risk panel.

We estimate HOW MUCH a stock tends to move, never WHICH WAY. Short-horizon
direction is unpredictable, but volatility clusters and is estimable — so this is
the one honest forecast the tool makes. Used to frame risk and size positions,
NOT to predict returns.
"""
from __future__ import annotations

import math


def expected_moves(price, atr=None, annual_vol_pct=None) -> dict:
    """± move magnitudes (non-directional) from ATR and annualized volatility."""
    out: dict = {}
    if not price or price <= 0:
        return out
    if atr:
        out["daily_atr_pct"] = round(atr / price * 100, 2)
        out["daily_atr_abs"] = round(atr, 2)
    if annual_vol_pct:
        daily_sigma_pct = annual_vol_pct / math.sqrt(252)      # ann. vol → 1-day σ
        out["daily_sigma_pct"] = round(daily_sigma_pct, 2)
        out["weekly_sigma_pct"] = round(daily_sigma_pct * math.sqrt(5), 2)
        out["weekly_abs"] = round(price * daily_sigma_pct * math.sqrt(5) / 100, 2)
    return out


def volatility_band(annual_vol_pct) -> str:
    """Plain-English volatility band."""
    if annual_vol_pct is None:
        return "—"
    if annual_vol_pct < 20:
        return "Low"
    if annual_vol_pct < 35:
        return "Moderate"
    if annual_vol_pct < 55:
        return "High"
    return "Very high"
