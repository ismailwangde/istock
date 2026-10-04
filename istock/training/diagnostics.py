# OFFLINE only — never import this at runtime
"""Diagnostics for brain v2 training runs.

Three responsibilities:

1. **Feature-correlation matrix** per ticker — Pearson on the training-window
   feature columns. Surface top-3 most-correlated pairs in the per-ticker
   weight file, and flag any pair with `|r| ≥ 0.7` that appears across ≥ 5
   tickers in the aggregate diagnostics file.

2. **Bootstrap PF confidence intervals** — resample test trades with
   replacement, recompute net PF, return (raw_pf, p5, p95). Used by the
   `bootstrap_pf_p5 ≥ 1.20` gate in §8 (locked NET-of-costs).

3. **VIX-regime stratification** — split test trades by month-average VIX
   into low (<17) / mid (17-22) / high (>22) and report stratified PF.
   §8 gate 5: any stratum's net PF < 1.10 fails.

All PF figures here are NET of costs (use `features.apply_costs`).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from istock.features.spec import FEATURE_NAMES, apply_costs
from istock.model.weights import WeightSet


# --------------------------------------------------------------------------- #
# Correlation
# --------------------------------------------------------------------------- #
def compute_correlation_matrix(X: np.ndarray) -> np.ndarray:
    """Return the Pearson correlation matrix of feature columns (NxN where
    N = X.shape[1]). Columns with zero variance get correlation 0 (vs NaN)
    so downstream code doesn't have to special-case them."""
    if X.ndim != 2:
        raise ValueError(f"X must be 2-D, got shape {X.shape}")
    Xf = X.astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.corrcoef(Xf, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
    return corr


def top_correlated_pairs(
    corr: np.ndarray,
    feature_names: Sequence[str],
    k: int = 3,
) -> List[Tuple[str, str, float]]:
    """Return the k highest-|r| off-diagonal pairs as (name_a, name_b, r),
    sorted by descending |r|. Uses the upper triangle only (no duplicates)."""
    n = corr.shape[0]
    if n != len(feature_names):
        raise ValueError(f"corr is {n}×{n} but feature_names has {len(feature_names)} entries")
    iu, ju = np.triu_indices(n, k=1)
    triples = [(feature_names[i], feature_names[j], float(corr[i, j])) for i, j in zip(iu, ju)]
    triples.sort(key=lambda t: -abs(t[2]))
    return triples[:k]


# --------------------------------------------------------------------------- #
# Profit-factor + bootstrap
# --------------------------------------------------------------------------- #
def profit_factor(pnl_pcts_net: np.ndarray) -> float:
    """PF = sum(positive net pnl) / |sum(negative net pnl)|.
    Returns float('inf') if there are no losers, 0.0 if there are no
    winners. Caller must already have applied `features.apply_costs`."""
    arr = np.asarray(pnl_pcts_net, dtype=float)
    if arr.size == 0:
        return 0.0
    pos = arr[arr > 0].sum()
    neg = -arr[arr < 0].sum()
    if neg == 0:
        return float("inf") if pos > 0 else 0.0
    return float(pos / neg)


def win_rate(pnl_pcts_net: np.ndarray) -> float:
    """Fraction of trades with net pnl > 0. Caller must already have
    applied `features.apply_costs`."""
    arr = np.asarray(pnl_pcts_net, dtype=float)
    if arr.size == 0:
        return 0.0
    return float((arr > 0).sum() / arr.size)


def bootstrap_pf(
    pnl_pcts_net: np.ndarray,
    n_resamples: int = 1000,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Return (raw_pf, p5_pf, p95_pf). Resamples `pnl_pcts_net` with
    replacement `n_resamples` times. Caller must already have applied
    `features.apply_costs`."""
    arr = np.asarray(pnl_pcts_net, dtype=float)
    raw = profit_factor(arr)
    if arr.size < 5:
        return raw, raw, raw
    rng = np.random.default_rng(seed)
    n = arr.size
    samples = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        samples[i] = profit_factor(arr[idx])
    finite_samples = np.where(np.isinf(samples), 1e6, samples)
    p5 = float(np.percentile(finite_samples, 5))
    p95 = float(np.percentile(finite_samples, 95))
    return raw, p5, p95


# --------------------------------------------------------------------------- #
# VIX regime stratification
# --------------------------------------------------------------------------- #
def load_vix_daily(cache_dir: Path) -> pd.DataFrame:
    """Read VIX daily closes from the OHLC cache."""
    path = Path(cache_dir) / "ohlc_^VIX.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"No ^VIX parquet at {path}. Call scripts.ohlc_cache.prefetch_universe(['^VIX'], ...) first."
        )
    df = pd.read_parquet(path)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    out = pd.DataFrame({"close": df["Close"].astype(float)})
    out["month"] = out.index.to_period("M").astype(str)
    return out


def vix_regime_for_month(
    monthly_avg_vix: float,
    low_cutoff: float = 17.0,
    high_cutoff: float = 22.0,
) -> str:
    """Map a month's average VIX to 'low', 'mid', or 'high' per §8.5."""
    if monthly_avg_vix < low_cutoff:
        return "low"
    if monthly_avg_vix > high_cutoff:
        return "high"
    return "mid"


def stratified_pf_by_vix(
    trades_with_pnl_net: List[Dict[str, Any]],
    vix_daily: pd.DataFrame,
) -> Dict[str, Optional[float]]:
    """Group trades by entry-month VIX regime; return
    {'low': pf, 'mid': pf, 'high': pf}."""
    if vix_daily.empty or not trades_with_pnl_net:
        return {"low": None, "mid": None, "high": None}

    monthly_avg = vix_daily.groupby("month")["close"].mean()
    regime_by_month: Dict[str, str] = {
        m: vix_regime_for_month(float(v)) for m, v in monthly_avg.items()
    }

    buckets: Dict[str, List[float]] = {"low": [], "mid": [], "high": []}
    for t in trades_with_pnl_net:
        sd = t.get("sample_date")
        if not sd:
            continue
        month = sd[:7]
        regime = regime_by_month.get(month)
        if regime is None:
            continue
        buckets[regime].append(float(t["pnl_net"]))

    result: Dict[str, Optional[float]] = {}
    for regime, vals in buckets.items():
        result[regime] = profit_factor(np.asarray(vals)) if vals else None
    return result


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_diagnostics_md(
    run_summary: Dict[str, Any],
    out_path: Path,
) -> None:
    """Write `results/brain_v2_weights/_diagnostics.md` from a training-run summary."""
    pt = run_summary.get("per_ticker", [])
    n_confident = sum(1 for r in pt if r["status"] == "confident")
    n_pooled = sum(1 for r in pt if r["status"] == "pooled")
    n_disabled = sum(1 for r in pt if r["status"] == "disabled")

    confident = sorted(
        (r for r in pt if r["status"] == "confident"),
        key=lambda r: -r["test_pf_net"],
    )
    top5 = confident[:5]
    bottom5 = confident[-5:] if len(confident) > 5 else []

    pooled = run_summary.get("pooled", {})

    def _fmt(x, prec=2):
        if x is None:
            return "—"
        if isinstance(x, float):
            return f"{x:.{prec}f}"
        return str(x)

    md = []
    md.append("# Brain v2 — Training Diagnostics")
    md.append("")
    md.append(f"_Fold: **{run_summary.get('fold_label', '')}** — fit at {run_summary.get('fit_at', '')}._")
    md.append("")
    md.append("All PF / WR / avg_pnl values below are **net of the 0.20% round-trip cost** (§5b).")
    md.append("")
    md.append("## Roster outcome")
    md.append("")
    md.append("| State | Count |")
    md.append("|---|---:|")
    md.append(f"| Per-ticker confident | {n_confident} |")
    md.append(f"| Pooled fallback | {n_pooled} |")
    md.append(f"| Disabled (no recommendation) | {n_disabled} |")
    md.append(f"| **Total** | **{len(pt)}** |")
    md.append("")
    md.append("## Pooled model")
    md.append("")
    md.append("| Metric | Value |")
    md.append("|---|---:|")
    md.append(f"| C (L2 strength) | {_fmt(pooled.get('C'))} |")
    md.append(f"| n_train / val / test | {pooled.get('n_train','—')} / {pooled.get('n_val','—')} / {pooled.get('n_test','—')} |")
    md.append(f"| Train PF (net) | {_fmt(pooled.get('train_pf_net'))} |")
    md.append(f"| Val PF (net) | {_fmt(pooled.get('val_pf_net'))} |")
    md.append(f"| Test PF (net) | {_fmt(pooled.get('test_pf_net'))} |")
    md.append(f"| Test PF bootstrap 5th / 95th | {_fmt(pooled.get('test_pf_bootstrap_p5'))} / {_fmt(pooled.get('test_pf_bootstrap_p95'))} |")
    vs = pooled.get("vix_stratified_pf", {})
    md.append(f"| VIX-stratified test PF (low/mid/high) | {_fmt(vs.get('low'))} / {_fmt(vs.get('mid'))} / {_fmt(vs.get('high'))} |")
    md.append("")

    if top5:
        md.append("## Top 5 per-ticker confident models (by test PF net)")
        md.append("")
        md.append("| Ticker | n_test | Train PF | Test PF | Test PF p5 | C |")
        md.append("|---|---:|---:|---:|---:|---:|")
        for r in top5:
            md.append(
                f"| {r['ticker']} | {r['n_test']} | "
                f"{_fmt(r['train_pf_net'])} | {_fmt(r['test_pf_net'])} | "
                f"{_fmt(r['test_pf_bootstrap_p5'])} | {_fmt(r['C'])} |"
            )
        md.append("")

    if bottom5:
        md.append("## Bottom 5 per-ticker confident models (candidates for 'don't trade')")
        md.append("")
        md.append("| Ticker | n_test | Train PF | Test PF | Test PF p5 | C |")
        md.append("|---|---:|---:|---:|---:|---:|")
        for r in bottom5:
            md.append(
                f"| {r['ticker']} | {r['n_test']} | "
                f"{_fmt(r['train_pf_net'])} | {_fmt(r['test_pf_net'])} | "
                f"{_fmt(r['test_pf_bootstrap_p5'])} | {_fmt(r['C'])} |"
            )
        md.append("")

    md.append("## Full per-ticker outcome")
    md.append("")
    md.append("| Ticker | Status | n_train | n_test | Train PF | Test PF | Test PF p5 | Max \\|coef\\| | Reason |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for r in sorted(pt, key=lambda r: r["ticker"]):
        md.append(
            f"| {r['ticker']} | {r['status']} | {r['n_train']} | {r['n_test']} | "
            f"{_fmt(r.get('train_pf_net'))} | {_fmt(r.get('test_pf_net'))} | "
            f"{_fmt(r.get('test_pf_bootstrap_p5'))} | {_fmt(r.get('max_abs_coef'))} | "
            f"{r.get('reason', '')} |"
        )
    md.append("")

    flags = run_summary.get("system_wide_corr_flags", [])
    if flags:
        md.append("## System-wide correlation flags (|r| ≥ 0.7 across ≥ 5 tickers)")
        md.append("")
        md.append("| Pair A | Pair B | Median r | N tickers |")
        md.append("|---|---|---:|---:|")
        for a, b, r, n in flags:
            md.append(f"| {a} | {b} | {_fmt(r, 3)} | {n} |")
        md.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md), encoding="utf-8")
