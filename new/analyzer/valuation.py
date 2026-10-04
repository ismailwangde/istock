"""Valuation (framework §6). Multiples + intrinsic value, with the star tool:
the REVERSE-DCF reality check — solve for the FCF growth the CURRENT price
implies, then judge whether that's realistic vs the company's actual history.
That cuts through narrative without needing peer data.

Uses free data (yfinance info + statements). Cost of capital comes from STEP 0.
"""
from __future__ import annotations

import numpy as np

from .data import CompanyData
from .forensic import _at, _safe_div

TERMINAL_GROWTH = 0.025   # ~long-run GDP/inflation
HIGH_GROWTH_YEARS = 10


def _enterprise_value(c: CompanyData):
    mcap = c.market_cap
    debt = _at(c.total_debt(), 0)
    cash = _at(c.cash(), 0)
    if np.isnan(mcap):
        return np.nan, mcap
    ev = mcap + (0 if np.isnan(debt) else debt) - (0 if np.isnan(cash) else cash)
    return ev, mcap


def multiples(c: CompanyData) -> dict:
    ev, mcap = _enterprise_value(c)
    info = c.info
    ebitda, ebit = _at(c.ebitda(), 0), _at(c.ebit(), 0)
    rev, fcf = _at(c.rev(), 0), _at(c.fcf(), 0)
    ni = _at(c.net_income(), 0)
    # dividend yield computed from statements (yfinance's dividendYield field is
    # unit-inconsistent across versions) = cash dividends paid / market cap
    div_yield = _safe_div(_at(c.dividends(), 0), mcap) * 100 if not np.isnan(mcap) else np.nan
    out = {
        "pe_trailing": _r(info.get("trailingPE")),
        "pe_forward": _r(info.get("forwardPE")),
        "price_to_book": _r(info.get("priceToBook")),
        "ev_ebitda": _r(_safe_div(ev, ebitda)),
        "ev_ebit": _r(_safe_div(ev, ebit)),
        "ev_sales": _r(_safe_div(ev, rev)),
        "ev_fcf": _r(_safe_div(ev, fcf)),
        "fcf_yield_pct": _r(_safe_div(fcf, mcap) * 100 if not np.isnan(_safe_div(fcf, mcap)) else np.nan),
        "peg": _r(info.get("pegRatio") or info.get("trailingPegRatio")),
        "dividend_yield_pct": _r(div_yield),
        "earnings_yield_pct": _r(_safe_div(ni, mcap) * 100 if not np.isnan(_safe_div(ni, mcap)) else np.nan),
    }
    return out


def _pv_dcf(fcf0, g, r, tg=TERMINAL_GROWTH, n=HIGH_GROWTH_YEARS):
    """PV of FCF growing at g for n years + Gordon terminal at tg, discount r."""
    if r <= tg:
        return np.inf
    pv = 0.0
    f = fcf0
    for t in range(1, n + 1):
        f = f * (1 + g)
        pv += f / (1 + r) ** t
    terminal = f * (1 + tg) / (r - tg)
    pv += terminal / (1 + r) ** n
    return pv


