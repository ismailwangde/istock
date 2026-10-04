"""Measure whether the analyzer's quality_score predicted forward returns, using
the forward-logged snapshots. Honest metrics: Spearman IC (score vs forward
return) and quintile spread. Needs enough elapsed time to be meaningful.

Usage: python performance.py [horizon_trading_days]   (default 21)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LOGS = Path(__file__).resolve().parent / "logs"


def load():
    scores = pd.read_csv(LOGS / "scores.csv", parse_dates=["date"]) if (LOGS / "scores.csv").exists() else None
    prices = pd.read_csv(LOGS / "prices.csv", parse_dates=["date"]) if (LOGS / "prices.csv").exists() else None
    return scores, prices


def forward_return(prices, ticker, from_date, horizon):
    """Return over `horizon` trading days after from_date, from the price log."""
    p = prices[prices.ticker == ticker].sort_values("date")
    p = p[p.date >= from_date].reset_index(drop=True)
    if len(p) <= horizon:
        return np.nan
    p0, p1 = p.loc[0, "close"], p.loc[horizon, "close"]
    return (p1 / p0 - 1) * 100 if p0 > 0 else np.nan


def main(horizon=21):
    scores, prices = load()
    if scores is None or prices is None:
        print("No logs yet. Run snapshot.py prices (daily) and scores (weekly) first.")
        return
    span = (prices.date.max() - prices.date.min()).days
    print(f"price log spans {span} days; {scores.date.nunique()} score snapshots")
    if span < horizon:
        print(f"Not enough forward data yet for a {horizon}-day horizon — keep logging.")
        return

    rows = []
    for _, s in scores.iterrows():
        fr = forward_return(prices, s.ticker, s.date, horizon)
        if not np.isnan(fr):
            rows.append({"score": s.quality_score, "fwd_ret": fr})
    df = pd.DataFrame(rows)
    if len(df) < 30:
        print(f"Only {len(df)} score→return pairs resolved — need more time/coverage.")
        return

    ic = df["score"].corr(df["fwd_ret"], method="spearman")
    print(f"\nn={len(df)} pairs | horizon={horizon}td")
    print(f"Spearman IC (score vs forward return): {ic:+.3f}   (>+0.03 = mild signal)")
    q = pd.qcut(df["score"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
    print("\nquintile | avg score | avg fwd ret %")
    for qq in [1, 2, 3, 4, 5]:
        sub = df[q == qq]
        print(f"   Q{qq}    |  {sub.score.mean():6.1f}   |  {sub.fwd_ret.mean():+6.2f}")
    spread = df[q == 5].fwd_ret.mean() - df[q == 1].fwd_ret.mean()
    print(f"\nQ5-Q1 spread: {spread:+.2f}%  (high-score minus low-score forward return)")
    print("Positive & monotone across quintiles = the score sorts winners. "
          "Flat/negative = it doesn't (honest either way).")


if __name__ == "__main__":
    h = int(sys.argv[1]) if len(sys.argv) > 1 else 21
    main(h)
