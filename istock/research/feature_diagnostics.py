# OFFLINE research — feature diagnostics for the Brain v2 logistic model.
"""VIF / IV / WOE analysis of the model's features (credit-scoring toolkit).

WHY: a logistic-regression model lives or dies by (a) how much each feature
actually separates winners from losers — measured by Information Value (IV) via
Weight of Evidence (WOE) binning — and (b) whether features are redundant —
measured by the Variance Inflation Factor (VIF). This quantifies, per feature,
exactly why the model scores AUC ~0.51.

Adds two NEW candidate features to the existing 36:
  * momentum_12_1 — 12-1 cross-sectional momentum (the one signal with edge)
  * news_sent     — daily headline sentiment (FNSPID, ~15% coverage)

IV interpretation (standard bands):
  <0.02 useless | 0.02-0.1 weak | 0.1-0.3 medium | 0.3-0.5 strong | >0.5 suspicious
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS = _ROOT / "results"
OUT = RESULTS / "analysis"
NEWS_DIR = RESULTS / "cache" / "news"
COST = 0.60


# --------------------------------------------------------------------------- #
# Feature assembly
# --------------------------------------------------------------------------- #
def load_trades() -> List[dict]:
    d = json.load(open(RESULTS / "retrain1_backtest.json"))
    t = d.get("trades", d) if isinstance(d, dict) else d
    return [x for x in t if x.get("outcome") in ("hit_t1", "hit_t2", "hit_stop")
            and x.get("pnl_pct") is not None and x.get("sample_date")]


def _momentum_lookup(tickers: List[str]):
    """ticker -> (dates, 12-1 momentum series) for fast PIT lookup."""
    from istock.training.factor_ranker import _load_close
    out = {}
    for tk in set(tickers):
        s = _load_close(tk)
        if s is None or len(s) < 260:
            continue
        mom = s.shift(21) / s.shift(252) - 1.0   # 12-1: ~12mo ago vs ~1mo ago
        out[tk] = mom
    return out


def _news_lookup() -> Dict[Tuple[str, pd.Timestamp], float]:
    """(ticker, date) -> mean daily VADER sentiment."""
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    frames = [pd.read_parquet(NEWS_DIR / f"fnspid_ndx_{i}.parquet",
                              columns=["Date", "Article_title", "Stock_symbol"])
              for i in (0, 1)]
    df = pd.concat(frames, ignore_index=True)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True).dt.tz_localize(None)
    df = df.dropna(subset=["Date", "Article_title", "Stock_symbol"])
    an = SentimentIntensityAnalyzer()
    df["sent"] = [an.polarity_scores(t)["compound"] for t in df["Article_title"]]
    df["d"] = df["Date"].dt.normalize()
    g = df.groupby(["Stock_symbol", "d"])["sent"].mean()
    return {(tk, d): v for (tk, d), v in g.items()}


def build_matrix() -> pd.DataFrame:
    """Return a DataFrame: 36 binary features + momentum + news + target 'win'."""
    from istock.features.spec import FEATURE_NAMES, extract_features
    trades = load_trades()
    mom_lk = _momentum_lookup([t["ticker"] for t in trades])
    news_lk = _news_lookup()

    rows = []
    for t in trades:
        feats = extract_features(t)
        row = {name: int(v) for name, v in zip(FEATURE_NAMES, feats)}
        tk = t["ticker"]; ts = pd.Timestamp(t["sample_date"]).normalize()

        # momentum (PIT): last value <= sample_date
        mom = np.nan
        if tk in mom_lk:
            s = mom_lk[tk]; s = s[s.index <= ts]
            if len(s): mom = float(s.iloc[-1])
        row["momentum_12_1"] = mom

        # news: same day, else walk back up to 3 days
        sent = np.nan
        for back in range(0, 4):
            key = (tk, ts - pd.Timedelta(days=back))
            if key in news_lk:
                sent = news_lk[key]; break
        row["news_sent"] = sent

        row["win"] = 1 if (t["pnl_pct"] - COST) > 0 else 0
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# WOE / IV
# --------------------------------------------------------------------------- #
def woe_iv(feature: pd.Series, target: pd.Series, bins: int = 10
           ) -> Tuple[pd.DataFrame, float, float]:
    """Return (per-bin WOE table, IV, coverage%). Binary features use their two
    values; continuous features are quantile-binned. good=win(1), bad=lose(0)."""
    mask = feature.notna()
    cov = mask.mean() * 100
    f, y = feature[mask], target[mask]
    nun = f.nunique()
    if nun <= 2:
        grp = f.astype(int)
    else:
        try:
            grp = pd.qcut(f, min(bins, nun), duplicates="drop")
        except Exception:
            grp = pd.cut(f, min(bins, nun))
    tot_good = max((y == 1).sum(), 1); tot_bad = max((y == 0).sum(), 1)
    recs, iv = [], 0.0
    for b, idx in y.groupby(grp, observed=True).groups.items():
        yy = y.loc[idx]
        g = (yy == 1).sum(); bd = (yy == 0).sum()
        pg = max(g, 0.5) / tot_good; pb = max(bd, 0.5) / tot_bad
        w = np.log(pg / pb); iv += (pg - pb) * w
        recs.append({"bin": str(b), "n": len(yy), "win_rate": yy.mean(),
                     "woe": w})
    return pd.DataFrame(recs), iv, cov


def iv_table(df: pd.DataFrame) -> pd.DataFrame:
    feats = [c for c in df.columns if c != "win"]
    out = []
    for c in feats:
        _, iv, cov = woe_iv(df[c], df["win"])
        out.append({"feature": c, "iv": iv, "coverage_pct": cov})
    t = pd.DataFrame(out).sort_values("iv", ascending=False).reset_index(drop=True)
    band = pd.cut(t["iv"], [-1, 0.02, 0.1, 0.3, 0.5, 99],
                  labels=["useless", "weak", "medium", "strong", "suspicious"])
    t["strength"] = band
    return t


# --------------------------------------------------------------------------- #
# VIF
# --------------------------------------------------------------------------- #
def vif_table(df: pd.DataFrame) -> pd.DataFrame:
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.tools.tools import add_constant
    feats = [c for c in df.columns if c != "win"]
    X = df[feats].copy()
    X["momentum_12_1"] = X["momentum_12_1"].fillna(X["momentum_12_1"].median())
    X["news_sent"] = X["news_sent"].fillna(0.0)
    # drop zero-variance columns (VIF undefined)
    X = X.loc[:, X.std() > 0]
    Xc = add_constant(X)
    rows = [{"feature": c, "vif": variance_inflation_factor(Xc.values, i)}
            for i, c in enumerate(Xc.columns) if c != "const"]
    return pd.DataFrame(rows).sort_values("vif", ascending=False).reset_index(drop=True)
