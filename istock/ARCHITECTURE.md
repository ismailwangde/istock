# istock — Architecture & README

A single-stock technical-analysis and trade-recommendation system for US equities,
served through a Streamlit web app. You give it a ticker (e.g. `AAPL`); it fetches
price data, runs a battery of technical checks, scores the stock 0–100 with a trained
machine-learning model ("Brain v2"), turns that score into a verdict
(STRONG BUY → AVOID), sizes a position if it's a BUY, and tracks the pick over time.

> This document describes the **`istock/`** package — the clean, current codebase.
> The older `ismail_p/` folder is the legacy original, kept only for reference and data.
> Where the old `docs/SYSTEM_LOGIC.md` describes "v1" (a hand-weighted 8-section
> scorer), that logic now lives **only as a fallback**. The real engine is Brain v2.

---

## 1. The big idea in one paragraph

The system reads the last year of daily candles for a stock and computes ~25 technical
indicators (moving averages, RSI, MACD, ATR, ADX, Bollinger Bands, volume, etc.).
A set of **14 analyzers** each look at those indicators and answer one yes/no question
at a time (e.g. "Is price above MA200?", "Is there a bullish MACD crossover?",
"Is volume above average?"). Their answers, plus 11 extra computed signals, become a
**36-number on/off feature vector**. A trained logistic-regression model (Brain v2)
turns that vector into a single **0–100 score**, which maps to a **verdict**. If the
verdict is a BUY, a position sizer works out how many shares to buy — always choosing
the safest (smallest) size. A separate market **regime detector** reads broad-market
signals to decide whether it's a good time to be buying at all.

---

## 2. Folder layout

```
istock/
├── data/
│   ├── engine.py        DataEngine — fetches OHLC + computes all indicators
│   └── fetcher.py       DataFetcher — standalone yfinance helper (universe/scanner)
├── features/
│   ├── spec.py          The 36-feature roster (LOCKED order) + extract_features()
│   ├── live_features.py The 11 "E+F" extra features (SMC, VWAP, ATR regime, etc.)
│   │                    + VIX loader + per-(ticker,date) score cache
│   └── analyzers/       14 analyzers, one concern each (see §4)
├── model/
│   ├── scorer.py        score() = sigmoid(weights · features) × 100; verdict mapping
│   ├── weights.py       WeightSet + loads the trained pooled model from disk
│   └── exits.py         exit-rule logic (stop-with-floor; partial stub)
├── decision/
│   ├── advisor.py       TradeAdvisor.analyze(symbol) — THE orchestrator
│   ├── types.py         FullAnalysis, TradeConfig, TradeSetup, CheckItem dataclasses
│   ├── position_sizer.py  4 sizing methods, smallest wins
│   └── regime.py        RegimeDetector — 5 macro signals → regime label + multiplier
├── execution/
│   ├── alert_manager.py     alerting
│   ├── live_monitor.py      live price monitoring loop
│   └── position_tracker.py  in-session P&L / trailing-stop tracking
├── training/
│   ├── trainer.py       OFFLINE Brain v2 training (walk-forward folds)
│   └── diagnostics.py   profit-factor, bootstrap CIs, VIX stratification
└── ui/
    ├── app.py               Streamlit app (Home, Stock Deep Dive, Picks)
    └── terminal_display.py  terminal/CLI output formatting
```

### Important paths (all resolve to `ismail_personal/`, NOT `istock/`)

`weights.py` and `live_features.py` walk three parents up from their file, so every
result path lands in the project root:

| Path | What it holds |
|---|---|
| `results/brain_v2_weights/_pooled.json` | the trained pooled model weights |
| `results/cache/ohlc_^VIX.parquet` | VIX daily closes (for the guardrail) |
| `results/cache/ohlc_<TICKER>.parquet` | cached OHLC (sector ETFs, etc.) |
| `results/cache/brain_v2_scores/<TICKER>_<DATE>.json` | per-(ticker,date) score cache |
| `results/recommendation_log.json` | tracked picks (open + closed) |

Run the app with:

