# NOTE: The VIX + sector-ETF helpers (SECTOR_ETF dict, VixDataUnavailable) can be split into
#       istock/data/market_data.py later, but move the whole file first, then refactor.
"""Live-time computation of the 11 E+F brain v2 feature columns.

Trade rows in `results/advisor_backtest.json` carry the 11 SMC + other-new
columns as flat keys (added by the S21.5 one-time backfill). The live
`TradeAdvisor.analyze()` produces a `FullAnalysis` that has the 25 brain
checks (categories A/B/C/D, via `sections[*].checks`) but NOT the 11 E+F
columns — those need to be computed from the same OHLC frame and live
yfinance data.

This module is the live counterpart to the now-archived S21.5 backfill
script. The logic is the same; the inputs come from `DataEngine.daily`
(already in scope when the advisor calls v2) rather than from a parquet
cache loop.

Public surface used by `core/trade_advisor.py`:
- `compute_live_features(ticker, daily_df, as_of_date, cache_dir) -> Dict[str, int]`
- `get_current_vix(as_of_date, cache_dir) -> Optional[float]`
- `analysis_to_trade_dict(analysis, ticker, sample_date) -> Dict`

All are pure-ish (read parquets + one yfinance call for earnings per
ticker per process). Failure modes degrade silently to 0 for the missing
column and log a one-line warning — they NEVER raise into the advisor.
"""

from __future__ import annotations

# SMC_CREDIT MUST be set before `from smartmoneyconcepts import smc`
# (Windows cp1252 stdout would otherwise crash on its credit-line emoji).
import os
os.environ.setdefault("SMC_CREDIT", "0")

import sys
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CACHE_DIR = _ROOT / "results" / "cache"

# Per-(ticker, date) cache for the dual-verdict block — see Amendment A.
# Files: results/cache/brain_v2_scores/<TICKER>_<YYYY-MM-DD>.json
SCORE_CACHE_DIR = _ROOT / "results" / "cache" / "brain_v2_scores"


class VixDataUnavailable(RuntimeError):
    """Raised by `get_current_vix` when the VIX parquet cache is missing
    or has no bar on/before the requested date. The advisor catches this
    explicitly and records `v2_skipped_reason='vix_unavailable'` rather
    than silently applying a default — VIX failures must be visible."""


# --------------------------------------------------------------------------- #
# Sector ETF mapping (copied from S21.5 backfill)
# --------------------------------------------------------------------------- #
# Hardcoded TICKER -> SPDR sector ETF for the 57-ticker brain v2 universe.
# Unmapped tickers fall back to SPY at the RS computation level.
SECTOR_ETF: Dict[str, str] = {
    # Information Technology -> XLK
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AVGO": "XLK",
    "ORCL": "XLK", "CRM": "XLK", "ADBE": "XLK", "CSCO": "XLK",
    "INTC": "XLK", "IBM": "XLK", "QCOM": "XLK", "TXN": "XLK",
    "AMD": "XLK", "MU": "XLK", "NOW": "XLK", "ACN": "XLK",
    "STX": "XLK", "WDC": "XLK", "SNDK": "XLK",
    # Communication Services -> XLC
    "GOOGL": "XLC", "META": "XLC", "NFLX": "XLC",
    # Consumer Discretionary -> XLY
    "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "MCD": "XLY",
    "PCRHY": "XLY",
    # Consumer Staples -> XLP
    "WMT": "XLP", "PG": "XLP", "COST": "XLP", "KO": "XLP",
    "PEP": "XLP", "PM": "XLP",
    # Health Care -> XLV
    "LLY": "XLV", "UNH": "XLV", "JNJ": "XLV", "ABBV": "XLV",
    "MRK": "XLV", "TMO": "XLV", "ABT": "XLV", "DHR": "XLV",
    # Financials -> XLF
    "BRK-B": "XLF", "JPM": "XLF", "V": "XLF", "MA": "XLF",
    "BAC": "XLF", "WFC": "XLF", "GS": "XLF",
    # Energy -> XLE
    "XOM": "XLE", "CVX": "XLE",
    # Industrials -> XLI
    "CAT": "XLI", "UPS": "XLI", "HON": "XLI", "FANUY": "XLI",
    "BE": "XLI",
    # Materials -> XLB
    "LIN": "XLB",
    # Utilities -> XLU
    "NEE": "XLU",
}


# --------------------------------------------------------------------------- #
# Process-level caches (warm-once per import)
# --------------------------------------------------------------------------- #
_EARNINGS_CACHE: Dict[str, List[date]] = {}
_ETF_DF_CACHE: Dict[str, pd.DataFrame] = {}
_VIX_DF_CACHE: Optional[pd.DataFrame] = None

