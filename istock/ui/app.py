"""
ui.app - New Streamlit dashboard (Session 3).

Page 1 (Home) is fully implemented. Pages 2 & 3 are placeholders that
will be built in follow-up sessions. Legacy ui/dashboard.py is
intentionally untouched and still available as a reference.

Run:
    streamlit run ui/app.py      # from project root
    streamlit run app.py         # via the root shim
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# Project root on sys.path (so `from config import ...` works when Streamlit
# launches this file directly).
# --------------------------------------------------------------------------- #
_ROOT = Path(__file__).resolve().parent.parent.parent  # ismail_personal/
_LEGACY_ROOT = _ROOT / "ismail_p"  # config.py, results/, etc. still live here
for _p in [str(_ROOT), str(_LEGACY_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd
import streamlit as st

from config import (
    CURRENT_HOLDINGS,
    USER_PROFILE,
    THRESHOLDS,
    WATCHLIST,
    SCANNER_UNIVERSE_BASE,
)


# --------------------------------------------------------------------------- #
# Page config (must be the first Streamlit call)
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Ismail's Trading System",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Global style tweaks. Bump the expander header label font so the collapsible
# section titles (💰 Fundamentals — Score: 68/100, etc.) read at roughly the
# size of the old subheaders instead of the small default.
st.markdown(
    """
    <style>
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary span,
    [data-testid="stExpander"] details summary {
        font-size: 1.25rem !important;
        font-weight: 600 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Tracker — recommendation log persistence (Page 5 / "📓 Tracked Picks")
# Single-file JSON journal of every pick the user has tracked. The auto
# status-updater only sweeps when Page 5 is visited, not on every rerun.
# --------------------------------------------------------------------------- #

LOG_PATH = Path(_ROOT) / "results" / "recommendation_log.json"
TRACKER_EXPIRY_DAYS = 90
TRACKER_DUP_WINDOW_MIN = 60   # block re-track of same symbol inside 60 min


def _load_log() -> List[Dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    try:
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_log(rows: List[Dict[str, Any]]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOG_PATH.with_suffix(".json.tmp")
    # default=str catches numpy floats / pandas timestamps if any slip in.
    tmp.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    tmp.replace(LOG_PATH)   # atomic on POSIX + Windows


def _append_pick(pick: Dict[str, Any]) -> None:
    rows = _load_log()
    rows.append(pick)
    _save_log(rows)


def _update_pick(pick_id: str, **updates: Any) -> None:
    rows = _load_log()
    for r in rows:
        if r.get("id") == pick_id:
            r.update(updates)
            break
    _save_log(rows)


# --------------------------------------------------------------------------- #
# Editable user profile — persisted to results/profile.json
# (Session 11a). config.USER_PROFILE may still hold stale fields like
# `annual_income` / `investment_horizon_years`; we deliberately ignore
# those and only read/write the 4-key schema below.
# --------------------------------------------------------------------------- #

PROFILE_PATH = Path(_ROOT) / "results" / "profile.json"

DEFAULT_PROFILE: Dict[str, Any] = {
    "goal": "Build long-term wealth",
    "monthly_investment_inr": 25000,
    "risk_score": 8,           # 1-10
    "risk_category": "AGGRESSIVE",  # auto-derived from risk_score
}


def _risk_score_to_category(score: int) -> str:
    if score <= 3:
        return "CONSERVATIVE"
    if score <= 7:
        return "MODERATE"
    return "AGGRESSIVE"


def _load_profile() -> Dict[str, Any]:
    if PROFILE_PATH.exists():
        try:
            saved = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                return {**DEFAULT_PROFILE, **saved}
        except Exception:
            pass
    return dict(DEFAULT_PROFILE)


def _save_profile(profile: Dict[str, Any]) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROFILE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(profile, indent=2, default=str), encoding="utf-8")
    tmp.replace(PROFILE_PATH)


# --------------------------------------------------------------------------- #
# Editable holdings (Session 11b) — drop-in mirror of config.CURRENT_HOLDINGS
# schema (nested wrapper dicts with a per-holding `trades` list). The JSON
# file is a list of those wrapper dicts. When the file is absent,
# get_holdings() falls back to config.CURRENT_HOLDINGS so the prior
# "edit config.py" workflow keeps working untouched.
# --------------------------------------------------------------------------- #

HOLDINGS_PATH = Path(_ROOT) / "results" / "holdings.json"


def _load_holdings_json() -> Optional[List[Dict[str, Any]]]:
    if not HOLDINGS_PATH.exists():
        return None
    try:
        data = json.loads(HOLDINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return None


def _save_holdings_json(holdings: List[Dict[str, Any]]) -> None:
    HOLDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = HOLDINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(holdings, indent=2, default=str), encoding="utf-8")
    tmp.replace(HOLDINGS_PATH)


def get_holdings() -> List[Dict[str, Any]]:
    """Single source of truth for the UI. Returns persisted holdings if
    results/holdings.json exists, else config.CURRENT_HOLDINGS. Existing
    helpers (build_holdings_rows, render_holdings, compute_closed_trades,
    etc.) consume this transparently — they never see the underlying source."""
    loaded = _load_holdings_json()
    if loaded is not None:
        return loaded
    import config as _cfg
    return list(getattr(_cfg, "CURRENT_HOLDINGS", []) or [])


# --------------------------------------------------------------------------- #
# Currency display layer (Session 11a)
# Internal storage stays INR-denominated (build_holdings_rows /
# portfolio_totals / etc. all emit *_inr fields). The currency toggle on
# Home only changes the *display*, so storage round-trips are avoided.
# --------------------------------------------------------------------------- #

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_usd_inr() -> float:
    """Live USD→INR rate via yfinance (cached 1h). Falls back to 83.0
    if the lookup fails."""
    try:
        import yfinance as yf
        df = yf.Ticker("INR=X").history(period="5d")
        if not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass
    return 83.0


_INR_MARKETS = {"IN", "NSE", "BSE", "INDIA", "NS", "BO"}


def _is_inr_market(market: Optional[str]) -> bool:
    """True when a holding's market denominates trades in INR."""
    return str(market or "US").strip().upper() in _INR_MARKETS


def _current_currency() -> str:
    """Currency toggle, defaults to USD per spec. Page renderers set
    this in session_state at the top of render_home_page."""
    return st.session_state.get("display_currency", "USD")


def _md_dollars(text: str) -> str:
    """Escape $ for st.markdown. Streamlit treats a pair of $ as LaTeX math, so
    two dollar amounts in one block turn everything between them into garbage."""
    return text.replace("$", "\\$")


def _fmt_currency(amount_inr: Optional[float], currency: str,
                  fx: float, *, signed: bool = False) -> str:
    """Format an INR-denominated amount in the chosen display currency.
    Storage is always INR; this only formats. Use signed=True to force
    a leading +/- (handy for P&L). Returns "—" for None values."""
    if amount_inr is None:
        return "—"
    try:
        v = float(amount_inr)
    except (TypeError, ValueError):
        return "—"
    if currency == "USD" and fx > 0:
        usd = v / fx
        return f"${usd:+,.2f}" if signed else f"${usd:,.2f}"
    return f"₹{v:+,.0f}" if signed else f"₹{v:,.0f}"


# --------------------------------------------------------------------------- #
# Cached backend calls — Streamlit reruns this file on every widget click,
# so every expensive call must be cached. TTL=300s (5 min) is a good
# tradeoff between freshness and rate-limit pain from Yahoo.
# --------------------------------------------------------------------------- #

@st.cache_resource
def _get_advisor():
    """One TradeAdvisor instance for the whole session (heavy to construct)."""
    from istock.decision.advisor import TradeAdvisor
    return TradeAdvisor()


@st.cache_data(ttl=300, show_spinner=False)
def fetch_regime() -> Dict[str, Any]:
    """Current market regime as a plain dict (dataclass → dict for cache)."""
    from istock.decision.regime import get_current_regime
    reading = get_current_regime()
    return asdict(reading)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_live_quote(symbol: str) -> Optional[Dict[str, float]]:
    """Live price and previous close for a ticker. None on failure."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        hist = t.history(period="5d", interval="1d")
        if hist.empty:
            return None
        current = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
        return {
            "current_price": current,
            "previous_close": prev,
            "day_change_pct": (current - prev) / prev * 100 if prev else 0.0,
        }
    except Exception:
        return None


def _analysis_to_dict(result: Any) -> Dict[str, Any]:
    """FullAnalysis → cache-hashable dict. Shared by analyze_symbol and
    analyze_symbol_as_of so both helpers emit identical shape."""
    sections: Dict[str, Dict[str, Any]] = {}
    for key, sec in (result.sections or {}).items():
        sections[key] = {
            "name": sec.name,
            "score": float(sec.score),
            "summary": sec.summary,
            "checks": [
                {
                    "name": c.name,
                    "passed": bool(c.passed),
                    "detail": c.detail,
                    "weight": float(getattr(c, "weight", 1.0)),
                    "value": float(getattr(c, "value", 0.0) or 0.0),
                }
                for c in (sec.checks or [])
            ],
        }
    return {
        "symbol": result.symbol,
        "company_name": result.company_name,
        "current_price": result.current_price,
        "day_change_pct": result.day_change_pct,
        "verdict": result.verdict,
        "buy_score": result.buy_score,
        "sell_score": result.sell_score,
        "confidence": result.confidence,
        "setup_type": result.setup.setup_type if result.setup else "none",
        "entry": getattr(result.setup, "entry", 0.0) or 0.0,
        "stop_loss": getattr(result.setup, "stop_loss", 0.0) or 0.0,
        "targets": list(getattr(result.setup, "targets", []) or []),
        "risk_reward": getattr(result.setup, "risk_reward", 0.0) or 0.0,
        "sector": result.sector,
        "timestamp": result.timestamp,
        "sections": sections,
        "avoid_flags": list(result.avoid_flags or []),
        "key_observations": list(result.key_observations or []),
        # Brain v2 dual-verdict fields (S23b). v1_* always mirrors the
        # pre-v2 numbers; v2_* is populated whenever brain v2 ran.
        "v1_verdict": getattr(result, "v1_verdict", None),
        "v1_score": getattr(result, "v1_score", None),
        "v2_verdict": getattr(result, "v2_verdict", None),
        "v2_score": getattr(result, "v2_score", None),
        "v2_source": getattr(result, "v2_source", None),
        "v2_vix_guardrail_applied": getattr(result, "v2_vix_guardrail_applied", None),
        "v2_skipped_reason": getattr(result, "v2_skipped_reason", None),
    }


@st.cache_data(ttl=300, show_spinner=False)
def analyze_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """Run TradeAdvisor.analyze on a symbol. Returns a flat dict for the
    cache (the FullAnalysis dataclass itself isn't cleanly hashable).
    Session 5b: also emits `sections`, `avoid_flags`, and
    `key_observations` for the deep-dive reasoning panel."""
    try:
        advisor = _get_advisor()
        result = advisor.analyze(symbol)
        if result is None:
            return None
        return _analysis_to_dict(result)
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def analyze_symbol_as_of(symbol: str, as_of_date: str) -> Optional[Dict[str, Any]]:
    """Same return shape as analyze_symbol but for a past date. Cached
    longer (10 min) since past-date results don't drift with live
    quotes. `as_of_date` is the ISO string the cache keys on."""
    try:
        advisor = _get_advisor()
        result = advisor.analyze(symbol, as_of_date=as_of_date)
        if result is None:
            return None
        return _analysis_to_dict(result)
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def compute_sizing(symbol: str, portfolio_inr: float, cash_inr: float) -> Optional[Dict[str, Any]]:
    """Run the position sizer for a given symbol. Re-runs analyze to get a
    fresh FullAnalysis (cached analysis dict isn't usable directly).

    Gated off globally via config.ENABLE_POSITION_SIZING — returns None when
    disabled so every caller (picks + deep-dive) degrades gracefully."""
    try:
        from config import ENABLE_POSITION_SIZING
    except Exception:
        ENABLE_POSITION_SIZING = False
    if not ENABLE_POSITION_SIZING:
        return None
    try:
        advisor = _get_advisor()
        analysis = advisor.analyze(symbol)
        if analysis is None or analysis.setup.setup_type == "none":
            return None
        from istock.decision.position_sizer import size_position_from_analysis
        sizing = size_position_from_analysis(
            analysis=analysis,
            portfolio_value_inr=portfolio_inr,
            cash_available_inr=cash_inr,
            open_positions=[],
        )
        # Normalize method_results into a list of {method, shares, notional, used}.
        methods: List[Dict[str, Any]] = []
        raw_methods = getattr(sizing, "method_results", {}) or {}
        winning = sizing.winning_method or ""
        for method_name, info in raw_methods.items():
            if isinstance(info, dict):
                shares = info.get("shares") or info.get("size") or 0
                notional = info.get("notional") or info.get("value") or 0
                note = info.get("note") or info.get("reason") or ""
            else:
                shares, notional, note = info, 0, ""
            methods.append({
                "method": str(method_name),
                "shares": float(shares or 0),
                "notional": float(notional or 0),
                "used": str(method_name) == winning,
                "note": str(note),
            })
        return {
            "shares": int(sizing.shares),
            "approved": sizing.approved,
            "position_value_inr": sizing.position_value_inr,
            "position_value_native": float(sizing.position_value_native),
            "risk_amount_inr": sizing.risk_amount_inr,
            "risk_pct_of_portfolio": sizing.risk_pct_of_portfolio,
            "rejection_reason": sizing.rejection_reason or "",
            "winning_method": sizing.winning_method or "",
            # Session 5b additions:
            "entry_price": float(sizing.entry_price),
            "stop_loss": float(sizing.stop_loss),
            "currency": sizing.currency,
            "conviction_multiplier": float(sizing.conviction_multiplier),
            "volatility_multiplier": float(sizing.volatility_multiplier),
            "heat_multiplier": float(sizing.heat_multiplier),
            "reasoning": list(sizing.reasoning or []),
            "warnings": list(sizing.warnings or []),
            "method_results": methods,
        }
    except Exception:
        return None


# Yahoo Finance has hard-coded caps per interval — these are the largest
# lookback windows that reliably return data without being truncated.
# Daily window extended to 5y so MAX-button users see real history.
INTERVAL_PERIOD_MAP: Dict[str, str] = {
    "1d":  "5y",     # full history; default *visible* window narrows to 2y
    "1h":  "1mo",    # ~22 trading days of hourly bars — plenty for context
    "15m": "1mo",
    "5m":  "1mo",
    "2m":  "5d",     # yfinance's tightest valid period for 2m
}

# MA windows scale with interval so "MA200" on 2-minute candles doesn't
# devolve into a straight line over 10 months of bars.
INTERVAL_MA_WINDOWS: Dict[str, List[int]] = {
    "1d":  [20, 50, 200],
    "1h":  [20, 50, 100],
    "15m": [20, 50],
    "5m":  [20, 50],
    "2m":  [20, 50],
}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_ohlc(symbol: str, interval: str = "1d",
               cutoff: Optional[str] = None) -> Optional[Dict[str, List[Any]]]:
    """Fetch OHLC for the deep-dive candlestick.

    Cache key includes symbol, interval, AND cutoff, so changing the
    "as of" date or timeframe triggers a fresh fetch.  When `cutoff`
    is provided (ISO date), bars after that day are dropped — used
    by Page 3's date picker so charts don't show "future" bars.
    Returns a dict-of-lists (Plotly + pandas friendly) or None on
    failure."""
    period = INTERVAL_PERIOD_MAP.get(interval, "5y")
    try:
        import yfinance as yf
        # Pre/post market data only matters for intraday — daily already
        # bakes the regular session close. yfinance returns extra rows
        # outside RTH when prepost=True.
        prepost = interval != "1d"
        df = yf.Ticker(symbol).history(
            period=period, interval=interval, prepost=prepost,
        )
        if df is None or df.empty or len(df) < 5:
            return None
        # Drop bars after the cutoff date (point-in-time view).
        if cutoff:
            try:
                cutoff_ts = pd.to_datetime(cutoff)
                if df.index.tz is not None and cutoff_ts.tz is None:
                    cutoff_ts = cutoff_ts.tz_localize(df.index.tz)
                df = df[df.index <= cutoff_ts]
                if df.empty or len(df) < 5:
                    return None
            except Exception:
                pass
        df = df.reset_index()
        # Datetime column name varies between interval='1d' (Date) and
        # intraday intervals (Datetime). Normalize both to a single string
        # column so the downstream renderer doesn't care which shape came
        # back.
        timestamp_fmt = "%Y-%m-%d" if interval == "1d" else "%Y-%m-%d %H:%M"
        if "Datetime" in df.columns:
            df["Date"] = pd.to_datetime(df["Datetime"]).dt.strftime(timestamp_fmt)
            df = df.drop(columns=["Datetime"])
        elif "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime(timestamp_fmt)
        return df[["Date", "Open", "High", "Low", "Close", "Volume"]].to_dict("list")
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_week_history(symbol: str) -> Optional[Dict[str, float]]:
    """Fetch ~7 trading days of closes so we can compute a 1-week % change.
    Returns None on failure."""
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(period="10d", interval="1d")
        if hist.empty or len(hist) < 2:
            return None
        latest = float(hist["Close"].iloc[-1])
        # "5 trading days ago" — fall back to earliest bar if shorter.
        five_back_idx = -6 if len(hist) >= 6 else 0
        five_back = float(hist["Close"].iloc[five_back_idx])
        pct = (latest - five_back) / five_back * 100 if five_back else 0.0
        return {"latest": latest, "five_back": five_back, "week_pct": pct}
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_sector(symbol: str) -> str:
    """Look up a ticker's sector via yfinance. Cached for an hour since it
    rarely changes. Returns 'Unknown' if missing or on failure."""
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        sector = info.get("sector") or info.get("category") or "Unknown"
        return sector if sector else "Unknown"
    except Exception:
        return "Unknown"


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_market_cap(symbol: str) -> Optional[float]:
    """Market cap in USD, cached for a day (rarely meaningful intra-day)."""
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        mc = info.get("marketCap")
        return float(mc) if mc is not None else None
    except Exception:
        return None


# Cap-band breakpoints in USD billions. Bands are widely-used industry
# conventions; tweak only if the user explicitly asks.
_CAP_BANDS = [
    ("Mega Cap (>$200B)",     200.0),
    ("Large Cap ($10-200B)",   10.0),
    ("Mid Cap ($2-10B)",        2.0),
    ("Small Cap ($300M-2B)",    0.3),
    ("Micro Cap (<$300M)",      0.0),
]


def _cap_category(market_cap_usd: Optional[float]) -> str:
    """Bucket a market cap (USD) into one of the standard cap bands."""
    if market_cap_usd is None:
        return "Unknown"
    mcap_b = market_cap_usd / 1e9
    for label, threshold in _CAP_BANDS:
        if mcap_b >= threshold:
            return label
    return "Unknown"


@st.cache_data(ttl=300, show_spinner=False)
def load_backtest_results() -> Optional[Dict[str, Any]]:
    """Read results/backtest_results.json if it exists. Returns None otherwise.
    Shape matches the backtester's output (strategy name → metrics dict)."""
    import json
    path = _ROOT / "results" / "backtest_results.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Page 3 — Stock Deep-Dive fetchers (cached, dict-returning)
# --------------------------------------------------------------------------- #

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fundamentals(symbol: str) -> Optional[Dict[str, Any]]:
    """Run FundamentalAnalyzer end-to-end. Returns the analyzer's dict,
    or None on failure. Cached for 5 minutes. The analyzer already returns
    a plain-dict tree so no conversion needed."""
    try:
        # Import core.trade_advisor FIRST to avoid the known data_engine
        # circular-init pattern (Session 2.5 note).
        from istock.decision.advisor import TradeAdvisor  # noqa: F401
        from istock.data.fetcher import DataFetcher
        from istock.features.analyzers.fundamental import FundamentalAnalyzer
        stock_data = DataFetcher().get_stock_data(symbol)
        if not stock_data:
            return None
        return FundamentalAnalyzer().analyze(stock_data)
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_technicals(symbol: str) -> Optional[Dict[str, Any]]:
    """Run TechnicalAnalyzer end-to-end. Returns the analyzer's dict,
    or None on failure."""
    try:
        from istock.decision.advisor import TradeAdvisor  # noqa: F401
        from istock.data.fetcher import DataFetcher
        from istock.features.analyzers.technical import TechnicalAnalyzer
        stock_data = DataFetcher().get_stock_data(symbol)
        if not stock_data:
            return None
        return TechnicalAnalyzer().analyze(stock_data)
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_market_context(symbol: str,
                         cutoff: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Run MarketContextAnalyzer end-to-end. It needs a full DataEngine,
    not the DataFetcher dict, so it's more expensive. Returns SectionResult
    flattened to a plain dict for cache-hashability. When `cutoff` is
    provided (ISO date), DataEngine slices its frames to bars on/before
    that day so the market context reflects the point-in-time view."""
    try:
        from istock.decision.advisor import TradeAdvisor  # noqa: F401
        from istock.data.engine import DataEngine
        from istock.features.analyzers.market_context import MarketContextAnalyzer
        engine = DataEngine(symbol)
        try:
            ok = engine.fetch_all(as_of_date=cutoff)
        except ValueError:
            return None
        if not ok:
            return None
        result = MarketContextAnalyzer(engine).analyze()
        return {
            "name": result.name,
            "score": result.score,
            "summary": result.summary,
            "checks": [
                {"name": c.name, "passed": bool(c.passed), "detail": c.detail}
                for c in result.checks
            ],
        }
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Holdings math (pure, no network)
# --------------------------------------------------------------------------- #

def _aggregate_trades(trades: List[Dict[str, Any]]) -> Dict[str, float]:
    """Fold a trades list into {qty, total_cost_native, avg_buy_price_native,
    currency}. Assumes BUY adds, SELL subtracts."""
    qty = 0.0
    invested = 0.0
    realized = 0.0      # profit already locked in by sells (average-cost basis)
    bought_cash = 0.0   # all money ever put in
    currency = "USD"
    for t in trades:
        action = t.get("action", "BUY").upper()
        q = float(t.get("qty", 0))
        price = t.get("price_usd") if "price_usd" in t else t.get("price_inr")
        if price is None:
            continue
        if "price_inr" in t:
            currency = "INR"
        if action == "BUY":
            qty += q
            invested += q * float(price)
            bought_cash += q * float(price)
        elif action == "SELL":
            # Reduce cost basis proportionally (simplest FIFO-free approximation)
            if qty > 0:
                avg = invested / qty
                sold = min(q, qty)
                realized += sold * (float(price) - avg)
                invested -= avg * sold
                qty -= sold
    return {
        "qty": qty,
        "invested_native": invested,
        "avg_buy_native": invested / qty if qty > 0 else 0.0,
        "realized_native": realized,
        "bought_native": bought_cash,
        "currency": currency,
    }


def _to_inr(amount: float, currency: str) -> float:
    # Use the SAME live rate as _fmt_currency so USD→INR→USD round-trips exactly.
    # (Previously used a static 85.5 here vs the live rate for display, which
    # distorted every USD figure and broke qty×avg-buy = invested.)
    if currency == "INR":
        return amount
    return amount * fetch_usd_inr()


def build_holdings_rows(with_score: bool = True) -> List[Dict[str, Any]]:
    """Compute holdings table rows with live prices (+ optional quality scores).
    Skips any ticker whose quote fails rather than failing the whole page.
    `with_score=False` skips the heavy per-holding Brain-v2 analysis — used on the
    Home page so it opens fast (P&L needs only the live quote; the quality score
    lives on the Deep-Dive)."""
    rows: List[Dict[str, Any]] = []
    for h in get_holdings():
        symbol = h["symbol"]
        agg = _aggregate_trades(h.get("trades", []))
        if agg["qty"] <= 0:
            # Fully sold: nothing to price, but its realized P&L still counts
            # toward the portfolio totals. Not shown in the holdings table.
            rows.append({
                "symbol": symbol, "type": h.get("type", "Stock"), "status": "closed",
                "realized_inr": _to_inr(agg["realized_native"], agg["currency"]),
                "bought_inr": _to_inr(agg["bought_native"], agg["currency"]),
            })
            continue
        quote = fetch_live_quote(symbol)
        if quote is None:
            rows.append({
                "symbol": symbol, "type": h.get("type", "Stock"),
                "status": "⚠️ quote unavailable",
            })
            continue
        # Guard: the live quote is in the ticker's exchange currency (INR for an
        # Indian market, USD otherwise). If the stored trades were recorded in a
        # DIFFERENT currency, invested and current would be summed in mismatched
        # units → nonsense P&L. Flag it instead of silently miscomputing.
        quote_currency = "INR" if _is_inr_market(h.get("market")) else "USD"
        if quote_currency != agg["currency"]:
            rows.append({
                "symbol": symbol, "type": h.get("type", "Stock"),
                "status": f"⚠️ currency mismatch ({agg['currency']} cost vs "
                          f"{quote_currency} quote) — re-check this holding",
            })
            continue
        analysis = analyze_symbol(symbol) if with_score else None
        current_native = quote["current_price"]
        invested_inr = _to_inr(agg["invested_native"], agg["currency"])
        current_inr = _to_inr(current_native * agg["qty"], agg["currency"])
        pnl_inr = current_inr - invested_inr
        pnl_pct = (pnl_inr / invested_inr * 100) if invested_inr else 0.0
        score = analysis["buy_score"] if analysis else None
        if score is None:
            rec = "—"
        else:
            from istock.model.scorer import quality_band_from_score
            rec = quality_band_from_score(score)   # non-directional quality band
        rows.append({
            "symbol": symbol,
            "type": h.get("type", "Stock"),
            "qty": agg["qty"],
            "avg_buy_native": agg["avg_buy_native"],
            "current_native": current_native,
            "currency": agg["currency"],
            "day_change_pct": quote["day_change_pct"],
            "invested_inr": invested_inr,
            "current_inr": current_inr,
            "pnl_inr": pnl_inr,
            "realized_inr": _to_inr(agg["realized_native"], agg["currency"]),
            "bought_inr": _to_inr(agg["bought_native"], agg["currency"]),
            "pnl_pct": pnl_pct,
            "score": score,
            "recommendation": rec,
            "status": "ok",
        })
    return rows


def portfolio_totals(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """Sum the holdings rows into portfolio-wide numbers."""
    current = sum(r.get("current_inr", 0) for r in rows if r.get("status") == "ok")
    invested = sum(r.get("invested_inr", 0) for r in rows if r.get("status") == "ok")
    pnl = current - invested
    pnl_pct = (pnl / invested * 100) if invested else 0.0
    open_positions = sum(1 for r in rows if r.get("status") == "ok")
    counted = [r for r in rows if r.get("status") in ("ok", "closed")]
    realized = sum(r.get("realized_inr", 0) for r in counted)
    bought = sum(r.get("bought_inr", 0) for r in counted)
    total_pnl = pnl + realized
    return {
        "current_inr": current, "invested_inr": invested,
        "pnl_inr": pnl, "pnl_pct": pnl_pct, "open_positions": open_positions,
        "realized_inr": realized, "bought_inr": bought,
        "total_pnl_inr": total_pnl,
        "total_pnl_pct": (total_pnl / bought * 100) if bought else 0.0,
    }


# --------------------------------------------------------------------------- #
# Watchlist → opportunities
# --------------------------------------------------------------------------- #

DEFAULT_WATCH = ["VOO", "QQQ", "SCHD", "VUG", "VTI", "AAPL", "MSFT", "NVDA"]


# Scanner universe lives in config.py — see SCANNER_UNIVERSE_BASE import above.
# Don't duplicate the list here; edit config.py to add/remove tickers.


def build_watchlist() -> List[str]:
    """Flatten the config WATCHLIST dict, fall back to DEFAULT_WATCH."""
    if isinstance(WATCHLIST, dict):
        flat: List[str] = []
        for v in WATCHLIST.values():
            if isinstance(v, list):
                flat.extend(v)
        return list(dict.fromkeys(flat)) or DEFAULT_WATCH
    if isinstance(WATCHLIST, list):
        return list(WATCHLIST) or DEFAULT_WATCH
    return DEFAULT_WATCH


SCANNER_LIMIT = 10   # cap the scan to the first N names to keep it fast


def build_scanner_universe() -> List[str]:
    """Merge SCANNER_UNIVERSE_BASE with config.WATCHLIST + session-only
    user addons (st.session_state['custom_universe_addons']),
    deduplicating while preserving order. Capped to SCANNER_LIMIT for speed."""
    merged: List[str] = list(SCANNER_UNIVERSE_BASE)
    watch = build_watchlist()
    for t in watch:
        if t not in merged:
            merged.append(t)
    # Session-only addons — populated by the "Add tickers" input on the
    # Picks → Opportunities tab. Wrapped in hasattr because this helper
    # is also called from cached scan functions where st.session_state
    # is still available but might be empty on cold start.
    try:
        addons = st.session_state.get("custom_universe_addons", []) or []
    except Exception:
        addons = []
    for t in addons:
        if t and t not in merged:
            merged.append(t)
    return merged[:SCANNER_LIMIT]


@st.cache_data(ttl=1800, show_spinner=False)
def run_full_scan(universe: tuple[str, ...]) -> List[Dict[str, Any]]:
    """Run analyze_symbol across the whole scanner universe. Cached for
    30 min as a unit, but each underlying analyze_symbol call is itself
    cached at 5 min, so re-scans on partial TTL expiry are cheap."""
    results: List[Dict[str, Any]] = []
    for symbol in universe:
        try:
            analysis = analyze_symbol(symbol)
        except Exception:
            continue
        if not analysis:
            continue
        results.append({"symbol": symbol, "analysis": analysis})
    return results


def _verdict_category(raw: str) -> Optional[str]:
    """Map raw verdict text to ('BUY' | 'LEAN BUY' | None). Checked
    in this order because 'LEAN BUY' contains 'BUY' as a substring."""
    v = (raw or "").upper()
    if "LEAN BUY" in v:
        return "LEAN BUY"
    if "BUY" in v:  # 'BUY' or 'STRONG BUY'
        return "BUY"
    return None


def _top_reasons(analysis: Dict[str, Any], n: int = 3) -> List[tuple[str, str]]:
    """Pull the top-N passed checks across all sections, sorted by weight
    descending. Returns [(check_name, detail), ...]."""
    passed: List[tuple[float, str, str]] = []
    for sec in (analysis.get("sections") or {}).values():
        for c in (sec.get("checks") or []):
            if c.get("passed"):
                weight = float(c.get("weight", 1.0) or 1.0)
                passed.append((weight, c.get("name", ""), c.get("detail", "")))
    passed.sort(key=lambda t: -t[0])
    return [(name, detail) for _w, name, detail in passed[:n]]


@st.cache_data(ttl=300, show_spinner=False)
def scan_opportunities(symbols: tuple[str, ...], portfolio_inr: float,
                       cash_inr: float) -> List[Dict[str, Any]]:
    """Analyze a batch of symbols and keep the top BUY-ish candidates."""
    results: List[Dict[str, Any]] = []
    for sym in symbols:
        a = analyze_symbol(sym)
        if not a:
            continue
        verdict = (a.get("verdict") or "").upper()
        if not any(tag in verdict for tag in ("BUY",)):
            continue
        sizing = compute_sizing(sym, portfolio_inr, cash_inr)
        results.append({
            "symbol": a["symbol"],
            "price": a["current_price"],
            "score": a["buy_score"],
            "setup": a["setup_type"],
            "verdict": a["verdict"],
            "rr": a["risk_reward"],
            "shares": (sizing or {}).get("shares", 0),
            "approved": (sizing or {}).get("approved", False),
        })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:5]


# --------------------------------------------------------------------------- #
# Regime visual helpers
# --------------------------------------------------------------------------- #

REGIME_COLORS = {
    "RISK_ON_TREND": "#16a34a",  # green
    "RISK_ON_CHOP":  "#eab308",  # yellow
    "TRANSITION":    "#f97316",  # orange
    "RISK_OFF":      "#dc2626",  # red
    "RECOVERY":      "#2563eb",  # blue
}

REGIME_BLURBS = {
    "RISK_ON_TREND": "Market is in a steady uptrend — size up good setups.",
    "RISK_ON_CHOP":  "Sideways-bullish — take setups, stay selective.",
    "TRANSITION":    "Mixed signals — reduce size, favor higher-conviction trades.",
    "RISK_OFF":      "Defensive posture — cut size or sit out until signals recover.",
    "RECOVERY":      "Early recovery from a downturn — scaling in carefully.",
}


# --------------------------------------------------------------------------- #
# Section renderers
# --------------------------------------------------------------------------- #

def render_top_metrics(totals: Dict[str, float], currency: str, fx: float):
    """Currency-aware 4-metric row used at the top of Home. If there are
    no priced positions we still render the row but the money cells
    say "—" so the layout stays consistent."""
    has_data = totals.get("open_positions", 0) > 0 and totals.get("current_inr", 0) > 0
    c1, c2, c3, c4, c5 = st.columns(5)
    if not has_data:
        for c, label in zip((c1, c2, c3, c4, c5), ("Money Put In", "Current Value",
                            "Unrealized P&L", "Realized P&L", "Total P&L")):
            c.metric(label, "—")
        return
    c1.metric("Money Put In", _fmt_currency(totals["bought_inr"], currency, fx),
              help="Every buy, added up.")
    c2.metric("Current Value", _fmt_currency(totals["current_inr"], currency, fx),
              help="What the shares you still hold are worth now.")
    c3.metric("Unrealized P&L", _fmt_currency(totals["pnl_inr"], currency, fx, signed=True),
              delta=f"{totals['pnl_pct']:+.2f}%",
              help="Gain or loss on shares you still hold, vs what they cost.")
    c4.metric("Realized P&L", _fmt_currency(totals["realized_inr"], currency, fx, signed=True),
              help="Profit or loss already locked in by selling.")
    c5.metric("Total P&L", _fmt_currency(totals["total_pnl_inr"], currency, fx, signed=True),
              delta=f"{totals['total_pnl_pct']:+.2f}%",
              help="Unrealized + realized, as a % of money put in.")


def render_regime():
    st.subheader("🌊 Market Regime")
    try:
        regime = fetch_regime()
    except Exception as exc:
        st.warning(f"⚠️ Regime data temporarily unavailable — {exc}")
        return

    label = regime["regime"]
    color = REGIME_COLORS.get(label, "#64748b")
    blurb = REGIME_BLURBS.get(label, "")
    mult = regime["regime_multiplier"]
    confidence = regime["confidence"]

    # Coloured banner card (inline HTML — no external CSS needed).
    st.markdown(
        f"""
        <div style="padding:18px 24px;border-radius:10px;
                    background:{color}1A;border-left:6px solid {color};">
          <div style="font-size:28px;font-weight:700;color:{color};">{label}</div>
          <div style="font-size:16px;margin-top:4px;color:#334155;">{blurb}</div>
          <div style="font-size:14px;margin-top:8px;color:#475569;">
            Position multiplier: <b>{mult:.2f}x</b>
            &nbsp;·&nbsp; Confidence: <b>{confidence}</b>
            &nbsp;·&nbsp; Weighted score: <b>{regime['weighted_score']:+.2f}</b>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("🔬 Signal readings"):
        signals = regime.get("signals", {}) or {}
        scores = regime.get("signal_scores", {}) or {}
        if signals:
            rows = [
                {"signal": k, "value": v, "score": scores.get(k, 0)}
                for k, v in signals.items()
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.caption("No signal detail available.")
        reasoning = regime.get("reasoning", []) or []
        if reasoning:
            st.markdown("**Why this regime:**")
            for r in reasoning:
                st.markdown(f"- {r}")
        warnings = regime.get("warnings", []) or []
        if warnings:
            st.markdown("**Warnings:**")
            for w in warnings:
                st.markdown(f"- ⚠️ {w}")


# --------------------------------------------------------------------------- #
# Holdings CRUD (Session 11b) — flat-row editor + add form, denormalized to
# the nested config schema on save. New symbols default to {type:"Stock",
# market:"US", notes:""}; existing symbols preserve their wrapper metadata.
# --------------------------------------------------------------------------- #

def _flatten_holdings_to_rows(holdings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per trade: {Symbol, Action, Quantity, Price, Date}. Used
    to feed st.data_editor and to merge the Add-form's new entry."""
    rows: List[Dict[str, Any]] = []
    for h in holdings:
        sym = h.get("symbol", "")
        for t in h.get("trades", []) or []:
            d_raw = t.get("date")
            try:
                d = date.fromisoformat(str(d_raw)) if d_raw else date.today()
            except ValueError:
                d = date.today()
            price = t.get("price_usd")
            if price is None:
                price = t.get("price_inr") or 0
            rows.append({
                "Symbol": sym,
                "Action": (t.get("action") or "BUY").upper(),
                "Quantity": float(t.get("qty", 0) or 0),
                "Price": float(price or 0),
                "Date": d,
            })
    return rows


def _validate_holding_rows(rows: List[Dict[str, Any]]) -> List[str]:
    """Spec 2D rules: symbol non-empty, action in {BUY,SELL}, qty>0,
    price>0, date not in future. Returns list of error messages —
    empty means ready to save."""
    today = date.today()
    errors: List[str] = []
    for i, r in enumerate(rows):
        sym = (r.get("Symbol") or "").strip().upper()
        label = sym if sym else f"row {i + 1}"
        if not sym:
            errors.append(f"Row {i + 1}: Symbol is required.")
            continue
        action = str(r.get("Action") or "").upper()
        if action not in ("BUY", "SELL"):
            errors.append(f"{label}: Action must be BUY or SELL.")
        try:
            qty = float(r.get("Quantity", 0) or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            errors.append(f"{label}: Quantity must be > 0.")
        try:
            price = float(r.get("Price", 0) or 0)
        except (TypeError, ValueError):
            price = 0.0
        if price <= 0:
            errors.append(f"{label}: Price must be > 0.")
        d = r.get("Date")
        if isinstance(d, datetime):
            d = d.date()
        if isinstance(d, str):
            try:
                d = date.fromisoformat(d)
            except ValueError:
                errors.append(f"{label}: Date format invalid (YYYY-MM-DD).")
                continue
        if isinstance(d, date) and d > today:
            errors.append(f"{label}: Date can't be in the future.")
    return errors


def _rows_to_holdings(
    rows: List[Dict[str, Any]],
    existing: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Re-group flat rows back into the nested holdings schema. Wrapper
    metadata (name / type / market / notes) is preserved from the
    matching existing entry when the symbol is already known; new
    symbols default to type='Stock', market='US', notes=''."""
    by_symbol: Dict[str, Dict[str, Any]] = {}
    for h in existing:
        sym = (h.get("symbol") or "").strip().upper()
        if sym:
            by_symbol[sym] = {
                "name": h.get("name", ""),
                "type": h.get("type", "Stock"),
                "market": h.get("market", "US"),
                "notes": h.get("notes", ""),
            }

    grouped: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        sym = (r.get("Symbol") or "").strip().upper()
        if not sym:
            continue
        if sym not in grouped:
            meta = by_symbol.get(sym, {})
            grouped[sym] = {
                "symbol": sym,
                "name": meta.get("name", sym),
                "type": meta.get("type", "Stock"),
                "market": meta.get("market", "US"),
                "notes": meta.get("notes", ""),
                "trades": [],
            }
        d = r.get("Date")
        if isinstance(d, datetime):
            d = d.date()
        d_str = d.isoformat() if isinstance(d, date) else str(d)
        # Store the price in the holding's NATIVE currency field so the round-trip
        # is stable: an Indian-market holding keeps price_inr (never re-stamped as
        # USD, which would inflate it ~83x on the next edit). All math downstream
        # infers currency from which field is present.
        price_key = "price_inr" if _is_inr_market(grouped[sym].get("market")) else "price_usd"
        grouped[sym]["trades"].append({
            "date": d_str,
            "qty": float(r.get("Quantity", 0) or 0),
            price_key: float(r.get("Price", 0) or 0),
            "action": str(r.get("Action") or "BUY").upper(),
        })
    return list(grouped.values())


def render_holdings_crud():
    """Manage / Add / Reset / Export — appears below the read-only
    holdings table. All three actions persist to results/holdings.json."""
    holdings = get_holdings()

    with st.expander("✏️ Manage holdings (edit / remove)"):
        flat = _flatten_holdings_to_rows(holdings)
        editor_df = pd.DataFrame(
            flat, columns=["Symbol", "Action", "Quantity", "Price", "Date"],
        )
        edited = st.data_editor(
            editor_df,
            num_rows="dynamic",
            use_container_width=True,
            key="holdings_editor",
            column_config={
                "Symbol":   st.column_config.TextColumn("Symbol", required=True, help="e.g. AAPL"),
                "Action":   st.column_config.SelectboxColumn("Action", options=["BUY", "SELL"], required=True),
                "Quantity": st.column_config.NumberColumn("Quantity", min_value=0.0, step=0.0001, format="%.4f"),
                "Price":    st.column_config.NumberColumn("Price ($)", min_value=0.0, step=0.01, format="%.2f"),
                "Date":     st.column_config.DateColumn("Date", max_value=date.today()),
            },
        )
        c1, c2 = st.columns([1, 4])
        with c1:
            save = st.button("💾 Save changes", type="primary", key="holdings_save_btn")
        with c2:
            st.caption("Edits are not saved until you click Save.")

        if save:
            edited_rows = edited.to_dict("records") if hasattr(edited, "to_dict") else list(edited)
            errors = _validate_holding_rows(edited_rows)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                _save_holdings_json(_rows_to_holdings(edited_rows, holdings))
                st.success(f"Saved.")
                st.cache_data.clear()
                st.rerun()

    with st.expander("➕ Add new holding"):
        with st.form("add_holding_form", clear_on_submit=True):
            new_symbol = st.text_input("Symbol", key="add_holding_symbol")
            new_action = st.selectbox("Action", ["BUY", "SELL"], index=0, key="add_holding_action")
            new_qty = st.number_input(
                "Quantity", min_value=0.0, step=0.0001, format="%.4f", key="add_holding_qty",
            )
            new_price = st.number_input(
                "Price (USD)", min_value=0.0, step=0.01, format="%.2f", key="add_holding_price",
            )
            new_date = st.date_input(
                "Date", value=date.today(), max_value=date.today(), key="add_holding_date",
            )
            submitted = st.form_submit_button("➕ Add holding")

        if submitted:
            row = {
                "Symbol": (new_symbol or "").strip().upper(),
                "Action": new_action,
                "Quantity": float(new_qty),
                "Price": float(new_price),
                "Date": new_date,
            }
            errors = _validate_holding_rows([row])
            if errors:
                for e in errors:
                    st.error(e)
            else:
                merged = _rows_to_holdings(
                    _flatten_holdings_to_rows(holdings) + [row], holdings,
                )
                _save_holdings_json(merged)
                st.success(
                    f"Added {row['Quantity']:g} {row['Symbol']} @ "
                    f"${row['Price']:,.2f} ({row['Action']}) on {row['Date']}."
                )
                st.cache_data.clear()
                st.rerun()

    col_reset, col_export = st.columns([1, 1])
    with col_reset:
        if st.button("↩️ Reset to config defaults", key="holdings_reset_btn"):
            HOLDINGS_PATH.unlink(missing_ok=True)
            st.cache_data.clear()
            st.rerun()
    with col_export:
        if HOLDINGS_PATH.exists():
            st.download_button(
                "⬇️ Download holdings.json",
                data=HOLDINGS_PATH.read_text(encoding="utf-8"),
                file_name="holdings.json",
                mime="application/json",
                key="holdings_export_btn",
            )


def render_holdings(rows: List[Dict[str, Any]], totals: Dict[str, float]):
    st.subheader("💼 Your Holdings")
    if not get_holdings():
        st.info("You have no holdings yet. Add one using the form below.")
        return

    if not rows:
        st.warning("⚠️ Data temporarily unavailable — couldn't price any holdings.")
        return

    currency = _current_currency()
    fx = fetch_usd_inr()
    money_label = "Invested" if currency == "USD" else "Invested (₹)"
    value_label = "Value" if currency == "USD" else "Value (₹)"
    pnl_label = "P&L" if currency == "USD" else "P&L (₹)"

    display_rows = []
    warnings_below: List[str] = []
    for r in rows:
        if r.get("status") == "closed":
            continue
        if r.get("status") != "ok":
            display_rows.append({
                "Symbol": r["symbol"], "Type": r["type"],
                "Status": r.get("status", "unknown"),
            })
            continue
        display_rows.append({
            "Symbol": r["symbol"],
            "Type": r["type"],
            "Qty": f"{r['qty']:.2f}",
            "Avg Buy": f"{r['avg_buy_native']:.2f} {r['currency']}",
            "Current": f"{r['current_native']:.2f} {r['currency']}",
            "Day %": f"{r['day_change_pct']:+.2f}%",
            money_label: _fmt_currency(r["invested_inr"], currency, fx),
            value_label: _fmt_currency(r["current_inr"], currency, fx),
            pnl_label: _fmt_currency(r["pnl_inr"], currency, fx, signed=True),
            "P&L %": f"{r['pnl_pct']:+.2f}%",
            "Score": f"{r['score']:.0f}" if r.get("score") is not None else "—",
            "Quality": r["recommendation"],
        })
        if r.get("score") is not None and r["score"] < 35:
            warnings_below.append(f"**{r['symbol']}** scores low (quality {r['score']:.0f} / 100) — worth a review.")

    st.dataframe(pd.DataFrame(display_rows), hide_index=True, use_container_width=True)

    tc1, tc2 = st.columns(2)
    tc1.markdown(
        f"**Total Unrealized P&L:** "
        f"{_fmt_currency(totals['pnl_inr'], currency, fx, signed=True)} "
        f"({totals['pnl_pct']:+.2f}%)"
    )
    tc2.markdown(
        f"**Total Realized P&L:** "
        f"{_fmt_currency(totals.get('realized_inr', 0), currency, fx, signed=True)}"
    )

    for w in warnings_below:
        st.warning(w)


def render_my_profile():
    """Editable user profile, persisted to results/profile.json.
    Drops the legacy `annual_income` / `investment_horizon_years` /
    `name` / `age` fields — they're not part of the new schema."""
    st.subheader("👤 My Profile")
    profile = _load_profile()
    currency = _current_currency()
    fx = fetch_usd_inr()

    # Read-only display row
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Goal**")
        st.markdown(f"{profile.get('goal', '—')}")
    with c2:
        st.markdown("**Monthly Investment**")
        st.markdown(_fmt_currency(
            profile.get("monthly_investment_inr", 0), currency, fx,
        ))
    with c3:
        st.markdown("**Risk Category**")
        st.markdown(f"`{profile.get('risk_category', '—')}`")
        st.caption(f"Risk score: {profile.get('risk_score', '—')}/10")

    with st.expander("✏️ Edit profile"):
        with st.form("profile_form", clear_on_submit=False):
            new_goal = st.text_input(
                "Goal",
                value=profile.get("goal", DEFAULT_PROFILE["goal"]),
            )
            new_monthly = st.number_input(
                "Monthly investment (₹)",
                min_value=0,
                step=1000,
                value=int(profile.get(
                    "monthly_investment_inr",
                    DEFAULT_PROFILE["monthly_investment_inr"],
                )),
            )
            new_risk = st.slider(
                "Risk score",
                min_value=1, max_value=10,
                value=int(profile.get(
                    "risk_score", DEFAULT_PROFILE["risk_score"]
                )),
            )
            st.caption(
                f"Category: **{_risk_score_to_category(int(new_risk))}**"
            )
            saved_clicked = st.form_submit_button("💾 Save profile")

        if saved_clicked:
            new_profile = {
                "goal": new_goal.strip() or DEFAULT_PROFILE["goal"],
                "monthly_investment_inr": int(new_monthly),
                "risk_score": int(new_risk),
                "risk_category": _risk_score_to_category(int(new_risk)),
            }
            _save_profile(new_profile)
            st.success("Profile saved.")
            st.rerun()

    st.caption(
        "🛈 Your risk category controls position sizing limits, default "
        "stop-loss tightness, and minimum R:R required to trigger BUY "
        "verdicts."
    )


def render_opportunities(portfolio_inr: float, cash_inr: float):
    st.subheader("📈 Opportunities")
    watchlist = build_watchlist()
    with st.spinner(f"Scanning {len(watchlist)} symbols (this can take 20–30 s on first load)…"):
        top = scan_opportunities(tuple(watchlist), portfolio_inr, cash_inr)

    if not top:
        st.info("No high-scoring names in your watchlist right now. Check back later or broaden WATCHLIST. (This is a screener, not a buy list.)")
        return

    rows = []
    for r in top:
        rows.append({
            "Symbol": r["symbol"],
            "Price": f"{r['price']:.2f}",
            "Score": f"{r['score']:.0f}",
            "Setup": r["setup"],
            "Quality": _score_band(r.get("score")),
            "R:R": f"1:{r['rr']:.1f}" if r["rr"] else "—",
            "Shares": r["shares"],
            "Sized?": "✅" if r["approved"] else "❌",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("Suggested share count comes from core.position_sizer (applies regime + volatility tilts).")


# --------------------------------------------------------------------------- #
# Closed-trade detection + win rate (from CURRENT_HOLDINGS trade list)
# --------------------------------------------------------------------------- #

def _parse_date(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(raw), fmt)
        except ValueError:
            continue
    return None


def compute_closed_trades(holdings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Scan CURRENT_HOLDINGS for symbols whose SELL qty >= BUY qty.
    Produces {symbol, entry_avg, exit_avg, realized_inr, realized_pct, hold_days}
    per closed symbol. Partial exits (sold < bought) are treated as still open."""
    closed: List[Dict[str, Any]] = []
    rate = fetch_usd_inr()   # live rate, consistent with display formatting
    for h in holdings:
        trades = h.get("trades", []) or []
        buys = [t for t in trades if t.get("action", "BUY").upper() == "BUY"]
        sells = [t for t in trades if t.get("action", "").upper() == "SELL"]
        buy_qty = sum(float(t.get("qty", 0)) for t in buys)
        sell_qty = sum(float(t.get("qty", 0)) for t in sells)
        if buy_qty <= 0 or sell_qty < buy_qty:
            continue

        def _price(t: Dict[str, Any]) -> float:
            return float(t.get("price_inr") if "price_inr" in t else t.get("price_usd", 0) or 0)

        currency = "INR" if any("price_inr" in t for t in buys + sells) else "USD"
        buy_cost_native = sum(float(t.get("qty", 0)) * _price(t) for t in buys)
        sell_proceeds_native = sum(float(t.get("qty", 0)) * _price(t) for t in sells)
        entry_avg = buy_cost_native / buy_qty if buy_qty else 0.0
        exit_avg = sell_proceeds_native / sell_qty if sell_qty else 0.0
        realized_native = sell_proceeds_native - buy_cost_native
        realized_inr = realized_native if currency == "INR" else realized_native * rate
        realized_pct = (realized_native / buy_cost_native * 100) if buy_cost_native else 0.0

        first_buy = min((_parse_date(t.get("date")) for t in buys), default=None, key=lambda d: d or datetime.max)
        last_sell = max((_parse_date(t.get("date")) for t in sells), default=None, key=lambda d: d or datetime.min)
        hold_days = (last_sell - first_buy).days if (first_buy and last_sell) else None

        closed.append({
            "symbol": h["symbol"],
            "entry_avg": entry_avg,
            "exit_avg": exit_avg,
            "realized_inr": realized_inr,
            "realized_pct": realized_pct,
            "hold_days": hold_days,
            "currency": currency,
        })
    return closed


def compute_win_rate(closed: List[Dict[str, Any]]) -> Optional[float]:
    if not closed:
        return None
    wins = sum(1 for c in closed if c["realized_inr"] > 0)
    return wins / len(closed) * 100


# --------------------------------------------------------------------------- #
# Page 2 — Portfolio Analytics sections
# --------------------------------------------------------------------------- #

def render_performers(rows: List[Dict[str, Any]]):
    st.subheader("🏆 Best / Worst Performers (1 Day)")
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    if not ok_rows:
        st.info("Not enough holdings data to rank performers.")
        return

    currency = _current_currency()
    fx = fetch_usd_inr()

    # Attach 1-week change from cached history.
    enriched = []
    for r in ok_rows:
        wk = fetch_week_history(r["symbol"])
        enriched.append({**r, "week_pct": wk["week_pct"] if wk else None})

    def _row(r: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "Symbol": r["symbol"],
            "Qty": f"{r['qty']:.2f}",
            "Current Price": f"{r['current_native']:.2f} {r['currency']}",
            "1D %": f"{r['day_change_pct']:+.2f}%",
            "1W %": f"{r['week_pct']:+.2f}%" if r.get("week_pct") is not None else "—",
            "Unrealized P&L": _fmt_currency(r["pnl_inr"], currency, fx, signed=True),
        }

    best = sorted(enriched, key=lambda r: r["day_change_pct"], reverse=True)[:3]
    worst = sorted(enriched, key=lambda r: r["day_change_pct"])[:3]

    left, right = st.columns(2)
    with left:
        st.markdown("**🟢 Best 3 (by 1D %)**")
        st.dataframe(pd.DataFrame([_row(r) for r in best]),
                     hide_index=True, use_container_width=True)
    with right:
        st.markdown("**🔴 Worst 3 (by 1D %)**")
        st.dataframe(pd.DataFrame([_row(r) for r in worst]),
                     hide_index=True, use_container_width=True)


def render_sector_allocation(rows: List[Dict[str, Any]]):
    st.subheader("🥧 Sector Allocation")
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    if not ok_rows:
        st.info("No priced holdings yet — sector breakdown unavailable.")
        return

    buckets: Dict[str, float] = {}
    for r in ok_rows:
        sector = fetch_sector(r["symbol"])
        buckets[sector] = buckets.get(sector, 0.0) + r["invested_inr"]

    total = sum(buckets.values()) or 1.0
    currency = _current_currency()
    fx = fetch_usd_inr()
    alloc_rows = [
        {
            "Sector": s,
            "Invested": v,  # numeric INR, drives the arc
            "Amount": _fmt_currency(v, currency, fx),  # display in chosen currency
            "Share": v / total * 100,
        }
        for s, v in sorted(buckets.items(), key=lambda kv: -kv[1])
    ]
    df = pd.DataFrame(alloc_rows)

    # Altair pie via mark_arc (plotly not installed; altair ships with streamlit).
    import altair as alt
    chart = (
        alt.Chart(df)
        .mark_arc(innerRadius=60)
        .encode(
            theta=alt.Theta(field="Invested", type="quantitative"),
            color=alt.Color(field="Sector", type="nominal",
                            legend=alt.Legend(title="Sector")),
            tooltip=["Sector", alt.Tooltip("Amount", title="Invested"),
                     alt.Tooltip("Share", format=".1f")],
        )
    )
    st.altair_chart(chart, use_container_width=True)

    invested_label = "Invested" if currency == "USD" else "Invested (₹)"
    st.dataframe(
        pd.DataFrame([
            {
                "Sector": r["Sector"],
                invested_label: _fmt_currency(r["Invested"], currency, fx),
                "% of portfolio": f"{r['Share']:.1f}%",
            }
            for r in alloc_rows
        ]),
        hide_index=True,
        use_container_width=True,
    )


def render_backtest_results():
    data = load_backtest_results()
    if not data:
        st.info(
            "No backtest results yet. "
            "Run `python validation/backtester.py --universe us --years 3` first."
        )
        st.caption(
            "Backtest = historical simulation of the strategy on 3 years of data. "
            "Higher Sharpe = better risk-adjusted return."
        )
        return

    rows = []
    for strategy_name, metrics in data.items():
        if not isinstance(metrics, dict):
            continue
        rows.append({
            "Strategy": metrics.get("strategy", strategy_name),
            "Return %": f"{metrics.get('total_return_pct', 0):+.2f}",
            "Sharpe": f"{metrics.get('sharpe_ratio', 0):.2f}",
            "Max DD %": f"{metrics.get('max_drawdown_pct', 0):.2f}",
            "Win %": f"{metrics.get('win_rate_pct', 0):.1f}",
            "Trades": int(metrics.get("total_trades", 0)),
        })

    if not rows:
        st.info("Backtest file found but empty / unrecognized shape.")
        return

    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption(
        "Backtest = historical simulation of the strategy on 3 years of data. "
        "Higher Sharpe = better risk-adjusted return. "
        "Max DD = worst peak-to-trough drop during the simulation."
    )


def render_closed_trades(holdings: List[Dict[str, Any]]):
    st.subheader("📉 Closed Trades")
    closed = compute_closed_trades(holdings)
    if not closed:
        st.info("No closed trades yet.")
        return

    currency = _current_currency()
    fx = fetch_usd_inr()
    pnl_label = "Realized P&L" if currency == "USD" else "Realized P&L (₹)"
    rows = []
    for c in closed:
        rows.append({
            "Symbol": c["symbol"],
            "Entry Avg": f"{c['entry_avg']:.2f} {c['currency']}",
            "Exit Avg": f"{c['exit_avg']:.2f} {c['currency']}",
            pnl_label: _fmt_currency(c["realized_inr"], currency, fx, signed=True),
            "Realized P&L %": f"{c['realized_pct']:+.2f}%",
            "Hold Days": c["hold_days"] if c["hold_days"] is not None else "—",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


_BENCHMARK = {"USD": ("SPY", "S&P 500 (SPY)"), "INR": ("^NSEI", "Nifty 50")}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_benchmark_closes(ticker: str, start: str) -> Optional[Dict[str, float]]:
    """Daily closes {iso_date: close} for a benchmark from `start`. Cached 1h."""
    try:
        import yfinance as yf
        s = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
        hist = yf.Ticker(ticker).history(start=s, auto_adjust=True)
        if hist.empty:
            return None
        return {d.strftime("%Y-%m-%d"): float(c) for d, c in hist["Close"].items()}
    except Exception:
        return None


def render_trade_review(holdings: List[Dict[str, Any]]):
    """Did trading beat doing nothing? Your result vs never selling vs the index."""
    from istock.decision.trade_review import review_holding, summarize

    st.subheader("🧾 Trade Review: did trading beat doing nothing?")
    currency = _current_currency()
    fx = fetch_usd_inr()

    dates = [str(t.get("date")) for h in holdings for t in (h.get("trades") or []) if t.get("date")]
    if not dates:
        st.info("No dated trades to review yet.")
        return
    start = min(dates)

    rows: List[Dict[str, Any]] = []
    bench_labels = set()
    for h in holdings:
        cur = "INR" if _is_inr_market(h.get("market")) else "USD"
        bench_tkr, bench_label = _BENCHMARK[cur]
        closes = fetch_benchmark_closes(bench_tkr, start)
        quote = fetch_live_quote(h.get("symbol", ""))
        if not closes or not quote:
            continue
        keys = sorted(closes)

        def bench_on(d: str, _c=closes, _k=keys) -> Optional[float]:
            prior = [k for k in _k if k <= d]
            return _c[prior[-1]] if prior else None

        r = review_holding(h, quote["current_price"], bench_on, closes[keys[-1]])
        if not r:
            continue
        # Convert to INR so mixed-currency portfolios sum correctly.
        for k in ("invested", "actual", "never_sold", "benchmark"):
            if r[k] is not None:
                r[k] = _to_inr(r[k], cur)
        rows.append(r)
        bench_labels.add(bench_label)

    if not rows:
        st.warning("⚠️ Couldn't price the holdings or the index right now.")
        return

    invested = sum(r["invested"] for r in rows)
    actual = sum(r["actual"] for r in rows)
    never = sum(r["never_sold"] for r in rows)
    bench_rows = [r for r in rows if r["benchmark"] is not None]
    bench = sum(r["benchmark"] for r in bench_rows) if bench_rows else None
    bench_label = " / ".join(sorted(bench_labels))

    def _pct(x):
        return f"{x / invested * 100:+.2f}%" if invested else "—"

    c1, c2, c3 = st.columns(3)
    c1.metric("Your result", _fmt_currency(actual, currency, fx, signed=True), _pct(actual))
    c2.metric("If you never sold", _fmt_currency(never, currency, fx, signed=True), _pct(never))
    if bench is not None:
        c3.metric(f"If it all went into {bench_label}",
                  _fmt_currency(bench, currency, fx, signed=True), _pct(bench))

    lines = []
    if bench is not None:
        gap = actual - bench
        lines.append(f"Your picks {'beat' if gap >= 0 else 'trailed'} {bench_label} by "
                     f"**{_fmt_currency(abs(gap), currency, fx)}** on the same money.")
    sell_effect = actual - never
    if not any(r["n_sells"] for r in rows):
        lines.append("No sells yet, so *never sold* matches your result.")
    elif abs(sell_effect) >= 0.005 * invested:
        lines.append(f"Your sells {'added' if sell_effect > 0 else 'cost you'} "
                     f"**{_fmt_currency(abs(sell_effect), currency, fx)}** vs just holding.")
    else:
        lines.append("Overall, your sells made little difference vs just holding.")
    # Per-stock: the net can hide large effects that cancel out.
    effects = [(r["symbol"], r["actual"] - r["never_sold"]) for r in rows if r["n_sells"]]
    worst = min(effects, key=lambda e: e[1], default=None)
    best = max(effects, key=lambda e: e[1], default=None)
    if worst and worst[1] < 0:
        lines.append(f"Selling **{worst[0]}** cost you **{_fmt_currency(-worst[1], currency, fx)}** "
                     f"vs holding it.")
    if best and best[1] > 0:
        lines.append(f"Selling **{best[0]}** added **{_fmt_currency(best[1], currency, fx)}**.")
    st.markdown(_md_dollars("  \n".join(lines)))

    s = summarize(rows)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Positions in profit", f"{s['winners']} / {s['positions']}")
    m2.metric("Avg winner", _fmt_currency(s["avg_win"], currency, fx, signed=True))
    m3.metric("Avg loser", _fmt_currency(s["avg_loss"], currency, fx, signed=True))
    m4.metric("Win / loss size", f"{s['payoff']:.1f}×" if s["payoff"] else "—",
              help="Average winner ÷ average loser. Below 1× means losers are bigger than winners.")

    table = []
    for r in sorted(rows, key=lambda r: r["actual"], reverse=True):
        b = r["benchmark"]
        table.append({
            "Symbol": r["symbol"],
            "Trades": f"{r['n_buys']} buy / {r['n_sells']} sell",
            "Invested": _fmt_currency(r["invested"], currency, fx),
            "Your P&L": _fmt_currency(r["actual"], currency, fx, signed=True),
            "Never sold": _fmt_currency(r["never_sold"], currency, fx, signed=True),
            "Index instead": _fmt_currency(b, currency, fx, signed=True) if b is not None else "—",
            "Beat index?": ("✅" if r["actual"] >= b else "❌") if b is not None else "—",
        })
    st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)
    st.caption(
        f"Same money, three outcomes. *Index instead* puts each buy's cash into {bench_label} "
        "on the day you bought and holds it to today. Assumes cash from sells earns nothing; "
        "trading costs and taxes aren't included yet."
    )


# Note: render_portfolio_page() was removed in Session 11a — its 6
# subsections (performers, sector, backtest, closed trades, etc.) now
# render directly from page_home() under the "📊 Portfolio Analytics"
# subheader. The Settings page was also removed.


# --------------------------------------------------------------------------- #
# Page 3 — Stock Deep-Dive
# --------------------------------------------------------------------------- #

def _score_label(score: Optional[float]) -> tuple[str, str]:
    """Return (label, color) for a 0-100 score, using the spec thresholds."""
    if score is None:
        return ("—", "#64748b")
    if score >= 70:
        return ("Strong", "#16a34a")
    if score >= 50:
        return ("Fair", "#eab308")
    return ("Weak", "#dc2626")


def _render_score_card(title: str, score: Optional[float]):
    label, color = _score_label(score)
    text = f"{score:.0f} / 100" if score is not None else "— / 100"
    st.markdown(
        f"""
        <div style="padding:14px 20px;border-radius:8px;
                    background:{color}1A;border-left:4px solid {color};
                    margin-top:8px;">
          <span style="font-size:13px;color:#475569;">{title}</span>
          <div style="font-size:32px;font-weight:700;color:{color};">{text}</div>
          <span style="font-size:14px;color:{color};font-weight:600;">{label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _format_number(value: Any, kind: str = "num") -> str:
    """Uniform formatter for the deep-dive tables."""
    if value is None or value == "" or (isinstance(value, float) and (value != value)):
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if kind == "pct":
        return f"{v:.2f}%"
    if kind == "ratio":
        return f"{v:.2f}"
    if kind == "money":
        if abs(v) >= 1e12: return f"{v/1e12:.2f} T"
        if abs(v) >= 1e9:  return f"{v/1e9:.2f} B"
        if abs(v) >= 1e6:  return f"{v/1e6:.2f} M"
        return f"{v:,.0f}"
    return f"{v:,.2f}"


def _kv_table(pairs: List[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(pairs, columns=["Metric", "Value"])


def render_deepdive_header(symbol: str, fund: Optional[Dict[str, Any]],
                           tech: Optional[Dict[str, Any]],
                           quote: Optional[Dict[str, float]]):
    name = (fund or {}).get("name") or symbol
    st.title(f"🔍 {symbol}  —  {name}")

    price = (quote or {}).get("current_price")
    day_pct = (quote or {}).get("day_change_pct")
    mc = (fund or {}).get("market_cap")
    vol_avg = ((tech or {}).get("volume") or {}).get("avg_20_volume")
    hi52 = ((tech or {}).get("momentum") or {}).get("high_52w")
    lo52 = ((tech or {}).get("momentum") or {}).get("low_52w")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Price",
        _format_number(price) if price else "—",
        delta=f"{day_pct:+.2f}%" if day_pct is not None else None,
        delta_color="normal" if (day_pct or 0) >= 0 else "inverse",
    )
    c2.metric("Market Cap", _format_number(mc, "money"))
    c3.metric("Avg Volume (20d)", _format_number(vol_avg, "money"))
    c4.metric(
        "52-Week Range",
        f"{_format_number(lo52)} – {_format_number(hi52)}" if (hi52 and lo52) else "—",
    )


def _score_label(title: str, score: Optional[float]) -> str:
    """Expander label that carries the section's 0-100 score, e.g.
    '💰 Fundamentals — Score: 68/100'."""
    if score is None:
        return f"{title} — Score: N/A"
    return f"{title} — Score: {float(score):.0f}/100"


def render_deepdive_fundamentals(fund: Optional[Dict[str, Any]]):
    if not fund:
        st.warning("Fundamentals temporarily unavailable.")
        return

    val = fund.get("valuation") or {}
    prof = fund.get("profitability") or {}
    growth = fund.get("growth") or {}
    health = fund.get("financial_health") or {}
    div = fund.get("dividend") or {}

    left, right = st.columns(2)
    with left:
        st.markdown("**Key Ratios**")
        st.dataframe(_kv_table([
            ("P/E (trailing)", _format_number(val.get("pe_ratio"), "ratio")),
            ("P/E (forward)",  _format_number(val.get("forward_pe"), "ratio")),
            ("P/B",            _format_number(val.get("pb_ratio"), "ratio")),
            ("PEG",            _format_number(val.get("peg_ratio"), "ratio")),
            ("EV/EBITDA",      _format_number(val.get("ev_ebitda"), "ratio")),
            ("Dividend Yield", _format_number(div.get("dividend_yield"), "pct")),
        ]), hide_index=True, use_container_width=True)

    with right:
        st.markdown("**Health Metrics**")
        st.dataframe(_kv_table([
            ("ROE",                _format_number(prof.get("roe"), "pct")),
            ("ROA",                _format_number(prof.get("roa"), "pct")),
            ("Debt / Equity",      _format_number(health.get("debt_to_equity"), "ratio")),
            ("Current Ratio",      _format_number(health.get("current_ratio"), "ratio")),
            ("Profit Margin",      _format_number(prof.get("profit_margin"), "pct")),
            ("Revenue Growth YoY", _format_number(growth.get("revenue_growth"), "pct")),
            ("Earnings Growth YoY", _format_number(growth.get("earnings_growth"), "pct")),
        ]), hide_index=True, use_container_width=True)

    _render_score_card("Fundamental Score", fund.get("fundamental_score"))


def render_deepdive_technicals(tech: Optional[Dict[str, Any]]):
    if not tech:
        st.warning("Technicals temporarily unavailable.")
        return

    ma = tech.get("moving_averages") or {}
    rsi = tech.get("rsi") or {}
    macd = tech.get("macd") or {}
    stoch_k = rsi.get("stoch_rsi_k")
    vol = tech.get("volume") or {}
    volat = tech.get("volatility") or {}

    price = ma.get("current_price")
    sma50 = ma.get("sma_50")
    if price and sma50:
        if price > ma.get("sma_200", 0) and ma.get("sma_50_above_200") in (True, "True"):
            trend_dir = "🟢 Uptrend"
        elif price < ma.get("sma_200", price):
            trend_dir = "🔴 Downtrend"
        else:
            trend_dir = "🟡 Sideways"
    else:
        trend_dir = "—"

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Trend**")
        st.dataframe(_kv_table([
            ("Current Price", _format_number(price, "ratio")),
            ("SMA 20",  _format_number(ma.get("sma_20"), "ratio")),
            ("SMA 50",  _format_number(ma.get("sma_50"), "ratio")),
            ("SMA 200", _format_number(ma.get("sma_200"), "ratio")),
            ("Direction", trend_dir),
        ]), hide_index=True, use_container_width=True)
    with c2:
        st.markdown("**Momentum**")
        st.dataframe(_kv_table([
            ("RSI (14)",    _format_number(rsi.get("rsi_14"), "ratio")),
            ("RSI Signal",  rsi.get("rsi_signal") or "—"),
            ("MACD Signal", macd.get("signal") or "—"),
            ("MACD Cross",  macd.get("crossover") or "—"),
            ("StochRSI %K", _format_number(stoch_k, "ratio")),
        ]), hide_index=True, use_container_width=True)
    with c3:
        st.markdown("**Volatility / Volume**")
        st.dataframe(_kv_table([
            ("ATR",            _format_number(volat.get("atr"), "ratio")),
            ("Annual Vol %",   _format_number(volat.get("annual_volatility"), "pct")),
            ("Risk Level",     volat.get("risk_level") or "—"),
            ("Avg Vol (20d)",  _format_number(vol.get("avg_20_volume"), "money")),
            ("Vol Ratio (vs avg)", _format_number(vol.get("volume_ratio"), "ratio")),
        ]), hide_index=True, use_container_width=True)

    _render_score_card("Technical Score", tech.get("technical_score"))


def render_deepdive_risk(tech: Optional[Dict[str, Any]]):
    """Risk & Volatility — how MUCH the stock tends to move (never which way).
    The one honest forecast the tool makes; feeds position sizing."""
    st.subheader("📉 Risk & Volatility")
    if not tech:
        st.caption("Risk data unavailable.")
        return
    from istock.decision.volatility import expected_moves, volatility_band
    volat = tech.get("volatility") or {}
    ma = tech.get("moving_averages") or {}
    price = ma.get("current_price")
    ann = volat.get("annual_volatility")
    m = expected_moves(price, volat.get("atr"), ann)
    daily = m.get("daily_atr_pct") or m.get("daily_sigma_pct")
    weekly = m.get("weekly_sigma_pct")

    c1, c2, c3 = st.columns(3)
    c1.metric("Volatility", volatility_band(ann),
              f"{ann:.0f}% annual" if isinstance(ann, (int, float)) else None)
    c2.metric("Typical daily move", f"±{daily:.1f}%" if daily else "—")
    c3.metric("Typical weekly move", f"±{weekly:.1f}%" if weekly else "—")
    st.caption(
        "Estimates **how much** the stock tends to move — **not which way** "
        "(direction is unpredictable). Use it to size risk: a bigger typical move "
        "means a smaller position for the same risk."
    )


def render_deepdive_market_context(mc: Optional[Dict[str, Any]],
                                   fund: Optional[Dict[str, Any]],
                                   tech: Optional[Dict[str, Any]]):
    incomplete_note = False

    sector = (fund or {}).get("sector") or "—"
    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("**Sector**")
        st.markdown(f"`{sector}`")

    # Stock-vs-market / relative-strength panel driven by MarketContextAnalyzer.
    if mc:
        with col2:
            st.markdown(f"**Summary:** {mc['summary']}  ·  Score: **{mc['score']:.0f} / 100**")
            rows = [
                {"Signal": c["name"], "Pass": "✅" if c["passed"] else "❌", "Detail": c["detail"]}
                for c in (mc.get("checks") or [])
            ]
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            else:
                incomplete_note = True
    else:
        incomplete_note = True
        col2.warning("Market context analyzer returned nothing.")

    # 3-month momentum vs SPY proxy (fallback using the technicals output).
    returns = ((tech or {}).get("momentum") or {}).get("returns") or {}
    stock_3m = returns.get("3_month")
    if stock_3m is not None:
        st.markdown(
            f"**3-month return:** {stock_3m:+.2f}%  ·  "
            f"1-month: {returns.get('1_month', 0):+.2f}%  ·  "
            f"1-week: {returns.get('1_week', 0):+.2f}%"
        )
    else:
        incomplete_note = True

    if incomplete_note:
        st.caption("ℹ️ Some macro data temporarily unavailable.")


_ANALYST_LABEL_COLOR: Dict[str, str] = {
    "strong_buy":  "#16a34a",
    "buy":         "#16a34a",
    "outperform":  "#16a34a",
    "hold":        "#eab308",
    "neutral":     "#eab308",
    "underperform": "#dc2626",
    "sell":        "#dc2626",
    "strong_sell": "#dc2626",
}


def _analyst_pretty(rec: str) -> str:
    """yfinance returns 'strong_buy' / 'buy' / 'hold' etc. Render in
    title case for the UI ('Strong Buy', 'Buy', 'Hold')."""
    if not rec:
        return "—"
    return str(rec).replace("_", " ").title()


def render_deepdive_analyst_forecast(fund: Optional[Dict[str, Any]],
                                     current_price: Optional[float]):
    st.subheader("🎓 Analyst Forecast")
    analyst = (fund or {}).get("analyst") or {}
    num = analyst.get("num_analysts") or 0
    rec = analyst.get("recommendation")
    target = analyst.get("target_price")
    target_high = analyst.get("target_high")
    target_low = analyst.get("target_low")
    mean_rating = analyst.get("recommendation_mean")

    if not analyst or not num or not target:
        st.info("No analyst coverage data available for this ticker.")
        return

    color = _ANALYST_LABEL_COLOR.get(str(rec).lower(), "#64748b")
    pretty = _analyst_pretty(rec)

    left, right = st.columns([1, 2])
    with left:
        st.markdown(
            f"""
            <div style="padding:14px 18px;border-radius:8px;
                        background:{color}1A;border-left:4px solid {color};">
              <span style="font-size:13px;color:#475569;">Analyst Consensus</span>
              <div style="font-size:30px;font-weight:700;color:{color};">{pretty}</div>
              <span style="font-size:13px;color:#475569;">
                {num} analysts cover this stock
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if mean_rating is not None:
            st.caption(f"Mean rating: **{float(mean_rating):.2f} / 5.0**  (1=Strong Buy, 5=Sell)")

    with right:
        c1, c2, c3 = st.columns(3)

        def _delta_str(target_val: Optional[float]) -> Optional[str]:
            if not target_val or not current_price:
                return None
            pct = (float(target_val) - float(current_price)) / float(current_price) * 100
            return f"{pct:+.1f}% vs current"

        c1.metric("Target (mean)", f"${float(target):.2f}", delta=_delta_str(target))
        if target_high is not None:
            c2.metric("Target High", f"${float(target_high):.2f}", delta=_delta_str(target_high))
        else:
            c2.metric("Target High", "—")
        if target_low is not None:
            c3.metric("Target Low", f"${float(target_low):.2f}", delta=_delta_str(target_low))
        else:
            c3.metric("Target Low", "—")

    # Horizontal range visualization: low —— mean —— high, with current
    # price as a vertical pin. Plotly gives the cleanest single-line layout.
    if target_low is not None and target_high is not None and current_price:
        import plotly.graph_objects as go
        rng_fig = go.Figure()
        # Range bar (low → high)
        rng_fig.add_trace(go.Scatter(
            x=[float(target_low), float(target_high)], y=[0, 0],
            mode="lines", line=dict(color="#94a3b8", width=8),
            name="Target range", hoverinfo="skip", showlegend=False,
        ))
        # Mean target marker
        rng_fig.add_trace(go.Scatter(
            x=[float(target)], y=[0], mode="markers+text",
            marker=dict(color="#2563eb", size=14, symbol="circle"),
            text=[f"Mean ${float(target):.2f}"], textposition="top center",
            name="Mean target", showlegend=False,
        ))
        # Current price pin
        rng_fig.add_trace(go.Scatter(
            x=[float(current_price)], y=[0], mode="markers+text",
            marker=dict(color="#f97316", size=18, symbol="line-ns",
                        line=dict(width=3, color="#f97316")),
            text=[f"Current ${float(current_price):.2f}"],
            textposition="bottom center",
            name="Current price", showlegend=False,
        ))
        # Endpoint labels
        rng_fig.add_annotation(
            x=float(target_low), y=0, text=f"Low ${float(target_low):.2f}",
            showarrow=False, yshift=-25, font=dict(color="#dc2626", size=11),
        )
        rng_fig.add_annotation(
            x=float(target_high), y=0, text=f"High ${float(target_high):.2f}",
            showarrow=False, yshift=25, font=dict(color="#16a34a", size=11),
        )
        rng_fig.update_layout(
            height=140,
            margin=dict(l=20, r=20, t=20, b=20),
            yaxis=dict(visible=False, range=[-1, 1]),
            xaxis=dict(showgrid=False, zeroline=False),
            template="plotly_dark",
            showlegend=False,
        )
        st.plotly_chart(rng_fig, use_container_width=True,
                        config={"displayModeBar": False})


# The tool NEVER shows a BUY/SELL verdict. Internally the engine still produces a
# directional label (kept for logic/filters), but everything the user SEES is a
# non-directional quality band — the honest framing, since short-horizon direction
# is unpredictable (NEXT_STEPS.md). This maps the internal verdict → the shown band.
_VERDICT_TO_BAND = {
    "STRONG BUY": "Excellent", "BUY": "Strong", "LEAN BUY": "Solid",
    "HOLD": "Average", "LEAN SELL": "Mixed", "SELL": "Weak", "AVOID": "Poor",
}
_BAND_COLOR = {
    "Excellent": "#16a34a", "Strong": "#22c55e", "Solid": "#84cc16",
    "Average": "#eab308", "Mixed": "#f59e0b", "Weak": "#f97316", "Poor": "#dc2626",
}


def _verdict_to_band(verdict: str) -> str:
    """Internal directional verdict → the non-directional quality band shown to users."""
    return _VERDICT_TO_BAND.get((verdict or "").upper().strip(), "—")


def _score_band(score: Optional[float]) -> str:
    """Canonical, non-directional band straight from the 0–100 score. This is the
    single source of truth for the quality band everywhere it's shown — deriving it
    from the raw score (not the VIX-guardrailed verdict) keeps Home, Deep-Dive and
    the tables in agreement. Falls back to '—' when no score is available."""
    if score is None:
        return "—"
    from istock.model.scorer import quality_band_from_score
    return quality_band_from_score(float(score))


def _band_color(band: str) -> str:
    return _BAND_COLOR.get(band, "#64748b")


def _verdict_color(verdict: str) -> str:
    """Accent color, keyed off the non-directional quality band."""
    return _band_color(_verdict_to_band(verdict))


def render_deepdive_scoring(analysis: Optional[Dict[str, Any]]):
    st.subheader("🎯 Scoring Engine")
    if not analysis:
        st.warning("Scoring engine temporarily unavailable.")
        return

    verdict = analysis.get("verdict", "—")
    score = analysis.get("buy_score", 0)
    confidence = analysis.get("confidence", "—")
    setup_type = analysis.get("setup_type", "none")
    entry = analysis.get("entry", 0) or 0
    stop = analysis.get("stop_loss", 0) or 0
    targets = analysis.get("targets") or []
    rr = analysis.get("risk_reward", 0) or 0

    v2_verdict = analysis.get("v2_verdict") or verdict
    v2_score = analysis.get("v2_score") if analysis.get("v2_score") is not None else score
    skipped = analysis.get("v2_skipped_reason")

    v2_caption = ""
    if skipped == "vix_unavailable":
        v2_caption = "⚠️ High-VIX guardrail skipped (VIX data unavailable)"
    elif skipped:
        v2_caption = f"⚠️ {skipped}"

    color = _band_color(_score_band(v2_score))
    st.markdown(
        f"""
        <div style="padding:18px 24px;border-radius:10px;
                    background:{color}1A;border-left:6px solid {color};">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <div style="font-size:14px;color:#475569;">Quality</div>
              <div style="font-size:28px;font-weight:700;color:{color};">{_score_band(v2_score)}</div>
            </div>
            <div style="text-align:right;">
              <div style="font-size:14px;color:#475569;">Score</div>
              <div style="font-size:32px;font-weight:700;color:#0f172a;">{v2_score:.0f} / 100</div>
              <div style="font-size:13px;color:#475569;">Confidence: <b>{confidence}</b></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if v2_caption:
        st.caption(v2_caption)
    try:
        from config import ENABLE_VIX_GUARDRAIL as _vix_on
    except Exception:
        _vix_on = False
    _vix_note = (
        " · High-VIX guardrail active (VIX > 22 lowers the band one tier)"
        if _vix_on else
        " · VIX guardrail off"
    )
    st.caption(
        f"Confidence: **{confidence}** · Setup: **{setup_type.title() if setup_type else 'None'}**"
        + _vix_note
    )
    st.caption(
        "ℹ️ This is a **technical quality score** (0–100) summarizing the measured "
        "signals — **not a prediction and not a buy/sell recommendation**. "
        "Short-horizon direction is unpredictable; treat it as one input and decide "
        "for yourself. See the Fundamentals section below for the business analysis."
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Setup", setup_type.title() if setup_type else "None")
    c2.metric("Entry", f"{entry:.2f}" if entry else "—")
    c3.metric("Stop", f"{stop:.2f}" if stop else "—")
    c4.metric("Target 1", f"{targets[0]:.2f}" if len(targets) >= 1 else "—")
    c5.metric("R:R", f"1:{rr:.1f}" if rr else "—")

    if len(targets) >= 2:
        st.caption(
            f"Target 2: {targets[1]:.2f}"
            + (f"  ·  Target 3: {targets[2]:.2f}" if len(targets) >= 3 else "")
        )


# --------------------------------------------------------------------------- #
# Page 4 — Opportunities scanner
# --------------------------------------------------------------------------- #

SIDEBAR_KEY = "nav_selection"  # radio widget key used for cross-page nav


def _verdict_badge_html(verdict: str, *, score: Optional[float] = None,
                        muted: bool = False) -> str:
    """Small colored badge for the top-right of each opportunity card.
    Set `muted=True` to render a lighter / outlined variant — used for
    the non-primary band in the v1/v2 side-by-side. Prefers the raw score
    (the canonical, non-directional band) when available."""
    band = _score_band(score) if score is not None else _verdict_to_band(verdict)
    color = _band_color(band)
    if muted:
        # Outlined / lighter version — non-primary verdict in side-by-side.
        return (
            f"<span style='background:transparent;color:{color};"
            f"border:1.5px solid {color};padding:2px 8px;"
            f"border-radius:12px;font-size:11px;font-weight:600;'>"
            f"{band}</span>"
        )
    return (
        f"<span style='background:{color};color:white;padding:3px 10px;"
        f"border-radius:12px;font-size:12px;font-weight:700;'>"
        f"{band}</span>"
    )


def _render_dual_verdict_html(a: Dict[str, Any]) -> str:
    """Render verdict badge + score for a v2 analysis."""
    verdict = a.get("v2_verdict") or a.get("verdict") or "—"
    score = a.get("v2_score") if a.get("v2_score") is not None else a.get("buy_score", 0)
    skipped = a.get("v2_skipped_reason")

    badge = _verdict_badge_html(verdict, score=score)
    vix_warn = ""
    if skipped == "vix_unavailable":
        vix_warn = (
            "<span title='VIX cache unavailable — guardrail was skipped' "
            "style='color:#dc2626;font-size:11px;'>⚠️ no-VIX</span>"
        )

    return (
        f"<div style='display:flex;align-items:center;gap:6px;flex-wrap:wrap;'>"
        f"{badge}{vix_warn}"
        f"</div>"
        f"<div style='font-size:10px;color:#64748b;'>{float(score or 0):.0f}/100</div>"
    )


def _render_opportunity_card(result: Dict[str, Any]):
    symbol = result["symbol"]
    a = result["analysis"]
    verdict = a.get("verdict", "—")
    score = a.get("buy_score", 0)
    confidence = a.get("confidence", "—")
    rr = a.get("risk_reward") or 0
    entry = a.get("entry") or 0
    stop = a.get("stop_loss") or 0
    targets = a.get("targets") or []
    t1 = targets[0] if targets else 0
    company = a.get("company_name") or symbol

    with st.container(border=True):
        head_left, head_right = st.columns([4, 1])
        with head_left:
            st.markdown(
                f"<div style='font-size:20px;font-weight:700;'>"
                f"{symbol} <span style='color:#64748b;font-weight:400;'>"
                f"— {company}</span></div>",
                unsafe_allow_html=True,
            )
        with head_right:
            st.markdown(_render_dual_verdict_html(a), unsafe_allow_html=True)

        st.markdown(
            f"**Score:** {score:.0f}/100  ·  **Confidence:** {confidence}  ·  "
            f"**R:R:** {'1:' + format(rr, '.1f') if rr else '—'}"
        )
        if entry:
            st.markdown(
                f"**Entry:** {entry:.2f}  ·  "
                f"**Stop:** {stop:.2f}  ·  "
                f"**Target:** {t1:.2f}" if t1 else f"**Entry:** {entry:.2f}"
            )

        reasons = _top_reasons(a, n=3)
        if reasons:
            st.markdown("**Top 3 strengths:**")
            for name, detail in reasons:
                line = f"&nbsp;&nbsp;&nbsp;✓ <b>{name}</b>"
                if detail:
                    line += f" — <span style='color:#64748b;'>{detail}</span>"
                st.markdown(line, unsafe_allow_html=True)

        # Two-column row of actions: 🔍 deep-dive + 📌 track. Both keys
        # include the symbol so cards stay independently clickable.
        view_col, track_col = st.columns(2)
        with view_col:
            if st.button("🔍 View full analysis",
                         key=f"view_{symbol}",
                         use_container_width=True):
                # Streamlit forbids writing a widget's own session_state
                # key after that widget has rendered (the sidebar radio
                # already ran on this tick). Stash an intent flag that
                # main() reads BEFORE the radio renders on the next run.
                st.session_state["deepdive_symbol"] = symbol
                st.session_state["_nav_intent"] = "🔍 Stock Deep-Dive"
                st.rerun()
        with track_col:
            if st.button("📌 Track this pick",
                         key=f"track_card_{symbol}",
                         use_container_width=True):
                blocker = _find_blocking_open_pick(symbol)
                if blocker is not None:
                    st.warning(_format_blocked_warning(symbol, blocker))
                else:
                    pick = _build_pick_from_analysis(symbol, a)
                    _append_pick(pick)
                    st.success(f"✅ Tracking {symbol}")
                    st.rerun()


def _render_universe_info(universe: List[str]) -> None:
    """Show an expander with the scanner universe size, cap-band
    distribution, and an input for session-only custom tickers. Caps
    are fetched lazily and cached for a day, so opening the expander
    on a fresh universe is the only slow path."""
    with st.expander("🌐 Universe info", expanded=False):
        st.markdown(f"**Total tickers in scanner:** {len(universe)}")

        with st.spinner("Bucketing tickers by market cap..."):
            buckets: Dict[str, int] = {label: 0 for label, _ in _CAP_BANDS}
            buckets["Unknown"] = 0
            for sym in universe:
                buckets[_cap_category(fetch_market_cap(sym))] += 1

        total = max(sum(buckets.values()), 1)
        rows = []
        for label, _ in _CAP_BANDS:
            count = buckets[label]
            if count == 0:
                continue
            rows.append({"Cap band": label,
                         "Count": count,
                         "%": f"{count / total * 100:.1f}%"})
        if buckets["Unknown"] > 0:
            rows.append({"Cap band": "Unknown",
                         "Count": buckets["Unknown"],
                         "%": f"{buckets['Unknown'] / total * 100:.1f}%"})
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True)

        st.caption(
            "All opportunities are scored against the same model. The "
            "model was backtested primarily on mega caps — treat mid/"
            "small cap signals as exploratory."
        )

        st.divider()
        existing = st.session_state.get("custom_universe_addons", []) or []
        raw = st.text_input(
            "Add tickers (comma-separated)",
            value=", ".join(existing),
            key="custom_universe_input",
            placeholder="e.g. PLTR, SOFI, RIVN",
        )
        # Normalize on every render so the universe reflects the input
        # immediately on the next scan without an extra "Apply" button.
        cleaned = [t.strip().upper() for t in raw.split(",") if t.strip()]
        if cleaned != existing:
            st.session_state["custom_universe_addons"] = cleaned
            # Force the cached scan to invalidate so the next render picks
            # up the new tickers — otherwise the user sees stale results.
            run_full_scan.clear()
        st.caption(
            "Added tickers are scanned for this session only. To make "
            "permanent, edit `SCANNER_UNIVERSE_BASE` in `ui/app.py`."
        )


def _render_opportunities_tab():
    """Inner body of the Opportunities tab on the merged Picks page.
    Self-contained: header caption + Rerun Scan button + filter row +
    cards. Designed to live inside an st.tab on render_picks_page()."""
    universe = build_scanner_universe()
    st.caption(
        f"Screening top {len(universe)} US stocks by quality (a screener, not a buy list). "
        f"Cached for 30 min after the first run."
    )

    _render_universe_info(universe)

    rerun = st.button("🔄 Rerun Scan", key="picks_rerun_scan")
    if rerun:
        # Clearing the cached scan forces a fresh full run; per-ticker
        # analyze_symbol cache may still hit if under its own 5 min TTL.
        run_full_scan.clear()
        st.rerun()

    # Scan. The spinner only shows on actual cache miss; on a hit this
    # is near-instant and the spinner flashes briefly.
    with st.spinner(f"Scanning {len(universe)} symbols... (~60-120s on first run)"):
        try:
            scan_results = run_full_scan(tuple(universe))
        except Exception:
            scan_results = []

    # Keep only BUY-worthy results for the scanner surface.
    buyworthy: List[Dict[str, Any]] = []
    errored: List[str] = []
    for r in scan_results:
        cat = _verdict_category(r["analysis"].get("verdict", ""))
        if cat is not None:
            buyworthy.append({**r, "category": cat})
    # Tickers in the universe with no analysis = errored
    returned = {r["symbol"] for r in scan_results}
    errored = [t for t in universe if t not in returned]

    st.caption(
        f"Analyzed: **{len(scan_results)}** / {len(universe)}  ·  "
        f"Solid+ quality: **{len(buyworthy)}**  ·  "
        f"Errors: **{len(errored)}**  ·  *screener, not a buy list*"
    )

    # --- Filter row -------------------------------------------------------
    f1, f3 = st.columns([1, 2])
    with f1:
        min_score = st.slider("Min Score", 0, 100, 50, key="scan_min_score")
    with f3:
        sectors_all = sorted({
            (r["analysis"].get("sector") or "Unknown") for r in buyworthy
        }) or ["Unknown"]
        sectors = st.multiselect(
            "Sector",
            options=sectors_all,
            default=sectors_all,
            key="scan_sectors",
        )

    # --- Apply filters + sort by score desc ------------------------------
    filtered = [
        r for r in buyworthy
        if r["analysis"].get("buy_score", 0) >= min_score
        and (r["analysis"].get("sector") or "Unknown") in sectors
    ]
    filtered.sort(key=lambda r: r["analysis"].get("buy_score", 0), reverse=True)

    st.divider()

    if not filtered:
        st.info(
            "No opportunities match your filters right now. Try lowering "
            "the minimum score or widening the quality filter. Remember: "
            "a good system says NO most of the time."
        )
        return

    st.markdown(f"### Showing **{min(len(filtered), 20)}** of {len(filtered)} matches")
    for r in filtered[:20]:
        _render_opportunity_card(r)


# --------------------------------------------------------------------------- #
# Tracker pick builder + auto-status updater
# --------------------------------------------------------------------------- #

def _build_pick_from_analysis(symbol: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Snapshot the current analysis into a tracker pick. Field names use
    the actual analyze_symbol() output keys (stop_loss, targets list,
    risk_reward) and break them out into target_1 / target_2 / rr_ratio
    for the persisted schema."""
    targets = list(analysis.get("targets") or [])
    target_1 = float(targets[0]) if len(targets) >= 1 and targets[0] else None
    target_2 = float(targets[1]) if len(targets) >= 2 and targets[1] else None

    try:
        regime_dict = fetch_regime() or {}
    except Exception:
        regime_dict = {}

    def _maybe_float(v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        "id": uuid.uuid4().hex,
        "tracked_at": datetime.utcnow().isoformat(),
        "symbol": symbol,
        "verdict": analysis.get("verdict", ""),
        "verdict_category": _verdict_category(analysis.get("verdict", "")),
        "score": float(analysis.get("buy_score", 0) or 0),
        "confidence": analysis.get("confidence", ""),
        "regime": regime_dict.get("regime", "UNKNOWN"),
        "setup_type": analysis.get("setup_type", ""),
        "tracked_price": _maybe_float(analysis.get("current_price")),
        "entry": _maybe_float(analysis.get("entry")),
        "stop": _maybe_float(analysis.get("stop_loss")),
        "target_1": target_1,
        "target_2": target_2,
        "rr_ratio": _maybe_float(analysis.get("risk_reward")),
        "user_note": "",
        "status": "open",
        "status_updated_at": datetime.utcnow().isoformat(),
        "closed_at": None,
        "close_price": None,
        "close_reason": None,
        "max_high_since": None,
        "min_low_since": None,
        "current_price": None,
        "current_pl_pct": None,
    }


def _find_blocking_open_pick(
    symbol: str, within_min: int = TRACKER_DUP_WINDOW_MIN
) -> Optional[Dict[str, Any]]:
    """Return the open pick that blocks a fresh track of `symbol`, or None.

    Block rule (per spec): same symbol, status == "open", tracked within
    the last `within_min` calendar minutes. Closed picks (hit_target_*,
    hit_stop, expired, closed_manual) NEVER block. Returning the pick
    itself — instead of just a bool — lets the UI surface its tracked_at
    and id in the warning."""
    cutoff = datetime.utcnow() - timedelta(minutes=within_min)
    for r in _load_log():
        if r.get("symbol") != symbol or r.get("status") != "open":
            continue
        try:
            ts = datetime.fromisoformat(r.get("tracked_at", ""))
        except (TypeError, ValueError):
            continue
        # Strip any tz info defensively — internal writes are naive UTC,
        # but a hand-edited log entry could carry an offset.
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        if ts >= cutoff:
            return r
    return None


def _has_recent_open_pick(symbol: str, within_min: int = TRACKER_DUP_WINDOW_MIN) -> bool:
    """Thin bool wrapper around _find_blocking_open_pick for callers that
    don't need the pick details. Kept so existing tests stay unchanged."""
    return _find_blocking_open_pick(symbol, within_min) is not None


def _format_blocked_warning(symbol: str, pick: Dict[str, Any]) -> str:
    """Build the user-facing warning shown when a duplicate track is
    blocked. Includes the original tracked_at (best-effort formatted)
    and the pick's short id so the user can locate it."""
    raw_ts = pick.get("tracked_at", "")
    pretty = raw_ts
    try:
        dt = datetime.fromisoformat(raw_ts)
        pretty = dt.strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        pass
    short_id = (pick.get("id") or "")[:8]
    return (
        f"⛔ {symbol} is already being tracked (open pick from {pretty}"
        + (f", id `{short_id}`" if short_id else "")
        + f"). Wait until it closes or {TRACKER_DUP_WINDOW_MIN} min passes."
    )


def _refresh_pick_status(pick: Dict[str, Any]) -> Dict[str, Any]:
    """Pull bars-since-tracked for this pick and decide if any level got
    hit. Mutates the pick dict in place AND returns it. Skip the hit
    checks for non-BUY verdicts (they have no stop/target). Stores
    max_high / min_low / current_price / current_pl_pct for display."""
    try:
        tracked_dt = datetime.fromisoformat(pick.get("tracked_at"))
    except (TypeError, ValueError):
        return pick
    now = datetime.utcnow()

    # 1) Expiry first — works even when yfinance is offline.
    if (now - tracked_dt).days >= TRACKER_EXPIRY_DAYS and pick.get("status") == "open":
        pick["status"] = "expired"
        pick["closed_at"] = now.isoformat()
        pick["status_updated_at"] = now.isoformat()
        return pick

    # 2) Pull daily bars from tracking date through today.
    try:
        import yfinance as yf
        df = yf.Ticker(pick["symbol"]).history(
            start=tracked_dt.date().isoformat(),
            interval="1d",
            prepost=False,
        )
    except Exception:
        return pick

    if df is None or df.empty:
        return pick

    max_high = float(df["High"].max())
    min_low = float(df["Low"].min())
    last_close = float(df["Close"].iloc[-1])
    pick["max_high_since"] = max_high
    pick["min_low_since"] = min_low
    pick["current_price"] = last_close

    # 3) Level checks — only meaningful for BUY-side picks with levels.
    if pick.get("status") == "open" and pick.get("verdict_category") in ("BUY", "LEAN BUY"):
        stop = pick.get("stop")
        t1 = pick.get("target_1")
        t2 = pick.get("target_2")
        # Stop check first (a stop-out cancels any same-window target hit).
        if stop is not None and min_low <= float(stop):
            pick["status"] = "hit_stop"
            pick["closed_at"] = now.isoformat()
            pick["close_price"] = float(stop)
            pick["close_reason"] = "stop"
        elif t2 is not None and max_high >= float(t2):
            pick["status"] = "hit_target_2"
            pick["closed_at"] = now.isoformat()
            pick["close_price"] = float(t2)
            pick["close_reason"] = "target_2"
        elif t1 is not None and max_high >= float(t1):
            pick["status"] = "hit_target_1"
            pick["closed_at"] = now.isoformat()
            pick["close_price"] = float(t1)
            pick["close_reason"] = "target_1"

    # 4) P&L since tracking — uses entry if present, else tracked_price.
    anchor = pick.get("entry") or pick.get("tracked_price")
    if anchor:
        try:
            pick["current_pl_pct"] = (last_close - float(anchor)) / float(anchor) * 100
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    pick["status_updated_at"] = now.isoformat()
    return pick


@st.cache_data(ttl=600, show_spinner=False)
def _sweep_open_picks_token() -> str:
    """Run one full sweep across every open pick. Cached for 10 minutes
    so re-renders within that window don't re-hit yfinance. Returns a
    sentinel timestamp the caller can ignore — the side effect is the
    JSON log being updated."""
    rows = _load_log()
    if not rows:
        return datetime.utcnow().isoformat()
    changed = False
    for r in rows:
        if r.get("status") != "open":
            continue
        before = json.dumps(r, sort_keys=True, default=str)
        _refresh_pick_status(r)
        after = json.dumps(r, sort_keys=True, default=str)
        if before != after:
            changed = True
    if changed:
        _save_log(rows)
    return datetime.utcnow().isoformat()


@st.cache_data(ttl=3600, show_spinner=False)
def compute_verdict_trend(symbol: str, weeks: int = 13) -> List[Dict[str, Any]]:
    """Run analyze_symbol_as_of at weekly intervals across the last
    `weeks` weeks, then append today's analysis as the final point.
    Cached for an hour — re-runs of the same symbol within that
    window are essentially free.

    Hardened (Session 11) against intermittent yfinance flakiness:
      - Each per-week call is wrapped in try/except so one bad week
        doesn't kill the rest of the sweep.
      - A small inter-call delay throttles the burst, which keeps us
        below yfinance's rate-limit threshold during a fresh scan.
    """
    from datetime import date as _date
    results: List[Dict[str, Any]] = []
    today_d = _date.today()
    for w in range(weeks, 0, -1):
        d = today_d - timedelta(days=7 * w)
        try:
            a = analyze_symbol_as_of(symbol, d.isoformat())
        except Exception:
            # Skip this week silently; the trend is best-effort.
            time.sleep(0.1)
            continue
        if a is None:
            time.sleep(0.1)
            continue
        results.append({
            "date": d.isoformat(),
            "score": float(a.get("buy_score") or 0),
            "verdict": a.get("verdict", ""),
            "category": _verdict_category(a.get("verdict", "")) or "OTHER",
            "current_price": a.get("current_price"),
        })
        # Throttle slightly between fresh fetches to avoid Yahoo
        # rate-limiting the burst. Cache hits skip yfinance entirely
        # so this only matters on a cold cache.
        time.sleep(0.1)
    try:
        today_a = analyze_symbol(symbol)
    except Exception:
        today_a = None
    if today_a:
        results.append({
            "date": today_d.isoformat(),
            "score": float(today_a.get("buy_score") or 0),
            "verdict": today_a.get("verdict", ""),
            "category": _verdict_category(today_a.get("verdict", "")) or "OTHER",
            "current_price": today_a.get("current_price"),
        })
    return results


# Defaults for the experimental weight sliders. Mirror
# core.trade_advisor.TradeConfig.WEIGHTS — these are the *actual* section
# weights driving analysis["buy_score"], not config.SCORING_WEIGHTS
# (which feeds a different fundamental+technical composite path used by
# scoring_engine.py). Backend is frozen, so we re-declare here rather
# than import; values must stay in sync if cfg.WEIGHTS ever changes.
_DEFAULT_INDICATOR_WEIGHTS: Dict[str, int] = {
    "trend":          18,
    "location":       20,
    "setup":          15,
    "volume":         10,
    "momentum":       15,
    "candles":         7,
    "risk_reward":    10,
    "market_context":  5,
}

# Pretty labels for the slider rows. Keys must match analysis["sections"].
_INDICATOR_LABELS: Dict[str, str] = {
    "trend":          "Trend",
    "location":       "Location",
    "setup":          "Setup",
    "volume":         "Volume",
    "momentum":       "Momentum",
    "candles":        "Candlesticks",
    "risk_reward":    "Risk / Reward",
    "market_context": "Market Context",
}


def render_deepdive_indicator_weights(symbol: str,
                                      analysis: Optional[Dict[str, Any]]) -> None:
    """Experimental sandbox: 8 sliders matching the actual section weights."""
    if not analysis:
        return

    with st.expander("⚖️ Indicator Weights (Experimental)", expanded=False):
        st.caption(
            "Adjust how much each indicator contributes to the score. "
            "Changes recompute live for THIS analysis only — they don't "
            "persist or affect other pages."
        )

        sections = analysis.get("sections") or {}
        state_key = f"indicator_weights_{symbol}"
        if state_key not in st.session_state:
            st.session_state[state_key] = dict(_DEFAULT_INDICATOR_WEIGHTS)

        reset_key = f"_reset_indicator_weights_{symbol}"
        if st.session_state.get(reset_key):
            st.session_state[state_key] = dict(_DEFAULT_INDICATOR_WEIGHTS)
            for sec_key in _DEFAULT_INDICATOR_WEIGHTS:
                st.session_state.pop(f"weight_slider_{symbol}_{sec_key}", None)
            st.session_state[reset_key] = False
            st.rerun()

        keys = list(_DEFAULT_INDICATOR_WEIGHTS.keys())
        half = (len(keys) + 1) // 2
        col_a, col_b = st.columns(2)
        user_weights: Dict[str, int] = {}
        for col, group in ((col_a, keys[:half]), (col_b, keys[half:])):
            with col:
                for sec_key in group:
                    default = _DEFAULT_INDICATOR_WEIGHTS[sec_key]
                    stored = st.session_state[state_key].get(sec_key, default)
                    val = st.slider(
                        f"{_INDICATOR_LABELS[sec_key]} ({default}%)",
                        min_value=0, max_value=100, value=int(stored),
                        key=f"weight_slider_{symbol}_{sec_key}",
                    )
                    user_weights[sec_key] = val
        st.session_state[state_key] = dict(user_weights)

        total = sum(user_weights.values())
        sum_color = "#16a34a" if total == 100 else "#dc2626"
        st.markdown(
            f"<div style='font-size:14px;'>Sum: "
            f"<b style='color:{sum_color};'>{total}%</b>"
            + ("" if total == 100 else "  ⚠️ should equal 100%")
            + "</div>",
            unsafe_allow_html=True,
        )

        btn_a, btn_b = st.columns(2)
        with btn_a:
            if st.button("🔄 Reset to defaults", key=f"reset_w_{symbol}",
                         use_container_width=True):
                st.session_state[reset_key] = True
                st.rerun()
        with btn_b:
            recompute = st.button("📊 Recompute score with my weights",
                                  key=f"recompute_w_{symbol}",
                                  use_container_width=True)

        if not recompute:
            return

        if total <= 0:
            st.warning("All weights are zero — no score to compute.")
            return

        contributing = 0.0
        weight_sum = 0.0
        missing: List[str] = []
        for sec_key, weight in user_weights.items():
            if weight <= 0:
                continue
            sec = sections.get(sec_key)
            if sec is None:
                missing.append(_INDICATOR_LABELS.get(sec_key, sec_key))
                continue
            try:
                score = float(sec.get("score", 0) or 0)
            except (TypeError, ValueError):
                continue
            contributing += score * weight
            weight_sum += weight

        if weight_sum <= 0:
            st.warning("None of the active weights matched a section in this analysis.")
            return

        new_score = contributing / weight_sum
        original = float(analysis.get("buy_score") or 0)
        delta = new_score - original
        delta_color = "#16a34a" if delta > 0 else "#dc2626" if delta < 0 else "#475569"
        st.markdown(
            f"""
            <div style="padding:12px 16px;border-radius:8px;background:#f1f5f9;
                        margin-top:8px;">
              <span style="color:#475569;">Original:</span>
              <b>{original:.0f}/100</b>
              &nbsp;&nbsp;|&nbsp;&nbsp;
              <span style="color:#475569;">Your weights:</span>
              <b>{new_score:.0f}/100</b>
              &nbsp;&nbsp;|&nbsp;&nbsp;
              <span style="color:#475569;">Delta:</span>
              <b style="color:{delta_color};">{delta:+.0f} pts</b>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(
            "⚠️ Simplified linear recombination — avoid penalties and regime tilts "
            "are NOT replicated here."
        )
        for name in missing:
            st.warning(f"Could not apply weight for {name} (section not present).")


def render_deepdive_verdict_trend(symbol: str):
    st.subheader("📈 Quality Score Trend (Last ~90 Days)")
    st.caption(
        "How the system's 0–100 quality score for this stock has evolved over "
        "the past 13 weeks. Shows whether the current reading is fresh or "
        "sustained — it is not a prediction and not a buy/sell signal."
    )

    state_key = f"vtrend_run_{symbol}"
    if not st.session_state.get(state_key):
        if st.button(
            "🔄 Compute trend (slow, ~30-60s)",
            key=f"vtrend_btn_{symbol}",
        ):
            st.session_state[state_key] = True
            st.rerun()
        return

    # User clicked the button on a prior run — render the trend.
    with st.spinner("Running 13 historical analyses (one per week)…"):
        try:
            points = compute_verdict_trend(symbol, weeks=13)
        except Exception:
            points = []

    if len(points) < 3:
        st.info("Not enough historical data to plot a trend.")
        return

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    df = pd.DataFrame(points)
    df["date_dt"] = pd.to_datetime(df["date"])

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.6, 0.4], vertical_spacing=0.06,
    )

    # Marker color by non-directional quality band (derived from the score),
    # never by a buy/sell verdict.
    from istock.model.scorer import quality_band_from_score
    df["band"] = df["score"].apply(quality_band_from_score)
    colors = [_band_color(b) for b in df["band"]]

    # Composite score line (top subplot)
    fig.add_trace(go.Scatter(
        x=df["date_dt"], y=df["score"], mode="lines+markers",
        name="Composite score",
        line=dict(color="#94a3b8", width=2),
        marker=dict(color=colors, size=10,
                    line=dict(color="#0f172a", width=1)),
        hovertemplate=(
            "<b>%{x|%Y-%m-%d}</b><br>"
            "Score: %{y:.0f}<br>"
            "Quality: %{customdata[0]}<br>"
            "Price: $%{customdata[1]:.2f}"
            "<extra></extra>"
        ),
        customdata=df[["band", "current_price"]].values,
    ), row=1, col=1)

    # Reference lines at the quality-band cutoffs: 55 (Solid) and 65 (Strong).
    fig.add_hline(y=55, line=dict(color="#64748b", dash="dot", width=1),
                  row=1, col=1)
    fig.add_hline(y=65, line=dict(color="#16a34a", dash="dot", width=1),
                  row=1, col=1)

    # Price line (bottom subplot)
    fig.add_trace(go.Scatter(
        x=df["date_dt"], y=df["current_price"], mode="lines+markers",
        name="Stock price",
        line=dict(color="#2563eb", width=1.5),
        marker=dict(size=6),
    ), row=2, col=1)

    fig.update_layout(
        height=460,
        margin=dict(l=10, r=10, t=20, b=10),
        hovermode="x unified",
        template="plotly_dark",
        showlegend=False,
    )
    fig.update_yaxes(title_text="Score", range=[0, 100], row=1, col=1)
    fig.update_yaxes(title_text="Price", row=2, col=1)
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    if st.button("🗑 Reset trend", key=f"vtrend_reset_{symbol}"):
        st.session_state[state_key] = False
        st.rerun()


def render_deepdive_chart(symbol: str, tech: Optional[Dict[str, Any]],
                          analysis: Optional[Dict[str, Any]],
                          cutoff: Optional[str] = None):
    st.subheader("📊 Price Chart with Reference Levels")

    # Timeframe selector — keyed per-symbol so switching tickers
    # doesn't drag preferences from a prior view.
    interval_label_map = {
        "Daily": "1d", "1H": "1h", "15m": "15m", "5m": "5m", "2m": "2m",
    }
    label_choice = st.radio(
        "Timeframe",
        options=list(interval_label_map.keys()),
        horizontal=True,
        key=f"deepdive_interval_{symbol}",
        label_visibility="collapsed",
    )
    interval = interval_label_map[label_choice]

    ohlc = fetch_ohlc(symbol, interval, cutoff=cutoff)
    fell_back = False
    if not ohlc and interval != "1d":
        # Intraday fetch empty (market closed, illiquid ticker, etc.) —
        # fall back silently to daily so the user still sees a chart.
        st.info("No intraday data available for this timeframe. Try Daily or 1H.")
        ohlc = fetch_ohlc(symbol, "1d", cutoff=cutoff)
        interval = "1d"
        fell_back = True
    if not ohlc:
        st.warning("Chart data temporarily unavailable.")
        return

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    df = pd.DataFrame(ohlc)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    # Scale MA windows with the chosen interval so short intraday charts
    # don't try to draw an MA200 across 5 days of 15-minute candles.
    ma_windows = INTERVAL_MA_WINDOWS.get(interval, [20, 50, 200])
    for w in ma_windows:
        df[f"MA{w}"] = df["Close"].rolling(w, min_periods=1).mean()

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.3], vertical_spacing=0.04,
        subplot_titles=("", ""),
    )

    fig.add_trace(go.Candlestick(
        x=df["Date"], open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        name="Price",
        increasing_line_color="#16a34a",
        decreasing_line_color="#dc2626",
    ), row=1, col=1)

    # Styled line config per window — indexed so we gracefully skip
    # longer windows that aren't in ma_windows for short intraday charts.
    ma_style = {
        20:  {"color": "#94a3b8", "width": 1.0},
        50:  {"color": "#f97316", "width": 1.5},
        100: {"color": "#a855f7", "width": 1.8},
        200: {"color": "#2563eb", "width": 2.0},
    }
    for w in ma_windows:
        style = ma_style.get(w, {"color": "#94a3b8", "width": 1})
        fig.add_trace(go.Scatter(
            x=df["Date"], y=df[f"MA{w}"], name=f"MA{w}",
            line=dict(color=style["color"], width=style["width"]),
        ), row=1, col=1)

    # Volume bars colored by candle direction.
    vol_colors = [
        "#16a34a" if c >= o else "#dc2626"
        for c, o in zip(df["Close"], df["Open"])
    ]
    fig.add_trace(go.Bar(
        x=df["Date"], y=df["Volume"], name="Volume",
        marker_color=vol_colors, showlegend=False,
    ), row=2, col=1)

    # S/R horizontal lines from the technicals analyzer.
    sr = (tech or {}).get("support_resistance") or {}
    sr_lines = [
        ("pivot", "Pivot", "#64748b", "dash"),
        ("support_1", "S1", "#16a34a", "dash"),
        ("support_2", "S2", "#22c55e", "dot"),
        ("resistance_1", "R1", "#dc2626", "dash"),
        ("resistance_2", "R2", "#ef4444", "dot"),
    ]
    for key, label, color, dashstyle in sr_lines:
        val = sr.get(key)
        if val is None:
            continue
        fig.add_hline(
            y=float(val), line=dict(color=color, dash=dashstyle, width=1),
            annotation_text=f"{label} {val:.2f}",
            annotation_position="right",
            annotation_font=dict(color=color, size=10),
            row=1, col=1,
        )

    # Reference levels (Entry/Stop/T1/T2) — non-directional: drawn whenever the
    # engine derived support/resistance-based levels, regardless of any verdict.
    # They frame a typical entry / invalidation / profit-taking price, not a call.
    # The risk + reward zones make the R:R visible at a glance.
    has_buy_levels = False
    if analysis and (analysis.get("entry") or analysis.get("stop_loss")):
        entry = analysis.get("entry") or 0
        stop = analysis.get("stop_loss") or 0
        targets = analysis.get("targets") or []
        t1 = targets[0] if len(targets) >= 1 else 0
        t2 = targets[1] if len(targets) >= 2 else 0

        # Zones — drawn first so the lines render above them.
        if entry and stop and stop < entry:
            fig.add_hrect(
                y0=stop, y1=entry,
                fillcolor="rgba(239,68,68,0.12)",
                line_width=0, layer="below", row=1, col=1,
            )
        if entry and t1 and t1 > entry:
            fig.add_hrect(
                y0=entry, y1=t1,
                fillcolor="rgba(34,197,94,0.12)",
                line_width=0, layer="below", row=1, col=1,
            )
        if t1 and t2 and t2 > t1:
            fig.add_hrect(
                y0=t1, y1=t2,
                fillcolor="rgba(34,197,94,0.06)",
                line_width=0, layer="below", row=1, col=1,
            )

        # Lines — entry blue, stop red, T1/T2 green.
        trade_lines = []
        if entry:
            trade_lines.append((entry, "📍 Entry", "#2563eb", "solid", 2))
        if stop:
            trade_lines.append((stop, "🛑 Stop", "#dc2626", "solid", 2.5))
        if t1:
            trade_lines.append((t1, "🎯 T1", "#16a34a", "solid", 2))
        if t2:
            trade_lines.append((t2, "🎯 T2", "#16a34a", "dash", 2))
        for val, label, color, dashstyle, width in trade_lines:
            if not val:
                continue
            fig.add_hline(
                y=float(val),
                line=dict(color=color, dash=dashstyle, width=width),
                annotation_text=f"{label} ${val:.2f}",
                annotation_position="left",
                annotation_font=dict(color=color, size=11),
                row=1, col=1,
            )
        has_buy_levels = True

    # Range-selector buttons depend on the active interval. For Daily
    # we drop 1M (default visible is 2Y, so 1M would zoom in too hard
    # from the default). Intraday sets are constrained by the matching
    # period (e.g. 2m's period is 5d so MAX = 5d).
    rangeselector_buttons_by_interval = {
        "1d": [
            dict(count=3, label="3M", step="month", stepmode="backward"),
            dict(count=6, label="6M", step="month", stepmode="backward"),
            dict(count=1, label="1Y", step="year",  stepmode="backward"),
            dict(count=2, label="2Y", step="year",  stepmode="backward"),
            dict(count=5, label="5Y", step="year",  stepmode="backward"),
            dict(step="all", label="MAX"),
        ],
        "1h": [
            dict(count=5, label="5D", step="day",   stepmode="backward"),
            dict(count=1, label="1M", step="month", stepmode="backward"),
            dict(step="all", label="MAX"),
        ],
        "15m": [
            dict(count=1, label="1D", step="day",   stepmode="backward"),
            dict(count=5, label="5D", step="day",   stepmode="backward"),
            dict(step="all", label="MAX"),
        ],
        "5m": [
            dict(count=1, label="1D", step="day",   stepmode="backward"),
            dict(count=5, label="5D", step="day",   stepmode="backward"),
            dict(step="all", label="MAX"),
        ],
        "2m": [
            dict(count=1, label="1D", step="day",   stepmode="backward"),
            dict(step="all", label="MAX"),
        ],
    }
    rangeselector_buttons = rangeselector_buttons_by_interval.get(
        interval, rangeselector_buttons_by_interval.get("15m"),
    )

    # Default visible window:
    #   Daily   → last ~2 years of the 5y fetch (per user request)
    #   Intraday → no explicit range; let plotly autorange across the
    #              tightly-scoped fetch period (5d for 2m, 1mo for the rest).
    last_dt = pd.to_datetime(df["Date"].iloc[-1])
    initial_x_range: Optional[List[Any]] = None
    if interval == "1d" and len(df) > 0:
        x_start = last_dt - pd.Timedelta(days=730)
        initial_x_range = [x_start, last_dt]

    # Hide weekend gaps for every timeframe; for intraday also hide the
    # overnight/after-hours window. yfinance with prepost=True returns
    # extended-hours bars too, so we still show 4am-9:30am and 4pm-8pm
    # by NOT clipping pre/post — only deep-night 8pm-4am gets bridged.
    rangebreaks: List[Dict[str, Any]] = [dict(bounds=["sat", "mon"])]
    if interval != "1d":
        rangebreaks.append(dict(bounds=[20, 4], pattern="hour"))

    fig.update_layout(
        height=720,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="x unified",
        dragmode="pan",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.15,         # below the chart so it can't overlap the
            xanchor="left",  # range-selector buttons at the top.
            x=0,
        ),
        template="plotly_dark",
    )
    xaxis_kwargs = dict(
        rangeselector=dict(buttons=rangeselector_buttons),
        rangeslider=dict(visible=False),
        rangebreaks=rangebreaks,
        row=1, col=1,
    )
    if initial_x_range is not None:
        xaxis_kwargs["range"] = initial_x_range
    fig.update_xaxes(**xaxis_kwargs)
    # Mirror the rangebreaks on the volume axis so its bars line up with
    # the candlesticks (otherwise the bottom subplot keeps the gaps).
    fig.update_xaxes(rangebreaks=rangebreaks, row=2, col=1)
    fig.update_yaxes(title_text="Price", row=1, col=1)
    # Volume y-axis: pin to the max of the *visible* window for Daily so
    # an old massive spike doesn't crush recent bars. For intraday keep
    # autorange (the visible window is already short). Plotly does NOT
    # auto-rescale volume when the user zooms via range buttons / scroll
    # — that's a known plotly limitation; this only governs the default
    # view.
    if interval == "1d" and initial_x_range is not None:
        # Sum of bars whose Date is within the visible window
        visible_mask = (
            pd.to_datetime(df["Date"]) >= initial_x_range[0]
        ) & (
            pd.to_datetime(df["Date"]) <= initial_x_range[1]
        )
        visible_vol = df.loc[visible_mask, "Volume"]
        if not visible_vol.empty:
            visible_vol_max = float(visible_vol.max()) * 1.10
            fig.update_yaxes(title_text="Volume", range=[0, visible_vol_max], row=2, col=1)
        else:
            fig.update_yaxes(title_text="Volume", autorange=True, row=2, col=1)
    else:
        fig.update_yaxes(title_text="Volume", autorange=True, row=2, col=1)

    plotly_config = {
        "scrollZoom": True,
        "displayModeBar": True,
        "modeBarButtonsToAdd": ["drawline", "eraseshape"],
    }
    st.plotly_chart(fig, use_container_width=True, config=plotly_config)

    with st.expander("📖 What do these lines mean?"):
        st.markdown(
            """
**Pivot (P)** — The day's central price level. Acts as the baseline; price above pivot = bullish bias, below = bearish.

**Resistance 1 (R1) / Resistance 2 (R2)** — Price levels above the current price where selling pressure is expected. R2 is stronger / further away.

**Support 1 (S1) / Support 2 (S2)** — Price levels below the current price where buying pressure is expected. S2 is stronger / further away.

**Entry / Stop / Targets** — Reference levels derived from support/resistance (shown for higher-scoring setups). Entry ≈ a typical buy level, Stop ≈ where a thesis would be wrong, Targets (T1, T2) ≈ profit-taking levels. Informational, not a trade instruction.

**Risk Zone (red shade)** — How much you stand to lose per share if the stop hits.

**Reward Zone (green shade)** — How much you stand to gain per share if Target 1 hits. Visual ratio of green-area to red-area = your risk:reward.
"""
        )
        if not has_buy_levels:
            st.caption(
                "Entry / Stop / Targets and the risk/reward zones appear only "
                "when the engine has derived reference levels for this name."
            )


def render_deepdive_cheat_sheet(symbol: str, tech: Optional[Dict[str, Any]],
                                current_price: Optional[float]):
    """Barchart-style price-levels cheat sheet. Aggregates every level we
    already have from the technicals analyzer, sorts by price
    descending, and inserts the current price as a highlighted row
    in the middle. Filters anything more than ±25% from current to
    keep the table actionable."""
    if not tech or not current_price:
        return

    sr = tech.get("support_resistance") or {}
    ma = tech.get("moving_averages") or {}
    mom = tech.get("momentum") or {}

    # Candidate levels with their type label. None values are dropped.
    candidates: List[tuple[Optional[float], str]] = [
        (mom.get("high_52w"),         "52-Week High"),
        (sr.get("resistance_2"),      "Resistance 2 (R2)"),
        (sr.get("resistance_1"),      "Resistance 1 (R1)"),
        (sr.get("recent_high_20d"),   "Recent High (20d)"),
        (sr.get("pivot"),             "Pivot"),
        (sr.get("recent_low_20d"),    "Recent Low (20d)"),
        (sr.get("support_1"),         "Support 1 (S1)"),
        (sr.get("support_2"),         "Support 2 (S2)"),
        (mom.get("low_52w"),          "52-Week Low"),
        (ma.get("sma_20"),            "MA20"),
        (ma.get("sma_50"),            "MA50"),
        (ma.get("sma_200"),           "MA200"),
    ]

    cur = float(current_price)
    rows: List[Dict[str, Any]] = []
    for price, label in candidates:
        if price is None:
            continue
        try:
            p = float(price)
        except (TypeError, ValueError):
            continue
        # ±25% filter
        if cur > 0 and abs(p - cur) / cur > 0.25:
            continue
        side = "resistance" if p > cur else ("support" if p < cur else "current")
        rows.append({
            "Price": p,
            "Level Type": label,
            "Distance %": (p - cur) / cur * 100 if cur else 0.0,
            "_side": side,
        })

    if not rows:
        return

    rows.append({
        "Price": cur,
        "Level Type": "← Current Price",
        "Distance %": 0.0,
        "_side": "current",
    })
    # Sort by price descending (Barchart convention).
    rows.sort(key=lambda r: -r["Price"])

    df = pd.DataFrame(rows)

    def _row_style(row):
        if row["_side"] == "resistance":
            return ["background-color: rgba(239,68,68,0.10)"] * len(row)
        if row["_side"] == "support":
            return ["background-color: rgba(34,197,94,0.10)"] * len(row)
        return ["background-color: rgba(148,163,184,0.20); font-weight: bold"] * len(row)

    visible = df[["Price", "Level Type", "Distance %"]].copy()
    styled = (
        df.style.apply(_row_style, axis=1)
        .format({"Price": "{:.2f}", "Distance %": "{:+.2f}%"})
        .hide(axis="columns", subset=["_side"])
    )

    with st.expander("📋 Price Levels Cheat Sheet"):
        st.dataframe(styled, hide_index=True, use_container_width=True)
        st.caption(
            "Resistance levels (red) tend to slow upward moves. "
            "Support levels (green) tend to slow downward moves. "
            "Distances are from the latest closing price."
        )


def render_deepdive_sizing(symbol: str, analysis: Optional[Dict[str, Any]]):
    st.subheader("💰 Suggested Position Size")
    verdict = ((analysis or {}).get("verdict") or "").upper()
    if "BUY" not in verdict:
        st.caption("Risk-based size calculator — enter a position size and it works out "
                   "a risk-appropriate share count. Informational; not a recommendation to trade.")
        return

    # Portfolio size = current holdings value (same as Page 1's derivation).
    rows = build_holdings_rows()
    totals = portfolio_totals(rows)
    cash_inr = float(USER_PROFILE.get("monthly_investment", 25_000))
    portfolio_inr = max(totals["current_inr"], cash_inr)

    sizing = compute_sizing(symbol, portfolio_inr, cash_inr)
    if not sizing:
        st.info("Position sizer didn't return a result for this symbol "
                "(possibly no valid stop price).")
        return

    entry = sizing.get("entry_price") or 0
    stop = sizing.get("stop_loss") or 0
    approved = sizing.get("approved", False)
    shares = sizing.get("shares", 0)
    stop_dist = (entry - stop) if (entry and stop) else 0
    stop_dist_pct = (stop_dist / entry * 100) if entry else 0

    left, right = st.columns(2)
    with left:
        st.markdown("**Sizing Decision**")
        if approved:
            st.markdown(
                f"<div style='font-size:28px;font-weight:700;color:#16a34a;'>"
                f"✅ Approved: {shares} shares</div>",
                unsafe_allow_html=True,
            )
            _cur = _current_currency()
            _fx = fetch_usd_inr()
            st.markdown(_md_dollars(
                f"- Notional: {_fmt_currency(sizing['position_value_inr'], _cur, _fx)}\n"
                f"- Risk amount: {_fmt_currency(sizing['risk_amount_inr'], _cur, _fx)}\n"
                f"- Portfolio %: {sizing['risk_pct_of_portfolio']:.2f}%"
            ))
        else:
            st.markdown(
                "<div style='font-size:28px;font-weight:700;color:#dc2626;'>"
                "❌ Rejected</div>",
                unsafe_allow_html=True,
            )
            reason = sizing.get("rejection_reason") or "Pre-check failed."
            st.markdown(f"**Reason:** {reason}")
        winning = sizing.get("winning_method") or "—"
        st.caption(f"Winning method: **{winning}**" if winning != "—" else "Winning method: — (no methods evaluated)")

    with right:
        st.markdown("**Risk Breakdown**")
        rr = (analysis or {}).get("risk_reward") or 0
        risk_per_share = stop_dist or 0
        st.dataframe(_kv_table([
            ("Entry",              f"{entry:.2f}" if entry else "—"),
            ("Stop",               f"{stop:.2f}" if stop else "—"),
            ("Stop distance",      f"{stop_dist:.2f} ({stop_dist_pct:.2f}%)" if stop else "—"),
            ("Risk per share",     f"{risk_per_share:.2f}" if risk_per_share else "—"),
            ("Risk : Reward",      f"1:{rr:.1f}" if rr else "—"),
            ("Portfolio heat",     f"{sizing.get('risk_pct_of_portfolio', 0):.2f}%"),
            ("Sector exposure",    "— (not tracked yet)"),
        ]), hide_index=True, use_container_width=True)

    with st.expander("🔬 All 4 sizing methods compared"):
        methods = sizing.get("method_results") or []
        if not methods:
            st.caption(
                "Method-by-method breakdown not available for this trade. "
                "(The sizer short-circuits before running the four methods "
                "when a pre-check — score, R:R, etc. — fails.)"
            )
            return
        _cur = _current_currency()
        _fx = fetch_usd_inr()
        mrows = [
            {
                "Method": m["method"],
                "Shares": f"{m['shares']:.1f}",
                "Notional": _fmt_currency(m["notional"], _cur, _fx) if m.get("notional") else "—",
                "Used": "✅ winning" if m["used"] else "",
                "Note": m.get("note", ""),
            }
            for m in methods
        ]
        st.dataframe(pd.DataFrame(mrows), hide_index=True, use_container_width=True)


# High-signal check patterns, in display-priority order: location
# (support/resistance) first — the user's most-watched parameters — then
# setup, trend strength, momentum/flow. Anything not matched here is treated
# as lower-signal "noise" and tucked into an expander (#14).
_IMPORTANT_CHECK_PATTERNS: tuple[str, ...] = (
    # location / structure (shown first)
    "near support", "support level is strong", "support is strong",
    "near resistance", "resistance level is strong",
    # setup
    "setup detected", "uptrend present", "pullback", "breakout", "bounce", "reversal",
    # trend strength
    "adx", "higher high", "higher low", "ma20 slope", "ma alignment",
    # momentum / flow
    "rsi divergence", "volume spike", "macd bullish crossover", "obv",
)


def _important_rank(name: str) -> Optional[int]:
    """Return the priority index if `name` is a high-signal check, else None.
    Lower index = shown earlier."""
    low = (name or "").lower()
    for i, pat in enumerate(_IMPORTANT_CHECK_PATTERNS):
        if pat in low:
            return i
    return None


def _extract_adx(sections: Dict[str, Any]) -> Optional[float]:
    """Pull the raw ADX value from the trend section's ADX check, if present."""
    for sec in (sections or {}).values():
        for c in sec.get("checks", []) or []:
            if "adx" in (c.get("name", "") or "").lower():
                val = c.get("value")
                try:
                    v = float(val)
                except (TypeError, ValueError):
                    continue
                if v > 0:
                    return v
    return None


def _render_adx_banner(sections: Dict[str, Any]) -> None:
    """#13 — surface trend strength FIRST. ADX < 20 means no trend, so
    trend-following signals are unreliable; 20-25 is a weak/gray zone."""
    adx = _extract_adx(sections)
    if adx is None:
        return
    if adx < 20:
        st.error(
            f"📉 **No trend (ADX = {adx:.1f}).** The market isn't trending — "
            "trend-following signals (breakouts, MA alignment, HH/HL) are "
            "unreliable here. Favor mean-reversion / range setups or wait."
        )
    elif adx < 25:
        st.warning(
            f"⚠️ **Weak trend (ADX = {adx:.1f}).** Borderline — trend signals "
            "are only moderately reliable. Treat trend setups with caution."
        )
    else:
        st.success(f"✅ **Trending market (ADX = {adx:.1f}).** Trend setups are reliable.")


def _render_reason_rows(rows: List[tuple[str, str, str]], color: str, glyph: str,
                        empty_msg: str, cap: int = 25) -> None:
    """Render a list of (section_label, name, detail) reason rows."""
    if not rows:
        st.caption(empty_msg)
        return
    for section_label, name, detail in rows[:cap]:
        st.markdown(
            f"<div style='color:{color};'>{glyph} <b>{section_label}</b>: {name}"
            + (f" — <span style='color:#475569;'>{detail}</span>" if detail else "")
            + "</div>",
            unsafe_allow_html=True,
        )
    if len(rows) > cap:
        st.caption(f"… and {len(rows) - cap} more.")


def render_deepdive_reasoning(analysis: Optional[Dict[str, Any]]):
    st.subheader("🧠 Why This Score?")
    if not analysis:
        st.warning("Reasoning temporarily unavailable.")
        return

    sections = analysis.get("sections") or {}

    # #13 — trend-strength banner up top, before any trend-based reasoning.
    _render_adx_banner(sections)

    # Partition every check into supporting/risk AND important/noise (#14).
    # Each entry: (rank_or_None, section_label, name, detail).
    passed_imp: List[tuple] = []
    passed_noise: List[tuple] = []
    failed_imp: List[tuple] = []
    failed_noise: List[tuple] = []
    for key, sec in sections.items():
        section_label = sec.get("name", key)
        for c in sec.get("checks", []):
            name = c.get("name", "")
            rank = _important_rank(name)
            entry = (rank, section_label, name, c.get("detail", ""))
            if c.get("passed"):
                (passed_imp if rank is not None else passed_noise).append(entry)
            else:
                (failed_imp if rank is not None else failed_noise).append(entry)

    # Avoid flags are always high-signal risks.
    for flag in analysis.get("avoid_flags") or []:
        failed_imp.append((-1, "Avoid Check", "Avoid flag", str(flag)))

    # Sort important lists by priority rank; drop the rank for rendering.
    def _prep(rows: List[tuple]) -> List[tuple[str, str, str]]:
        rows = sorted(rows, key=lambda r: (r[0] if r[0] is not None else 999))
        return [(r[1], r[2], r[3]) for r in rows]

    passed_imp_r, passed_noise_r = _prep(passed_imp), _prep(passed_noise)
    failed_imp_r, failed_noise_r = _prep(failed_imp), _prep(failed_noise)
    n_passed = len(passed_imp_r) + len(passed_noise_r)
    n_failed = len(failed_imp_r) + len(failed_noise_r)

    # ── Key Factors (high-signal only) ──────────────────────────────────────
    st.markdown("#### 🎯 Key Factors")
    st.caption("Location, setup and trend-strength signals — the ones that move the needle.")
    left, right = st.columns(2)
    with left:
        st.markdown(f"**✅ Supporting** ({len(passed_imp_r)})")
        _render_reason_rows(passed_imp_r, "#16a34a", "✓", "No key supporting factors.")
    with right:
        st.markdown(f"**⚠️ Risk** ({len(failed_imp_r)})")
        _render_reason_rows(failed_imp_r, "#ca8a04", "✗", "No key risk factors.")

    # ── Other signals (lower-signal noise, collapsed) ───────────────────────
    n_other = len(passed_noise_r) + len(failed_noise_r)
    if n_other:
        with st.expander(f"➕ Other signals ({n_other}) — lower-signal, expand if needed",
                         expanded=False):
            o_left, o_right = st.columns(2)
            with o_left:
                st.markdown(f"**✅ Supporting** ({len(passed_noise_r)})")
                _render_reason_rows(passed_noise_r, "#16a34a", "✓", "None.")
            with o_right:
                st.markdown(f"**⚠️ Risk** ({len(failed_noise_r)})")
                _render_reason_rows(failed_noise_r, "#ca8a04", "✗", "None.")

    # Plain-English summary — FullAnalysis has no `verdict_reasoning` field,
    # so we synthesize one from the counts we already have.
    st.markdown("---")
    passed, failed = passed_imp_r + passed_noise_r, failed_imp_r + failed_noise_r
    score = analysis.get("buy_score", 0)
    setup = analysis.get("setup_type") or "none"
    summary = (
        f"This stock scores **{score:.0f}/100** with "
        f"**{len(passed)} supporting factors** and "
        f"**{len(failed)} risk factors**. "
        f"The dominant setup is **{setup}**."
    )
    key_obs = analysis.get("key_observations") or []
    if key_obs:
        summary += " Observations: " + "; ".join(key_obs[:3]) + "."
    st.markdown(summary)


def render_deepdive_summary_bar(analysis: Optional[Dict[str, Any]]):
    if not analysis:
        return
    score = analysis.get("buy_score") or 0
    confidence = analysis.get("confidence") or "—"
    band = _score_band(score)
    color = _band_color(band)
    st.markdown(
        f"""
        <div style="margin-top:24px;padding:16px 22px;border-radius:10px;
                    background:{color}1A;border-left:6px solid {color};
                    display:flex;justify-content:space-between;align-items:center;">
          <div style="font-size:14px;color:#475569;">Quality summary</div>
          <div style="font-size:22px;font-weight:700;color:{color};">
            {band}  ·  {score:.0f} / 100  ·  {confidence}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Page 5 — 📓 Tracked Picks
# --------------------------------------------------------------------------- #

# Outcome → human-readable label + emoji used in the Closed-tab table.
_OUTCOME_LABELS: Dict[str, str] = {
    "hit_target_1":  "🎯 T1 Hit",
    "hit_target_2":  "🎯🎯 T2 Hit",
    "hit_stop":      "🛑 Stop Hit",
    "expired":       "⏰ Expired",
    "closed_manual": "✋ Manual Close",
}


def _is_winning_pick(pick: Dict[str, Any]) -> Optional[bool]:
    """Return True/False for closed picks, None for still-open. Win
    semantics depend on verdict category — for BUY-side picks a win
    means price up since tracking; for HOLD/AVOID a win means price
    down (system was right to say don't buy)."""
    if pick.get("status") == "open":
        return None
    status = pick.get("status")
    if status in ("hit_target_1", "hit_target_2"):
        return True
    if status == "hit_stop":
        return False
    pl = pick.get("current_pl_pct")
    if pl is None:
        return None
    cat = pick.get("verdict_category")
    if cat in ("BUY", "LEAN BUY"):
        return pl > 0
    # HOLD / AVOID / unknown → "win" = price went down since tracked.
    return pl < 0


def _outcome_label(pick: Dict[str, Any]) -> str:
    return _OUTCOME_LABELS.get(pick.get("status", ""), pick.get("status", ""))


def _hold_days(pick: Dict[str, Any], end: Optional[str] = None) -> Optional[int]:
    try:
        start = datetime.fromisoformat(pick.get("tracked_at"))
    except (TypeError, ValueError):
        return None
    end_dt = datetime.utcnow()
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
        except (TypeError, ValueError):
            pass
    return (end_dt - start).days


def _render_tracked_metrics(rows: List[Dict[str, Any]]):
    total = len(rows)
    open_picks = [r for r in rows if r.get("status") == "open"]
    closed = [r for r in rows if r.get("status") != "open"]

    # Win rate uses _is_winning_pick semantics (handles HOLD/AVOID inverse).
    judged = [(_is_winning_pick(r), r) for r in closed]
    judged = [(w, r) for w, r in judged if w is not None]
    win_rate = (sum(1 for w, _r in judged if w) / len(judged) * 100) if judged else None

    pls = [r.get("current_pl_pct") for r in closed if r.get("current_pl_pct") is not None]
    avg_pl = (sum(pls) / len(pls)) if pls else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Picks", total)
    c2.metric("Open", len(open_picks))
    c3.metric(
        "Win Rate",
        f"{win_rate:.1f}%" if win_rate is not None else "N/A",
        help="Closed picks scored as wins. For BUY/LEAN BUY: price up. "
             "For HOLD/AVOID: price down (system was right to say no).",
    )
    c4.metric(
        "Avg P&L %",
        f"{avg_pl:+.2f}%" if avg_pl is not None else "N/A",
        help="Average current P&L across all closed picks.",
    )


def _render_tab_open(rows: List[Dict[str, Any]]):
    open_picks = [r for r in rows if r.get("status") == "open"]
    if not open_picks:
        st.info(
            "No open picks yet. Track some from the Stock Deep-Dive page."
        )
        return

    # Render each pick as its own bordered container so we can put a
    # per-row "Close" button alongside the data (not possible inside
    # st.dataframe today).
    for pick in sorted(open_picks, key=lambda r: r.get("tracked_at", ""), reverse=True):
        cur_pl = pick.get("current_pl_pct")
        pl_color = "#16a34a" if (cur_pl is not None and cur_pl >= 0) else "#dc2626"
        days_open = _hold_days(pick)
        # Pull a LIVE analysis for the dual-verdict render. analyze_symbol
        # is @st.cache_data(ttl=300) and TradeAdvisor.analyze caches v2 to
        # disk per (ticker, date), so this is cheap when warm. Fall back
        # to the rec_log v1-only badge if analysis is unavailable (network
        # off, ticker delisted, etc.). NOTE: rec_log schema is frozen —
        # we never write v2 back into the tracked pick.
        try:
            live_a = analyze_symbol(pick.get("symbol", ""))
        except Exception:
            live_a = None
        verdict_html = (
            _render_dual_verdict_html(live_a)
            if live_a else
            _verdict_badge_html(pick.get("verdict", ""),
                                score=pick.get("score", pick.get("buy_score")))
        )
        with st.container(border=True):
            cols = st.columns([1.0, 1.4, 0.9, 0.9, 0.9, 0.9, 1.1, 0.8])
            cols[0].markdown(f"**{pick.get('symbol', '—')}**")
            cols[1].markdown(verdict_html, unsafe_allow_html=True)
            cols[2].caption(f"{days_open}d open" if days_open is not None else "—")
            cols[3].markdown(
                f"Tracked\n${pick.get('tracked_price') or 0:.2f}"
            )
            cols[4].markdown(
                f"Current\n${pick.get('current_price') or 0:.2f}"
                if pick.get("current_price") is not None else "Current\n—"
            )
            cols[5].markdown(
                f"<span style='color:{pl_color};font-weight:700;'>"
                f"{(cur_pl or 0):+.2f}%</span>" if cur_pl is not None else "—",
                unsafe_allow_html=True,
            )
            cols[6].markdown(
                f"Stop ${pick.get('stop'):.2f}\nT1 ${pick.get('target_1'):.2f}"
                if (pick.get("stop") and pick.get("target_1"))
                else "—"
            )
            close_clicked = cols[7].button(
                "Close", key=f"close_{pick['id']}", use_container_width=True,
            )
            if close_clicked:
                close_price = pick.get("current_price") or pick.get("tracked_price")
                _update_pick(
                    pick["id"],
                    status="closed_manual",
                    closed_at=datetime.utcnow().isoformat(),
                    close_price=float(close_price) if close_price else None,
                    close_reason="manual",
                    status_updated_at=datetime.utcnow().isoformat(),
                )
                st.rerun()


def _render_tab_closed(rows: List[Dict[str, Any]]):
    closed = [r for r in rows if r.get("status") != "open"]
    if not closed:
        st.info("No closed picks yet.")
        return
    table = []
    for r in sorted(closed, key=lambda r: r.get("closed_at") or "", reverse=True):
        tracked = (r.get("tracked_at") or "")[:10]
        closed_d = (r.get("closed_at") or "")[:10] or "—"
        entry = r.get("entry") or r.get("tracked_price") or 0
        exit_p = r.get("close_price") or r.get("current_price") or 0
        pl = r.get("current_pl_pct")
        if pl is None and entry and exit_p:
            pl = (float(exit_p) - float(entry)) / float(entry) * 100
        table.append({
            "Symbol":        r.get("symbol", "—"),
            "Quality":       (_score_band(r.get("score"))
                              if r.get("score") is not None
                              else _verdict_to_band(r.get("verdict", "—"))),
            "Tracked":       tracked,
            "Closed":        closed_d,
            "Outcome":       _outcome_label(r),
            "Hold Days":     _hold_days(r, r.get("closed_at")),
            "Entry $":       f"{float(entry):.2f}" if entry else "—",
            "Exit $":        f"{float(exit_p):.2f}" if exit_p else "—",
            "P&L %":         f"{pl:+.2f}%" if pl is not None else "—",
        })
    st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)


ADVISOR_BACKTEST_PATH = Path(_ROOT) / "results" / "advisor_backtest.json"


def _load_advisor_backtest() -> Optional[Dict[str, Any]]:
    if not ADVISOR_BACKTEST_PATH.exists():
        return None
    try:
        return json.loads(ADVISOR_BACKTEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _humanize_age(iso_ts: Optional[str]) -> str:
    if not iso_ts:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_ts)
    except (TypeError, ValueError):
        return "unknown"
    delta = datetime.utcnow() - dt
    if delta.total_seconds() < 60:
        return "just now"
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def _render_advisor_backtest_section() -> None:
    """Surface the most recent results/advisor_backtest.json. The bake
    happens in scripts/advisor_backtester.py — this helper only reads."""
    st.subheader("🔬 Live Advisor Backtest")
    st.caption(
        "How the live advisor's BUY / LEAN BUY signals would have "
        "performed historically if traded mechanically with the "
        "system's recommended entry / stop / targets and a 60-day "
        "max hold."
    )

    if st.button("🔄 Refresh from disk", key="advisor_bt_refresh"):
        st.rerun()

    state = _load_advisor_backtest()
    if state is None:
        st.info(
            "No backtest results yet. Run "
            "`python -m scripts.advisor_backtester --quick` for a fast "
            "preview, or `python -m scripts.advisor_backtester` for the "
            "full overnight run."
        )
        return

    completed_at = state.get("run_completed_at") or state.get("run_started_at")
    status = state.get("status", "unknown")
    universe_size = state.get("universe_size", 0)
    date_range = state.get("date_range") or {}
    cap = (
        f"Last run: **{_humanize_age(completed_at)}** "
        f"&nbsp;·&nbsp; Status: **{status}** "
        f"&nbsp;·&nbsp; Universe: **{universe_size}** tickers "
        f"&nbsp;·&nbsp; {date_range.get('start', '?')} to "
        f"{date_range.get('end', '?')}"
    )
    st.markdown(cap, unsafe_allow_html=True)

    summary = state.get("summary") or {}
    if not summary:
        st.warning("Backtest file present but summary not yet computed. "
                   "If a run is still in progress, check back when it "
                   "finishes.")
        return

    # ── Top metric strip (4 wide).
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Trades", f"{summary.get('trades', 0):,}")
    m2.metric("Win Rate", f"{summary.get('win_rate_pct', 0):.1f}%")
    m3.metric("Avg P&L", f"{summary.get('avg_pnl_pct', 0):+.2f}%")
    pf = summary.get("profit_factor")
    m4.metric("Profit Factor",
              f"{pf:.2f}" if isinstance(pf, (int, float)) else "n/a")

    # ── Secondary metric strip (4 wide).
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Avg Winner", f"{summary.get('avg_winner_pct', 0):+.2f}%")
    s2.metric("Avg Loser", f"{summary.get('avg_loser_pct', 0):+.2f}%")
    s3.metric("Sharpe (approx)", f"{summary.get('sharpe_approx', 0):.2f}")
    s4.metric("Max DD", f"{summary.get('max_drawdown_pct', 0):.2f}%")

    trades = state.get("trades") or []
    eligible = [t for t in trades
                if t.get("outcome") in {"hit_stop", "hit_t1", "hit_t2", "expired"}
                and t.get("pnl_pct") is not None]

    if not eligible:
        st.caption(
            "No eligible BUY trades resolved within the hold window — "
            "summary stats above will all read zero."
        )
        return

    # ── Per-ticker table.
    by_ticker: Dict[str, List[Dict[str, Any]]] = {}
    for t in eligible:
        by_ticker.setdefault(t.get("ticker", "?"), []).append(t)
    rows_t: List[Dict[str, Any]] = []
    for tk, ts in by_ticker.items():
        wins = sum(1 for t in ts if (t.get("pnl_pct") or 0) > 0)
        avg_pl = sum(float(t["pnl_pct"]) for t in ts) / len(ts)
        rows_t.append({
            "Ticker": tk,
            "Trades": len(ts),
            "Win %": round(wins / len(ts) * 100, 1),
            "Avg P&L %": round(avg_pl, 2),
        })
    rows_t.sort(key=lambda r: (-r["Trades"], -r["Win %"]))
    rows_t = rows_t[:15]
    st.markdown("**Per-ticker performance** (top 15 by trade count)")
    st.dataframe(pd.DataFrame(rows_t), hide_index=True,
                 use_container_width=True)

    # ── Win rate by regime bar chart.
    by_reg: Dict[str, List[Dict[str, Any]]] = {}
    for t in eligible:
        by_reg.setdefault(t.get("regime") or "UNKNOWN", []).append(t)
    reg_rows: List[Dict[str, Any]] = []
    for reg, ts in by_reg.items():
        wins = sum(1 for t in ts if (t.get("pnl_pct") or 0) > 0)
        reg_rows.append({"Regime": reg, "Win %": round(wins / len(ts) * 100, 1),
                         "N": len(ts)})
    if reg_rows and any(r["Regime"] != "UNKNOWN" for r in reg_rows):
        import plotly.express as px
        st.markdown("**Win rate by regime**")
        fig = px.bar(
            pd.DataFrame(reg_rows), x="Regime", y="Win %",
            text=[f"n={r['N']}" for r in reg_rows],
            template="plotly_dark", height=260,
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=10),
                          yaxis_range=[0, 110])
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})


def _render_tab_analytics(rows: List[Dict[str, Any]]):
    # Live Advisor Backtest goes ABOVE the closed-pick analytics so the
    # historical view is visible even when the user has 0 closed picks.
    _render_advisor_backtest_section()
    st.divider()

    closed = [r for r in rows if r.get("status") != "open"]
    if not closed:
        st.info(
            "No closed picks yet. Once picks hit a stop / target / "
            "expire, this tab will show win rate by quality band, by "
            "regime, and a score-vs-outcome scatter."
        )
        return

    import plotly.express as px
    import plotly.graph_objects as go

    # (a) Win rate by verdict category
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for r in closed:
        cat = r.get("verdict_category") or "OTHER"
        by_cat.setdefault(cat, []).append(r)
    cat_rows = []
    for cat, rs in by_cat.items():
        judged = [_is_winning_pick(r) for r in rs]
        judged = [w for w in judged if w is not None]
        wr = (sum(1 for w in judged if w) / len(judged) * 100) if judged else 0
        cat_rows.append({
            "Quality": {"BUY": "Strong+", "LEAN BUY": "Solid"}.get(cat, "Other"),
            "Win %": wr, "N": len(rs),
        })
    cat_df = pd.DataFrame(cat_rows)
    if not cat_df.empty:
        st.markdown("**Win rate by quality band**")
        fig_cat = px.bar(
            cat_df, x="Quality", y="Win %",
            text=cat_df["N"].apply(lambda n: f"n={n}"),
            template="plotly_dark", height=280,
        )
        fig_cat.update_traces(textposition="outside")
        fig_cat.update_layout(margin=dict(l=10, r=10, t=20, b=10), yaxis_range=[0, 110])
        st.plotly_chart(fig_cat, use_container_width=True,
                        config={"displayModeBar": False})

    # (b) Win rate by regime
    by_reg: Dict[str, List[Dict[str, Any]]] = {}
    for r in closed:
        reg = r.get("regime") or "UNKNOWN"
        by_reg.setdefault(reg, []).append(r)
    reg_rows = []
    for reg, rs in by_reg.items():
        judged = [_is_winning_pick(r) for r in rs]
        judged = [w for w in judged if w is not None]
        wr = (sum(1 for w in judged if w) / len(judged) * 100) if judged else 0
        reg_rows.append({"Regime": reg, "Win %": wr, "N": len(rs)})
    reg_df = pd.DataFrame(reg_rows)
    if not reg_df.empty:
        st.markdown("**Win rate by market regime**")
        fig_reg = px.bar(
            reg_df, x="Regime", y="Win %",
            text=reg_df["N"].apply(lambda n: f"n={n}"),
            template="plotly_dark", height=280,
        )
        fig_reg.update_traces(textposition="outside")
        fig_reg.update_layout(margin=dict(l=10, r=10, t=20, b=10), yaxis_range=[0, 110])
        st.plotly_chart(fig_reg, use_container_width=True,
                        config={"displayModeBar": False})

    # (c) Score vs outcome scatter
    scatter_pts = []
    for r in closed:
        pl = r.get("current_pl_pct")
        if pl is None:
            continue
        scatter_pts.append({
            "Score":    float(r.get("score") or 0),
            "P&L %":    float(pl),
            "Outcome":  _outcome_label(r),
            "Symbol":   r.get("symbol", "—"),
        })
    if scatter_pts:
        st.markdown("**Score at tracking vs realized P&L**")
        sc_df = pd.DataFrame(scatter_pts)
        fig_sc = px.scatter(
            sc_df, x="Score", y="P&L %", color="Outcome",
            hover_data=["Symbol"], template="plotly_dark", height=320,
        )
        fig_sc.add_hline(y=0, line_dash="dot", line_color="#94a3b8")
        fig_sc.update_layout(margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig_sc, use_container_width=True,
                        config={"displayModeBar": False})
        st.caption(
            "Each dot is one closed pick. Higher scores should cluster in "
            "the upper region — if not, the scoring engine isn't separating "
            "winners from losers."
        )


def render_picks_page():
    """Merged Opportunities + Tracked Picks (Session 11c). One page,
    four tabs:

      1. 🔎 Opportunities — the wide market scanner with per-card
         track/view-deepdive buttons.
      2. 🟢 Open Picks    — every tracker pick still in flight.
      3. ✅ Closed Picks  — outcome history.
      4. 📊 Analytics     — win-rate / score-vs-PnL charts.

    The 4 KPI metrics from the prior Tracked Picks page render at the
    top so they're visible regardless of which tab the user is on."""
    st.title("🎯 Picks")
    st.caption("Live opportunities + your tracked positions")

    # Run the auto-status sweep — cached for 10 minutes, so on most
    # navigations this is a near-instant no-op.
    with st.spinner("Refreshing pick statuses…"):
        try:
            _sweep_open_picks_token()
        except Exception:
            pass

    rows = _load_log()
    _render_tracked_metrics(rows)
    st.divider()

    tab_opps, tab_open, tab_closed, tab_analytics = st.tabs([
        "🔎 Opportunities", "🟢 Open Picks", "✅ Closed Picks", "📊 Analytics",
    ])

    with tab_opps:
        _render_opportunities_tab()

    with tab_open:
        # Fast manual-refresh control: clears the cached sweep so the
        # next render hits yfinance for fresh bars on every open pick.
        rcol1, rcol2 = st.columns([1, 4])
        with rcol1:
            if st.button("🔄 Refresh tracker", key="tracker_refresh_btn",
                         use_container_width=True):
                try:
                    _sweep_open_picks_token.clear()
                except Exception:
                    pass
                st.rerun()
        with rcol2:
            st.caption(
                "Tracker auto-refreshes every 10 min; click to refresh now."
            )
        _render_tab_open(rows)

    with tab_closed:
        _render_tab_closed(rows)

    with tab_analytics:
        _render_tab_analytics(rows)


def render_deepdive_page():
    # Section 0 — ticker input
    default_symbol = st.session_state.get("deepdive_symbol", "AAPL")
    input_col, btn_col = st.columns([4, 1])
    with input_col:
        entered = st.text_input(
            "Ticker",
            value=default_symbol,
            placeholder="e.g. AAPL, MSFT, RELIANCE.NS",
            label_visibility="collapsed",
            key="deepdive_input",
        )
    with btn_col:
        analyze_clicked = st.button("Analyze", type="primary", use_container_width=True)

    if analyze_clicked and entered:
        st.session_state["deepdive_symbol"] = entered.strip().upper()

    symbol = st.session_state.get("deepdive_symbol", "").strip().upper()
    if not symbol:
        st.info("Enter a ticker above to begin.")
        return

    # Section 0b — "as of date" picker. Default = today (preserves
    # current behaviour). Past dates re-route to analyze_symbol_as_of.
    from datetime import date as _date
    st.markdown("### 🕒 Analysis Date")
    asof_col1, asof_col2 = st.columns([2, 1])
    with asof_col1:
        as_of = st.date_input(
            "As of date (leave at today for current analysis)",
            value=_date.today(),
            min_value=_date.today() - timedelta(days=730),
            max_value=_date.today(),
            key=f"asof_{symbol}",
            help=(
                "See what the system would have recommended on this "
                "date. Useful for validating the model retroactively. "
                "Note: fundamentals and analyst data remain current "
                "snapshots — only price-derived indicators are "
                "point-in-time."
            ),
        )
    with asof_col2:
        st.write("")
        if as_of < _date.today():
            st.warning(f"⏳ Showing analysis as of {as_of}")
        else:
            st.info("📍 Current analysis")

    is_past = as_of < _date.today()
    cutoff = as_of.isoformat() if is_past else None

    # Fetch everything up-front so each section's try/except is thin.
    with st.spinner(f"Analyzing {symbol}… first run can take 20–40 s."):
        try:
            quote = fetch_live_quote(symbol)
        except Exception:
            quote = None
        try:
            fund = fetch_fundamentals(symbol)
        except Exception:
            fund = None
        try:
            tech = fetch_technicals(symbol)
        except Exception:
            tech = None
        try:
            mc = fetch_market_context(symbol, cutoff=cutoff)
        except Exception:
            mc = None
        try:
            if is_past:
                analysis = analyze_symbol_as_of(symbol, cutoff)
            else:
                analysis = analyze_symbol(symbol)
        except Exception:
            analysis = None

    # If everything came back empty, treat as an invalid ticker.
    if quote is None and fund is None and tech is None and analysis is None:
        st.error("Ticker not found. Check the symbol.")
        return

    # When viewing a past date, override the live quote's price so the
    # header's "Price" metric matches the as-of analysis. Day-change %
    # also comes from the analysis snapshot.
    header_quote = quote
    if is_past and analysis:
        header_quote = {
            "current_price": analysis.get("current_price"),
            "previous_close": None,
            "day_change_pct": analysis.get("day_change_pct"),
        }

    # Section 1 — header
    render_deepdive_header(symbol, fund, tech, header_quote)
    st.divider()

    # Section 2 — fundamentals (collapsible; score in the label)
    with st.expander(_score_label("💰 Fundamentals",
                                  (fund or {}).get("fundamental_score")),
                     expanded=False):
        try:
            render_deepdive_fundamentals(fund)
        except Exception:
            st.warning("Fundamentals temporarily unavailable.")

    # Section 3 — technicals (collapsible)
    with st.expander(_score_label("📈 Technicals",
                                  (tech or {}).get("technical_score")),
                     expanded=False):
        try:
            render_deepdive_technicals(tech)
        except Exception:
            st.warning("Technicals temporarily unavailable.")

    # Section 3b — risk & volatility (how much it moves, not which way)
    with st.expander("📉 Risk & Volatility", expanded=False):
        try:
            render_deepdive_risk(tech)
        except Exception:
            st.warning("Risk data temporarily unavailable.")

    # Section 4 — market context (collapsible)
    with st.expander(_score_label("🌐 Market Context",
                                  (mc or {}).get("score")),
                     expanded=False):
        try:
            render_deepdive_market_context(mc, fund, tech)
        except Exception:
            st.warning("Market context temporarily unavailable.")
    st.divider()

    # Section 4b — analyst forecast (between Market Context and Scoring).
    # Use the as-of price so the +X% deltas vs targets reflect the
    # point-in-time view, but note that analyst targets themselves are
    # current snapshots (yfinance doesn't expose historical analyst data).
    _price_for_analyst = (header_quote or {}).get("current_price")
    try:
        render_deepdive_analyst_forecast(fund, _price_for_analyst)
    except Exception:
        st.warning("Analyst forecast temporarily unavailable.")
    st.divider()

    # Section 5 — scoring engine
    try:
        render_deepdive_scoring(analysis)
    except Exception:
        st.warning("Scoring engine temporarily unavailable.")

    # Section 5b — "📌 Track this pick" button. Sits right under the
    # verdict card so the user can record a paper-trade snapshot of
    # the analysis as-of-now. Persists to results/recommendation_log.json
    # and surfaces on Page 5 (📓 Tracked Picks).
    if analysis:
        track_cols = st.columns([3, 1])
        with track_cols[1]:
            if st.button(
                "📌 Track this pick",
                use_container_width=True,
                key=f"track_{symbol}",
            ):
                blocker = _find_blocking_open_pick(symbol)
                if blocker is not None:
                    st.warning(_format_blocked_warning(symbol, blocker))
                else:
                    pick = _build_pick_from_analysis(symbol, analysis)
                    _append_pick(pick)
                    st.success(
                        f"✅ Tracking {symbol}. View on 🎯 Picks."
                    )

    # Section 5c — Indicator weight sandbox (experimental). Shows below
    # the Track button so the canonical verdict stays the headline.
    st.divider()
    try:
        render_deepdive_indicator_weights(symbol, analysis)
    except Exception:
        st.warning("Indicator weight sandbox temporarily unavailable.")

    # Section 7 — candlestick chart with overlays
    st.divider()
    try:
        render_deepdive_chart(symbol, tech, analysis, cutoff=cutoff)
    except Exception as _chart_exc:
        st.warning(f"Chart temporarily unavailable: {_chart_exc}")

    # Section 7b — Barchart-style cheat sheet (between chart legend and sizing)
    try:
        render_deepdive_cheat_sheet(symbol, tech, (quote or {}).get("current_price"))
    except Exception:
        st.warning("Cheat sheet temporarily unavailable.")

    # Section 8 — position sizer (BUY only; hidden when gated off by config)
    try:
        from config import ENABLE_POSITION_SIZING
    except Exception:
        ENABLE_POSITION_SIZING = False
    if ENABLE_POSITION_SIZING:
        st.divider()
        try:
            render_deepdive_sizing(symbol, analysis)
        except Exception:
            st.warning("Position sizing temporarily unavailable.")

    # Section 9 — reasoning
    st.divider()
    try:
        render_deepdive_reasoning(analysis)
    except Exception:
        st.warning("Reasoning temporarily unavailable.")

    # Section 10 — final summary banner
    try:
        render_deepdive_summary_bar(analysis)
    except Exception:
        pass

    # Section 11 — Quality-score trend (last 13 weeks), moved to the very bottom.
    # On-demand because each call costs ~30-60s on first scan; cached 1h after.
    st.divider()
    try:
        render_deepdive_verdict_trend(symbol)
    except Exception:
        st.warning("Quality-score trend temporarily unavailable.")


# --------------------------------------------------------------------------- #
# Page routers
# --------------------------------------------------------------------------- #

def page_home():
    """Combined Home page (Session 11a) — title 'Investing with Ismail',
    currency toggle, top-of-page metrics, regime, holdings, editable
    profile, and the moved Portfolio Analytics block. Top Opportunities
    preview is intentionally gone — users go to the dedicated 🔎 page."""
    st.title("💼 Investing with Ismail")
    st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if any(str(h.get("notes", "")).startswith("SAMPLE") for h in get_holdings()):
        st.info("🧪 **Sample portfolio**: trades generated by a simple rule "
                "(sell half at +8%, hold losers, buy back 5% dips) on real closing prices. "
                "Not real trades.")

    # Currency toggle — read once, stored in session_state, all helpers
    # below read it via _current_currency().
    currency_choice = st.radio(
        "Currency",
        options=["USD", "INR"],
        index=0,  # default USD per spec
        horizontal=True,
        key="display_currency",
        label_visibility="collapsed",
    )
    fx = fetch_usd_inr()

    # Section 2 — top metrics (4 cells, currency-aware)
    # with_score=False → skip the heavy per-holding analysis so Home opens fast.
    rows = build_holdings_rows(with_score=False)
    totals = portfolio_totals(rows)
    render_top_metrics(totals, currency_choice, fx)
    st.divider()

    # Section 3 — market regime
    render_regime()
    st.divider()

    # Section 4 — holdings table (currency-aware, includes total
    # unrealized P&L summary — realized P&L is shown inside the
    # Portfolio Analytics block below). The CRUD block always renders
    # so the user can add their first holding even with an empty table.
    render_holdings(rows, totals)
    render_holdings_crud()
    st.divider()

    # Section 5 — editable profile (hidden from the home page; render_my_profile
    # and its persistence code are retained for future use).
    # render_my_profile()
    # st.divider()

    # Section 6 — Portfolio Analytics (moved verbatim from old page 2,
    # minus the top metrics — already covered above). Each subsection
    # renders its own subheader; the wrapping subheader keeps them
    # visually grouped.
    holdings_now = get_holdings()
    if not holdings_now:
        return
    st.subheader("📊 Portfolio Analytics")
    closed = compute_closed_trades(holdings_now)
    win_rate = compute_win_rate(closed)
    if win_rate is not None:
        st.caption(f"Realized win rate: **{win_rate:.1f}%** across closed trades.")
    render_trade_review(holdings_now)
    st.divider()
    render_performers(rows)
    st.divider()
    render_sector_allocation(rows)
    st.divider()
    # Backtest Results panel removed from Home: it came from an older backtester
    # (no costs, today's large caps) and contradicted the Evidence page.
    # render_backtest_results() is kept for reference.
    render_closed_trades(holdings_now)


# page_placeholder() was removed in Session 11a — Settings page is gone
# and the four remaining sidebar entries each route to a real page.


# --------------------------------------------------------------------------- #
# Sidebar navigation + main dispatch
# --------------------------------------------------------------------------- #

def _prefetch_vix_at_startup() -> None:
    """One-time VIX cache warm-up on app boot. Runs once per session
    (idempotent via st.session_state). Shows a brief spinner on cold
    cache; on failure surfaces a red error banner and sets
    st.session_state.vix_available = False so downstream code can react.

    Called from main() before navigation so the user sees the status
    before they toggle Brain v2."""
    if st.session_state.get("vix_prefetch_done"):
        return
    st.session_state["vix_prefetch_done"] = True
    try:
        from istock.features.live_features import get_current_vix
        with st.spinner("Refreshing VIX…"):
            vix = get_current_vix()
        st.session_state["vix_available"] = True
        st.session_state["vix_value"] = vix
    except Exception as e:
        st.session_state["vix_available"] = False
        st.session_state["vix_value"] = None
        st.session_state["vix_error"] = str(e)
        # Persistent banner so the user sees the failure on every rerun
        # until they refresh data (which clears the prefetch flag below
        # via the Refresh button's cache_data.clear()).
        st.error(
            f"⚠️  VIX cache unavailable ({e}). Brain v2's high-VIX "
            f"guardrail will be skipped until this is fixed. Try "
            "`python -c \"from scripts.ohlc_cache import prefetch_universe; "
            "prefetch_universe(['^VIX'], '2022-04-01', '2026-05-15')\"`."
        )


def _brain_v2_toggle_sidebar() -> None:
    """Sidebar toggle that sets USE_BRAIN_V2 env var per session.
    Persists across page navigation via st.session_state. Must run
    INSIDE the `with st.sidebar:` block."""
    if "use_brain_v2" not in st.session_state:
        st.session_state["use_brain_v2"] = False

    enabled = st.toggle(
        "🧠 Use Brain v2 (experimental)",
        value=st.session_state["use_brain_v2"],
        key="use_brain_v2_toggle",
        help=(
            "Pooled model from S22-S23a. Default OFF. When on, v2 verdict "
            "becomes primary; v1 still computes and shows side-by-side."
        ),
    )
    if enabled != st.session_state["use_brain_v2"]:
        st.session_state["use_brain_v2"] = enabled
        # Clear analysis cache when the flag flips so the next render
        # picks up the new "primary" verdict immediately.
        st.cache_data.clear()

    # Reflect the toggle in the env var that core/trade_advisor.py reads
    os.environ["USE_BRAIN_V2"] = "1" if st.session_state["use_brain_v2"] else "0"

    # Footer card — honest one-liner. Stays the same on/off.
    st.caption(
        "**Brain v2 (experimental):** pooled model, +33-37% PF over v1 "
        "on two backtest windows. High-VIX guardrail active. Default OFF "
        "until live evidence accumulates."
    )


def main():
    # Feature-integrity check: if any feature dependency is missing, brain v2
    # silently scores with zeroed inputs (train/serve skew). Fail LOUD.
    try:
        from istock.features.live_features import check_feature_dependencies
        _dep_problems = check_feature_dependencies()
        if _dep_problems:
            st.error(
                "🚨 **Brain v2 feature dependencies missing — scores are unreliable "
                "until fixed:**\n\n" + "\n".join(f"- {p}" for p in _dep_problems)
            )
    except Exception:
        pass

    # Apply any pending cross-page nav intent BEFORE the sidebar radio
    # is instantiated — Streamlit won't let us set the radio's own
    # session_state key after it renders.
    if "_nav_intent" in st.session_state:
        st.session_state[SIDEBAR_KEY] = st.session_state.pop("_nav_intent")

    # VIX cache warm-up — runs once per session, before any v2 scoring.
    _prefetch_vix_at_startup()

    with st.sidebar:
        st.markdown("## 🧭 Navigation")
        page = st.radio(
            "Go to",
            options=[
                "🏠 Home",
                "🎯 Picks",
                "🔍 Stock Deep-Dive",
                "📈 Evidence-Based",
            ],
            label_visibility="collapsed",
            key=SIDEBAR_KEY,
        )
        st.markdown("---")
        if st.button("🔄 Refresh data", use_container_width=True):
            st.cache_data.clear()
            # Re-arm the VIX prefetch so next rerun re-checks the cache
            st.session_state.pop("vix_prefetch_done", None)
            st.rerun()
        st.caption("Clears all cached quotes / analyses / regime.")
        st.markdown("---")
        st.caption(
            "⚠️ **Analytics, not advice.** This tool shows scores and data to help "
            "you think — it never tells you to buy or sell. Short-horizon direction "
            "is unpredictable; nothing here is a prediction or a recommendation. "
            "Not financial advice — do your own research."
        )

    if page == "🏠 Home":
        page_home()
    elif page == "🎯 Picks":
        render_picks_page()
    elif page == "🔍 Stock Deep-Dive":
        render_deepdive_page()
    elif page == "📈 Evidence-Based":
        render_evidence_page()


def render_evidence_page():
    """The honest 'what actually works' conclusion — the one result that survived
    fair, survivorship-free, cost-aware testing across this whole project."""
    st.title("📈 Evidence-Based Investing")
    st.caption("The honest conclusion of this project — what the data actually supports.")

    st.markdown(
        "After testing many strategies on fair, survivorship-free, cost-aware harnesses, "
        "the honest finding is blunt: **short-horizon direction is unpredictable, and "
        "almost nothing reliably beats a simple index.** This tool exists to show you the "
        "analysis transparently — not to sell you a market-beating signal that doesn't exist."
    )

    st.subheader("What did NOT work (tested and rejected)")
    st.markdown(
        "- **Single-name up/down prediction** — no skill (out-of-sample AUC ≈ 0.51; every "
        "feature's information value < 0.005).\n"
        "- **News / sentiment, chart patterns, technical triggers** — priced in within "
        "seconds, or don't survive costs.\n"
        "- **Intraday breakout (ORB), mean-reversion shorts (ConnorsRSI), dual-momentum (GEM)** "
        "— margin-called, whipsawed, or simply beaten by buy-and-hold after costs.\n"
        "- **LSTM / sequence models** — memorize noise at this signal-to-noise ratio."
    )

    st.subheader("The one thing that survived: a multi-factor tilt")
    st.markdown(
        "A simple **equal blend of Momentum + Value + Quality** (no weight tuning) was the "
        "only automatable approach to genuinely beat a risk-matched levered S&P 500 "
        "through-cycle (1999–2026):"
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Edge vs market", "+3.0 pp/yr")
    c2.metric("Sharpe", "0.61", "vs 0.51 market")
    c3.metric("Beat market", "18 / 28 yrs")
    st.markdown(
        "**Buyable, tax-efficient form (the actual recommendation):** roughly "
        "**⅓ MTUM + ⅓ VLUE + ⅓ QUAL**, or a single multi-factor ETF like **LRGF**, "
        "rebalanced ~quarterly. ETFs shed almost no taxable gains, which fixes the tax "
        "drag that killed the do-it-yourself version. Size it to survive a bad relative "
        "year (factor sleeves can lag the market by 20–30 pp in a single year)."
    )
    st.info(
        "This is educational, not financial advice. The honest edge is modest (~2–5 pp/yr) "
        "and comes with real drawdowns. For most people, a low-cost index fund plus a high "
        "savings rate does most of the work.",
        icon="ℹ️",
    )


main()
