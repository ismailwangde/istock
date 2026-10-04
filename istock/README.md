# istock

**Transparency-first equity research — the anti–black-box.**

There's a wave of "AI picks your stocks" products right now: you type a ticker, it
says *BUY*, and you're asked to trust a number you can't inspect. istock is the
opposite bet. It shows you **the entire reasoning** — every metric, honest
confidence labels, and the costs — and lets *you* decide whether to believe it.

> The goal isn't a magic verdict. It's an analyst that shows its work.

**It never issues a BUY/SELL.** Short-horizon direction is unpredictable (we tested
this exhaustively — see [CONCLUSIONS.md](CONCLUSIONS.md)), so the tool shows a 0–100
score and a non-directional **quality band** (Excellent → Poor), the fundamentals,
the risk, and the one thing that actually survived testing (an *Evidence-Based
investing* page) — then lets you decide.

Run the app: `…/.venv/bin/streamlit run istock/ui/app.py`

---

## Why this exists

Most retail "AI investing" tools optimize for a confident answer. That's exactly
the wrong thing to trust: a backtest that looks great is usually hiding
survivorship bias, look-ahead, or costs that quietly erase the edge. istock is
built on the opposite principle — **be honest about what's real, and show it** —
even when the honest answer is "this doesn't work."

---

## What's inside

**1. Fundamental analysis engine (12 modules)** — the trustworthy core (`new/`)
Give it a ticker; it runs a full due-diligence checklist and returns a 0–100
quality score and *every underlying number* — never a buy/sell call.
- Accounting forensics (Beneish M, Sloan accruals, Piotroski F)
- Returns on capital (ROIC − WACC spread, DuPont ROE)
- Valuation (reverse-DCF reality check + DCF scenarios)
- Sector-percentile peer ranking, moat/quality, growth, capital allocation
- A dedicated model for banks (different economics need a different model)
- **Honest confidence labels** on every signal — robust (⭐) vs. near-worthless (☠️)

**2. Strategy-research harness (QuantConnect / LEAN)**
Replicates *published* trading strategies and stress-tests them honestly on
survivorship-bias-free minute data — then **rejects the ones that don't survive**:
- Transaction costs, short-borrow fees, and regime dependence, all modeled
- Separates **gross signal from net-of-cost reality** (where most edges die)
- Per-year breakdowns so a single lucky year can't masquerade as an edge

**3. Forward-logging validation**
Instead of a survivorship-biased backtest, scores are logged *forward* and
measured later — clean by construction (no look-ahead, no delisting scrub).

---

## Design principles

- **Classify first, then apply the right model** — no cherry-picked thresholds.
- **Trend over snapshot** — multi-year series, not a single reading.
- **Robust vs. decorative** — strong signals are weighted; weak ones are shown as
  context only, never dressed up as alpha.
- **Costs are always on** — net-of-cost is the only number that counts.
- **Honest about limits** — missing or inapplicable data says so, out loud.

---

## Honest findings so far

Because the point is honesty, the rejections are part of the record:

- **Opening-Range Breakout + relative volume** — looked promising on a short
  sample; on 10 years it was **gross-negative in every year**. Rejected.
- **Intraday momentum** — statistically underpowered on available free data;
  pending a longer test.
- **ConnorsRSI mean-reversion** — the most promising candidate; currently in
  full cost- and regime-stress testing before any claim is made.

---

## Roadmap

Research project, in active development. Next: **ML meta-labeling** — a model that
doesn't imitate the rules, but decides *when to trust each rule* (run a strategy
only in the regimes where it historically works).

---

## Disclaimer

Personal research project, for educational purposes. **Not** financial advice.
Do your own research before making any investment decision.
