"""STEP 2 — Solvency / distress GATE (framework §2C, §13).

Altman Z, net debt/EBITDA, interest coverage, current ratio. If a company is
in distress the standard quality/valuation lens is the wrong tool, so this can
route to a distressed framework (out of scope for milestone 1 — we just flag).
"""
from __future__ import annotations

import numpy as np

from .data import CompanyData
from .forensic import _at, _safe_div


def altman_z(c: CompanyData) -> dict:
    """Original Altman Z (manufacturing-calibrated). >3 safe, 1.8-3 grey,
    <1.8 distress. Uses market cap for the equity/liabilities term."""
    a = _at(c.assets(), 0)
    wc = _at(c.working_cap(), 0)
    re = _at(c.retained(), 0)
    ebit = _at(c.ebit(), 0)
    sales = _at(c.rev(), 0)
    tl = _at(c.total_liab(), 0)
    mcap = c.market_cap
    if np.isnan(a) or a == 0:
        return {"value": np.nan, "note": "no assets"}
    x1 = _safe_div(wc, a)
    x2 = _safe_div(re, a)
    x3 = _safe_div(ebit, a)
    x4 = _safe_div(mcap, tl)
    x5 = _safe_div(sales, a)
    terms = [1.2*x1, 1.4*x2, 3.3*x3, 0.6*x4, 1.0*x5]
    z = np.nansum(terms)
    zone = "safe" if z > 3 else ("distress" if z < 1.8 else "grey")
    return {"value": round(z, 2), "zone": zone,
            "note": ">3 safe, <1.8 distress (mfg-calibrated)"}


def leverage(c: CompanyData) -> dict:
    nd = _at(c.net_debt(), 0)
    if np.isnan(nd):
        nd = _at(c.total_debt(), 0) - _at(c.cash(), 0)
    ebitda = _at(c.ebitda(), 0)
    ebit = _at(c.ebit(), 0)
    ie = _at(c.interest_exp(), 0)
    ca, cl = _at(c.cur_assets(), 0), _at(c.cur_liab(), 0)
    nd_ebitda = _safe_div(nd, ebitda)
    cov = _safe_div(ebit, ie)
    cr = _safe_div(ca, cl)
    de = _safe_div(_at(c.total_debt(), 0), _at(c.equity(), 0))
    return {
        "net_debt_ebitda": None if np.isnan(nd_ebitda) else round(nd_ebitda, 2),
        "interest_coverage": None if np.isnan(cov) else round(cov, 1),
        "current_ratio": None if np.isnan(cr) else round(cr, 2),
        "debt_to_equity": None if np.isnan(de) else round(de, 2),
        "flags": _lev_flags(nd_ebitda, cov, cr),
    }


def _lev_flags(nd_ebitda, cov, cr):
    f = []
    if not np.isnan(nd_ebitda) and nd_ebitda > 4: f.append(f"Net debt/EBITDA {nd_ebitda:.1f}x high (>4)")
    if not np.isnan(cov) and cov < 2: f.append(f"Interest coverage {cov:.1f}x weak (<2)")
    if not np.isnan(cr) and cr < 1: f.append(f"Current ratio {cr:.2f} <1 (liquidity stress)")
    return f


def run_solvency_gate(c: CompanyData, cls: dict = None) -> dict:
    z = altman_z(c)
    lev = leverage(c)

    # STEP 0: industrial solvency models don't apply to financials/REITs, and
    # utilities/captive-finance carry structurally high leverage → don't FAIL.
    if cls and not cls.get("industrial_solvency_applies", True):
        return {"verdict": "N/A", "flags": [],
                "note": f"Industrial solvency model not applicable to '{cls['type']}' — "
                        f"needs a sector-specific model (see STEP 0 caveats).",
                "altman_z": z, "leverage": lev}

    ctype = cls.get("type") if cls else "standard"
    flags = list(lev["flags"])

    if ctype == "utility":
        # Altman Z (mfg-calibrated) and net-debt/EBITDA misfire on regulated
        # utilities: high leverage + low asset turnover are structural, not
        # distress. Judge utilities on interest coverage instead.
        flags = [f for f in flags if "high (>4)" not in f]
        cov = lev.get("interest_coverage")
        verdict = "FAIL" if (cov is not None and cov < 1.5) else ("WARN" if flags else "PASS")
        return {"verdict": verdict, "flags": flags, "altman_z": z, "leverage": lev,
                "note": "Utility: Altman Z / net-debt-EBITDA are structural, not distress; "
                        "judged on interest coverage"}

    if z.get("zone") == "distress":
        flags.append(f"Altman Z {z['value']} in distress zone (<1.8)")
    if ctype == "cyclical" and cls and any("captive-finance" in cav for cav in cls.get("caveats", [])):
        # automaker finance arm: downgrade leverage FAIL to a caveat
        verdict = "WARN"
        flags = [f + " — likely captive-finance distortion" for f in flags]
        return {"verdict": verdict, "flags": flags, "altman_z": z, "leverage": lev,
                "note": "Leverage ratios distorted by financing arm; not genuine distress"}

    verdict = "FAIL" if (z.get("zone") == "distress" or len(lev["flags"]) >= 2) else \
              ("WARN" if flags else "PASS")
    return {"verdict": verdict, "flags": flags, "altman_z": z, "leverage": lev}
