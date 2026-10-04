"""Earnings & analyst signals (framework §10). The ⭐ (modest-but-real) signal is
ANALYST ESTIMATE REVISIONS — rising estimates tend to precede drift. Price
targets and buy/sell ratings are lagging → context only. Surprise history is
context (PEAD arbitraged in large caps). Fetches its own yfinance data (target
company only, so the peer-panel build stays lean)."""
from __future__ import annotations

import numpy as np


def run_analyst(ticker: str) -> dict:
    import yfinance as yf
    t = yf.Ticker(ticker)
    info = {}
    try:
        info = t.info or {}
    except Exception:
        pass

    out = {"flags": [], "signals": []}

    # --- estimate revisions (the scored signal) ---
    net_rev_30d = np.nan
    try:
        er = t.eps_revisions
        if er is not None and not er.empty:
            # focus on full-year estimates (0y, +1y)
            rows = [r for r in ("0y", "+1y") if r in er.index]
            up = sum(float(er.loc[r, "upLast30days"]) for r in rows if not _na(er.loc[r, "upLast30days"]))
            dn = sum(float(er.loc[r, "downLast30days"]) for r in rows if not _na(er.loc[r, "downLast30days"]))
            net_rev_30d = up - dn
            out["revisions_up_30d"] = int(up)
            out["revisions_down_30d"] = int(dn)
    except Exception:
        pass
    out["net_revisions_30d"] = None if np.isnan(net_rev_30d) else int(net_rev_30d)

    # estimate trend: current FY EPS estimate vs 90 days ago
    est_trend = None
    try:
        et = t.eps_trend
        if et is not None and not et.empty and "0y" in et.index:
            cur, old = float(et.loc["0y", "current"]), float(et.loc["0y", "90daysAgo"])
            if old > 0:
                est_trend = round((cur / old - 1) * 100, 1)
    except Exception:
        pass
    out["fy_estimate_trend_90d_pct"] = est_trend

    if not np.isnan(net_rev_30d):
        if net_rev_30d > 0 and (est_trend is None or est_trend >= 0):
            out["signals"].append(f"Analyst estimates being revised UP (net +{int(net_rev_30d)} in 30d) — ⭐ modest positive")
        elif net_rev_30d < 0:
            out["flags"].append(f"Analyst estimates being revised DOWN (net {int(net_rev_30d)} in 30d)")

    # --- surprise history (context) ---
    try:
        eh = t.earnings_history
        if eh is not None and not eh.empty and "surprisePercent" in eh.columns:
            sp = eh["surprisePercent"].dropna().astype(float)
            out["avg_surprise_pct"] = round(sp.mean() * 100, 1)
            out["beat_rate_pct"] = round((sp > 0).mean() * 100, 0)
    except Exception:
        pass

    # --- price target + recommendation (context, lagging) ---
    tgt, price = info.get("targetMeanPrice"), info.get("currentPrice")
    if tgt and price:
        out["price_target_upside_pct"] = round((tgt / price - 1) * 100, 1)
    out["analyst_count"] = info.get("numberOfAnalystOpinions")
    out["recommendation"] = info.get("recommendationKey")
    out["recommendation_mean"] = info.get("recommendationMean")  # 1=strong buy,5=sell

    out["note"] = ("estimate revisions are the scored signal (⭐ modest); price targets & "
                   "ratings lag and are context; surprise history rarely tradeable in large caps")
    return out


def _na(x):
    try:
        import pandas as pd
        return x is None or pd.isna(x)
    except Exception:
        return True
