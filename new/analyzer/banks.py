"""Bank / financial-institution model (framework §0 branch, §2 special-case).

Banks have no COGS/EBITDA/invested-capital — the industrial ROIC/EV models are
meaningless. The right lens: earnings on assets (ROA), on equity (ROE), spread
income (NIM), cost discipline (efficiency ratio), and price vs TANGIBLE book
(P/TBV) — banks are valued on book value + the ROE they earn on it.

Free-data limits (flagged): Tier-1/CET1 capital, loan/deposit ratio, and
credit-loss provisions / NPLs are not cleanly in yfinance — they need the 10-K
tables or FFIEC call reports. Noted where relevant.
"""
from __future__ import annotations

import numpy as np

from .data import CompanyData, _row
from .forensic import _at, _safe_div


def _inc(c, *names):
    return _row(c.income, *names)


def _noninterest_expense(c: CompanyData):
    """Sum granular non-interest expense lines; fall back to SG&A rollup."""
    parts = ["Salaries And Wages", "Occupancy And Equipment",
             "Professional Expense And Contract Services Expense",
             "Selling And Marketing Expense", "Other Non Interest Expense"]
    total = 0.0
    found = False
    for p in parts:
        s = _row(c.income, p)
        v = _at(s, 0)
        if not np.isnan(v):
            total += v
            found = True
    if not found:
        return _at(_row(c.income, "Selling General And Administration"), 0)
    return total


def bank_metrics(c: CompanyData) -> dict:
    ni = c.net_income()
    assets = c.assets()
    eq = c.equity()
    nii = _inc(c, "Net Interest Income")
    rev = c.rev()
    n = min(c.n_periods, 5)

    def series(num, den, mult=100, r=2):
        out = []
        for i in range(n):
            v = _safe_div(_at(num, i), _at(den, i))
            out.append(None if np.isnan(v) else round(v * mult, r))
        return out

    roa = series(ni, assets)                          # target >1%
    roe = series(ni, eq)                              # target >10-12%
    nim_proxy = series(nii, assets)                   # NII/assets (proxy for NIM)
    # efficiency ratio = non-interest expense / total revenue (lower better)
    noninterest_exp = _noninterest_expense(c)
    eff = _safe_div(noninterest_exp, _at(rev, 0))
    # tangible book value per share + growth
    tbv = c.balance.loc["Tangible Book Value"] if "Tangible Book Value" in c.balance.index else None
    shares = c.info.get("sharesOutstanding") or _at(c.dil_shares(), 0)
    tbv0 = _at(tbv, 0) if tbv is not None else np.nan
    tbvps = _safe_div(tbv0, shares)
    tbvps_cagr = None
    if tbv is not None and c.n_periods >= 4 and _at(tbv, 3) > 0:
        tbvps_cagr = round(((_at(tbv, 0) / _at(tbv, 3)) ** (1/3) - 1) * 100, 1)
    # P/TBV
    p_tbv = _safe_div(c.market_cap, tbv0)

    return {
        "roa_pct": roa, "roe_pct": roe, "nim_proxy_pct": nim_proxy,
        "efficiency_ratio_pct": None if np.isnan(eff) else round(eff * 100, 1),
        "tangible_bv_per_share": None if np.isnan(tbvps) else round(tbvps, 2),
        "tbv_per_share_cagr_3y_pct": tbvps_cagr,
        "price_to_tangible_book": None if np.isnan(p_tbv) else round(p_tbv, 2),
        "price_to_book": _r(c.info.get("priceToBook")),
        "pe_trailing": _r(c.info.get("trailingPE")),
        "dividend_yield_pct": _r(_safe_div(_at(c.dividends(), 0), c.market_cap) * 100),
        "notes": ["Tier-1/CET1 capital, loan/deposit ratio, NPLs/provisions not in "
                  "free data — check 10-K / FFIEC call reports",
                  "NIM here is NII/total-assets proxy (true NIM uses earning assets)"],
    }


def _r(x):
    try:
        return None if x is None else round(float(x), 2)
    except Exception:
        return None


def _first(lst):
    return lst[0] if lst and lst[0] is not None else None


def _trend(lst):
    v = [x for x in lst if x is not None]
    if len(v) < 2:
        return "n/a"
    return "rising" if v[0] > v[-1] * 1.03 else ("falling" if v[0] < v[-1] * 0.97 else "flat")


def run_bank_analysis(c: CompanyData, cls: dict) -> dict:
    m = bank_metrics(c)
    roa, roe = _first(m["roa_pct"]), _first(m["roe_pct"])
    eff = m["efficiency_ratio_pct"]
    flags = []
    if roa is not None and roa < 0.8:
        flags.append(f"ROA {roa}% weak for a bank (<0.8%)")
    if roe is not None and roe < 8:
        flags.append(f"ROE {roe}% weak (<8%)")
    if eff is not None and eff > 70:
        flags.append(f"Efficiency ratio {eff}% poor (>70% = high cost/income)")
    if m["tbv_per_share_cagr_3y_pct"] is not None and m["tbv_per_share_cagr_3y_pct"] < 0:
        flags.append("Tangible book/share shrinking (value destruction)")

    # quality read
    quality_note = []
    if roa is not None:
        quality_note.append("strong" if roa >= 1.3 else "solid" if roa >= 1.0 else "weak")
    return {
        "subtype": cls.get("financial_subtype", "bank"),
        "flags": flags,
        "metrics": m,
        "roa_trend": _trend(m["roa_pct"]),
        "roe_trend": _trend(m["roe_pct"]),
        "efficiency_assessment": (None if eff is None else
            "excellent (<50%)" if eff < 50 else "good (<60%)" if eff < 60 else
            "average (<70%)" if eff < 70 else "poor (>70%)"),
    }
