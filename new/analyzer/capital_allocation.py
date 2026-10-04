"""Capital allocation & dividends (framework §5). Munger: management's #1 job.
Judge a decade of choices: buyback quality (real reduction vs offsetting SBC),
dividend sustainability (payout of FCF not EPS), SBC dilution, debt behavior."""
from __future__ import annotations

import numpy as np

from .data import CompanyData
from .forensic import _at, _safe_div


def run_capital_allocation(c: CompanyData) -> dict:
    fcf = c.fcf()
    div = c.dividends()
    buyback = c.buybacks()
    sbc = c.sbc()
    shares = c.dil_shares()
    rev = c.rev()
    n = c.n_periods

    # buybacks: real share-count reduction vs gross buyback spend
    share_chg_3y = _safe_div(_at(shares, 0), _at(shares, 3)) - 1 if n >= 4 else np.nan
    buyback_fcf = _safe_div(_at(buyback, 0), _at(fcf, 0))
    # SBC dilution
    sbc_rev = _safe_div(_at(sbc, 0), _at(rev, 0))

    # dividend sustainability — payout of FCF (not EPS)
    payout_fcf = _safe_div(_at(div, 0), _at(fcf, 0))
    div_cagr = None
    if n >= 4 and _at(div, 3) > 0:
        div_cagr = round((_at(div, 0) / _at(div, 3)) ** (1/3) - 1, 3)
    pays_dividend = _at(div, 0) > 0

    flags = []
    # buybacks merely offsetting SBC (share count flat/up despite buybacks)
    if not np.isnan(buyback_fcf) and buyback_fcf > 0.1 and not np.isnan(share_chg_3y) and share_chg_3y > -0.01:
        flags.append("Buybacks not reducing share count — likely offsetting SBC dilution")
    if not np.isnan(sbc_rev) and sbc_rev > 0.08:
        flags.append(f"High SBC {sbc_rev*100:.1f}% of revenue (dilutive)")
    if pays_dividend and not np.isnan(payout_fcf) and payout_fcf > 1.0:
        flags.append(f"Dividend payout {payout_fcf*100:.0f}% of FCF — unsustainable (>100%)")

    # positive read
    reduces_shares = (not np.isnan(share_chg_3y)) and share_chg_3y < -0.02
    return {
        "share_count_change_3y_pct": _p(share_chg_3y),
        "reduces_share_count": reduces_shares,
        "buyback_pct_of_fcf": _p(buyback_fcf), "sbc_pct_of_revenue": _p(sbc_rev),
        "pays_dividend": bool(pays_dividend),
        "dividend_payout_of_fcf_pct": _p(payout_fcf),
        "dividend_cagr_3y_pct": None if div_cagr is None else round(div_cagr*100, 1),
        "flags": flags,
        "note": "good: buybacks below intrinsic value that truly cut share count; "
                "payout <60% of FCF; low SBC. Qualitative M&A discipline needs manual review.",
    }


def _p(x):
    return None if (x is None or (isinstance(x, float) and np.isnan(x))) else round(x * 100, 1)
