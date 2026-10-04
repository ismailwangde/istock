"""Growth analysis (framework §4). The key discipline: judge the SOURCE and
QUALITY of growth, not just the rate. Catches the §17 traps — revenue growth
without FCF, EPS growth only from buybacks."""
from __future__ import annotations

import numpy as np

from .data import CompanyData
from .forensic import _at, _safe_div


def _cagr(series, yrs):
    if series is None:
        return np.nan
    a, b = _at(series, 0), _at(series, yrs)
    # CAGR undefined if either endpoint <=0 or the ratio is negative (sign flip
    # would make the fractional power complex) — return NaN and let callers note it
    if np.isnan(a) or np.isnan(b) or b <= 0 or a <= 0:
        return np.nan
    return (a / b) ** (1 / yrs) - 1


def run_growth(c: CompanyData) -> dict:
    rev, ni, fcf = c.rev(), c.net_income(), c.fcf()
    eps = c.info.get("trailingEps")
    shares = c.dil_shares()
    n = c.n_periods

    rev_cagr3 = _cagr(rev, 3) if n >= 4 else np.nan
    rev_cagr5 = _cagr(rev, 4) if n >= 5 else np.nan
    ni_cagr3 = _cagr(ni, 3) if n >= 4 else np.nan
    fcf_cagr3 = _cagr(fcf, 3) if n >= 4 else np.nan

    # acceleration: latest YoY vs the 3y average
    yoy = _safe_div(_at(rev, 0), _at(rev, 1)) - 1 if n >= 2 else np.nan
    accel = None
    if not np.isnan(yoy) and not np.isnan(rev_cagr3):
        accel = "accelerating" if yoy > rev_cagr3 + 0.02 else ("decelerating" if yoy < rev_cagr3 - 0.02 else "steady")

    # source of EPS growth: revenue vs margin vs share-count reduction
    share_chg = _safe_div(_at(shares, 0), _at(shares, 3)) - 1 if n >= 4 else np.nan
    flags = []
    # growth without cash
    if not np.isnan(rev_cagr3) and rev_cagr3 > 0.10 and not np.isnan(fcf_cagr3) and fcf_cagr3 < 0:
        flags.append(f"Revenue growing {rev_cagr3*100:.0f}%/yr but FCF shrinking (unprofitable growth)")
    # EPS growth mostly from buybacks: net income flat but share count falling
    if not np.isnan(ni_cagr3) and not np.isnan(share_chg):
        if ni_cagr3 < 0.03 and share_chg < -0.05:
            flags.append("EPS growth driven by buybacks, not operations (NI ~flat, shares down)")
    # rule of 40 (SaaS-relevant): growth% + FCF margin%
    fcf_margin = _safe_div(_at(fcf, 0), _at(rev, 0))
    rule40 = None
    if not np.isnan(yoy) and not np.isnan(fcf_margin):
        rule40 = round((yoy + fcf_margin) * 100, 1)

    return {
        "rev_cagr_3y_pct": _p(rev_cagr3), "rev_cagr_5y_pct": _p(rev_cagr5),
        "rev_yoy_pct": _p(yoy), "acceleration": accel,
        "net_income_cagr_3y_pct": _p(ni_cagr3), "fcf_cagr_3y_pct": _p(fcf_cagr3),
        "share_count_change_3y_pct": _p(share_chg),
        "rule_of_40": rule40,
        "flags": flags,
        "note": "quality > rate: growth should convert to FCF and not rely on buybacks",
    }


def _p(x):
    return None if (x is None or (isinstance(x, float) and np.isnan(x))) else round(x * 100, 1)
