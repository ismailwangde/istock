# istock — Model & System Deep Dive

> **Purpose.** A complete, self-contained explanation of how the istock trading
> system works end to end — data → features → labels → training → scoring →
> verdict → downstream layers — written to be read by a human *or* another AI
> (e.g. for review). Every non-obvious claim is tied to a `file:line`. The last
> sections are deliberately honest about what is **unfinished, dead, or
> suspect**, plus a retrain-TODO list.
>
> Scope note: this covers the whole system, not just the ML model. UI/visual
> rendering is intentionally out of scope except where it consumes model output.

---

## 0. TL;DR

You give it a ticker. It fetches ~1y of daily candles, runs analyzers that each
answer yes/no questions, packs those answers into a **locked 36-bit feature
vector**, and a trained **L2 logistic-regression model ("Brain v2")** turns that
vector into a **0–100 score**. The score is bucketed into a verdict
(STRONG BUY … AVOID), downgraded one tier if VIX > 22. Position sizing exists but
is **gated off**. The model was trained offline on ~23k simulated historical
trades labeled win/lose net of a 0.60% round-trip cost.

**One-line mental model:** `sigmoid(intercept + weights · 36_features) × 100 → verdict`.

---

## 1. The two lives of "the model"

The same feature code serves two processes:

```
TRAINING (offline, once → produces weights on disk)
  1. Build dataset      backtester walks history monthly, records trades
  2. Label trades       simulate each trade forward → win/lose (net of costs)
  3. Assemble X, y      extract_features + extract_target over all trades
  4. Fit                L2 logistic regression; walk-forward C selection
  5. Validate & save    PF gates, pooled vs per-ticker, write JSON weights

INFERENCE (live, every analysis)
  6. Extract features   same extract_features → 36 bits for the stock now
  7. Score              sigmoid(intercept + weights · features) × 100
  8. Verdict            bucket by thresholds; VIX>22 downgrades one tier
```

Steps 3 and 6 call the **same** `extract_features` — this is the golden rule:
train-time and predict-time features must be computed identically.

Orchestrated by `TradeAdvisor.analyze()` in
[decision/advisor.py](decision/advisor.py).

---

## 2. Folder layout (non-UI)

```
istock/
├── data/         fetcher, engine (DataEngine), ohlc_cache (parquet cache)
├── features/     spec.py (36-feature contract), live_features.py, analyzers/ (14)
├── model/        scorer.py, weights.py, exits.py (STUB)
├── decision/     advisor.py (orchestrator), position_sizer.py (gated off),
│                 regime.py, types.py (TradeConfig, dataclasses)
├── execution/    alert_manager, live_monitor, position_tracker (live-ops)
├── training/     trainer.py, diagnostics.py (offline only)
└── ui/           Streamlit app (out of scope here)
```

### Important paths (all resolve to `ismail_personal/`, NOT `istock/`)
`_ROOT` = `ismail_personal/` (three parents up from a file in `istock/<pkg>/`).
- `results/brain_v2_weights/_pooled.json` — the trained model (intercept + 36 coefficients)
- `results/cache/ohlc_*.parquet` — daily OHLC cache (incl. `ohlc_^VIX.parquet`)
- `results/cache/brain_v2_scores/*.json` — per-(ticker, date) score cache
- `results/recommendation_log.json`, `backtest_results.json`, `holdings.json`

---

## 3. Step 1 — Feature Extraction (chart → 36 numbers)

The model never sees a chart. Everything about a stock at one moment is boiled
down to **36 yes/no facts**, each a `1` (true) or `0` (false). That length-36
vector is the *only* input to scoring.

