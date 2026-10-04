"""STEP 1 — Forensic / earnings-quality GATE (framework §2E).

The highest-ROI screen: a company that fails accounting integrity is
un-analyzable, so this runs first and can halt the whole pipeline. Computes:
  - Beneish M-score (8-var earnings-manipulation model; > -1.89 = flag)
  - Sloan accruals ratio (high = earnings won't persist)
  - Piotroski F-score (0-9 financial-strength; 8-9 strong, 0-2 weak)
  - OCF vs NI divergence, DSO trend, inventory-vs-sales trend

All are ⭐robust per the academic record. Needs >=2 annual periods for the
year-over-year models; degrades gracefully to NaN otherwise.
"""
from __future__ import annotations

import numpy as np

from .data import CompanyData


def _at(series, i):
    """Value at period i (0 = latest), NaN if unavailable."""
    try:
        v = series.iloc[i]
        return float(v) if v is not None else np.nan
    except Exception:
        return np.nan


def _safe_div(a, b):
    return a / b if (b not in (0, None) and not np.isnan(a) and not np.isnan(b) and b != 0) else np.nan


def beneish_m_score(c: CompanyData) -> dict:
    """8-variable Beneish M-score comparing year t to t-1. > -1.89 = likely
    earnings manipulator (caught Enron ex-ante)."""
    if c.n_periods < 2:
        return {"value": np.nan, "flag": None, "note": "needs 2 yrs"}

    rev, cogs = c.rev(), c.cogs()
    recv, assets = c.receivables(), c.assets()
    ca, ppe = c.cur_assets(), c.ppe_net()
    dep, sga = c.dep_inc(), c.sga()
    ni, ocf = c.net_income(), c.ocf()
    cl, ltd = c.cur_liab(), c.cur_ltd()

    def g(s, i): return _at(s, i)

    # t = 0, t-1 = 1
    sales_t, sales_p = g(rev, 0), g(rev, 1)
    # DSRI — days sales in receivables index
    dsri = _safe_div(_safe_div(g(recv, 0), sales_t), _safe_div(g(recv, 1), sales_p))
    # GMI — gross margin index (prior/current; >1 means margin deteriorating)
    gm_t = _safe_div(sales_t - g(cogs, 0), sales_t)
    gm_p = _safe_div(sales_p - g(cogs, 1), sales_p)
    gmi = _safe_div(gm_p, gm_t)
    # AQI — asset quality index (non-current, non-PPE assets share)
    aqi_t = 1 - _safe_div(g(ca, 0) + g(ppe, 0), g(assets, 0))
    aqi_p = 1 - _safe_div(g(ca, 1) + g(ppe, 1), g(assets, 1))
    aqi = _safe_div(aqi_t, aqi_p)
    # SGI — sales growth index
    sgi = _safe_div(sales_t, sales_p)
    # DEPI — depreciation rate index
    depr_t = _safe_div(g(dep, 0), g(dep, 0) + g(ppe, 0))
    depr_p = _safe_div(g(dep, 1), g(dep, 1) + g(ppe, 1))
    depi = _safe_div(depr_p, depr_t)
    # SGAI — SG&A index
    sgai = _safe_div(_safe_div(g(sga, 0), sales_t), _safe_div(g(sga, 1), sales_p))
    # LVGI — leverage index
    lev_t = _safe_div(g(cl, 0) + g(ltd, 0), g(assets, 0))
    lev_p = _safe_div(g(cl, 1) + g(ltd, 1), g(assets, 1))
    lvgi = _safe_div(lev_t, lev_p)
    # TATA — total accruals to total assets (the dominant term)
    tata = _safe_div(g(ni, 0) - g(ocf, 0), g(assets, 0))

    parts = {"DSRI": dsri, "GMI": gmi, "AQI": aqi, "SGI": sgi, "DEPI": depi,
             "SGAI": sgai, "LVGI": lvgi, "TATA": tata}
    # missing indices default to the "neutral" value 1.0 (0 for TATA) so a
    # single missing line item doesn't nuke the whole score
    neutral = {"DSRI": 1, "GMI": 1, "AQI": 1, "SGI": 1, "DEPI": 1, "SGAI": 1, "LVGI": 1, "TATA": 0}
    p = {k: (neutral[k] if np.isnan(v) else v) for k, v in parts.items()}
    m = (-4.84 + 0.92*p["DSRI"] + 0.528*p["GMI"] + 0.404*p["AQI"] + 0.892*p["SGI"]
         + 0.115*p["DEPI"] - 0.172*p["SGAI"] + 4.679*p["TATA"] - 0.327*p["LVGI"])
    return {"value": round(m, 3), "flag": m > -1.89,
            "components": {k: (None if np.isnan(v) else round(v, 3)) for k, v in parts.items()},
            "note": "> -1.89 = likely manipulator"}