# Per-process counter for the per-(ticker, date) score cache. Incremented
# by `load_score_cache` / `save_score_cache`. Used by the S24 smoke test to
# report hit rate. NOT thread-safe — fine for the Streamlit single-process
# model.
_SCORE_CACHE_STATS: Dict[str, int] = {"hits": 0, "misses": 0, "writes": 0, "errors": 0}


def get_score_cache_stats() -> Dict[str, int]:
    """Snapshot of the per-(ticker, date) cache hit/miss/write counts.
    Smoke-test helper; not load-bearing."""
    return dict(_SCORE_CACHE_STATS)


def reset_score_cache_stats() -> None:
    """Zero the counters. The smoke test calls this before navigating."""
    for k in _SCORE_CACHE_STATS:
        _SCORE_CACHE_STATS[k] = 0


def _warn(msg: str) -> None:
    """One-line warning to stderr — never raises, never silences."""
    print(f"  ⚠️  brain_v2.live_features: {msg}", file=sys.stderr)


# Feature-source dependencies. If any of these is missing, the corresponding
# brain v2 features silently compute as 0 — the model then runs on inputs it
# was never trained on (train/serve skew). The UI surfaces this via
# check_feature_dependencies(); fail LOUD, not soft.
_FEATURE_DEPENDENCIES = {
    "smartmoneyconcepts": "SMC features (order block, FVG, BOS, CHoCH) — the model's highest-weighted inputs",
    "pandas_ta_classic":  "VWAP features (vwap_above, vwap_band_stretched)",
    "talib":              "ATR regime features (atr_regime_low / high)",
    "lxml":               "earnings_within_5d (yfinance earnings calendar parse)",
}


def check_feature_dependencies() -> List[str]:
    """Return human-readable problems for every missing feature dependency.
    Empty list = all 36 features can actually be computed."""
    problems: List[str] = []
    for module, purpose in _FEATURE_DEPENDENCIES.items():
        try:
            __import__(module)
        except Exception as exc:
            problems.append(f"`{module}` missing ({exc}) → {purpose} will be 0")
    return problems


