"""Market-wide macro context (framework §14). Company-INDEPENDENT regime
context — the discount-rate and risk-appetite backdrop for ALL equities.
Non-scoring: it frames the analysis, it doesn't rate the company.

Free data via yfinance index tickers (no FRED key needed). Cached per-run.
"""
from __future__ import annotations

import numpy as np

_TICKERS = {"vix": "^VIX", "tnx": "^TNX", "irx": "^IRX",
            "dxy": "DX-Y.NYB", "oil": "CL=F"}
_cache = {}


def _last(ticker):
    import yfinance as yf
    try:
        h = yf.Ticker(ticker).history(period="5d")
        return float(h["Close"].iloc[-1]) if not h.empty else np.nan
    except Exception:
        return np.nan


def market_context() -> dict:
    if _cache:
        return _cache
    vals = {k: _last(t) for k, t in _TICKERS.items()}
    vix = vals["vix"]
    tnx = vals["tnx"]      # 10y yield (%)
    irx = vals["irx"]      # 13-week T-bill (%)
    curve = (tnx - irx) if (not np.isnan(tnx) and not np.isnan(irx)) else np.nan

    regime = []
    if not np.isnan(vix):
        regime.append("high fear (VIX>30)" if vix > 30 else
                      "elevated stress (VIX>20)" if vix > 20 else "calm (VIX<20)")
    if not np.isnan(curve):
        regime.append("inverted yield curve (recession signal)" if curve < 0
                      else "normal yield curve")
    if not np.isnan(tnx):
        regime.append("high rates (>4.5%) pressure valuations" if tnx > 4.5 else
                      "moderate rates")

    out = {
        "vix": _r(vix), "us_10y_yield_pct": _r(tnx), "us_3m_yield_pct": _r(irx),
        "yield_curve_10y_minus_3m": _r(curve),
        "dollar_index": _r(vals["dxy"]), "oil_wti": _r(vals["oil"]),
        "regime": regime,
        "note": "regime context (discount rate & risk appetite) — applies to all "
                "equities, not company-specific; non-scoring",
    }
    _cache.update(out)
    return out


def _r(x):
    return None if (x is None or (isinstance(x, float) and np.isnan(x))) else round(x, 2)
