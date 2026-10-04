# Conclusions — what this project actually found

> The honest end-state of istock. Written to be read start-to-finish in two minutes.

## The one-line finding

**Short-horizon stock direction is not predictable, and almost nothing reliably beats
a low-cost index fund after costs.** Every strategy here was given a fair,
survivorship-free, cost-aware test. The ones that looked good in a first pass were
killed by the honest version of the test. That result — proven, not assumed — *is* the
product: a tool that shows you the analysis transparently instead of selling a
market-beating signal that doesn't exist.

## Tested and rejected (each got a fair harness)

| Idea | Verdict |
|---|---|
| Single-name up/down prediction (36 features, logistic/LightGBM) | No skill — OOS AUC ≈ 0.51; every feature's information value < 0.005 |
| News / sentiment as a signal | Dead — priced in within seconds; any "edge" is momentum in disguise |
| Chart patterns / technical triggers (golden cross, RSI, MACD…) | Best event < transaction costs; bearish signals don't even work |
| Opening-Range Breakout + relative volume (QC, 10-yr) | Gross-negative every year 2021–2023, before fees |
| ConnorsRSI mean-reversion short (high-vol) | **Margin-called** in the Jan-2021 meme squeeze — disqualified |
| Dual-Momentum / GEM (2008–2024) | +30% vs SPY's +371% — whipsawed at every sharp reversal |
| LSTM / sequence models | Memorize noise at this signal-to-noise ratio; declined by design |
| Momentum sleeve as "alpha" | It's the UMD **factor** (buy MTUM), not skill; ≈ negative after tax |

## What survived: a multi-factor tilt (not a stock-picker)

An equal, untuned blend of **Momentum + Value + Quality** was the only automatable
approach to genuinely beat a risk-matched levered S&P 500 through-cycle (1999–2026):
**+3.0 pp/yr, Sharpe 0.61 vs 0.51, beat the market 18/28 years.**

**Buyable, tax-efficient form (the actual recommendation):** ≈ ⅓ MTUM + ⅓ VLUE + ⅓ QUAL,
or a single multi-factor ETF (LRGF), rebalanced ~quarterly. Honest edge is modest
(~2–5 pp/yr) and comes with real drawdowns. For most people, index + a high savings
rate does most of the work.

## What istock is now

A **transparency-first decision-support tool** — the anti-"AI stock-picker":

- It shows a **0–100 quality score** and a non-directional **quality band**
  (Excellent → Poor), plus fundamentals, technicals, peer context, and risk.
- It **never issues a BUY/SELL** call. Short-horizon direction is unpredictable, so
  the tool informs and the human decides.
- The **Evidence-Based** page states the honest conclusion and the multi-factor answer.
- A background logger records scores forward (survivorship-free) so the score's
  predictive value keeps being measured honestly over time.

## Engines (reconciled)

Two scoring engines exist and now play distinct, honest roles:
- **Fundamental analyzer (`new/`)** — the defensible core: forensics, ROIC−WACC,
  valuation, peer percentiles. Real financial analysis.
- **Brain v2 (`istock/`, technical)** — a technical-setup score shown as context only.
  It has no proven directional edge (AUC 0.51), so it is presented as a quality band,
  never as a recommendation.

*Not financial advice. Educational project.*