```bash
/Users/ismailwangde/fundly/.venv/bin/streamlit run ismail_personal/istock/ui/app.py
```

---

## 3. The full pipeline — `TradeAdvisor.analyze()`

The orchestrator is [`decision/advisor.py`](decision/advisor.py) (`TradeAdvisor.analyze`).
For one symbol it does, in order:

1. **Show the regime banner** once per session ([`RegimeDetector`](decision/regime.py)).
2. **Fetch data.** Build a `DataEngine` and call `fetch_all()` — pulls 1y daily, 2y
   weekly, 6mo of the market index (`^GSPC` for US, `^NSEI` for India), plus
   `Ticker.info` for fundamentals. Then `_add_indicators` decorates the daily and
   weekly frames with ~25 indicator columns. ([`data/engine.py`](data/engine.py))
3. **Compute support / resistance.** `SupportResistanceEngine` finds levels from swing
   highs/lows, pivots, Fibonacci, volume clusters, MAs and round numbers, then clusters
   nearby ones into stronger composites.
4. **Run the 8 scoring analyzers** — trend, location, setup, volume, momentum,
   candlesticks, market context, risk/reward. Each returns a `SectionResult` with a
   0–100 score and a list of `CheckItem`s (each check has a name + `passed` boolean).
5. **Run `AvoidChecker`** — collects red-flag strings.
6. **Run `SellSignalChecker`** — computes a separate 0–100 `sell_score`.
7. **Brain v2 scoring** (`_run_v2_scoring`, see §5):
   - check the per-(ticker,date) cache; if hit, reuse it
   - load the pooled weights
   - `compute_live_features` → the 11 extra signals
   - `analysis_to_trade_dict` + `extract_features` → 36-dim binary vector
   - `score()` → 0–100 → `verdict_from_score()` → VIX guardrail
   - write the result to cache
8. **Assemble a `FullAnalysis`** (the full result object). If v2 weights aren't on disk,
   fall back to a hand-weighted average of the 8 section scores (see §6).
9. **Position sizing** — only if the verdict contains "BUY" and a real setup was
   detected ([`decision/position_sizer.py`](decision/position_sizer.py)).

```
ticker
  │
  ▼
DataEngine.fetch_all ──► ~25 indicator columns on daily/weekly frames
  │
  ▼
SupportResistanceEngine ──► support / resistance / fib levels
  │
  ▼
8 scoring analyzers + AvoidChecker + SellSignalChecker
  │            │
  │            └──► sell_score (0-100), avoid_flags
  ▼
compute_live_features (11 E+F signals)
  │
  ▼
extract_features ──► 36-dim binary vector
  │
  ▼
score() = sigmoid(intercept + Σ wᵢ·xᵢ) × 100   ──► 0-100
  │
  ▼
verdict_from_score()  ──►  STRONG BUY / BUY / LEAN BUY / HOLD / LEAN SELL / SELL / AVOID
  │
  ▼
VIX guardrail (downgrade one tier if VIX > 22)
  │
  ▼
position sizer (only if verdict contains "BUY")
```

---

## 4. The analyzers

There are 14 analyzer modules in [`features/analyzers/`](features/analyzers/).
**Eight** of them produce the section scores that feed the model; the rest are support
or auxiliary. Each scoring analyzer builds a list of `CheckItem`s and scores itself with
the same formula:

```
section_score = (sum of weights of the checks that PASSED)
              / (sum of weights of ALL checks) × 100
```