# --------------------------------------------------------------------------- #
# OHLC helpers
# --------------------------------------------------------------------------- #
def _normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with lowercase column names + tz-naive index. The
    SMC library expects lowercase open/high/low/close/volume."""
    out = df.copy()
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    rename = {"Open": "open", "High": "high", "Low": "low",
              "Close": "close", "Volume": "volume"}
    out = out.rename(columns=rename)
    return out


def _load_parquet_cached(ticker: str, cache_dir: Path) -> Optional[pd.DataFrame]:
    """Read `results/cache/ohlc_<TICKER>.parquet` from disk, cache per process.
    Used by sector-RS and VIX computations. Returns None if missing."""
    if ticker in _ETF_DF_CACHE:
        return _ETF_DF_CACHE[ticker]
    safe = ticker.upper().replace("/", "_")
    path = cache_dir / f"ohlc_{safe}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    _ETF_DF_CACHE[ticker] = df
    return df


# --------------------------------------------------------------------------- #
# SMC (Order Block, FVG, BOS/CHoCH)
# --------------------------------------------------------------------------- #
def _smc_features(daily_norm: pd.DataFrame) -> Dict[str, int]:
    """Return the 4 SMC features evaluated at the LAST bar of daily_norm.
    Failure → all zeros + warning."""
    out = {
        "smc_order_block_bullish": 0,
        "smc_fvg_bullish": 0,
        "smc_bos_bullish": 0,
        "smc_choch_bullish": 0,
    }
    try:
        from smartmoneyconcepts import smc
    except Exception as e:
        _warn(f"smartmoneyconcepts import failed ({e}); SMC features set to 0.")
        return out

    try:
        sw = smc.swing_highs_lows(daily_norm, swing_length=10)
        ob = smc.ob(daily_norm, swing_highs_lows=sw)
        fvg = smc.fvg(daily_norm)
        bc = smc.bos_choch(daily_norm, swing_highs_lows=sw)
    except Exception as e:
        _warn(f"SMC computation failed ({e}); features set to 0.")
        return out

    last_idx = len(daily_norm) - 1
    close = float(daily_norm["close"].iloc[last_idx])

    # 1) Bullish OB in last 20 bars AND price within 1% of [Bottom, Top]
    lo = max(0, last_idx - 20)
    ob_window = ob.iloc[lo:last_idx + 1]
    bull = ob_window[ob_window["OB"] == 1]
    for _, row in bull.iterrows():
        top = float(row["Top"])
        bottom = float(row["Bottom"])
        if bottom * 0.99 <= close <= top * 1.01:
            out["smc_order_block_bullish"] = 1
            break

    # 2) Bullish FVG in last 10 bars AND unfilled at the reference bar
    lo = max(0, last_idx - 10)
    fvg_window = fvg.iloc[lo:last_idx + 1]
    fvg_bull = fvg_window[fvg_window["FVG"] == 1]
    for _, row in fvg_bull.iterrows():
        mit = row["MitigatedIndex"]
        if pd.isna(mit) or float(mit) == 0.0 or float(mit) > last_idx:
            out["smc_fvg_bullish"] = 1
            break

    # 3+4) BOS/CHoCH bullish in last 5 bars
    lo = max(0, last_idx - 5)
    bc_window = bc.iloc[lo:last_idx + 1]
    out["smc_bos_bullish"] = int((bc_window["BOS"] == 1).any())
    out["smc_choch_bullish"] = int((bc_window["CHOCH"] == 1).any())
    return out


# --------------------------------------------------------------------------- #
# VWAP (anchored monthly) + 20-bar stdev band
# --------------------------------------------------------------------------- #
def _vwap_features(daily_norm: pd.DataFrame) -> Dict[str, int]:
    """vwap_above + vwap_band_stretched evaluated at the LAST bar.
    Anchored monthly to match the S21.5 backfill."""
    out = {"vwap_above": 0, "vwap_band_stretched": 0}
    try:
        import pandas_ta_classic as ta
    except Exception as e:
        _warn(f"pandas_ta_classic import failed ({e}); VWAP features set to 0.")
        return out

    try:
        vwap = ta.vwap(
            daily_norm["high"], daily_norm["low"],
            daily_norm["close"], daily_norm["volume"],
            anchor="M",
        )
        resid = daily_norm["close"] - vwap
        stdev = resid.rolling(20, min_periods=5).std()
    except Exception as e:
        _warn(f"VWAP compute failed ({e}); features set to 0.")
        return out

    last_close = float(daily_norm["close"].iloc[-1])
    last_vwap = vwap.iloc[-1]
    last_std = stdev.iloc[-1]
    if pd.isna(last_vwap):
        return out
    out["vwap_above"] = int(last_close > float(last_vwap))
    if pd.notna(last_std):
        out["vwap_band_stretched"] = int(last_close > float(last_vwap) + 2.0 * float(last_std))
    return out


# --------------------------------------------------------------------------- #
# ATR regime (60-bar z-score on ATR / Close; cuts at ±0.43)
# --------------------------------------------------------------------------- #
def _atr_regime_features(daily_norm: pd.DataFrame) -> Dict[str, int]:
    """Two-of-three one-hot encoding (mid is the reference)."""
    out = {"atr_regime_low": 0, "atr_regime_high": 0}
    try:
        import talib
        atr = talib.ATR(
            daily_norm["high"].values, daily_norm["low"].values,
            daily_norm["close"].values, timeperiod=14,
        )
    except Exception as e:
        _warn(f"talib.ATR failed ({e}); atr_regime defaulting to mid.")
        return out

    atr_s = pd.Series(atr, index=daily_norm.index)
    atr_pct = atr_s / daily_norm["close"]
    mean = atr_pct.rolling(60, min_periods=20).mean()
    std = atr_pct.rolling(60, min_periods=20).std()
    z = (atr_pct - mean) / std
    last_z = z.iloc[-1]
    if pd.isna(last_z):
        return out  # default mid (both flags 0)

    if last_z < -0.43:
        out["atr_regime_low"] = 1
    elif last_z > 0.43:
        out["atr_regime_high"] = 1
    # else: mid (both flags 0)
    return out


# --------------------------------------------------------------------------- #
# Sector relative strength (20-day return vs sector ETF)
# --------------------------------------------------------------------------- #
def _sector_rs_feature(
    ticker: str, daily_norm: pd.DataFrame, cache_dir: Path,
) -> Dict[str, int]:
    out = {"sector_relative_strength_20d": 0}
    etf = SECTOR_ETF.get(ticker, "SPY")
    etf_df = _load_parquet_cached(etf, cache_dir)
    if etf_df is None:
        _warn(f"No cached parquet for sector ETF {etf} (ticker {ticker}); RS set to 0.")
        return out

    if len(daily_norm) < 21:
        return out

    tk_ret = float(daily_norm["close"].iloc[-1] / daily_norm["close"].iloc[-21] - 1)
    # Align ETF data to the ticker's last date (forward-fill across non-overlap)
    last_date = daily_norm.index[-1]
    if last_date.tz is not None:
        last_date = last_date.tz_localize(None)
    etf_close = etf_df["Close"]
    etf_at_last = etf_close.reindex([last_date], method="ffill").iloc[0]
    etf_window_start = last_date - pd.Timedelta(days=35)  # buffer for non-trading days
    etf_in_window = etf_close.loc[etf_window_start:last_date]
    if len(etf_in_window) < 20:
        return out
    etf_ret = float(etf_at_last / etf_in_window.iloc[-min(21, len(etf_in_window))] - 1)
    out["sector_relative_strength_20d"] = int(tk_ret > etf_ret)
    return out


# --------------------------------------------------------------------------- #
# Earnings proximity (yfinance, cached per ticker per process)
# --------------------------------------------------------------------------- #
def _earnings_feature(ticker: str, as_of: date) -> Dict[str, int]:
    out = {"earnings_within_5d": 0}
    if ticker not in _EARNINGS_CACHE:
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            ed = t.earnings_dates
            if ed is None or ed.empty:
                _EARNINGS_CACHE[ticker] = []
            else:
                _EARNINGS_CACHE[ticker] = sorted(set(
                    d.date() if hasattr(d, "date") else d for d in ed.index
                ))
        except Exception as e:
            _warn(f"yfinance earnings fetch failed for {ticker} ({e}); flag set to 0.")
            _EARNINGS_CACHE[ticker] = []

    earnings_list = _EARNINGS_CACHE[ticker]
    if not earnings_list:
        return out
    upper = as_of + timedelta(days=7)  # ~5 trading days
    for ed in earnings_list:
        if as_of <= ed <= upper:
            out["earnings_within_5d"] = 1
            break
    return out


# --------------------------------------------------------------------------- #
# Fibonacci retracement proximity
# --------------------------------------------------------------------------- #
def _fib_feature(daily_norm: pd.DataFrame) -> Dict[str, int]:
    """Fire if close is within 0.5% of 38.2/50/61.8 fib of last 60-day high→low."""
    out = {"fib_retracement_near": 0}
    if len(daily_norm) < 60:
        return out
    window = daily_norm.iloc[-60:]
    high60 = float(window["high"].max())
    low60 = float(window["low"].min())
    span = high60 - low60
    if span <= 0:
        return out
    close = float(daily_norm["close"].iloc[-1])
    levels = [high60 - span * 0.382, high60 - span * 0.500, high60 - span * 0.618]
    tol = close * 0.005
    if any(abs(close - lv) <= tol for lv in levels):
        out["fib_retracement_near"] = 1
    return out


# --------------------------------------------------------------------------- #
# Public — compute all 11 features at once
# --------------------------------------------------------------------------- #
def compute_live_features(
    ticker: str,
    daily_df: pd.DataFrame,
    as_of_date: Optional[date] = None,
    cache_dir: Optional[Path] = None,
) -> Dict[str, int]:
    """Return the 11 E+F brain v2 features for `ticker` evaluated at the
    LAST bar of `daily_df`. `as_of_date` controls only the earnings lookup;
    everything else uses the bars in `daily_df` directly. `cache_dir`
    defaults to `results/cache/`."""
    cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    if as_of_date is None:
        last_idx_dt = daily_df.index[-1]
        as_of_date = (last_idx_dt.tz_localize(None) if last_idx_dt.tz is not None
                      else last_idx_dt).date()

    if daily_df is None or daily_df.empty:
        _warn(f"compute_live_features({ticker}): empty daily_df; all 11 features set to 0.")
        return {k: 0 for k in _ALL_KEYS}

    daily_norm = _normalize_ohlc(daily_df)

    feats: Dict[str, int] = {}
    feats.update(_smc_features(daily_norm))
    feats.update(_vwap_features(daily_norm))
    feats.update(_atr_regime_features(daily_norm))
    feats.update(_sector_rs_feature(ticker, daily_norm, cache_dir))
    feats.update(_earnings_feature(ticker, as_of_date))
    feats.update(_fib_feature(daily_norm))
    return feats


_ALL_KEYS = [
    "smc_order_block_bullish", "smc_fvg_bullish",
    "smc_bos_bullish", "smc_choch_bullish",
    "vwap_above", "vwap_band_stretched",
    "atr_regime_low", "atr_regime_high",
    "sector_relative_strength_20d",
    "earnings_within_5d", "fib_retracement_near",
]


# --------------------------------------------------------------------------- #
# VIX getter for the §9 guardrail
# --------------------------------------------------------------------------- #
def get_current_vix(
    as_of_date: Optional[date] = None,
    cache_dir: Optional[Path] = None,
) -> float:
    """Latest VIX daily close (or the close on/before `as_of_date`).
    Reads `results/cache/ohlc_^VIX.parquet`.

    Raises `VixDataUnavailable` (NOT returning None) when:
      - the parquet is missing entirely
      - the parquet exists but has no bar on/before the requested date

    The advisor catches this explicitly and surfaces it via
    `v2_skipped_reason='vix_unavailable'` rather than silently applying
    a default — VIX failures must stay visible (Amendment B)."""
    global _VIX_DF_CACHE
    cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    if _VIX_DF_CACHE is None:
        path = cache_dir / "ohlc_^VIX.parquet"
        if not path.exists():
            raise VixDataUnavailable(
                f"VIX cache missing at {path}. Run "
                "`scripts/ohlc_cache.prefetch_universe(['^VIX'], ...)` "
                "to populate it."
            )
        df = pd.read_parquet(path)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        _VIX_DF_CACHE = df

    if as_of_date is None:
        return float(_VIX_DF_CACHE["Close"].iloc[-1])

    cutoff = pd.Timestamp(as_of_date)
    sliced = _VIX_DF_CACHE[_VIX_DF_CACHE.index <= cutoff]
    if sliced.empty:
        raise VixDataUnavailable(
            f"No VIX bar in cache on or before {as_of_date.isoformat()}."
        )
    return float(sliced["Close"].iloc[-1])


# --------------------------------------------------------------------------- #
# Adapter — live FullAnalysis → trade-dict (consumed by features.extract_features)
# --------------------------------------------------------------------------- #
def analysis_to_trade_dict(
    analysis: Any,
    ticker: str,
    sample_date: str,
    extra_keys: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Adapt a live `FullAnalysis` (with sections->checks->CheckItem) to the
    trade-dict shape that `features.extract_features` consumes (which reads
    `indicators.<section>.passed_checks`). Merges `extra_keys` (the 11 E+F
    columns from `compute_live_features`) at the top level."""
    indicators: Dict[str, Dict[str, List[str]]] = {}
    for section_name, sr in (analysis.sections or {}).items():
        passed = [c.name for c in (sr.checks or []) if getattr(c, "passed", False)]
        indicators[section_name] = {"passed_checks": passed}
    out: Dict[str, Any] = {
        "ticker": ticker,
        "sample_date": sample_date,
        "indicators": indicators,
    }
    if extra_keys:
        out.update(extra_keys)
    return out


