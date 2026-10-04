# OFFLINE research module — not imported by the live app.
"""Sleeve 2: monthly cross-sectional multi-factor ranker (see NEXT_STEPS.md).

Philosophy shift from Brain v2: we do NOT predict a single stock's move.
We RANK the whole universe each month and hold the top basket. The edge, if
any, is cross-sectional momentum (people underreact to trends) — the one
systematic signal with live evidence (MTUM beat the S&P by ~3pp/yr).

Point-in-time safety: at rebalance month-end t, the signal uses only prices
through t; the position is held over (t, t+1] and earns that forward return.
No lookahead.

Honest caveats (printed in the report too):
  * Survivorship bias: the universe is today's survivors, which inflates
    results. Same universe the whole project used, so comparison is consistent.
  * Quality factor is NOT included here: true fundamental quality (ROE, margins,
    debt) is not point-in-time available for free, and using today's snapshot
    on 2019 data is lookahead. We test a PIT-SAFE price proxy (risk-adjusted
    momentum = momentum / volatility) instead, and say so.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = _ROOT / "results" / "cache"

COST_PER_SIDE_PCT = 0.30          # matches spec.py
# BENCHMARK must be a TOTAL-RETURN series (dividends reinvested) to be a fair
# bar: our strategy's Adj Close returns include dividends. ^GSPC is price-only
# and understates the true index return by ~1.7pp/yr — SPY's Adj Close is the
# honest total-return benchmark. (Bug fixed 2026-07: was ^GSPC.)
BENCHMARK = "SPY"


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
def _load_close(ticker: str) -> Optional[pd.Series]:
    """Adjusted-close series (total-return correct), tz-naive daily."""
    path = CACHE / f"ohlc_{ticker.upper().replace('/', '_')}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if df.empty or "Adj Close" not in df.columns:
        return None
    s = df["Adj Close"].copy()
    if s.index.tz is not None:
        s.index = s.index.tz_localize(None)
    return s[~s.index.duplicated(keep="last")].sort_index()


def build_price_panel(tickers: List[str]) -> pd.DataFrame:
    """Daily adjusted-close panel: index=dates, columns=tickers."""
    cols = {}
    for t in tickers:
        s = _load_close(t)
        if s is not None and len(s) > 260:
            cols[t] = s
    panel = pd.DataFrame(cols).sort_index()
    return panel


def _drop_partial_trailing_month(obj):
    """Drop the final calendar month if the data doesn't reach its month-end
    (e.g. data ending Jul 9 → the partial 'July' bar would contaminate the
    prior month's forward return). A month is 'complete' once we have a bar on
    or after the 25th."""
    if obj is None or len(obj) == 0:
        return obj
    last = obj.index.max()
    if last.day < 25:
        return obj[obj.index < last.replace(day=1)]
    return obj


def month_end_panel(daily: pd.DataFrame) -> pd.DataFrame:
    """Last observed price each calendar month (partial trailing month dropped)."""
    return _drop_partial_trailing_month(daily).resample("ME").last()


# --------------------------------------------------------------------------- #
# Signals (all point-in-time: computed from prices up to and including t)
# --------------------------------------------------------------------------- #
def momentum_12_1(monthly: pd.DataFrame) -> pd.DataFrame:
    """Classic 12-1: return from t-12 to t-1 (skip most recent month to avoid
    short-term reversal). Value at row t uses only prices <= t."""
    # price at t-1 relative to price at t-12
    return monthly.shift(1) / monthly.shift(12) - 1.0


def risk_adj_momentum(daily: pd.DataFrame, monthly: pd.DataFrame) -> pd.DataFrame:
    """12-1 momentum divided by trailing 12m daily-return volatility.
    A PIT-safe 'quality-ish' tilt: rewards steady trends over jumpy ones."""
    mom = momentum_12_1(monthly)
    daily_ret = daily.pct_change()
    # annualized vol over trailing ~252 trading days, sampled at month-ends
    vol_daily = daily_ret.rolling(252).std() * np.sqrt(252)
    vol_me = vol_daily.resample("ME").last()
    vol_me = vol_me.reindex(mom.index)
    return mom / vol_me.replace(0, np.nan)


# --------------------------------------------------------------------------- #
# Backtest engine
# --------------------------------------------------------------------------- #
def run_ranker(
    daily: pd.DataFrame,
    signal: pd.DataFrame,
    top_n: int = 20,
    start: str = "2018-01-01",
    cost_per_side_pct: float = COST_PER_SIDE_PCT,
) -> Dict:
    """Equal-weight top-N by `signal`, rebalanced monthly, net of turnover cost.

    Returns dict with the monthly net-return series, weights history, and stats.
    """
    monthly = month_end_panel(daily)
    fwd_ret = monthly.pct_change().shift(-1)   # return over (t, t+1], indexed at t

    dates = signal.index[signal.index >= pd.Timestamp(start)]
    prev_w = pd.Series(dtype=float)
    rows = []
    for t in dates:
        sig_t = signal.loc[t].dropna()
        # need a realized forward return to hold into
        if t not in fwd_ret.index:
            continue
        fr = fwd_ret.loc[t]
        picks = sig_t.sort_values(ascending=False).head(top_n).index
        picks = [p for p in picks if pd.notna(fr.get(p, np.nan))]
        if not picks:
            continue
        w = pd.Series(1.0 / len(picks), index=picks)

        # turnover cost: sum |w_new - w_old| * cost_per_side
        allnames = prev_w.index.union(w.index)
        turnover = (w.reindex(allnames).fillna(0) - prev_w.reindex(allnames).fillna(0)).abs().sum()
        cost = turnover * (cost_per_side_pct / 100.0)

        gross = float((w * fr.reindex(w.index)).sum())
        net = gross - cost
        rows.append({"date": t, "gross": gross, "net": net,
                     "cost": cost, "turnover": turnover, "n": len(picks)})
        prev_w = w

    res = pd.DataFrame(rows).set_index("date")
    return {
        "returns": res["net"], "gross": res["gross"], "detail": res,
        "stats": _stats(res["net"], label=f"top{top_n}"),
    }


def benchmark_returns(daily: pd.DataFrame, start: str = "2018-01-01") -> pd.Series:
    """Monthly returns of the benchmark index over the same window."""
    s = _drop_partial_trailing_month(_load_close(BENCHMARK))
    m = s.resample("ME").last()
    r = m.pct_change().shift(-1)   # align to same (t, t+1] convention
    return r[r.index >= pd.Timestamp(start)].dropna()


def equal_weight_all(daily: pd.DataFrame, start: str = "2018-01-01") -> pd.Series:
    """Hold the ENTIRE universe equal-weight — isolates whether momentum
    SELECTION adds value over just owning everything (buy-and-hold basket)."""
    monthly = month_end_panel(daily)
    fwd = monthly.pct_change().shift(-1)
    fwd = fwd[fwd.index >= pd.Timestamp(start)]
    return fwd.mean(axis=1).dropna()


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #
def _stats(monthly_ret: pd.Series, label: str = "") -> Dict:
    r = monthly_ret.dropna()
    if r.empty:
        return {}
    n_years = len(r) / 12.0
    cum = (1 + r).prod()
    cagr = cum ** (1 / n_years) - 1
    vol = r.std() * np.sqrt(12)
    sharpe = (r.mean() * 12) / vol if vol > 0 else np.nan
    curve = (1 + r).cumprod()
    dd = (curve / curve.cummax() - 1).min()
    return {
        "label": label, "months": len(r), "total_return_pct": (cum - 1) * 100,
        "cagr_pct": cagr * 100, "vol_pct": vol * 100, "sharpe": sharpe,
        "max_drawdown_pct": dd * 100,
    }


def per_year(monthly_ret: pd.Series) -> pd.Series:
    return (1 + monthly_ret.dropna()).groupby(monthly_ret.dropna().index.year).prod() - 1
