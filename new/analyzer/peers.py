"""Peer-relative context (framework's core rule: metrics are only meaningful
vs. peers). Builds a cached metric panel across the S&P 500, then expresses a
target company's metrics as PERCENTILES within its GICS sector.

One-time build (~10-15 min, cached): `python build_peers.py`
After that, analyze() attaches peer percentiles automatically.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import data as _data
from .forensic import _at, _safe_div

_ROOT = Path(__file__).resolve().parent.parent
CACHE = _ROOT / "cache"
CONSTITUENTS = CACHE / "sp500.csv"
PANEL = CACHE / "peer_panel.json"
_SP500_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

# metrics compared vs peers; True = higher is better
_METRICS = {
    "roic": True, "roe": True, "gross_margin": True, "operating_margin": True,
    "net_margin": True, "fcf_margin": True, "rev_growth_3y": True,
    "net_debt_ebitda": False, "pe": False, "ev_ebitda": False, "fcf_yield": True,
}


def sp500_constituents(force: bool = False) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    if CONSTITUENTS.exists() and not force:
        return pd.read_csv(CONSTITUENTS)
    df = pd.read_csv(_SP500_URL)[["Symbol", "GICS Sector", "GICS Sub-Industry"]]
    df.columns = ["ticker", "sector", "sub_industry"]
    df["ticker"] = df["ticker"].str.replace(".", "-", regex=False)  # BRK.B -> BRK-B
    df.to_csv(CONSTITUENTS, index=False)
    return df


def extract_comparable(c: _data.CompanyData) -> dict:
    """Compact, sector-comparable metric snapshot from a CompanyData."""
    ebit = _at(c.ebit(), 0)
    tax_rate = _safe_div(_at(c.tax(), 0), _at(c.pretax(), 0))
    tax_rate = 0.21 if (np.isnan(tax_rate) or tax_rate < 0 or tax_rate > 0.5) else tax_rate
    nopat = ebit * (1 - tax_rate)
    rev = _at(c.rev(), 0)
    mcap = c.market_cap
    debt, cash = _at(c.total_debt(), 0), _at(c.cash(), 0)
    ev = (mcap + (0 if np.isnan(debt) else debt) - (0 if np.isnan(cash) else cash)) if not np.isnan(mcap) else np.nan
    nd = _at(c.net_debt(), 0)
    if np.isnan(nd):
        nd = (0 if np.isnan(debt) else debt) - (0 if np.isnan(cash) else cash)
    rev3 = _at(c.rev(), 3)
    return {
        "roic": _pct(_safe_div(nopat, _at(c.invested_cap(), 0))),
        "roe": _pct(_safe_div(_at(c.net_income(), 0), _at(c.equity(), 0))),
        "gross_margin": _pct(_safe_div(_at(c.gross(), 0), rev)),
        "operating_margin": _pct(_safe_div(ebit, rev)),
        "net_margin": _pct(_safe_div(_at(c.net_income(), 0), rev)),
        "fcf_margin": _pct(_safe_div(_at(c.fcf(), 0), rev)),
        "rev_growth_3y": _pct(((rev / rev3) ** (1/3) - 1) if (rev > 0 and rev3 and rev3 > 0) else np.nan),
        "net_debt_ebitda": _r(_safe_div(nd, _at(c.ebitda(), 0))),
        "pe": _r(c.info.get("trailingPE")),
        "ev_ebitda": _r(_safe_div(ev, _at(c.ebitda(), 0))),
        "fcf_yield": _pct(_safe_div(_at(c.fcf(), 0), mcap)),
    }


def build_peer_panel(tickers=None, force: bool = False, verbose: bool = True) -> dict:
    """Fetch + extract comparable metrics across the universe; cache to disk."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cons = sp500_constituents()
    sector_map = dict(zip(cons["ticker"], cons["sector"]))
    tickers = tickers or list(cons["ticker"])
    panel = {}
    if PANEL.exists() and not force:
        panel = json.loads(PANEL.read_text())
    for i, tk in enumerate(tickers):
        if tk in panel and not force:
            continue
        try:
            c = _data.fetch(tk)
            if c.n_periods == 0:
                continue
            row = extract_comparable(c)
            row["sector"] = sector_map.get(tk, "Unknown")
            panel[tk] = row
        except Exception as e:
            if verbose:
                print(f"  skip {tk}: {e}")
        if verbose and (i + 1) % 25 == 0:
            print(f"  [{i+1}/{len(tickers)}] built; saving checkpoint")
            PANEL.write_text(json.dumps(panel))
    PANEL.write_text(json.dumps(panel))
    if verbose:
        print(f"panel built: {len(panel)} companies -> {PANEL}")
    return panel


def load_panel():
    return json.loads(PANEL.read_text()) if PANEL.exists() else None


# yfinance's info.sector taxonomy differs from the S&P CSV's GICS sector names
_YF_TO_GICS = {
    "Technology": "Information Technology",
    "Financial Services": "Financials",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Healthcare": "Health Care",
    "Communication Services": "Communication Services",
    "Industrials": "Industrials", "Energy": "Energy", "Utilities": "Utilities",
    "Real Estate": "Real Estate", "Basic Materials": "Materials",
}


def peer_context(sector: str, target_metrics: dict) -> dict:
    """Percentile of each target metric within its sector peer group."""
    panel = load_panel()
    if not panel:
        return {"available": False,
                "note": "peer panel not built — run `python build_peers.py` (one-time ~12 min)"}
    gics = _YF_TO_GICS.get(sector, sector)
    peers = {tk: r for tk, r in panel.items() if r.get("sector") in (sector, gics)}
    if len(peers) < 5:
        return {"available": False, "note": f"only {len(peers)} sector peers cached — build more"}

    pct = {}
    for m, higher_better in _METRICS.items():
        vals = [r[m] for r in peers.values() if r.get(m) is not None]
        tv = target_metrics.get(m)
        if tv is None or len(vals) < 5:
            continue
        rank = sum(1 for v in vals if v <= tv) / len(vals) * 100
        if not higher_better:
            rank = 100 - rank
        pct[m] = {"value": tv, "percentile": round(rank), "peer_median": round(float(np.median(vals)), 2)}
    return {"available": True, "sector": sector, "n_peers": len(peers), "percentiles": pct,
            "note": "percentile = how the company ranks vs sector peers (higher = better, sign-adjusted)"}


def _pct(x):
    return None if (x is None or (isinstance(x, float) and np.isnan(x))) else round(x * 100, 2)


def _r(x):
    try:
        return None if (x is None or (isinstance(x, float) and np.isnan(x))) else round(float(x), 2)
    except Exception:
        return None
