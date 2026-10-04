# OFFLINE only — never import this at runtime
"""Continuous feature extraction for the LightGBM experiment (MODEL.md §15).

Rationale: the 36 binary features showed ZERO out-of-sample win/lose
discrimination (precision = base rate, see confusion-matrix analysis).
Hypothesis to falsify: the signal was destroyed by binarization — raw
indicator VALUES + a model that handles interactions (gradient boosting)
can discriminate. Pre-registered bar: OOS AUC > 0.5 / top-decile win rate
meaningfully above the 37.6% base rate.

Point-in-time safety: every feature below is a CAUSAL rolling computation
(rolling means/max/min, ewm, diff, pct_change) — the value at row t uses only
bars ≤ t. Computing on the full frame and reading row t is therefore identical
to computing on a frame sliced at t, just ~100× faster.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = _ROOT / "results" / "cache"

CONT_FEATURE_NAMES: List[str] = [
    # momentum / oscillators
    "rsi14", "adx14", "stoch_k", "stoch_d", "macd_hist_pct",
    "roc_5", "roc_10", "roc_20",
    # volatility
    "atr_pct", "bb_width", "day_change_pct",
    # trend / location (distances, in %)
    "px_vs_ma20", "px_vs_ma50", "px_vs_ma200", "ma20_vs_ma50",
    "px_vs_hi52", "px_vs_lo20",
    # volume / flow
    "vol_ratio", "obv_vs_ma",
    # market context
    "rel_spy_20d", "vix_close",
    # trade geometry (from the recorded levels)
    "risk_pct", "reward_pct", "rr_ratio",
    # analyzer section scores (continuous 0-100, computed point-in-time)
    "sec_trend", "sec_location", "sec_setup", "sec_volume",
    "sec_momentum", "sec_candles", "sec_risk_reward", "sec_market",
]

_SEC_KEYS = ["trend", "location", "setup", "volume",
             "momentum", "candles", "risk_reward", "market_context"]


def _indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    """All causal continuous indicators for one ticker's full daily frame."""
    o = pd.DataFrame(index=df.index)
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]

    # RSI — Wilder smoothing (matches TA-Lib)
    delta = c.diff()
    gain = delta.clip(lower=0); loss = (-delta).clip(lower=0)
    ag = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    al = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    o["rsi14"] = 100 - 100 / (1 + ag / al.replace(0, np.nan))

    # ADX — full Wilder smoothing (matches TA-Lib)
    up = h.diff(); dn = -l.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    a = 1/14
    atr = tr.ewm(alpha=a, adjust=False, min_periods=14).mean()
    pdi = 100 * plus_dm.ewm(alpha=a, adjust=False, min_periods=14).mean() / atr.replace(0, np.nan)
    mdi = 100 * minus_dm.ewm(alpha=a, adjust=False, min_periods=14).mean() / atr.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    o["adx14"] = dx.ewm(alpha=a, adjust=False, min_periods=14).mean()
    o["atr_pct"] = atr / c * 100

    # Stochastic — standard slow stochastic (matches TA-Lib STOCH 14,3,3)
    lo14, hi14 = l.rolling(14).min(), h.rolling(14).max()
    fast_k = (c - lo14) / (hi14 - lo14).replace(0, np.nan) * 100
    o["stoch_k"] = fast_k.rolling(3).mean()
    o["stoch_d"] = o["stoch_k"].rolling(3).mean()

    # MACD histogram, % of price
    macd = c.ewm(span=12).mean() - c.ewm(span=26).mean()
    o["macd_hist_pct"] = (macd - macd.ewm(span=9).mean()) / c * 100

    for n in (5, 10, 20):
        o[f"roc_{n}"] = c.pct_change(n) * 100

    bb_mid = c.rolling(20).mean(); bb_sd = c.rolling(20).std()
    o["bb_width"] = 4 * bb_sd / bb_mid * 100
    o["day_change_pct"] = c.pct_change() * 100

    ma20, ma50, ma200 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    o["px_vs_ma20"] = (c / ma20 - 1) * 100
    o["px_vs_ma50"] = (c / ma50 - 1) * 100
    o["px_vs_ma200"] = (c / ma200 - 1) * 100
    o["ma20_vs_ma50"] = (ma20 / ma50 - 1) * 100
    o["px_vs_hi52"] = (c / h.rolling(252).max() - 1) * 100
    o["px_vs_lo20"] = (c / l.rolling(20).min() - 1) * 100

    o["vol_ratio"] = v / v.rolling(20).mean().replace(0, np.nan)
    obv = (np.sign(c.diff()) * v).cumsum()
    o["obv_vs_ma"] = (obv / obv.rolling(20).mean().replace(0, np.nan) - 1).clip(-5, 5)

    o["ret_20"] = c.pct_change(20) * 100   # helper for rel_spy
    return o


def build_continuous_matrix(
    trades: List[Dict[str, Any]],
    cache_dir: Path = CACHE,
    verbose: bool = True,
) -> np.ndarray:
    """Return X_cont (n_trades × len(CONT_FEATURE_NAMES)), NaN where unavailable.
    Order matches `trades`. LightGBM handles NaN natively."""
    spy = pd.read_parquet(cache_dir / "ohlc_^GSPC.parquet")
    spy.index = spy.index.tz_localize(None)
    spy_ret20 = spy["Close"].pct_change(20) * 100
    vix = pd.read_parquet(cache_dir / "ohlc_^VIX.parquet")["Close"]
    vix.index = vix.index.tz_localize(None)

    by_ticker: Dict[str, List[int]] = {}
    for i, t in enumerate(trades):
        by_ticker.setdefault(t["ticker"], []).append(i)

    X = np.full((len(trades), len(CONT_FEATURE_NAMES)), np.nan)
    col = {n: j for j, n in enumerate(CONT_FEATURE_NAMES)}

    for n_done, (tk, idxs) in enumerate(sorted(by_ticker.items())):
        path = cache_dir / f"ohlc_{tk}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        ind = _indicator_frame(df)

        for i in idxs:
            t = trades[i]
            ts = pd.Timestamp(t["sample_date"])
            sub = ind[ind.index <= ts]
            if sub.empty:
                continue
            row = sub.iloc[-1]
            for name in CONT_FEATURE_NAMES[:19]:      # indicator block
                X[i, col[name]] = row.get(name, np.nan)
            # market context
            s_r = spy_ret20[spy_ret20.index <= ts]
            if len(s_r) and not np.isnan(row.get("ret_20", np.nan)):
                X[i, col["rel_spy_20d"]] = row["ret_20"] - float(s_r.iloc[-1])
            v_r = vix[vix.index <= ts]
            if len(v_r):
                X[i, col["vix_close"]] = float(v_r.iloc[-1])
            # geometry
            e, s, t1 = t.get("entry"), t.get("stop"), t.get("target_1")
            if e and s and t1 and e > 0:
                risk = (e - s) / e * 100; reward = (t1 - e) / e * 100
                X[i, col["risk_pct"]] = risk
                X[i, col["reward_pct"]] = reward
                X[i, col["rr_ratio"]] = reward / risk if risk > 0 else np.nan
            # section scores
            ind_d = t.get("indicators") or {}
            for k, name in zip(_SEC_KEYS, CONT_FEATURE_NAMES[24:]):
                sec = ind_d.get(k)
                if sec and sec.get("score") is not None:
                    X[i, col[name]] = float(sec["score"])
        if verbose and (n_done + 1) % 50 == 0:
            print(f"  [{n_done+1}/{len(by_ticker)}] tickers featurized")
    return X
