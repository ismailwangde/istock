"""Profitability & returns on capital (framework §3) — the quality core.

ROIC vs WACC spread (the single best moat proxy), DuPont decomposition of ROE
(to catch leverage-inflated ROE), gross profitability (Novy-Marx ⭐), margins,
and FCF generation. Trend over available years is reported, not just latest.
"""
from __future__ import annotations

import numpy as np

from .data import CompanyData
from .forensic import _at, _safe_div

# crude sector WACC proxies (%) — good enough to judge ROIC>WACC sign; refine later
_WACC_BY_SECTOR = {
    "Technology": 9.5, "Communication Services": 8.5, "Consumer Cyclical": 9.0,
    "Consumer Defensive": 7.0, "Healthcare": 8.0, "Industrials": 8.5,
    "Financial Services": 9.0, "Energy": 9.5, "Utilities": 6.0,
    "Real Estate": 7.5, "Basic Materials": 9.0,
}


def _series_pct(num, den, n):
    out = []
    for i in range(n):
        v = _safe_div(_at(num, i), _at(den, i))
        out.append(None if np.isnan(v) else round(v * 100, 2))
    return out


def roic(c: CompanyData, wacc: float = None) -> dict:
    """NOPAT / invested capital, vs WACC. Positive & widening spread = moat.
    `wacc` comes from STEP 0 classification; falls back to sector proxy."""
    ebit = c.ebit()
    tax_rate = _safe_div(_at(c.tax(), 0), _at(c.pretax(), 0))
    tax_rate = 0.21 if (np.isnan(tax_rate) or tax_rate < 0 or tax_rate > 0.5) else tax_rate
    ic = c.invested_cap()
    n = min(c.n_periods, 5)
    series = []
    for i in range(n):
        nopat = _at(ebit, i) * (1 - tax_rate)
        v = _safe_div(nopat, _at(ic, i))
        series.append(None if np.isnan(v) else round(v * 100, 2))
    latest = series[0] if series else None
    if wacc is None:
        wacc = _WACC_BY_SECTOR.get(c.sector, 8.5)
    spread = None if latest is None else round(latest - wacc, 2)
    trend = _trend([s for s in series if s is not None])
    return {"roic_pct": latest, "roic_series": series, "wacc_proxy_pct": wacc,
            "spread_pct": spread, "trend": trend,
            "creates_value": None if spread is None else spread > 0,
            "note": "ROIC>WACC = value creation; widening spread = moat"}


def dupont_roe(c: CompanyData) -> dict:
    """ROE = net margin x asset turnover x equity multiplier. Flags ROE that is
    driven by leverage rather than operating quality."""
    ni, rev, assets, eq = c.net_income(), c.rev(), c.assets(), c.equity()
    roe = _safe_div(_at(ni, 0), _at(eq, 0))
    margin = _safe_div(_at(ni, 0), _at(rev, 0))
    turnover = _safe_div(_at(rev, 0), _at(assets, 0))
    leverage_mult = _safe_div(_at(assets, 0), _at(eq, 0))
    leverage_driven = (not np.isnan(leverage_mult) and leverage_mult > 3)
    return {"roe_pct": None if np.isnan(roe) else round(roe*100, 2),
            "net_margin_pct": None if np.isnan(margin) else round(margin*100, 2),
            "asset_turnover": None if np.isnan(turnover) else round(turnover, 2),
            "equity_multiplier": None if np.isnan(leverage_mult) else round(leverage_mult, 2),
            "leverage_driven_flag": leverage_driven,
            "note": "equity multiplier >3 = ROE inflated by leverage"}


def margins(c: CompanyData) -> dict:
    n = min(c.n_periods, 5)
    gross = _series_pct(c.gross(), c.rev(), n)
    op = _series_pct(c.ebit(), c.rev(), n)
    net = _series_pct(c.net_income(), c.rev(), n)
    return {"gross_margin_pct": gross, "operating_margin_pct": op, "net_margin_pct": net,
            "gross_trend": _trend([x for x in gross if x is not None]),
            "operating_trend": _trend([x for x in op if x is not None])}


def gross_profitability(c: CompanyData) -> dict:
    """Gross profit / total assets (Novy-Marx) — ⭐ a robust quality factor."""
    v = _safe_div(_at(c.gross(), 0), _at(c.assets(), 0))
    return {"value": None if np.isnan(v) else round(v, 3),
            "note": "higher = higher-quality; robust return predictor"}


def cash_flow_quality(c: CompanyData) -> dict:
    n = min(c.n_periods, 5)
    fcf_margin = _series_pct(c.fcf(), c.rev(), n)
    fcf_conv = _safe_div(_at(c.fcf(), 0), _at(c.net_income(), 0))
    sbc_ocf = _safe_div(_at(c.sbc(), 0), _at(c.ocf(), 0))
    return {"fcf_margin_pct": fcf_margin,
            "fcf_conversion": None if np.isnan(fcf_conv) else round(fcf_conv, 2),
            "sbc_pct_of_ocf": None if np.isnan(sbc_ocf) else round(sbc_ocf*100, 1),
            "note": "FCF margin >10% strong; SBC>20% of OCF inflates adjusted FCF"}


def _trend(vals):
    """rising / falling / flat / n-a from a most-recent-first list."""
    v = [x for x in vals if x is not None]
    if len(v) < 2:
        return "n/a"
    # v[0] is latest; compare latest vs oldest available
    if v[0] > v[-1] * 1.03:
        return "rising"
    if v[0] < v[-1] * 0.97:
        return "falling"
    return "flat"


def run_profitability(c: CompanyData, wacc: float = None) -> dict:
    r = roic(c, wacc)
    d = dupont_roe(c)
    m = margins(c)
    gp = gross_profitability(c)
    cfq = cash_flow_quality(c)
    flags = []
    if r.get("creates_value") is False:
        flags.append(f"ROIC {r['roic_pct']}% < WACC ~{r['wacc_proxy_pct']}% (destroys value)")
    if d.get("leverage_driven_flag"):
        flags.append(f"ROE inflated by leverage (equity mult {d['equity_multiplier']}x)")
    if m.get("operating_trend") == "falling":
        flags.append("Operating margin declining")
    if cfq.get("sbc_pct_of_ocf") and cfq["sbc_pct_of_ocf"] > 20:
        flags.append(f"SBC {cfq['sbc_pct_of_ocf']}% of OCF (dilutive)")
    return {"flags": flags, "roic": r, "dupont": d, "margins": m,
            "gross_profitability": gp, "cash_flow_quality": cfq}
