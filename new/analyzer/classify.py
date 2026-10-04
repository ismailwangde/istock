"""STEP 0 — classify the company so the right model/thresholds get applied
(framework §0, §18). This is what structurally fixes generic-model misfires:
  - hyper-growth names (NVDA) trip Beneish's SGI term → mark Beneish unreliable
  - financials / captive-finance (banks, Ford Credit) break industrial solvency
    models → mark industrial solvency N/A and route to a caveat
  - utilities/REITs carry structurally high debt → relax leverage thresholds
  - cyclicals (memory, autos, energy) → single-year multiples mislead
"""
from __future__ import annotations

import numpy as np

from .data import CompanyData
from .forensic import _at, _safe_div

# type -> WACC proxy (%)
_WACC = {"utility": 6.0, "reit": 7.0, "financial": 9.0, "hypergrowth": 10.5,
         "cyclical": 9.5, "standard": 8.5}


def _rev_growth(c: CompanyData):
    rev = c.rev()
    yoy = _safe_div(_at(rev, 0), _at(rev, 1)) - 1 if c.n_periods >= 2 else np.nan
    if c.n_periods >= 4 and _at(rev, 3) > 0:
        cagr3 = (_at(rev, 0) / _at(rev, 3)) ** (1/3) - 1
    else:
        cagr3 = np.nan
    return yoy, cagr3


def classify(c: CompanyData) -> dict:
    sector = (c.sector or "").lower()
    industry = (c.industry or "").lower()
    yoy, cagr3 = _rev_growth(c)
    growth = np.nanmax([yoy if not np.isnan(yoy) else -9,
                        cagr3 if not np.isnan(cagr3) else -9])

    ctype = "standard"
    subtype = None
    caveats = []

    # order matters: financial/reit/utility structural first, then growth/cycle
    if "financial" in sector or any(k in industry for k in ("bank", "insurance", "capital markets", "asset management")):
        ctype = "financial"
        subtype = _financial_subtype(industry)
        caveats.append(f"Financial ({subtype}): industrial solvency (Altman Z, net-debt/EBITDA) does not apply; uses financial-specific model")
        if subtype != "bank":
            caveats.append(f"{subtype} uses bank-model approximation for now (insurance needs combined ratio; asset mgr needs AUM/fee margin) — see TODO")
    elif "real estate" in sector or "reit" in industry:
        ctype = "reit"
        caveats.append("REIT: use FFO/AFFO not EPS; high leverage is structural; P/FFO not P/E")
    elif "utilit" in sector:
        ctype = "utility"
        caveats.append("Utility: capital-intensive; net-debt/EBITDA up to ~5-6x normal; low WACC")
    elif ("auto manufacturer" in industry or "auto" in industry) and _captive_finance(c):
        ctype = "cyclical"
        caveats.append("Automaker with captive-finance arm: industrial leverage ratios distorted by financing receivables/debt")
    elif not np.isnan(growth) and growth > 0.35:
        ctype = "hypergrowth"
        caveats.append(f"Hyper-growth (~{growth*100:.0f}% rev): Beneish M over-flags rapid growth (SGI/AQI terms); treat M-score as unreliable")
    elif sector in ("energy", "basic materials") or any(k in industry for k in ("semiconductor", "memory", "oil", "gas", "mining", "steel", "chemical")):
        ctype = "cyclical"
        caveats.append("Cyclical/commodity: single-year margins & multiples mislead; use mid-cycle/normalized figures and full-cycle ROIC")

    return {
        "type": ctype,
        "financial_subtype": subtype,
        "sector": c.sector, "industry": c.industry,
        "rev_growth_yoy": None if np.isnan(yoy) else round(yoy*100, 1),
        "rev_cagr_3y": None if np.isnan(cagr3) else round(cagr3*100, 1),
        "wacc": _WACC[ctype],
        "beneish_reliable": ctype != "hypergrowth",
        "industrial_solvency_applies": ctype not in ("financial", "reit"),
        "caveats": caveats,
    }


def _financial_subtype(industry: str) -> str:
    if "insurance" in industry:
        return "insurance"
    if any(k in industry for k in ("asset management", "capital markets", "brokerage")):
        return "asset_manager"
    if "bank" in industry or "mortgage" in industry or "credit" in industry:
        return "bank"
    return "bank"   # default financial → bank-model approximation


def _captive_finance(c: CompanyData) -> bool:
    """Heuristic: extreme leverage inconsistent with an industrial → likely a
    captive-finance arm (Ford Credit) rather than genuine distress."""
    nd = _at(c.net_debt(), 0)
    ebitda = _at(c.ebitda(), 0)
    r = _safe_div(nd, ebitda)
    return (not np.isnan(r)) and r > 8