# --------------------------------------------------------------------------- #
# Per-(ticker, date) score cache (Amendment A)
# --------------------------------------------------------------------------- #
def _score_cache_path(ticker: str, as_of: date, cache_dir: Optional[Path] = None) -> Path:
    """Resolve the on-disk path for the per-(ticker, date) v2 cache file."""
    base = Path(cache_dir) if cache_dir else SCORE_CACHE_DIR
    safe = ticker.upper().replace("/", "_")
    return base / f"{safe}_{as_of.isoformat()}.json"


def load_score_cache(
    ticker: str,
    as_of: date,
    cache_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Return the cached v2 score record for `(ticker, as_of)`, or None
    if no cache file exists. Corrupted JSON returns None and logs a
    warning (next compute will overwrite the file).

    Increments `_SCORE_CACHE_STATS` and writes a single-line stderr
    breadcrumb so the S24 smoke test can count hit rate."""
    import json
    path = _score_cache_path(ticker, as_of, cache_dir)
    if not path.exists():
        _SCORE_CACHE_STATS["misses"] += 1
        print(f"[brain_v2_cache] MISS {ticker} {as_of.isoformat()}", file=sys.stderr)
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _SCORE_CACHE_STATS["hits"] += 1
        print(f"[brain_v2_cache] HIT  {ticker} {as_of.isoformat()}", file=sys.stderr)
        return data
    except Exception as e:
        _SCORE_CACHE_STATS["errors"] += 1
        _warn(f"score cache read failed for {path.name} ({e}); will recompute.")
        return None


def save_score_cache(
    record: Dict[str, Any],
    cache_dir: Optional[Path] = None,
) -> None:
    """Atomically write a v2 score record to the per-(ticker, date) cache.
    Schema: ticker, date, v2_score, v2_verdict, v2_source, v2_features,
    vix_at_compute, vix_guardrail_applied, computed_at."""
    import json
    ticker = record["ticker"]
    as_of = datetime.strptime(record["date"], "%Y-%m-%d").date()
    path = _score_cache_path(ticker, as_of, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, sort_keys=True)
    tmp.replace(path)
    _SCORE_CACHE_STATS["writes"] += 1
