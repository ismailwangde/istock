"""Equity analysis engine implementing ANALYSIS_FRAMEWORK.md (milestone 1).

Public API:
    from analyzer import analyze
    result = analyze("AAPL")        # -> dict (also writes JSON + markdown)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import data as _data
from .classify import classify
from .forensic import run_forensic_gate
from .solvency import run_solvency_gate
from .profitability import run_profitability
from .valuation import run_valuation
from .banks import run_bank_analysis
from .growth import run_growth
from .capital_allocation import run_capital_allocation
from .moat import run_moat
from .ownership import run_ownership
from .macro import market_context
from .analyst import run_analyst
from .news import run_news
from .peers import extract_comparable, peer_context
from .report import to_markdown

OUT_DIR = Path(__file__).resolve().parent.parent / "reports"


def _fmt_cap(v):
    if not isinstance(v, (int, float)) or math.isnan(v):
        return "?"
    for unit, div in [("T", 1e12), ("B", 1e9), ("M", 1e6)]:
        if abs(v) >= div:
            return f"${v/div:.1f}{unit}"
    return f"${v:,.0f}"


def _quality_score(forensic, solvency, prof) -> int:
    """0-100 composite: gates can zero it out; profitability drives the rest."""
    if forensic["verdict"] == "FAIL" or solvency["verdict"] == "FAIL":
        return 0
    score = 50
    # forensic
    f = forensic["piotroski_f"].get("value")
    if isinstance(f, (int, float)):
        score += (f - 4.5) * 3            # +/- up to ~13
    if forensic["verdict"] == "WARN":
        score -= 8
    if solvency["verdict"] == "WARN":
        score -= 5
    # profitability
    roic = prof["roic"]
    if roic.get("spread_pct") is not None:
        score += max(-15, min(20, roic["spread_pct"] * 1.2))
    if roic.get("trend") == "rising":
        score += 5
    elif roic.get("trend") == "falling":
        score -= 5
    if prof["dupont"].get("leverage_driven_flag"):
        score -= 6
    if prof["margins"].get("operating_trend") == "rising":
        score += 4
    score -= 3 * len(prof["flags"])
    return int(max(0, min(100, round(score))))


def _apply_common_adjustments(score, growth, capalloc, ownership, analyst=None, moat=None) -> int:
    """Nudge the quality score with growth/capital-allocation/moat/insider/analyst signals."""
    if score == 0:
        return 0
    # growth quality
    rc = growth.get("rev_cagr_3y_pct")
    if rc is not None:
        score += max(-4, min(6, (rc - 5) * 0.4))
    score -= 3 * len(growth.get("flags", []))
    # capital allocation
    if capalloc.get("reduces_share_count"):
        score += 3
    score -= 3 * len(capalloc.get("flags", []))
    # moat
    if moat:
        score += 2 * len(moat.get("moat_signals", []))
        score -= 3 * len(moat.get("weak_signals", []))
    # insider cluster buying (robust positive)
    if any("Cluster insider buying" in s for s in ownership.get("signals", [])):
        score += 4
    # analyst estimate revisions (⭐ modest)
    if analyst:
        nr = analyst.get("net_revisions_30d")
        if nr is not None:
            score += max(-4, min(4, nr))
    return int(max(0, min(100, round(score))))


def _bank_quality_score(forensic, bank) -> int:
    """0-100 for banks: ROA/ROE/efficiency/TBV growth."""
    m = bank["metrics"]
    roa = m["roa_pct"][0] if m["roa_pct"] and m["roa_pct"][0] is not None else None
    roe = m["roe_pct"][0] if m["roe_pct"] and m["roe_pct"][0] is not None else None
    eff = m["efficiency_ratio_pct"]
    score = 50
    if roa is not None:
        score += (roa - 1.0) * 20          # 1% ROA neutral; 1.5% → +10
    if roe is not None:
        score += (roe - 10) * 1.2          # 10% ROE neutral
    if eff is not None:
        score += (60 - eff) * 0.6          # <60% good
    if bank["roa_trend"] == "rising": score += 4
    elif bank["roa_trend"] == "falling": score -= 4
    if m["tbv_per_share_cagr_3y_pct"] and m["tbv_per_share_cagr_3y_pct"] > 5:
        score += 5
    if forensic["verdict"] == "FAIL":
        return 0
    score -= 4 * len(bank["flags"])
    return int(max(0, min(100, round(score))))


def _bank_verdict(quality, forensic):
    if forensic["verdict"] == "FAIL":
        return "AVOID — accounting integrity failure"
    if quality >= 70:
        return "QUALITY BANK — strong returns & efficiency"
    if quality >= 45:
        return "MIXED — average bank economics"
    return "WEAK — subpar bank returns/efficiency"


def _overall_verdict(forensic, solvency, quality):
    if forensic["verdict"] == "FAIL":
        return "AVOID — accounting integrity failure"
    if solvency["verdict"] == "FAIL":
        return "AVOID — distress risk"
    if quality >= 70:
        return "QUALITY — strong on measured dimensions"
    if quality >= 45:
        return "MIXED — proceed with the flagged caveats"
    return "WEAK — poor returns/quality profile"


def analyze(ticker: str, write: bool = True, include_news: bool = True) -> dict:
    c = _data.fetch(ticker)
    if c.n_periods == 0:
        return {"ticker": ticker.upper(), "error": "no financial data from yfinance"}

    cls = classify(c)
    forensic = run_forensic_gate(c, cls)
    solvency = run_solvency_gate(c, cls)

    result = {
        "company": {
            "ticker": c.ticker,
            "name": c.info.get("longName") or c.info.get("shortName", ""),
            "sector": c.sector, "industry": c.industry,
            "market_cap": c.market_cap, "market_cap_fmt": _fmt_cap(c.market_cap),
            "periods": c.n_periods,
        },
        "classification": cls,
        "forensic": forensic,
        "solvency": solvency,
    }

    # modules that apply to all company types
    growth = run_growth(c)
    capalloc = run_capital_allocation(c)
    ownership = run_ownership(c)
    analyst = run_analyst(c.ticker)
    peer = peer_context(c.sector, extract_comparable(c))
    result.update({"growth": growth, "capital_allocation": capalloc, "ownership": ownership,
                   "analyst": analyst, "peer_context": peer,
                   "market_context": market_context()})
    if include_news:
        result["news"] = run_news(c.ticker)
    common_flags = growth["flags"] + capalloc["flags"] + ownership["flags"] + analyst["flags"]

    if cls["type"] == "financial":
        # banks/insurers: industrial profitability & valuation don't apply
        bank = run_bank_analysis(c, cls)
        quality = _bank_quality_score(forensic, bank)
        quality = _apply_common_adjustments(quality, growth, capalloc, ownership, analyst)
        all_flags = forensic["flags"] + bank["flags"] + common_flags
        verdict = _bank_verdict(quality, forensic)
        result.update({"bank_analysis": bank, "verdict": verdict,
                       "quality_score": quality, "all_flags": all_flags})
    else:
        prof = run_profitability(c, cls["wacc"])
        valuation = run_valuation(c, cls)
        moat = run_moat(c, prof["roic"].get("roic_series"))
        quality = _quality_score(forensic, solvency, prof)
        quality = _apply_common_adjustments(quality, growth, capalloc, ownership, analyst, moat)
        all_flags = forensic["flags"] + solvency["flags"] + prof["flags"] + valuation["flags"] + common_flags
        verdict = _overall_verdict(forensic, solvency, quality)
        result.update({"profitability": prof, "valuation": valuation, "moat": moat,
                       "verdict": verdict, "quality_score": quality,
                       "all_flags": all_flags})

    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / f"{c.ticker}.json").write_text(json.dumps(result, indent=2, default=str))
        (OUT_DIR / f"{c.ticker}.md").write_text(to_markdown(result))
    return result