### The 36 features and their sources
Defined, in **LOCKED order**, in [features/spec.py:58](features/spec.py#L58). Order
must never change — a weight is bound to each position; reordering invalidates
every saved weight file.

| Category | Count | How the bit is filled |
|---|---:|---|
| A — validated candle/momentum checks | 14 | present in analyzers' `passed_checks`? |
| B — library-swap checks (Stochastic, ADX) | 2 | `passed_checks` |
| C — breakout detector | 1 | `passed_checks` (**dead — see §14**) |
| D — in-house checks (setups, HH/HL, support) | 8 | `passed_checks` |
| E — SMC (order block, FVG, BOS, CHoCH) | 4 | dedicated top-level fields (backfill) |
| F — VWAP, ATR regime, sector RS, earnings, Fib | 7 | dedicated top-level fields |

25 (A+B+C+D) + 11 (E+F) = **36**.

### Three extraction mechanisms ([spec.py:144](features/spec.py#L144))
1. **`passed_checks` match** — is this exact string in the set of checks the
   analyzers passed? → 1/0. (Categories A–D.)
2. **Flat-key read** — SMC/VWAP/ATR/etc. are read from named fields, not the
   checklist (Categories E–F). [spec.py:119](features/spec.py#L119)
3. **Synthetic AND** — "Higher Highs + Higher Lows" is 1 only if *both*
   underlying checks passed. [spec.py:115](features/spec.py#L115)

### Why binary?
Deliberate trade of precision for robustness: no feature scaling issues, less
overfitting on a small (~23k) noisy dataset, and each weight is directly
interpretable ("how much does this condition being true help?"). **Cost:** loses
*magnitude* (RSI 72 and 95 both read "overbought = 1") and is brittle at
thresholds (ADX 24.9 vs 25.1). Trend *direction* is preserved (dedicated trend
features); trend *strength* is not. ATR regime is the one feature already using
multi-bin one-hot ([spec.py:96](features/spec.py#L96)) — the natural template for
extending binning to RSI/ADX later.

---

## 4. Step 2 — Labeling (win or lose, net of costs)

To train, each historical trade needs a truth label. We do **not** label by "did
price rise" — we simulate the actual trade.

### Every trade has a plan
The risk/reward analyzer produces entry, stop, T1, T2 (§6). The backtester
([ismail_p/scripts/advisor_backtester.py](../ismail_p/scripts/advisor_backtester.py))
walks the universe at a **monthly cadence** (configurable weekly/daily), analyzes
each ticker as of the sample date, and if a setup exists, records a trade.

### Forward simulation & outcome ([advisor_backtester.py:237](../ismail_p/scripts/advisor_backtester.py#L237))
Walk forward day by day up to a max hold window:
```
if day Low  <= stop → HIT_STOP     (stop checked FIRST — see below)
elif day High >= T2 → HIT_T2
elif day High >= T1 → HIT_T1
else after window    → EXPIRED
```
**Stop-first conservative rule:** daily bars don't reveal intraday order, so if a
single bar touches both stop and target, we assume the *stop* hit. This biases
outcomes pessimistic on purpose (better to undercount wins).

**Exit price** = whichever band triggered (stop / T1 / T2), or last close if
expired. P&L = `(exit − entry) / entry × 100`.

### The label ([spec.py:159](features/spec.py#L159))
```
win (1)  iff  pnl_pct − 0.60% > 0      (0.30% brokerage per side)
lose (0) otherwise
```
The 0.60% gate quietly kills marginal trades: a trade that *hits* a tight target
for +0.4% is still a **loss** after costs. Cost constant:
[spec.py:46](features/spec.py#L46) (`COST_ROUND_TRIP_PCT = 0.60`).

### Eligibility filter (important)
Only **decisive** outcomes train the model:
`ELIGIBLE_OUTCOMES = {hit_t1, hit_t2, hit_stop}` ([spec.py:128](features/spec.py#L128)).
**`expired` trades are dropped entirely.** Consequence: the model only ever sees
clean wins and clean losses — never "went nowhere" — which can make it
overconfident that setups *do something*, and may contribute to score clustering
(§14). Planned change: include expired (three-class) — see §15.

---

## 5. Setup detection ([features/analyzers/setup_detector.py](features/analyzers/setup_detector.py))

Four detectors run in parallel, each a weighted 0–100 checklist; the highest wins.

- **Pullback** — uptrend (MA20>MA50, price>MA50) + 2–12% dip from recent high +
  touch MA20/50 + declining volume
- **Breakout** — through resistance with volume
- **Bounce** — off strong support
- **Reversal** — oversold turning up

`best = max(...)`; if best < 40 → `"none"` ([setup_detector.py:59](features/analyzers/setup_detector.py#L59)).
The feature `"Setup detected: X"` fires only at score ≥ 50 ([line 68](features/analyzers/setup_detector.py#L68)).

**Known issues (see §14):** (1) comment/code threshold mismatch (40 vs 50);
(2) `Setup: PULLBACK` and `Setup: BREAKOUT` train to weight **0.000** — dead in
the model — while `REVERSAL` (+0.43) and `BOUNCE` (−0.24) work.

---

## 6. Risk/Reward — entry, stop, targets ([features/analyzers/risk_reward.py](features/analyzers/risk_reward.py))

- **Entry** = current price ([line 43](features/analyzers/risk_reward.py#L43)).
- **Stop** = best of four candidates, chosen by setup type
  ([lines 46–83](features/analyzers/risk_reward.py#L46)): below nearest support
  (×0.995), ATR-based (`entry − 2×ATR`), below 10-day swing low, or just under
  MA20/50. Pullback → tightest; breakout → below breakout level; fallback 5%.
- **T1** = nearest resistance (or +5%). **T2** = `entry + 2×risk`. **T3** = next
  resistance or `entry + 3×risk`. Sorted, floored to ≥ +1%.
- **R:R** = `(T1 − entry) / (entry − stop)`.

**Caveats:** market entry takes any fill; "tightest stop" selection raises
stop-out frequency; fixed T1 (nearest resistance) caps winners and can understate
R:R. R:R alone is misleading — real metric is **expectancy**
(`P(win)·avg_win − P(lose)·avg_loss`). Improvements (ATR-normalized levels,
trailing exits) are retrain-territory.

---

## 7. Steps 3–4 — Assemble & Fit

### Assemble ([trainer.py:163](training/trainer.py#L163))
Loop eligible trades → `extract_features` (row of 36) + `extract_target` (label).
Stack into `X` (~23k × 36) and `y` (~23k). This pair is the model's entire
experience.

### Fit ([trainer.py:181](training/trainer.py#L181))
```python
LogisticRegression(C=C, penalty="l2", class_weight="balanced", solver="liblinear")
```
Learns **36 weights + 1 intercept** so `sigmoid(intercept + weights·features)` is
high for winners, low for losers, across all rows. Positive weight = "more common
in winners"; negative = "more common in losers"; ~0 = "irrelevant".

- **`penalty="l2"`** — shrinks weights toward 0 unless data strongly justifies
  them; the core anti-overfit guard. `C` = inverse strength (small C = harder shrink).
- **`class_weight="balanced"`** — up-weights the rarer class so it doesn't predict
  one label for everything. **Side effect:** distorts sigmoid calibration → the
  0–100 score is NOT a true probability (§9).
- **Coefficient clip to ±3** ([trainer.py:248](training/trainer.py#L248)).

### C selection — walk-forward ([trainer.py:193](training/trainer.py#L193))
Train on an early window; test each candidate `C` on a *later* validation window;
keep the `C` maximizing **net profit-factor** above a win-rate floor. Chronological
& out-of-sample — no lookahead.

---

## 8. Step 5 — Validate, per-ticker vs pooled, save

### Weight selection at inference — **pooled only, today**
`find_weight_for_ticker` ([model/weights.py](model/weights.py)) currently returns
the **pooled** WeightSet for *every* ticker ("per-ticker disabled (r3)"). So even
though per-ticker weight files can exist, **all live scoring uses `_pooled.json`**.
The training code still supports per-ticker/pooled/disabled classification
([fit_ticker](training/trainer.py#L261)), but the loader is hardcoded to pooled.

### Quality gates ([training/diagnostics.py](training/diagnostics.py))
- **Bootstrap PF CI** — resample test trades 1000×, require 5th-percentile PF ≥ 1.20.
- **VIX-regime stratification** — split test trades low/mid/high-VIX; each bucket's
  PF must clear ~1.10 (guards "only works in calm markets").
- **Correlation flags** — feature pairs with |r| ≥ 0.7 across ≥5 tickers flagged.

### Saved artifact
JSON with `intercept`, 36 `coefficients`, `C`, counts, `feature_names`, diagnostics
→ `results/brain_v2_weights/`. The pooled model: `intercept ≈ +0.05`, `C = 1.0`,
`n_train/val/test = 12705 / 2985 / 7575`.

---

## 9. Steps 6–8 — Inference (live)

1. **Extract** — same `extract_features` → 36 bits for the stock now.
2. **Score** ([model/scorer.py:47](model/scorer.py#L47)):
   `score = sigmoid(intercept + coefficients · features) × 100`.
3. **Verdict** — bucket the score
   ([scorer.py:36](model/scorer.py#L36)):

| Score | Verdict |
|---:|---|
| ≥ 80 | STRONG BUY |
| ≥ 65 | BUY |
| ≥ 55 | LEAN BUY |
| ≥ 45 | HOLD |
| ≥ 35 | LEAN SELL |
| ≥ 20 | SELL |
| < 20 | AVOID |

4. **VIX guardrail** ([scorer.py:77](model/scorer.py#L77)) — if VIX > 22
   (`HIGH_VIX_THRESHOLD`), downgrade an actionable verdict one tier. If VIX data
   is missing the guardrail is **skipped and flagged** (`v2_skipped_reason`),
   never silently assumed. Requires `results/cache/ohlc_^VIX.parquet`.

Result cached per (ticker, date) in `results/cache/brain_v2_scores/`.

### What the score IS and ISN'T
- **IS**: a monotonic 0–100 confidence that the setup is a net win — higher =
  more favorable. The verdict is just its bucket.
- **ISN'T**: a predicted return/price target; and NOT a calibrated probability
  ("68" ≠ "68% win chance") because of `class_weight="balanced"`.
- The `confidence` label (HIGH/MED/LOW) is derived from distance of score from 50
  ([advisor.py `_confidence_from_score`](decision/advisor.py)).

---

## 10. Fallback path (no trained weights)

If no pooled weights are on disk, `advisor._section_score` computes a weighted
average of the 8 analyzer section scores (trend 18, location 20, setup 15,
volume 10, momentum 15, candles 7, risk_reward 10, market_context 5) and
`_verdict_from_section_score` maps it to BUY/LEAN BUY/HOLD/AVOID
([decision/advisor.py](decision/advisor.py)). This is the pre-v2 "hand-weighted"
logic, kept only as a safety net. `TradeConfig.WEIGHTS` in
[decision/types.py](decision/types.py) is now otherwise dead code (mirrored inside
the fallback).

---

## 11. The 14 analyzers

Each emits `passed_checks` (feeding §3 features) and a 0–100 section score. Deep
detail in this doc covers `trend`, `setup_detector`, `risk_reward`; the rest:

| Analyzer | Role |
|---|---|
| trend | MAs, EMA, ADX, HH/HL, weekly-trend confirmation |
| location | distance to support/resistance, dead-zone |
| setup_detector | pullback/breakout/bounce/reversal |
| volume | volume spike / above-average / OBV |
| momentum | RSI, MACD, Stochastic, ROC |
| candlesticks | hammer, engulfing, morning star, doji, etc. |
| market_context | relative strength vs SPY, sector |
| risk_reward | entry/stop/targets, R:R |
| support_resistance | swing/pivot/Fib level clustering |
| avoid_checker | red-flag strings (spike, wicks, choppy ADX) |
| sell_signals | separate 0–100 `sell_score` (weighted bearish checklist) |
| fundamental | P/E, ROE, growth, health → fundamental_score (UI) |
| technical | MA/RSI/MACD snapshot → technical_score (UI) |

Note `weekly` frame is resampled from cached daily (~61 weeks) and feeds only the
"Weekly trend bullish" check — which is **not** one of the 36 features, so it has
~zero effect on the v2 verdict (only nudges the §10 fallback).

---

## 12. Regime detector ([decision/regime.py](decision/regime.py))

A separate market-wide model (not per-stock) that gauges whether it's a good time
to buy at all, producing a regime label + `regime_multiplier`. Six weighted
signals ([regime.py:120](decision/regime.py#L120)):

| Signal | Weight | Source |
|---|---:|---|
| VIX level | 0.22 | ^VIX |
| SPY vs 200-DMA | 0.22 | SPY |
| SPY 20-DMA slope | 0.13 | SPY |
| Breadth (RSP−SPY) | 0.16 | RSP vs SPY |
| **Sector participation** | 0.15 | % of 11 SPDR sector ETFs above 50-DMA |
| Yield curve (10Y−3M) | 0.12 | ^TNX, ^IRX |

Sector participation was added recently (all six sum to 1.0; missing signals
renormalize). Each signal returns an integer score (≈ −3…+2); weighted → regime.

---

## 13. Downstream layers (exist, mostly not model)

### Position sizing — GATED OFF ([decision/position_sizer.py](decision/position_sizer.py))
Four sizing methods run and the **smallest (safest) share count wins**
([size():263](decision/position_sizer.py#L263)): fixed-risk, ATR-parity, Kelly
(win-rate capped 0.75), and a max-cap; plus conviction/volatility/heat multipliers
and a 6% portfolio-heat cap. Hard rules refuse trades with bad stop / R:R < floor.
**Currently disabled everywhere** via `config.ENABLE_POSITION_SIZING = False`
(§16).

### Execution / live-ops ([execution/](execution/))
- `alert_manager` — dispatch alerts (sound, terminal, Telegram)
- `live_monitor` — continuous monitoring loop
- `position_tracker` — per-session open-position tracking

Not covered by ARCHITECTURE.md; **untested/undiscussed** — unclear how much is
wired to anything live. Treat as experimental.

### Exits — STUB ([model/exits.py](model/exits.py))
Docstring: *"V2 exit rules — stub; real implementation pending."* Stops/targets are
set at entry, but there is **no implemented v2 exit-rule engine**. Real gap.

### Caching
- **OHLC cache** ([data/ohlc_cache.py](data/ohlc_cache.py)) — `get_or_update_daily`
  stores daily history once and fetches only missing recent days on repeat visits
  (live path only; backtest replay always fetches fresh). `USE_OHLC_CACHE` flag.
- **Score cache** — per (ticker, date) JSON so repeat lookups are instant.

---

## 14. Known issues / audit findings 🚩

Findings from inspecting the actual trained `_pooled.json` coefficients:

1. **Model dominated by 4 SMC features.** Largest magnitudes both directions are
   SMC: `smc_order_block_bullish +1.26`, `smc_choch_bullish −1.36`,
   `smc_bos_bullish −1.17`, `smc_fvg_bullish +0.59`. These are **backfilled**
   features ([spec.py:20](features/spec.py#L20)) — if backfill has noise/lookahead,
   the model rests on the least-trustworthy inputs.
2. **Contradictory SMC signs.** `order_block` & `fvg` (bullish) are strongly
   positive, but `bos` & `choch` (also "bullish") are strongly negative — either a
   real contrarian effect or a polarity/label bug in backfill. Verify before trust.
3. **Dead features.** `Setup: BREAKOUT` = 0.000 (flagged known-broken,
   [spec.py:183](features/spec.py#L183)) and `Setup: PULLBACK` = 0.000. Two of 36
   features contribute nothing; pullback is one you care about.
4. **Near-zero classics.** MACD crossover, ADX>25, OBV, sector RS, MA20 slope all
   ≈ 0 — the model effectively ignores most classic technicals.
5. **Scores cluster ~50 (observed 34–55).** With intercept ≈ 0.05 and most
   features ≈ 0, scores barely leave the `sigmoid(0)≈0.5` baseline — so the live
   scanner often finds nothing ≥ 55 (LEAN BUY). Likely compounded by binary
   feature loss (§3) and training only on decisive outcomes (§4).
6. **Doc drift.** ARCHITECTURE.md omits: expired filter, walk-forward C-selection,
   profit-factor gates, stop-first labeling rule, and the entire `execution/` layer.
7. **exits.py stub / execution untested** (§13).

---

## 15. Retrain-TODO list

**Post-review status (2026-07-05).** An adversarial review confirmed §14 and found
worse: four missing runtime dependencies (`smartmoneyconcepts`, `pandas_ta_classic`,
`talib`, `lxml`) meant **9 of 36 features were permanently 0 at live inference** —
including the model's 4 highest-weighted (SMC). Fixed: deps installed, stale score
cache cleared, `check_feature_dependencies()` added to
[features/live_features.py](features/live_features.py) with a hard UI banner.
Additional findings now tracked below: no purge/embargo at fold boundaries
(60-day holds leak across splits; overlapping same-ticker windows inflate the
bootstrap CI), and **selection bias** (backtester forward-tests only v1-BUY
verdicts — [advisor_backtester.py:454](../ismail_p/scripts/advisor_backtester.py#L454) —
so the model trained only on v1-approved situations but scores everything live).

Substantive model changes identified — all require an offline **retrain** (feature
or label changes invalidate current weights). Priority order per review:

**RETRAIN-1 RESULT (2026-07-05) — the honest baseline: NO EDGE.** Event-driven
backtest (all verdicts, exact 60-trading-day window, point-in-time features,
17,946 decisive trades, 57 tickers, 2023-05→2026-06) + purged folds + 0.60%
costs → pooled model: **test PF 0.575** (bootstrap CI 0.536–0.615), train PF
0.575, WR 48.7%. The system loses money *even in-sample* — no reweighting of
the 36 features finds a profitable pocket. Root cause is **trade geometry, not
the model**: median hold 1 day, median stop distance 1.23%, median |move| 1.14%
vs 0.60% cost — the "tightest-of-4-stops" + sorted-nearest-target design creates
micro-trades where costs consume the edge. The old reported PF ≥ 1.20 was an
artifact of 0.20% costs, unpurged folds, v1-BUY selection, and backfilled
features. **Next lever: redesign exits/levels (item 4), then re-measure.**
New artifacts: `results/retrain1_backtest.json` (dataset),
`results/brain_v2_weights_retrain1/` (weights + diagnostics; live model untouched).

**GEOMETRY-V1 RESULT (2026-07-06) — edge restored.** Redesigned trade geometry in
[risk_reward.py](features/analyzers/risk_reward.py): stop = 2×ATR floored at
2.5% (no more "tightest-of-4"), targets ≥ 2R (resistance used only beyond 2R).
Dataset transformed: median hold 1→13 trading days, median |move| 1.14%→6.84%
(cost now ~9% of move, not ~50%), 2,103 decisive trades, 7% expiry.
Purged, cost-honest results (pooled, both folds):
| fold | test period | test PF net | bootstrap p5–p95 | WR |
|---|---|---:|---:|---:|
| fold1 | 2025-06→2026-06 | **1.589** | 1.30–1.91 | 42.4% |
| fold2 | 2024-10→2025-10 | **1.704** | 1.39–2.06 | 44.9% |
VIX-stratified (fold1): low 2.05 / mid 1.48 / high 1.05 — guardrail justified.
Caveats: small dataset (~2.1k trades ≈ 25/feature in train); fold1 val window
(2024-10→2025-04) was weak (PF 0.72) — regime sensitivity to watch; geometry was
chosen a priori (standard 2×ATR / 2R), not tuned on test. Weights at
`results/brain_v2_weights_retrain1/_pooled_geomv1.json` — NOT yet deployed live.
⚠️ Deploy note: live app already runs the NEW geometry (risk_reward.py edited)
but the OLD pooled weights — deploy geomv1 weights + clear score cache to align.

**RETRAIN-2 / ROLLING EVAL (2026-07-06) — the real yardstick.** Dataset expanded
to 269 tickers × 2019-2026 (22,243 decisive trades, `retrain1_backtest.json`;
57-ticker set preserved as `retrain1_backtest_geomv1_57tkr.json`). New
user-designed **rolling walk-forward evaluation** ([training/rolling.py](training/rolling.py)):
monthly refits, purged by `resolved_date`, C re-selected per refit on trailing
6 months, 66 test months (2021-01→2026-06). Results (net 0.60%):
**overall PF 1.135** (bootstrap CI 1.09–1.18), WR 37.3%, 8,885 picks
(~135/mo), avg +0.52%/trade, 24/66 losing months. Yearly: 2021 +1194%,
**2022 −1658% (bear year — system loses in sustained downtrends)**, 2023 +1410%,
2024 +1457%, 2025 +1792%, 2026H1 +543%. The static-fold PF 1.6–1.7 was
period-specific (bull years); 1.13 is the honest through-cycle number.
**Regime-filter test (surprising):** blocking VIX>22 entries CUTS PF to 1.04 —
high-VIX entries are this system's BEST trades (bounce-buying panic works);
SPY>MA200 filter ≈ neutral (1.127); both filters ≈ kills edge (1.03) and still
lose in 2022 (bear rallies are traps). ⇒ (a) the live **VIX guardrail may be
blocking the best trades — revisit** (TODO 11 evidence), (b) no cheap regime
filter fixes bear years — accept drawdown regimes or hedge at portfolio level,
(c) do NOT keep iterating filters against this eval (overfitting the yardstick).
Eval artifact: `results/rolling_eval_retrain2.json`.

**FINAL EXPERIMENT (2026-07-06) — LightGBM + continuous features: BAR NOT CLEARED.**
Pre-registered test: does gradient boosting on RAW indicator values (32 continuous
features: RSI, ADX, ATR%, MA-distances, 52w-high distance, vol ratio, OBV, SPY
relative strength, VIX, trade geometry, 8 section scores + the 36 binary) beat
the 37.6% base rate out of sample? Protocol: identical rolling monthly refits,
purged, 66 months, n=16,374 OOS trades ([training/continuous_features.py](training/continuous_features.py)).
Result: **logistic(binary) AUC 0.498, LightGBM(continuous) AUC 0.478** — both
coin-flips; LGBM top-decile WR 37.5% = exactly base rate. **The signal is not in
these features at this horizon — not a binarization problem, not a model-class
problem.** Combined with the confusion-matrix finding (precision = base rate),
the ML question is closed: the system's profitability (+65%/5.5yr, PF 1.135)
comes from trade geometry (2R:1R asymmetry) + market exposure, not prediction.
Consistent with the academic literature on daily-bar technical trading.
**Status: model R&D concluded. The honest system = take valid setups, 2×ATR stop
(8% cap), ≥2R targets, always-invested slots. The 0-100 score should be treated
as decoration until some future feature source (not daily OHLC technicals)
clears the pre-registered bar.**

0. **(P0, done)** Restore feature integrity at inference; clear stale score cache.
0b. **(P0)** Retrain at 0.60% costs with **purged folds** (embargo ≥ max_hold=60d at
   train/val and val/test boundaries) and dedup overlapping same-ticker windows.
0c. **(P0)** Fix selection bias: forward-test all analyses with valid levels (or
   explicit two-stage gate: setup-exists → model scores), so train matches serve.
0d. **(P1)** Calibrate the score (Platt/isotonic on validation) and re-derive verdict
   thresholds; rank opportunities by **expectancy** = P(win)·reward − P(lose)·risk,
   not raw score.

1. **Fix dead setup features** — investigate why `Setup: PULLBACK` / `BREAKOUT`
   train to 0 (name mismatch or never ≥50 in training); fix or drop.
2. **Include expired trades — three-class** (win/neutral/lose): model becomes
   multinomial; the 0–100 score must be re-derived from three probabilities
   (e.g. `P(win) − P(lose)` or expected value).
3. **Hourly label resolution** — feed the forward *hourly path* into the outcome
   simulator to remove the pessimistic stop-first rule (recent trades only; yfinance
   depth: ~730d hourly, ~60d sub-hourly).
4. **Better exits** — trailing / expectancy-based targets vs fixed T1 (caps winners).
5. **Binning** — extend one-hot binning (already used for ATR) to RSI/ADX to recover
   magnitude lost by binary features.
6. **News-based market context** — new sentiment feature (Category E/F, 0/1 or
   binned). Requires its own point-in-time news→sentiment pipeline (no future-leak).
   Locked-order change → retrain.
7. **SMC dominance / calibration** — **lookahead empirically confirmed
   (2026-07-05)**: across 40 (ticker, date) test points, computing SMC on full
   history vs data-sliced-to-date flips ~8% of feature values; FVG fires 2×
   more with future data (15 vs 7), OB 3 vs 1. Mechanism: swing confirmation
   needs 10 future bars; FVG `MitigatedIndex` uses future fills. The original
   backfill script (`backfill_brain_v2_features.py`) is deleted, so whether it
   sliced correctly is unverifiable → **treat trained SMC weights as suspect;
   at retrain, recompute ALL features point-in-time** via the as-of pipeline.
8. **Re-enable per-ticker weights?** — loader is pooled-only today; decide whether
   to restore per-ticker selection. Context: 53/57 tickers failed per-ticker
   gates (39 pf_raw_fail, 9 bootstrap, 3 WR floor, 2 low-n) — needs more data
   per ticker before revisiting.
9. **Event-driven sampling** (replaces monthly cadence): one open trade per
   ticker at a time; after a trade resolves (stop/target), scan **every
   subsequent day** for the next setup; enter when found; 60-day max hold
   unchanged. Eliminates overlapping windows by construction and samples setups
   promptly instead of on arbitrary month boundaries.
10. **Hold-window unit bug**: `_fetch_forward_bars` fetches `max_hold_days + 7`
    **calendar** days then caps at `max_hold_days` **rows** (trading days) —
    67 calendar days ≈ only ~46 trading days, so the "60-day hold" is really
    ~46 trading days. Pick one unit (trading days) and fix the fetch window.
11. **VIX guardrail v2**: replace the hard one-tier downgrade at VIX>22 with
    VIX-regime as a model feature (learned) and/or continuous position-size
    scaling by VIX. Keep the hard rail until then.

---

## 16. Config flags & cost model

[config.py](config.py):
- `ENABLE_POSITION_SIZING = False` — gates sizing everywhere (advisor + UI).
- `USE_OHLC_CACHE = True` — live path serves daily/weekly from parquet cache.
- Cost model of record: `features.spec.apply_costs` (0.30%/side, 0.60% round-trip).
  `TRANSACTION_COSTS` in config.py is aligned but **unused** by istock.

> Note: current weights were trained at the *old* 0.20% cost. The 0.60% takes full
> effect on the next retrain; today it only affects backtest/diagnostics displays.

---

## 17. Data-flow gotchas

- **Paths resolve to `ismail_personal/`**, not `istock/`. A stray
  `istock/results/` tree exists but is **not** read.
- **Module-level caches** (e.g. VIX in `live_features`) persist for the process
  life — a file added mid-run needs a Streamlit restart, not just "Refresh data".
- **Point-in-time replay**: price indicators can be recomputed as of a past date;
  fundamentals/analyst data remain *current* snapshots (yfinance has no historical
  fundamentals).
- **Train/predict parity**: never change `FEATURE_NAMES` order or `extract_features`
  logic without retraining — it silently corrupts every score.