def reverse_dcf(c: CompanyData, wacc_pct: float) -> dict:
    """Solve for the constant FCF growth the current EV implies (bisection),
    then compare to the company's actual FCF/revenue history."""
    ev, _ = _enterprise_value(c)
    fcf0 = _at(c.fcf(), 0)
    r = wacc_pct / 100
    if np.isnan(ev) or np.isnan(fcf0) or fcf0 <= 0 or ev <= 0:
        return {"implied_growth_pct": None,
                "note": "reverse-DCF needs positive FCF & EV (n/a for unprofitable/negative-FCF)"}
    lo, hi = -0.20, 0.60
    if _pv_dcf(fcf0, hi, r) < ev:   # even 60% growth can't justify price
        return {"implied_growth_pct": ">60", "verdict": "extreme",
                "note": "price implies >60%/yr FCF growth for 10y — priced for perfection"}
    for _ in range(100):
        mid = (lo + hi) / 2
        if _pv_dcf(fcf0, mid, r) > ev:
            hi = mid
        else:
            lo = mid
    implied = (lo + hi) / 2
    # reality check vs history
    rev = c.rev()
    hist_rev_cagr = None
    if c.n_periods >= 4 and _at(rev, 3) > 0:
        hist_rev_cagr = round(((_at(rev, 0) / _at(rev, 3)) ** (1/3) - 1) * 100, 1)
    realistic = None
    if hist_rev_cagr is not None:
        realistic = implied * 100 <= hist_rev_cagr + 3   # implied within/below recent growth+buffer
    return {
        "implied_growth_pct": round(implied * 100, 1),
        "historical_rev_cagr_3y_pct": hist_rev_cagr,
        "wacc_used_pct": wacc_pct,
        "assumptions": f"{HIGH_GROWTH_YEARS}y high-growth + {TERMINAL_GROWTH*100:.1f}% terminal",
        "looks_reasonable": realistic,
        "note": "if implied growth >> historical, price bakes in optimism (risk); if <<, potential value",
    }


def forward_dcf(c: CompanyData, wacc_pct: float) -> dict:
    """Base/bull/bear intrinsic EV → equity value → margin of safety vs price."""
    ev_now, mcap = _enterprise_value(c)
    fcf0 = _at(c.fcf(), 0)
    r = wacc_pct / 100
    if np.isnan(fcf0) or fcf0 <= 0 or np.isnan(mcap):
        return {"note": "forward-DCF needs positive FCF"}
    # anchor base growth on historical rev CAGR, capped to sane range
    rev = c.rev()
    base_g = 0.08
    if c.n_periods >= 4 and _at(rev, 3) > 0:
        base_g = float(np.clip((_at(rev, 0) / _at(rev, 3)) ** (1/3) - 1, 0.0, 0.25))
    debt, cash = _at(c.total_debt(), 0), _at(c.cash(), 0)
    net_debt = (0 if np.isnan(debt) else debt) - (0 if np.isnan(cash) else cash)
    shares = c.info.get("sharesOutstanding") or _at(c.dil_shares(), 0)
    price = c.info.get("currentPrice") or c.info.get("regularMarketPrice")

    scen = {}
    for name, g in [("bear", max(0.0, base_g - 0.05)), ("base", base_g), ("bull", base_g + 0.05)]:
        ev = _pv_dcf(fcf0, g, r)
        eq = ev - net_debt
        ps = _safe_div(eq, shares)
        scen[name] = {"growth_pct": round(g*100, 1),
                      "intrinsic_per_share": _r(ps),
                      "upside_pct": _r((_safe_div(ps, price) - 1) * 100) if price else None}
    return {"current_price": price, "scenarios": scen,
            "margin_of_safety_note": "buy meaningfully below base-case intrinsic"}


def _r(x, mult=1):
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return None
        return round(float(x) * mult, 2)
    except Exception:
        return None


def run_valuation(c: CompanyData, cls: dict) -> dict:
    wacc = cls["wacc"]
    m = multiples(c)
    rev_dcf = reverse_dcf(c, wacc)
    fwd_dcf = forward_dcf(c, wacc)
    flags = []
    fy = m.get("fcf_yield_pct")
    if fy is not None and fy < 2:
        flags.append(f"Low FCF yield {fy}% (rich valuation)")
    if rev_dcf.get("looks_reasonable") is False:
        flags.append(f"Reverse-DCF: price implies {rev_dcf.get('implied_growth_pct')}%/yr FCF growth vs {rev_dcf.get('historical_rev_cagr_3y_pct')}% historical (priced for optimism)")
    if rev_dcf.get("verdict") == "extreme":
        flags.append("Reverse-DCF: priced for perfection (>60%/yr implied)")
    if cls["type"] == "cyclical":
        flags.append("Cyclical: current-year multiples unreliable — normalize earnings across the cycle")
    return {"flags": flags, "multiples": m, "reverse_dcf": rev_dcf, "forward_dcf": fwd_dcf,
            "wacc_used_pct": wacc}
