"""Render an analysis result dict to a readable markdown report."""
from __future__ import annotations


def _bullets(flags):
    return "\n".join(f"- ⚠️ {f}" for f in flags) if flags else "- none"


def _v(x, suffix=""):
    """Format a possibly-None numeric field; 'n/a' instead of 'Nonex'."""
    return "n/a" if x is None else f"{x}{suffix}"


def _common_sections(r):
    """Growth, capital allocation, ownership — shared by all company types."""
    L = []
    g = r.get("growth", {})
    L.append("## Growth")
    L.append(f"- Revenue CAGR 3y **{_v(g.get('rev_cagr_3y_pct'),'%')}** / 5y {_v(g.get('rev_cagr_5y_pct'),'%')} · "
             f"YoY {_v(g.get('rev_yoy_pct'),'%')} ({g.get('acceleration')})")
    L.append(f"- Net income CAGR 3y {_v(g.get('net_income_cagr_3y_pct'),'%')} · FCF CAGR 3y {_v(g.get('fcf_cagr_3y_pct'),'%')} · "
             f"share count 3y {_v(g.get('share_count_change_3y_pct'),'%')}")
    if g.get("rule_of_40") is not None:
        L.append(f"- Rule of 40 (growth + FCF margin): {g['rule_of_40']}")
    for fl in g.get("flags", []):
        L.append(f"- ⚠️ {fl}")

    ca = r.get("capital_allocation", {})
    L.append("\n## Capital allocation")
    L.append(f"- Share count 3y {_v(ca.get('share_count_change_3y_pct'),'%')} "
             f"({'reduces ✅' if ca.get('reduces_share_count') else 'not reducing'}) · "
             f"buyback {_v(ca.get('buyback_pct_of_fcf'),'% of FCF')} · SBC {_v(ca.get('sbc_pct_of_revenue'),'% of rev')}")
    if ca.get("pays_dividend"):
        L.append(f"- Dividend: payout {_v(ca.get('dividend_payout_of_fcf_pct'),'% of FCF')} · 3y growth {_v(ca.get('dividend_cagr_3y_pct'),'%')}")
    else:
        L.append("- No dividend")
    for fl in ca.get("flags", []):
        L.append(f"- ⚠️ {fl}")

    ow = r.get("ownership", {})
    L.append("\n## Ownership & insiders")
    for s in ow.get("signals", []):
        L.append(f"- ✅ {s}")
    L.append(f"- Insider net shares (6m): {ow.get('insider_net_shares_6m')} · "
             f"buys {ow.get('insider_buy_transactions_6m')} / sells {ow.get('insider_sell_transactions_6m')} · "
             f"distinct buyers {ow.get('distinct_insider_buyers_recent')}")
    L.append(f"- Insider held {_v(ow.get('insider_pct_held'),'%')} · institutions {_v(ow.get('institution_pct_held'),'%')} · "
             f"short {_v(ow.get('short_pct_float'),'% of float')}")
    for fl in ow.get("flags", []):
        L.append(f"- ⚠️ {fl}")

    # analyst signals
    an = r.get("analyst", {})
    if an:
        L.append("\n## Earnings & analyst signals")
        for s in an.get("signals", []):
            L.append(f"- ✅ {s}")
        L.append(f"- Est. revisions 30d: net {an.get('net_revisions_30d')} "
                 f"(↑{an.get('revisions_up_30d')}/↓{an.get('revisions_down_30d')}) · "
                 f"FY estimate trend 90d {_v(an.get('fy_estimate_trend_90d_pct'),'%')}")
        L.append(f"- Surprise: avg {_v(an.get('avg_surprise_pct'),'%')} · beat rate {_v(an.get('beat_rate_pct'),'%')} · "
                 f"price target upside {_v(an.get('price_target_upside_pct'),'%')} · "
                 f"rating {an.get('recommendation')} ({an.get('analyst_count')} analysts)")
        for fl in an.get("flags", []):
            L.append(f"- ⚠️ {fl}")

    # peer-relative
    pc = r.get("peer_context", {})
    if pc:
        L.append("\n## Peer-relative (sector percentiles)")
        if pc.get("available"):
            L.append(f"*vs {pc['n_peers']} {pc['sector']} peers — percentile (higher = better)*")
            for m, d in pc.get("percentiles", {}).items():
                bar = "█" * (d["percentile"] // 10)
                L.append(f"- {m:16} {d['percentile']:3}th pct  {bar}  (co {d['value']} vs peer median {d['peer_median']})")
        else:
            L.append(f"- ⓘ {pc.get('note')}")

    mc = r.get("market_context", {})
    if mc:
        L.append("\n## Market context (regime — non-scoring)")
        L.append(f"- VIX {_v(mc.get('vix'))} · US 10y {_v(mc.get('us_10y_yield_pct'),'%')} · "
                 f"curve 10y-3m {_v(mc.get('yield_curve_10y_minus_3m'),'pp')} · "
                 f"DXY {_v(mc.get('dollar_index'))} · oil {_v(mc.get('oil_wti'))}")
        if mc.get("regime"):
            L.append(f"- Regime: {' · '.join(mc['regime'])}")

    # news — display only
    nw = r.get("news", {})
    if nw and nw.get("headlines"):
        L.append("\n## Recent news (context only — NOT scored)")
        for h in nw["headlines"][:6]:
            L.append(f"- [{h['sentiment_tag']}] {h['published']} — {h['title']}")
    return "\n".join(L)


def to_markdown(r: dict) -> str:
    c = r["company"]
    L = []
    L.append(f"# Analysis: {c['ticker']} — {c.get('name','')}")
    L.append(f"*{c.get('sector','?')} / {c.get('industry','?')} · "
             f"mktcap {c.get('market_cap_fmt','?')} · {c['periods']} yrs data*\n")
    L.append(f"## Verdict: **{r['verdict']}**  (quality score {r['quality_score']}/100)\n")

    # STEP 0 — classification
    cl = r.get("classification", {})
    L.append(f"## STEP 0 — Classification: **{cl.get('type','?')}**")
    L.append(f"- Rev growth: YoY {_v(cl.get('rev_growth_yoy'),'%')} · 3y CAGR {_v(cl.get('rev_cagr_3y'),'%')} · WACC used {cl.get('wacc')}%")
    for cav in cl.get("caveats", []):
        L.append(f"- ⓘ {cav}")
    L.append("")

    if r["all_flags"]:
        L.append("### Red flags")
        L.append(_bullets(r["all_flags"]) + "\n")

    # Step 1 — forensic
    fg = r["forensic"]
    L.append(f"## STEP 1 — Forensic gate: **{fg['verdict']}**")
    m = fg["beneish_m"]; s = fg["sloan_accruals"]; f = fg["piotroski_f"]
    L.append(f"- Beneish M-score: **{m.get('value')}** ({'FLAG' if m.get('flag') else 'ok'}) — {m.get('note')}")
    L.append(f"- Sloan accruals: **{s.get('value')}** ({'FLAG' if s.get('flag') else 'ok'})")
    L.append(f"- Piotroski F-score: **{f.get('value')}/9**")
    ce = fg["cash_vs_earnings"]
    L.append(f"- FCF conversion: **{ce.get('fcf_conversion')}** · NI>OCF in {ce.get('years_ni_above_ocf')}/{ce.get('years_checked')} yrs")
    L.append("")

    # Step 2 — solvency
    sg = r["solvency"]
    z = sg["altman_z"]; lev = sg["leverage"]
    L.append(f"## STEP 2 — Solvency gate: **{sg['verdict']}**")
    if sg.get("note"):
        L.append(f"- ⓘ {sg['note']}")
    L.append(f"- Altman Z: **{z.get('value')}** ({z.get('zone')})")
    L.append(f"- Net debt/EBITDA: **{_v(lev.get('net_debt_ebitda'),'x')}** · "
             f"interest coverage **{_v(lev.get('interest_coverage'),'x')}** · current ratio **{_v(lev.get('current_ratio'))}**")
    L.append("")

    # bank branch — replaces profitability/valuation for financials
    if "bank_analysis" in r:
        b = r["bank_analysis"]; m = b["metrics"]
        L.append(f"## Bank / financial model  ({b['subtype']})")
        L.append(f"- **ROA** {m['roa_pct']} ({b['roa_trend']}) — target >1% · "
                 f"**ROE** {m['roe_pct']} ({b['roe_trend']}) — target >10-12%")
        L.append(f"- **Efficiency ratio** {_v(m['efficiency_ratio_pct'],'%')} — {b['efficiency_assessment']} (lower = better)")
        L.append(f"- **NIM proxy** (NII/assets) {m['nim_proxy_pct']}")
        L.append(f"- **P/TBV** {_v(m['price_to_tangible_book'])} · P/B {_v(m['price_to_book'])} · P/E {_v(m['pe_trailing'])} · div yield {_v(m['dividend_yield_pct'],'%')}")
        L.append(f"- Tangible book/share {_v(m['tangible_bv_per_share'])} · 3y BVPS CAGR {_v(m['tbv_per_share_cagr_3y_pct'],'%')}")
        for note in m.get("notes", []):
            L.append(f"  - ⓘ {note}")
        L.append("")
        L.append(_common_sections(r))
        L.append("\n*Bank model + growth/capital-allocation/ownership. "
                 "Insurance/asset-manager use bank approximation (see TODO).*")
        return "\n".join(L)

    # profitability
    p = r["profitability"]
    roic = p["roic"]; dp = p["dupont"]; mg = p["margins"]; cfq = p["cash_flow_quality"]
    L.append("## Profitability & returns on capital")
    L.append(f"- **ROIC {roic.get('roic_pct')}%** vs WACC ~{roic.get('wacc_proxy_pct')}% "
             f"→ spread **{roic.get('spread_pct')}pp** ({roic.get('trend')}) — "
             f"{'✅ creates value' if roic.get('creates_value') else '❌ destroys value' if roic.get('creates_value') is False else 'n/a'}")
    L.append(f"  - ROIC series (recent→old): {roic.get('roic_series')}")
    L.append(f"- **ROE {dp.get('roe_pct')}%** = margin {dp.get('net_margin_pct')}% × turnover {dp.get('asset_turnover')} × leverage {dp.get('equity_multiplier')}x"
             + ("  ⚠️ leverage-driven" if dp.get("leverage_driven_flag") else ""))
    L.append(f"- Gross margin {mg.get('gross_margin_pct')} ({mg.get('gross_trend')}) · "
             f"operating margin {mg.get('operating_margin_pct')} ({mg.get('operating_trend')})")
    L.append(f"- FCF conversion {cfq.get('fcf_conversion')} · FCF margin {cfq.get('fcf_margin_pct')} · "
             f"SBC {cfq.get('sbc_pct_of_ocf')}% of OCF")
    L.append(f"- Gross profitability (GP/assets): **{p['gross_profitability'].get('value')}**")
    L.append("")

    # moat / quality
    mo = r.get("moat")
    if mo:
        L.append("## Moat / quality (data-derived)")
        for s in mo.get("moat_signals", []):
            L.append(f"- ✅ {s}")
        for s in mo.get("weak_signals", []):
            L.append(f"- ⚠️ {s}")
        L.append(f"- Gross margin avg {_v(mo.get('gross_margin_avg_pct'),'%')} (±{mo.get('gross_margin_stability')}, {mo.get('gross_margin_trend')}) · "
                 f"revenue volatility ±{_v(mo.get('revenue_volatility_pct'),'%')}")
        L.append(f"- ⓘ needs manual review: {', '.join(mo.get('manual_review_needed', []))}")
        L.append("")

    # valuation
    v = r.get("valuation", {})
    mult = v.get("multiples", {}); rd = v.get("reverse_dcf", {}); fd = v.get("forward_dcf", {})
    L.append("## Valuation")
    L.append(f"- P/E {_v(mult.get('pe_trailing'))} (fwd {_v(mult.get('pe_forward'))}) · "
             f"EV/EBITDA {_v(mult.get('ev_ebitda'))} · EV/FCF {_v(mult.get('ev_fcf'))} · P/B {_v(mult.get('price_to_book'))}")
    L.append(f"- FCF yield **{_v(mult.get('fcf_yield_pct'),'%')}** · earnings yield {_v(mult.get('earnings_yield_pct'),'%')} · div yield {_v(mult.get('dividend_yield_pct'),'%')}")
    L.append(f"- **Reverse-DCF:** price implies **{_v(rd.get('implied_growth_pct'),'%/yr')}** FCF growth "
             f"(10y) vs **{_v(rd.get('historical_rev_cagr_3y_pct'),'%')}** historical rev CAGR"
             + (f" — {'✅ reasonable' if rd.get('looks_reasonable') else '⚠️ optimistic' if rd.get('looks_reasonable') is False else ''}"))
    if rd.get("note"):
        L.append(f"  - {rd['note']}")
    if fd.get("scenarios"):
        s = fd["scenarios"]
        L.append(f"- **DCF scenarios** (intrinsic/share vs price {_v(fd.get('current_price'))}): "
                 f"bear {_v(s['bear']['intrinsic_per_share'])} ({_v(s['bear']['upside_pct'],'%')}) · "
                 f"base {_v(s['base']['intrinsic_per_share'])} ({_v(s['base']['upside_pct'],'%')}) · "
                 f"bull {_v(s['bull']['intrinsic_per_share'])} ({_v(s['bull']['upside_pct'],'%')})")
    L.append("")
    L.append(_common_sections(r))
    L.append("\n*Full core: STEP 0 classification · forensic/solvency gates · profitability · "
             "moat · valuation · growth · capital allocation · ownership. "
             "Remaining (see TODO): insurance/REIT models, peer-relative context, macro overlay.*")
    return "\n".join(L)