def sloan_accruals(c: CompanyData) -> dict:
    """(NI - OCF) / avg total assets. High positive = low-quality earnings that
    tend to reverse (Sloan anomaly)."""
    if c.n_periods < 2:
        ni, ocf, a = _at(c.net_income(), 0), _at(c.ocf(), 0), _at(c.assets(), 0)
        val = _safe_div(ni - ocf, a)
    else:
        ni, ocf = _at(c.net_income(), 0), _at(c.ocf(), 0)
        avg_a = np.nanmean([_at(c.assets(), 0), _at(c.assets(), 1)])
        val = _safe_div(ni - ocf, avg_a)
    # >0.10 is a common "high accruals" flag
    return {"value": None if np.isnan(val) else round(val, 4),
            "flag": (not np.isnan(val)) and val > 0.10,
            "note": ">0.10 = high accruals / low earnings quality"}


def piotroski_f(c: CompanyData) -> dict:
    """0-9 financial-strength score (4 profitability, 3 leverage/liquidity,
    2 efficiency). 8-9 strong, 0-2 weak."""
    if c.n_periods < 2:
        return {"value": np.nan, "note": "needs 2 yrs"}
    ni, ocf, assets = c.net_income(), c.ocf(), c.assets()
    ltd, ca, cl = c.cur_ltd(), c.cur_assets(), c.cur_liab()
    shares, rev, cogs = c.dil_shares(), c.rev(), c.cogs()

    roa_t = _safe_div(_at(ni, 0), _at(assets, 0))
    roa_p = _safe_div(_at(ni, 1), _at(assets, 1))
    checks = {}
    checks["roa_positive"] = _at(ni, 0) > 0
    checks["ocf_positive"] = _at(ocf, 0) > 0
    checks["roa_improving"] = (not np.isnan(roa_t) and not np.isnan(roa_p) and roa_t > roa_p)
    checks["accruals_ok"] = _at(ocf, 0) > _at(ni, 0)            # OCF > NI (quality)
    checks["leverage_down"] = _safe_div(_at(ltd, 0), _at(assets, 0)) < _safe_div(_at(ltd, 1), _at(assets, 1))
    checks["curr_ratio_up"] = _safe_div(_at(ca, 0), _at(cl, 0)) > _safe_div(_at(ca, 1), _at(cl, 1))
    checks["no_dilution"] = _at(shares, 0) <= _at(shares, 1) * 1.01   # <=1% growth tolerated
    gm_t = _safe_div(_at(rev, 0) - _at(cogs, 0), _at(rev, 0))
    gm_p = _safe_div(_at(rev, 1) - _at(cogs, 1), _at(rev, 1))
    checks["gross_margin_up"] = (not np.isnan(gm_t) and not np.isnan(gm_p) and gm_t > gm_p)
    at_t = _safe_div(_at(rev, 0), _at(assets, 0))
    at_p = _safe_div(_at(rev, 1), _at(assets, 1))
    checks["asset_turnover_up"] = (not np.isnan(at_t) and not np.isnan(at_p) and at_t > at_p)

    score = sum(1 for v in checks.values() if v is True)
    return {"value": score, "checks": {k: bool(v) for k, v in checks.items()},
            "note": "8-9 strong, 0-2 weak"}


def cash_vs_earnings(c: CompanyData) -> dict:
    """FCF conversion + persistent NI>OCF flag (aggressive-accrual signature)."""
    ni, ocf, fcf = c.net_income(), c.ocf(), c.fcf()
    conv = _safe_div(_at(fcf, 0), _at(ni, 0))
    # count years where NI > OCF over available history
    n = min(c.n_periods, 5)
    ni_gt_ocf = sum(1 for i in range(n) if _at(ni, i) > _at(ocf, i) and not np.isnan(_at(ocf, i)))
    return {"fcf_conversion": None if np.isnan(conv) else round(conv, 2),
            "years_ni_above_ocf": ni_gt_ocf, "years_checked": n,
            "flag": ni_gt_ocf >= max(2, n - 1),
            "note": "FCF/NI ~1 healthy; persistent NI>OCF = accrual flag"}


