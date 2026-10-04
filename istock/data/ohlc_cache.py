"""OHLC parquet cache for the live app and backtester.

Goal (user request #2): we look at the same tickers repeatedly, so we
store each ticker's daily history once in
`results/cache/ohlc_{ticker}.parquet` and, on later visits, fetch only
the missing recent days from yfinance and append them — never the whole
year again.

Public API
----------
get_or_update_daily(ticker, ...) -> pd.DataFrame   # primary live-app entry
get_cached_ohlc(ticker, start, end) -> pd.DataFrame
prefetch_universe(tickers, start, end, force_refresh=False) -> dict
resample_daily_to_weekly(daily_df) -> pd.DataFrame
"""

from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

# istock/data/ohlc_cache.py → parents: data → istock → ismail_personal
_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = _ROOT / "results" / "cache"

_BACKOFF_SCHEDULE: List[float] = [0.0, 5.0, 30.0, 120.0]
_INTER_DOWNLOAD_SLEEP = 0.3


def _cache_path(ticker: str) -> Path:
    safe = ticker.upper().replace("/", "_")
    return CACHE_DIR / f"ohlc_{safe}.parquet"


def _to_date(d: Union[str, date, datetime]) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return datetime.strptime(d, "%Y-%m-%d").date()


def _read_parquet(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        return df if not df.empty else None
    except Exception:
        return None


def _merge(existing: Optional[pd.DataFrame], fresh: pd.DataFrame) -> pd.DataFrame:
    """Concat existing + fresh, drop duplicate index dates (keep newest), sort."""
    if existing is None or existing.empty:
        return fresh.sort_index()
    try:
        combined = pd.concat([existing, fresh])
        combined = combined[~combined.index.duplicated(keep="last")]
        return combined.sort_index()
    except Exception:
        return fresh.sort_index()


# --------------------------------------------------------------------------- #
# Core fetch with retry/backoff
# --------------------------------------------------------------------------- #
def _download(ticker: str, start: date, end: date,
              min_bars: int = 5) -> Optional[pd.DataFrame]:
    """Daily bars over [start, end] (yfinance end is exclusive — we pad +2d).
    Returns the frame or None after the backoff schedule is exhausted.
    `min_bars` guards against silent rate-limit empties; pass a low value
    for small incremental top-ups."""
    import yfinance as yf

    end_arg = (end + timedelta(days=2)).isoformat()
    start_arg = start.isoformat()

    for attempt, wait in enumerate(_BACKOFF_SCHEDULE, start=1):
        if wait > 0:
            print(f"  [retry] {ticker} attempt {attempt} after {wait:.0f}s...",
                  file=sys.stderr)
            time.sleep(wait)
        try:
            df = yf.Ticker(ticker).history(
                start=start_arg, end=end_arg, interval="1d",
                auto_adjust=False, prepost=False,
            )
        except Exception as e:
            print(f"  [warn] {ticker} attempt {attempt} raised: {e}", file=sys.stderr)
            df = None
        if df is not None and not df.empty and len(df) >= min_bars:
            return df
    return None


# --------------------------------------------------------------------------- #
# Primary live-app entry: cache-first, incremental top-up
# --------------------------------------------------------------------------- #
def get_or_update_daily(
    ticker: str,
    min_history_days: int = 420,
    force_refresh: bool = False,
) -> Optional[pd.DataFrame]:
    """Return daily OHLC for `ticker`, served from cache and topped-up with
    only the missing recent days.

    - No cache (or force_refresh) → full download of the last
      `min_history_days`, persist, return.
    - Cache already includes today's bar → return cached, zero network.
    - Cache stale → download only the tail since the last cached bar
      (with a small overlap so the retry's min-bars guard is satisfied),
      merge, persist, return.

    Returns None only if there is no cache AND the network fetch fails.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(ticker)
    today = datetime.now().date()

    existing = None if force_refresh else _read_parquet(path)

    if existing is None:
        df = _download(ticker, today - timedelta(days=min_history_days), today)
        if df is None:
            return None
        try:
            df.to_parquet(path)
        except Exception as e:
            print(f"  [warn] {ticker}: parquet write failed: {e}", file=sys.stderr)
        return df

    last = existing.index[-1].date()
    # Fresh enough: last bar is today (or the market simply hasn't produced a
    # newer bar yet). Serve from disk with no network call.
    if last >= today:
        return existing

    # Incremental: fetch from a week before the last cached bar (guarantees
    # overlap + >=5 bars for the retry guard), merge, persist.
    tail_start = last - timedelta(days=7)
    fresh = _download(ticker, tail_start, today, min_bars=1)
    if fresh is None:
        # Network failed — stale cache beats nothing for a repeat-view app.
        return existing
    merged = _merge(existing, fresh)
    try:
        merged.to_parquet(path)
    except Exception as e:
        print(f"  [warn] {ticker}: parquet write failed: {e}", file=sys.stderr)
    return merged


# --------------------------------------------------------------------------- #
# Read sliced frame (no network)
# --------------------------------------------------------------------------- #
def get_cached_ohlc(
    ticker: str,
    start_date: Optional[Union[str, date, datetime]] = None,
    end_date: Optional[Union[str, date, datetime]] = None,
) -> pd.DataFrame:
    """Read parquet for `ticker` and slice to [start_date, end_date] inclusive.
    Raises FileNotFoundError if the cache file is missing."""
    path = _cache_path(ticker)
    if not path.exists():
        raise FileNotFoundError(
            f"No cached OHLC for {ticker} at {path}. Call get_or_update_daily() first."
        )
    df = pd.read_parquet(path)
    if df.empty:
        return df
    if start_date is not None:
        ts = pd.Timestamp(_to_date(start_date))
        if df.index.tz is not None:
            ts = ts.tz_localize(df.index.tz)
        df = df[df.index >= ts]
    if end_date is not None:
        ts = pd.Timestamp(_to_date(end_date))
        if df.index.tz is not None:
            ts = ts.tz_localize(df.index.tz)
        df = df[df.index <= ts]
    return df


# --------------------------------------------------------------------------- #
# Bulk pre-fetch (backtester / warm-up)
# --------------------------------------------------------------------------- #
def prefetch_universe(
    tickers: List[str],
    start: Union[str, date, datetime],
    end: Union[str, date, datetime],
    force_refresh: bool = False,
) -> Dict[str, str]:
    """Pre-fetch/merge daily OHLC for each ticker covering [start, end].
    Returns a per-ticker status dict: 'cached' | 'downloaded' | 'failed'."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    start_d, end_d = _to_date(start), _to_date(end)
    status: Dict[str, str] = {}
    for tk in tickers:
        path = _cache_path(tk)
        existing = None if force_refresh else _read_parquet(path)
        if existing is not None:
            first, last = existing.index[0].date(), existing.index[-1].date()
            if first <= start_d and (end_d - last).days <= 5:
                status[tk] = "cached"
                continue
        df = _download(tk, start_d, end_d)
        if df is None:
            status[tk] = "failed"
            continue
        merged = _merge(existing, df)
        try:
            merged.to_parquet(path)
        except Exception as e:
            print(f"  [warn] {tk}: parquet write failed: {e}", file=sys.stderr)
            status[tk] = "failed"
            continue
        print(f"  Cached {tk} ({len(merged)} bars, "
              f"{merged.index[0].date()} -> {merged.index[-1].date()})")
        status[tk] = "downloaded"
        time.sleep(_INTER_DOWNLOAD_SLEEP)
    return status


def resample_daily_to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Build a weekly OHLCV frame from a daily one (W-FRI buckets)."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    agg = {"Open": "first", "High": "max", "Low": "min",
           "Close": "last", "Volume": "sum"}
    cols = {k: v for k, v in agg.items() if k in df.columns}
    return df.resample("W-FRI").agg(cols).dropna(how="all")


