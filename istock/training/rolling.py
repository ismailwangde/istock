# OFFLINE only — never import this at runtime
"""Rolling walk-forward evaluation (monthly refits).

The user-designed evaluation (MODEL.md §15): for every test month M, train a
fresh model on all trades FULLY RESOLVED before M begins, then score M's
trades. Aggregating across months measures the *process you'd actually run
live* (monthly retrains), not one stale snapshot.

Purge rule: a trade enters a training set only if its `resolved_date` is
strictly before the boundary — no label can contain post-boundary prices.
C selection: per refit, the trailing 6 months of the train window act as
validation (purged at their own boundary); the chosen C is then refit on the
full train window. The test month is never touched during selection.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from istock.features.spec import apply_costs, is_eligible_trade
from istock.training import diagnostics as diag
from istock.training.trainer import TrainConfig, build_xy, select_C, _fit_logreg


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _resolved(t: Dict[str, Any]) -> date:
    rd = t.get("resolved_date")
    if rd:
        try:
            return _d(rd)
        except ValueError:
            pass
    return _d(t["sample_date"]) + timedelta(days=90)  # conservative fallback


def _month_starts(first: date, last: date) -> List[date]:
    out, y, m = [], first.year, first.month
    while date(y, m, 1) <= last:
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def rolling_walk_forward(
    trades: List[Dict[str, Any]],
    min_train_months: int = 24,
    val_months: int = 6,
    cfg: Optional[TrainConfig] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Run the monthly-refit evaluation. Returns aggregate + per-month stats."""
    cfg = cfg or TrainConfig()
    trades = [t for t in trades if is_eligible_trade(t) and t.get("pnl_pct") is not None]
    trades.sort(key=lambda t: t["sample_date"])
    if not trades:
        raise ValueError("no eligible trades")

    first = _d(trades[0]["sample_date"])
    last = _d(trades[-1]["sample_date"])
    months = _month_starts(first, last)
    test_months = [m for m in months
                   if m >= (first + timedelta(days=int(min_train_months * 30.44)))]

    picked_pnls: List[float] = []
    picked_records: List[Dict[str, Any]] = []
    monthly: List[Dict[str, Any]] = []

    for m_start in test_months:
        m_next = date(m_start.year + (m_start.month == 12),
                      m_start.month % 12 + 1, 1)

        # --- splits (purged by resolution date) ---
        train_all = [t for t in trades if _resolved(t) < m_start]
        test = [t for t in trades if m_start <= _d(t["sample_date"]) < m_next]
        if len(train_all) < cfg.min_train_trades or not test:
            continue
        val_start = m_start - timedelta(days=int(val_months * 30.44))
        train_core = [t for t in train_all if _resolved(t) < val_start]
        val = [t for t in train_all if _d(t["sample_date"]) >= val_start]

        # --- C selection on the trailing-val window ---
        C = 1.0
        if len(train_core) >= cfg.min_train_trades and len(val) >= 30:
            X_tr, y_tr, _ = build_xy(train_core)
            X_v, y_v, pnl_v = build_xy(val)
            c_sel, _m = select_C(X_tr, y_tr, X_v, y_v, pnl_v, cfg)
            if c_sel is not None:
                C = c_sel

        # --- refit on full train window, score the test month ---
        X_full, y_full, _ = build_xy(train_all)
        model = _fit_logreg(X_full, y_full, C)
        if model is None:
            continue
        X_te, _y_te, pnl_te = build_xy(test)
        picked = model.predict(X_te) == 1

        m_pnls = pnl_te[picked]
        picked_pnls.extend(m_pnls.tolist())
        for t, p in zip(test, picked):
            if p:
                picked_records.append({**t, "pnl_net": apply_costs(float(t["pnl_pct"]))})

        pf = diag.profit_factor(m_pnls) if m_pnls.size else None
        monthly.append({
            "month": m_start.isoformat()[:7], "C": C,
            "n_train": len(train_all), "n_test": len(test),
            "n_picked": int(picked.sum()),
            "pf_net": (round(pf, 3) if pf is not None and np.isfinite(pf) else pf),
            "sum_pnl_net": round(float(m_pnls.sum()), 2) if m_pnls.size else 0.0,
        })
        if verbose:
            pf_s = f"{pf:5.2f}" if pf is not None and np.isfinite(pf) else "  inf" if pf is not None else "   —"
            print(f"  {m_start.isoformat()[:7]}  train={len(train_all):5d}  "
                  f"test={len(test):3d}  picked={int(picked.sum()):3d}  PF={pf_s}")

    arr = np.asarray(picked_pnls, dtype=float)
    pf_all, p5, p95 = diag.bootstrap_pf(arr)
    result = {
        "n_test_months": len(monthly),
        "n_picked_total": int(arr.size),
        "overall_pf_net": round(pf_all, 3),
        "bootstrap_p5": round(p5, 3), "bootstrap_p95": round(p95, 3),
        "overall_wr_net": round(diag.win_rate(arr), 3),
        "sum_pnl_net_pct": round(float(arr.sum()), 1),
        "monthly": monthly,
    }
    return result
