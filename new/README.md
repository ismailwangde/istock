# Equity Analyzer

An AI-usable engine that runs the due-diligence checklist in
[ANALYSIS_FRAMEWORK.md](ANALYSIS_FRAMEWORK.md) on any US-listed company, using
free data (yfinance). Produces a machine-readable JSON + a human-readable report.

## Usage

```bash
python build_peers.py              # ONE-TIME (~12 min, cached): S&P 500 peer panel
python run.py AAPL MSFT JPM        # prints reports, writes reports/TICKER.{json,md}
```

Peer-relative percentiles need the peer panel built once; everything else works
without it.

```python
from analyzer import analyze
r = analyze("AAPL")                # -> dict; also writes reports/AAPL.{json,md}
print(r["verdict"], r["quality_score"], r["all_flags"])
```

## What it does

Runs, in order (framework steps):

0. **Classify** the company (standard / hyper-growth / cyclical / utility /
   financial / REIT) → picks the right model & thresholds.
1. **Forensic gate** — Beneish M, Sloan accruals, Piotroski F, cash-vs-earnings.
   A failure here halts the thesis (un-analyzable accounting).
2. **Solvency gate** — Altman Z, leverage (N/A for financials).
3. **Profitability** — ROIC−WACC spread, DuPont ROE, margins, FCF quality.
4. **Moat/quality** — pricing power (margin stability), durability (ROIC/rev vol).
5. **Valuation** — multiples + reverse-DCF reality check + DCF scenarios.
6. **Growth** — CAGRs, source of EPS growth, Rule of 40, quality traps.
7. **Capital allocation** — buyback quality, dividend sustainability, dilution.
8. **Ownership/insiders** — cluster insider buys, institutional %, short interest.
9. **Earnings & analyst** — estimate revisions (scored), targets/ratings (context).
10. **Peer-relative** — sector-percentile ranking vs S&P 500 peers.
11. **Market context** — VIX, rates, yield curve (regime; non-scoring).
12. **News** — recent headlines + sentiment tag (display-only, unscored).

Banks branch to a dedicated model (ROA/ROE/NIM/efficiency/P-TBV).

Output: an overall **verdict**, a 0–100 **quality_score**, and a consolidated
**red-flag list** — plus every underlying metric in the JSON.

## Design principles (from the framework)

- **Classify first, then apply the right model** — no cherry-picking thresholds.
- **Trend over snapshot** — 5-yr series where available.
- **Cross-metric traps** — leverage-driven ROE, buyback-driven EPS, growth
  without FCF are flagged, not hidden.
- **Robust vs decorative** — ⭐ signals (ROIC, accruals, insider clusters,
  momentum) are weighted; ☠️ weak ones (single technicals, headline sentiment)
  are context-only.
- **Honest about limits** — missing/inapplicable data says so (see TODO.md).

## Forward-logging (validate the score over time)

Instead of a (survivorship-biased, lookahead-prone) backtest, we log scores
forward and measure them later — clean by construction.

```bash
python snapshot.py prices     # daily  — batch close prices  -> logs/prices.csv
python snapshot.py scores     # weekly — full analyze scores -> logs/scores.csv
python performance.py 21      # once enough time passes: does score predict 21d return?
```

- **Watchlist**: edit `watchlist.txt` (add/remove tickers anytime; new ones start
  logging from that day). The S&P 500 is tracked too (toggle `TRACK_SP500` in
  `snapshot.py`).
- **Schedule it** (macOS): `bash schedule/install.sh` → prices daily 09:00,
  scores weekly Sat 09:30. Uninstall: `bash schedule/uninstall.sh`.
- Needs **months** of accumulation to be meaningful; expected edge is modest.

## Status
Full per-company core + peer-relative + forward-logging built.
Remaining: insurance/asset-manager/REIT models. See [TODO.md](TODO.md).
