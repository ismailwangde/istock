# OFFLINE only — never import this at runtime
"""Retrain-1 event-driven backtester.

Fixes over the legacy monthly backtester (see MODEL.md §15):
  0b. purge-ready output   — every trade records `resolved_date`, so the
      trainer can purge boundary-crossing trades exactly.
  0c. no selection bias    — EVERY analysis with valid levels is forward-
      tested, regardless of verdict (not just BUYs).
  9.  event-driven sampling — one open trade per ticker at a time; while
      flat, scan every trading day; while a trade is open, don't sample.
      Eliminates overlapping forward windows by construction.
  10. trading-day window   — forward bars are sliced from the cached daily
      frame (bars == trading days), killing the calendar/trading-day bug.

Costs: labels are cut later by the trainer via features.spec.apply_costs
(0.60% round-trip) — this module records RAW pnl_pct.

Usage:
    from istock.training.backtester import run_backtest
    run_backtest(start="2023-05-01", end="2026-06-30")     # full universe
    run_backtest(tickers=["AAPL"], start=..., end=...)      # subset

Resumable: state is persisted to results/retrain1_backtest.json after each
ticker; rerunning skips completed tickers.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_PATH = _ROOT / "results" / "retrain1_backtest.json"

MAX_HOLD_BARS = 60          # trading days (bars), enforced exactly
MIN_HISTORY_DAYS = 1600     # calendar days of OHLC to prefetch (~4.4y)


# --------------------------------------------------------------------------- #
# Outcome resolution — bars sliced straight from the cached daily frame
# --------------------------------------------------------------------------- #
def resolve_outcome(
    fwd: pd.DataFrame,
    entry: float, stop: float, t1: Optional[float], t2: Optional[float],
) -> Tuple[str, Optional[float], Optional[int]]:
    """Walk forward bar by bar. Stop checked FIRST within a bar (conservative:
    intraday order unknown). Returns (outcome, exit_price, bars_held)."""
    if fwd is None or fwd.empty:
        return "data_missing", None, None
    if not entry or not stop or not t1:
        return "no_levels", None, None
    for i, (_, row) in enumerate(fwd.iterrows(), start=1):
        if float(row["Low"]) <= stop:
            return "hit_stop", float(stop), i
        if t2 and float(row["High"]) >= t2:
            return "hit_t2", float(t2), i
        if float(row["High"]) >= t1:
            return "hit_t1", float(t1), i
    return "expired", float(fwd["Close"].iloc[-1]), len(fwd)


# --------------------------------------------------------------------------- #
# Trade-record assembly
# --------------------------------------------------------------------------- #
def _sections_to_indicators(analysis) -> Dict[str, Any]:
    """FullAnalysis.sections → {section: {passed_checks: [...]}} in the exact
    shape spec._all_passed_checks expects."""
    out: Dict[str, Any] = {}
    for key, sec in (analysis.sections or {}).items():
        out[key] = {
            "score": float(sec.score),
            "passed_checks": [c.name for c in (sec.checks or []) if c.passed],
        }
    return out


def _build_record(ticker: str, d: date, analysis, extra: Dict[str, int]) -> Dict[str, Any]:
    setup = analysis.setup
    targets = list(getattr(setup, "targets", []) or [])
    rec: Dict[str, Any] = {
        "ticker": ticker,
        "sample_date": d.isoformat(),
        "verdict": analysis.verdict,
        "buy_score": analysis.buy_score,
        "setup_type": getattr(setup, "setup_type", "none"),
        "entry": float(getattr(setup, "entry", 0) or 0),
        "stop": float(getattr(setup, "stop_loss", 0) or 0),
        "target_1": float(targets[0]) if targets else None,
        "target_2": float(targets[1]) if len(targets) > 1 else None,
        "indicators": _sections_to_indicators(analysis),
        # outcome fields filled by caller
        "outcome": None, "exit_price": None, "days_held": None,
        "pnl_pct": None, "resolved_date": None,
    }
    rec.update(extra)  # the 11 E+F flat keys
    return rec


@contextlib.contextmanager
def _silence():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def _load_state() -> Dict[str, Any]:
    if RESULTS_PATH.exists():
        try:
            return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"status": "in_progress", "created_at": datetime.now().isoformat(),
            "completed_tickers": [], "trades": [], "errors": []}


def _save_state(state: Dict[str, Any]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = RESULTS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
    tmp.replace(RESULTS_PATH)


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
def run_backtest(
    tickers: Optional[List[str]] = None,
    start: str = "2023-05-01",
    end: Optional[str] = None,
    max_hold_bars: int = MAX_HOLD_BARS,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Event-driven backtest over `tickers` (default: SCANNER_UNIVERSE_BASE)."""
    from istock.config import SCANNER_UNIVERSE_BASE  # istock/config.py
    from istock.data.ohlc_cache import monkey_patch_yfinance, prefetch_universe
    from istock.decision.advisor import TradeAdvisor

    universe = [t.upper() for t in (tickers or SCANNER_UNIVERSE_BASE)]
    end = end or date.today().isoformat()

    # 1. Prefetch OHLC once (incl. VIX + SPY for regime/guardrail).
    if verbose:
        print(f"[prefetch] {len(universe)} tickers + ^VIX/^GSPC …")
    prefetch_universe(universe + ["^VIX", "^GSPC"],
                      (pd.Timestamp(start) - pd.DateOffset(years=2)).date(), end)

    state = _load_state()
    done = set(state["completed_tickers"])

    with monkey_patch_yfinance(universe + ["^VIX", "^GSPC"]):
        advisor = TradeAdvisor()
        for tk in universe:
            if tk in done:
                continue
            try:
                _run_ticker(tk, start, end, max_hold_bars, advisor, state, verbose)
            except Exception as exc:
                state["errors"].append({"ticker": tk, "error": str(exc)})
                if verbose:
                    print(f"  ❌ {tk}: {exc}")
            state["completed_tickers"].append(tk)
            _save_state(state)

    state["status"] = "complete"
    state["completed_at"] = datetime.now().isoformat()
    _save_state(state)
    if verbose:
        n = len(state["trades"])
        resolved = sum(1 for t in state["trades"]
                       if t["outcome"] in ("hit_t1", "hit_t2", "hit_stop"))
        print(f"[done] {n} trades recorded, {resolved} resolved → {RESULTS_PATH}")
    return state