| Analyzer | Question it answers |
|---|---|
| `trend.py` | Is the bigger picture going up (price vs MAs, MA stacking, ADX, weekly trend)? |
| `location.py` | Are we buying at a good *price* — near support, away from resistance? |
| `setup_detector.py` | Is there a recognizable setup *right now*: pullback / breakout / bounce / reversal? |
| `volume.py` | Is real money flowing in (volume vs average, OBV, Bollinger squeeze)? |
| `momentum.py` | Are RSI / MACD / Stochastic / ROC bullish? |
| `candlesticks.py` | Do recent candles show bullish patterns (and no bearish ones)? |
| `risk_reward.py` | If we entered here with the computed stop/target, is the R:R acceptable? |
| `market_context.py` | Is the broad index up, and is the stock outperforming it? |
| `support_resistance.py` | (support) finds & clusters S/R and Fibonacci levels |
| `avoid_checker.py` | (support) emits red-flag strings (spike, parabolic, downtrend…) |
| `sell_signals.py` | (support) graded 0–100 bearish-evidence score |
| `technical.py` | (auxiliary) extra technical helpers |
| `fundamental.py` | (auxiliary) fundamental checks |

**Setup detector** is special: it runs four pattern checks in parallel and keeps the
strongest. Each setup has a default win-rate used later by Kelly sizing:
pullback 0.55, breakout 0.40, bounce 0.60, reversal 0.45; `none` blocks the trade.

**Risk/Reward** also computes the actual trade levels: entry = today's close; stop =
the tightest sensible candidate (support-based, ATR-based, swing-based, or MA-based);
three targets; and `R:R = (target₁ − entry) / (entry − stop)`.

---

## 5. Brain v2 — the scoring model

### 5.1 The 36 features

[`features/spec.py`](features/spec.py) is the **single source of truth**. The column
order is **locked** — changing it invalidates every saved weight file. The 36 features
are grouped:

- **A (14)** — validated brain checks read from the analyzers' `passed_checks`
  (candlestick patterns, MACD signals, volume spike, OBV, MA20 slope, etc.)
- **B (2)** — Stochastic and ADX checks
- **C (1)** — breakout setup detected
- **D (8)** — in-house checks (RSI divergence, the four setups, higher-highs+lows,
  near support, strong support)
- **E (4)** — Smart-Money-Concepts: order block, fair-value-gap, BOS, CHoCH
- **F (7 columns)** — VWAP above / band-stretched, ATR-regime low / high,
  sector relative strength, earnings-within-5-days, fib-retracement-near

`extract_features(trade)` reads each feature as a 0/1 and returns a length-36 NumPy
array. Most come from `passed_checks`; the E+F columns are flat top-level keys produced
live by `compute_live_features` ([`features/live_features.py`](features/live_features.py)).

### 5.2 The score

[`model/scorer.py`](model/scorer.py):

```
score = sigmoid(intercept + Σ wᵢ × featureᵢ) × 100        # a 0-100 number
```

The weights come from a trained **pooled** logistic-regression model loaded from
`results/brain_v2_weights/_pooled.json`. (Per-ticker models were tried but are
**disabled** in the current revision — `find_weight_for_ticker` always returns the
pooled set; see [`model/weights.py`](model/weights.py).)

### 5.3 Verdict thresholds (locked, in `scorer.py`)

| Score | Verdict |
|---|---|
| ≥ 80 | STRONG BUY |
| ≥ 65 | BUY |
| ≥ 55 | LEAN BUY |
| ≥ 45 | HOLD |
| ≥ 35 | LEAN SELL |
| ≥ 20 | SELL |
| < 20 | AVOID |

### 5.4 VIX guardrail

When the daily VIX close is **above 22.0**, any actionable verdict is **downgraded one
tier** (STRONG BUY→BUY, BUY→LEAN BUY, LEAN BUY→HOLD). It needs
`results/cache/ohlc_^VIX.parquet`; if that file is missing, the guardrail is skipped and
the result is flagged `v2_skipped_reason = "vix_unavailable"` rather than silently
assuming a value (failures must stay visible).

### 5.5 The score cache

Every computed score is written to
`results/cache/brain_v2_scores/<TICKER>_<YYYY-MM-DD>.json`. On the next request for the
same ticker and date, the advisor reuses it instead of recomputing.

---

## 6. The fallback path

If no trained weights are on disk, `_run_v2_scoring` returns `None` and the advisor
falls back to a hand-weighted average of the 8 section scores
(`trend 18, location 20, setup 15, volume 10, momentum 15, candles 7, risk_reward 10,
market_context 5`), then maps it crudely: ≥70 BUY, ≥58 LEAN BUY, ≤35 AVOID, else HOLD.
This keeps the scanner producing output before a model is trained. **It is a safety net,
not the main engine.**