# --------------------------------------------------------------------------- #
# Backtest support: serve yfinance reads from the parquet cache
# --------------------------------------------------------------------------- #
import contextlib
from typing import Any


def _slice_by_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Honor yfinance's period= semantics from a cached daily frame."""
    if df.empty:
        return df
    period = (period or "").lower()
    last = df.index[-1]
    offsets = {"1y": pd.DateOffset(years=1), "2y": pd.DateOffset(years=2),
               "5y": pd.DateOffset(years=5), "6mo": pd.DateOffset(months=6),
               "3mo": pd.DateOffset(months=3), "1mo": pd.DateOffset(months=1)}
    off = offsets.get(period)
    if off is None:
        return df
    return df[df.index >= last - off]


@contextlib.contextmanager
def monkey_patch_yfinance(known_tickers: List[str]):
    """Replace `yf.Ticker.history` and `.info` with cache-backed shims for the
    duration of the context. Lets DataEngine.fetch_all run thousands of
    point-in-time analyses without hitting the network.

    - history(interval='1d')  → slice cached daily frame
    - history(interval='1wk') → resample cached daily to weekly
    - other intervals / unknown tickers → real call
    - .info → memoized per ticker (at most ONE live call per ticker per run)
    """
    import yfinance as yf

    known = {t.upper() for t in known_tickers}
    original_history = yf.Ticker.history
    original_info = yf.Ticker.info
    info_cache: Dict[str, Dict[str, Any]] = {}

    def patched_history(self, *args, **kwargs):
        sym = (getattr(self, "ticker", "") or "").upper()
        interval = kwargs.get("interval", "1d")
        if sym not in known or interval not in ("1d", "1wk"):
            return original_history(self, *args, **kwargs)
        df = _read_parquet(_cache_path(sym))
        if df is None:
            return original_history(self, *args, **kwargs)
        start, end, period = kwargs.get("start"), kwargs.get("end"), kwargs.get("period")
        if start:
            ts = pd.Timestamp(start)
            if df.index.tz is not None and ts.tz is None:
                ts = ts.tz_localize(df.index.tz)
            df = df[df.index >= ts]
        if end:
            ts = pd.Timestamp(end)
            if df.index.tz is not None and ts.tz is None:
                ts = ts.tz_localize(df.index.tz)
            df = df[df.index < ts]   # yfinance end is exclusive
        if period and not start and not end:
            df = _slice_by_period(df, period)
        if interval == "1wk" and not df.empty:
            df = resample_daily_to_weekly(df)
        return df

    class _CachedInfo:
        def __get__(self, obj, objtype=None):
            if obj is None:
                return self
            sym = (getattr(obj, "ticker", "") or "").upper()
            if sym in info_cache:
                return info_cache[sym]
            try:
                live = original_info.fget(obj) if hasattr(original_info, "fget") else {}
            except Exception:
                live = {}
            info_cache[sym] = live or {}
            return info_cache[sym]

    yf.Ticker.history = patched_history
    try:
        yf.Ticker.info = _CachedInfo()  # type: ignore[assignment]
    except Exception:
        pass
    try:
        yield
    finally:
        yf.Ticker.history = original_history
        try:
            yf.Ticker.info = original_info  # type: ignore[assignment]
        except Exception:
            pass
