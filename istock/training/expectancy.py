# OFFLINE only — never import this at runtime
"""Calibration + expectancy ranking (MODEL.md §15 item 0d).

Problem: the raw model score is NOT a probability (class_weight="balanced"
distorts the sigmoid), and it ignores trade geometry — a 60-score trade with a
tight stop and far target can be worth more than a 65 with poor geometry.

Fix, two steps:
1. **Platt calibration** — fit a tiny 1-D logistic on a trailing validation
   window mapping raw model probability → observed win frequency. Output is a
   real P(win).
2. **Expectancy** — for each candidate trade:
       expectancy = P(win) × reward_pct − (1 − P(win)) × risk_pct − cost
   with reward = (T1 − entry)/entry, risk = (entry − stop)/entry,
   cost = 0.60% round trip. Rank candidates by expectancy; trade the top N.

This is conservative: reward assumes exit at T1 (T2 hits are upside surprise).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from istock.features.spec import COST_ROUND_TRIP_PCT, extract_features


def fit_calibrator(model, val_trades: List[Dict[str, Any]]):
    """Platt scaling: 1-D logistic mapping raw model prob → true P(win).
    Returns the fitted calibrator (or None if val is degenerate)."""
    from sklearn.linear_model import LogisticRegression
    from istock.training.trainer import build_xy
    X_v, y_v, _ = build_xy(val_trades)
    if X_v.shape[0] < 30 or len(set(y_v.tolist())) < 2:
        return None
    p_raw = model.predict_proba(X_v)[:, 1].reshape(-1, 1)
    cal = LogisticRegression()
    cal.fit(p_raw, y_v)
    return cal


def p_win(model, calibrator, trades: List[Dict[str, Any]]) -> np.ndarray:
    """Calibrated win probabilities for a list of trade dicts."""
    X = np.vstack([extract_features(t) for t in trades])
    p_raw = model.predict_proba(X)[:, 1].reshape(-1, 1)
    if calibrator is None:
        return p_raw.ravel()
    return calibrator.predict_proba(p_raw)[:, 1]


def expectancy_pct(trade: Dict[str, Any], p: float) -> Optional[float]:
    """Expected net % return of the trade at calibrated P(win) = p.
    Conservative: reward measured to T1 only. None if levels invalid."""
    entry, stop, t1 = trade.get("entry"), trade.get("stop"), trade.get("target_1")
    if not entry or not stop or not t1 or entry <= 0:
        return None
    reward = (t1 - entry) / entry * 100.0
    risk = (entry - stop) / entry * 100.0
    if reward <= 0 or risk <= 0:
        return None
    return p * reward - (1.0 - p) * risk - COST_ROUND_TRIP_PCT


MAX_RISK_PCT = 8.0   # enforce TradeConfig.MAX_STOP_DISTANCE_PCT at selection:
                     # a 2×ATR stop wider than this (hyper-volatile names, e.g.
                     # post-spinoff SNDK at 15%) is an automatic skip.


def rank_by_expectancy(
    model, calibrator, candidates: List[Dict[str, Any]],
    max_risk_pct: float = MAX_RISK_PCT,
) -> List[Tuple[Dict[str, Any], float, float]]:
    """Return [(trade, p_win, expectancy)] sorted by expectancy desc,
    excluding trades with invalid levels or stop distance > max_risk_pct."""
    if not candidates:
        return []
    probs = p_win(model, calibrator, candidates)
    out = []
    for t, p in zip(candidates, probs):
        entry, stop = t.get("entry"), t.get("stop")
        if entry and stop and (entry - stop) / entry * 100.0 > max_risk_pct:
            continue
        e = expectancy_pct(t, float(p))
        if e is not None:
            out.append((t, float(p), e))
    out.sort(key=lambda r: -r[2])
    return out