def receivables_inventory_trend(c: CompanyData) -> dict:
    """DSO and inventory growing faster than sales = demand cracks / channel
    stuffing."""
    if c.n_periods < 2:
        return {"note": "needs 2 yrs"}
    rev = c.rev()
    dso_t = _safe_div(_at(c.receivables(), 0), _at(rev, 0)) * 365
    dso_p = _safe_div(_at(c.receivables(), 1), _at(rev, 1)) * 365
    sales_g = _safe_div(_at(rev, 0), _at(rev, 1)) - 1
    inv_g = _safe_div(_at(c.inventory(), 0), _at(c.inventory(), 1)) - 1
    return {"dso_days": None if np.isnan(dso_t) else round(dso_t, 1),
            "dso_prev": None if np.isnan(dso_p) else round(dso_p, 1),
            "dso_rising": (not np.isnan(dso_t) and not np.isnan(dso_p) and dso_t > dso_p * 1.15),
            "inventory_vs_sales_flag": (not np.isnan(inv_g) and not np.isnan(sales_g) and inv_g > sales_g + 0.15),
            "note": "DSO +15% or inventory outgrowing sales = flag"}


def run_forensic_gate(c: CompanyData, cls: dict = None) -> dict:
    """Aggregate the forensic checks and decide PASS / WARN / FAIL.
    STEP 0: for hyper-growth names the Beneish SGI/AQI terms over-flag, so the
    M-score is demoted from a hard fraud signal to a caveat."""
    m = beneish_m_score(c)
    sloan = sloan_accruals(c)
    f = piotroski_f(c)
    cash = cash_vs_earnings(c)
    trend = receivables_inventory_trend(c)

    beneish_reliable = cls.get("beneish_reliable", True) if cls else True
    is_financial = (cls.get("type") == "financial") if cls else False
    flags = []
    if m.get("flag"):
        if beneish_reliable:
            flags.append(f"Beneish M {m['value']} > -1.89 (manipulation risk)")
        else:
            m["note"] += " | demoted: hyper-growth over-flags Beneish (not counted as fraud signal)"
            m["flag_demoted"] = True
    if sloan.get("flag"): flags.append(f"High accruals {sloan['value']} (low earnings quality)")

    # bank OCF (loan/deposit flows), inventory, and Piotroski margin/turnover
    # components are not comparable to industrials — suppress for financials
    if not is_financial:
        if cash.get("flag"): flags.append(f"NI>OCF in {cash['years_ni_above_ocf']}/{cash['years_checked']} yrs (accruals)")
        if trend.get("dso_rising"): flags.append("DSO rising >15% (channel-stuffing / demand risk)")
        if trend.get("inventory_vs_sales_flag"): flags.append("Inventory outgrowing sales")
        if isinstance(f.get("value"), (int, float)) and f["value"] <= 2:
            flags.append(f"Piotroski F {f['value']} (weak fundamentals)")
    else:
        f["note"] = (f.get("note", "") + " | Piotroski partly N/A for banks (no gross margin/inventory/turnover)").strip(" |")
        cash["note"] = (cash.get("note", "") + " | bank OCF distorted by loan/deposit flows — not a valid accrual signal").strip(" |")

    # verdict: FAIL if the two heavyweight fraud signals both fire, else WARN if
    # any flag, else PASS. A demoted (hyper-growth) Beneish flag doesn't count.
    beneish_counts = bool(m.get("flag")) and beneish_reliable
    cash_counts = bool(cash.get("flag")) and not is_financial
    heavy = int(beneish_counts) + int(bool(sloan.get("flag"))) + int(cash_counts)
    if heavy >= 2:
        verdict = "FAIL"
    elif flags:
        verdict = "WARN"
    else:
        verdict = "PASS"

    return {
        "verdict": verdict,
        "flags": flags,
        "beneish_m": m,
        "sloan_accruals": sloan,
        "piotroski_f": f,
        "cash_vs_earnings": cash,
        "receivables_inventory": trend,
    }