def _run_ticker(tk, start, end, max_hold_bars, advisor, state, verbose):
    from istock.data.ohlc_cache import get_cached_ohlc
    from istock.features.live_features import compute_live_features

    df = get_cached_ohlc(tk)  # full cached frame
    if df is None or df.empty:
        raise RuntimeError("no cached OHLC")
    idx = df.index
    lo = pd.Timestamp(start); hi = pd.Timestamp(end)
    if idx.tz is not None:
        lo, hi = lo.tz_localize(idx.tz), hi.tz_localize(idx.tz)
    days = [ts for ts in idx if lo <= ts <= hi]
    if not days:
        raise RuntimeError("no trading days in range")

    n_trades, i = 0, 0
    while i < len(days):
        d = days[i].date()
        try:
            with _silence():
                analysis = advisor.analyze(tk, as_of_date=d.isoformat())
        except ValueError:
            i += 1
            continue
        if analysis is None:
            i += 1
            continue

        # E+F features, point-in-time (df sliced to d)
        sliced = df[df.index <= days[i]]
        try:
            extra = compute_live_features(tk, sliced, as_of_date=d)
        except Exception:
            extra = {}

        rec = _build_record(tk, d, analysis, extra)

        has_levels = rec["entry"] and rec["stop"] and rec["target_1"] \
            and rec["setup_type"] != "none"
        if not has_levels:
            rec["outcome"] = "no_levels"
            state["trades"].append(rec)
            i += 1
            continue

        # Forward bars: strictly after d, capped at max_hold_bars TRADING days.
        pos = idx.get_loc(days[i])
        fwd = df.iloc[pos + 1: pos + 1 + max_hold_bars]
        outcome, exit_price, bars_held = resolve_outcome(
            fwd, rec["entry"], rec["stop"], rec["target_1"], rec["target_2"])
        rec["outcome"] = outcome
        rec["exit_price"] = exit_price
        rec["days_held"] = bars_held
        if exit_price is not None and rec["entry"]:
            rec["pnl_pct"] = round((exit_price - rec["entry"]) / rec["entry"] * 100, 4)
        if bars_held is not None and pos + bars_held < len(idx):
            rec["resolved_date"] = idx[pos + bars_held].date().isoformat()
        state["trades"].append(rec)
        n_trades += 1

        # Event-driven: while the trade is open we do NOT sample.
        # Jump to the first day AFTER resolution.
        if bars_held is not None:
            target_ts = idx[min(pos + bars_held, len(idx) - 1)]
            while i < len(days) and days[i] <= target_ts:
                i += 1
        else:
            i += 1

    if verbose:
        print(f"  ✅ {tk}: {n_trades} forward-tested trades")