> Known, by-design consequence: the Opportunities scanner can legitimately show "no
> opportunities" when Brain v2 rates nothing ≥55. That's correct behaviour, not a bug.

---

## 7. Position sizing

[`decision/position_sizer.py`](decision/position_sizer.py) runs only after a BUY-shaped
verdict **and** a real setup (`setup_type != "none"`). It computes four sizes and takes
the **smallest** (safety-first):

1. **Fixed-fractional risk** — risk ~1% of the portfolio per trade, scaled by conviction
   and the regime multiplier.
2. **Volatility parity (ATR)** — higher volatility ⇒ smaller size.
3. **Fractional Kelly** — 25% Kelly from the setup's win-rate and the R:R.
4. **Max position cap** — a hard ceiling as a % of portfolio.

It first rejects outright if the stop is invalid, risk is too tight/too wide, the score
is too low, R:R < 1.5, or no setup. Defaults assume an INR portfolio
(₹500,000 portfolio / ₹100,000 cash in the advisor's call) with USD↔INR conversion.

---

## 8. Regime detection

[`decision/regime.py`](decision/regime.py) ignores the individual stock and reads five
broad-market signals, each scored and weighted:

| Signal | Source | Weight |
|---|---|---|
| Volatility | `^VIX` | 25% |
| Trend | SPY vs MA200 | 25% |
| Slope | SPY 20-DMA slope | 15% |
| Breadth | RSP vs SPY (equal-weight vs cap-weight) | 20% |
| Yield curve | `^TNX` − `^IRX` | 15% |

It outputs one of five regime labels — `RISK_ON_TREND`, `RISK_ON_CHOP`, `TRANSITION`,
`RISK_OFF`, `RECOVERY` — plus a **position-size multiplier** (~0.4 → 1.2) used by the
position sizer. It is fail-soft: missing signals lower confidence but never crash.

---

## 9. Training (offline only)

[`training/trainer.py`](training/trainer.py) is **offline-only** — never imported at
request time. It fits the logistic-regression weights with a walk-forward scheme
(train on the first 18 months, pick the regularization `C` on the next 6 months of
validation, then test once on the final 12 months). A trade counts as a **net win** only
if `pnl% − 0.20% > 0` (the 0.20% is a round-trip cost model). `training/diagnostics.py`
reports profit factor, bootstrap confidence intervals and VIX-stratified results.

---

## 10. Data flow notes & gotchas

- **Single fetch chokepoint.** Every analyzer reads pre-computed columns off
  `DataEngine.daily`; no analyzer fetches its own data. That's why a backtester can
  monkey-patch yfinance once and redirect everyone.
- **Point-in-time replay.** Pass `as_of_date` to `analyze()` and `DataEngine` slices its
  frames to that date so indicators recompute on truncated history. **Caveat:**
  `Ticker.info` (sector, market cap, analyst targets) is **always today's snapshot** —
  yfinance does not expose historical fundamentals. Only price-derived indicators are
  truly point-in-time.
- **Process-level caches persist.** VIX and ETF frames are cached for the life of the
  Streamlit process; a parquet added mid-run needs a server restart to be seen.
- **Two `DataEngine`-like fetchers exist.** `data/engine.py` (`DataEngine`) is the main
  one used by the advisor; `data/fetcher.py` (`DataFetcher`) is a standalone helper that
  suppresses ETF 404 noise, used by universe/scanner code.

---

## 11. Housekeeping / known state

- A stray duplicate tree at `istock/results/brain_v2_weights/` is **not** used —
  `weights.py` resolves to `ismail_personal/results/`. Safe to delete.
- `model/exits.py` is partly a stub (the documented exit rule isn't fully implemented).
- Per-ticker weights are disabled; only the pooled model is active.
- `tests/` import paths may still reference the old package and need updating to `istock`.
</content>
</invoke>
