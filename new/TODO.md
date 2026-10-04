# Analyzer Build — Roadmap & Status

Implements [ANALYSIS_FRAMEWORK.md](ANALYSIS_FRAMEWORK.md). Free data (yfinance +
FRED-free indices). Output: `reports/TICKER.json` + `reports/TICKER.md`.
Run: `python run.py AAPL MSFT ...` or `from analyzer import analyze`.

## ✅ Done — the full per-company core
- **STEP 0 — Classification** (`classify.py`): standard / hypergrowth / cyclical /
  utility / financial(+subtype) / reit. Sets WACC, solvency applicability,
  Beneish reliability. Structurally fixes NVDA & Ford.
- **STEP 1 — Forensic gate** (`forensic.py`): Beneish M, Sloan accruals,
  Piotroski F, cash-vs-earnings, DSO/inventory. Bank-inappropriate checks suppressed.
- **STEP 2 — Solvency gate** (`solvency.py`): Altman Z, leverage; N/A for financials.
- **Profitability** (`profitability.py`): ROIC−WACC spread, DuPont ROE, margins,
  gross profitability, FCF quality.
- **Moat/quality** (`moat.py`): sustained ROIC, gross-margin stability (pricing
  power), revenue volatility (durability); qualitative parts flagged for manual.
- **Valuation** (`valuation.py`): multiples + reverse-DCF reality check + DCF scenarios.
- **Growth** (`growth.py`): CAGRs, acceleration, source of EPS growth, Rule of 40,
  growth-without-FCF / buyback-driven-EPS traps.
- **Capital allocation** (`capital_allocation.py`): buyback quality vs SBC,
  dividend sustainability (of FCF), dilution.
- **Ownership/insiders** (`ownership.py`): insider cluster-buy (⭐), net activity,
  institutional %, short interest.
- **Bank model** (`banks.py`): ROA, ROE, NIM proxy, efficiency ratio, P/TBV, BVPS growth.
- **Macro/market context** (`macro.py`): VIX, 10y, yield curve, DXY, oil (non-scoring regime).
- **Earnings & analyst signals** (`analyst.py`): estimate revisions (⭐ scored),
  surprise history, price targets & ratings (context).
- **News context** (`news.py`): recent headlines + sentiment tag, DISPLAY-ONLY
  (unscored — proven non-predictive).
- **Peer-relative context** (`peers.py` + `build_peers.py`): S&P 500 metric panel,
  sector percentile ranking. One-time build: `python build_peers.py`.
- **Composite scoring + verdict** with per-category adjustments.
- **Forward-logging + validation** (`snapshot.py`, `performance.py`): daily price
  + weekly score logs (survivorship-free, no lookahead); `performance.py` measures
  score→forward-return IC/quintile spread. Editable `watchlist.txt`.
- **Scheduler LIVE** (`schedule/`): launchd jobs installed — prices daily 11:00 IST,
  scores weekly Sat 11:30 IST. (`install.sh` / `uninstall.sh`)

## ☐ Remaining (priority order)
- [ ] **Broader ~1000+ peer universe** — S&P 500 works now; add mid-caps for
      finer industry-level peer groups (S&P 500 is the current backup/default).
- [ ] **Insurance model** — combined ratio, float, book-value growth (currently
      approximated as a bank).
- [ ] **Asset-manager model** — AUM, fee margin, net flows (approximated as bank).
- [ ] **REIT model** — FFO/AFFO, P/FFO, NAV (classify tags it; no dedicated model yet).
- [ ] **Tier-1/CET1, loan-deposit, NPLs** for banks — need EDGAR 10-K tables / FFIEC.
- [ ] **Historical multiples** (P/E now vs own 5y avg) — needs aligned price×earnings.
- [ ] **Growth×reinvestment intrinsic-growth** (reinvestment rate × ROIC).
- [ ] **JSON schema freeze** — stable contract doc for the platform.

## Known limitations (honest)
- WACC is a crude sector/type proxy, not a computed CAPM cost of capital.
- No point-in-time data — latest filings only (fine for current analysis, not backtest).
- Reverse/forward DCF need positive FCF — n/a for unprofitable names.
- Non-bank financials (GS, insurers) use the bank-model approximation.
- Absolute thresholds without peer context can misjudge unusual-but-fine cases.
