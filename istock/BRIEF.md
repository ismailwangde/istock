# istock — Quick Brief

**What it is:** give it a stock ticker → it scores the stock 0–100 with a trained model
(Brain v2) and tells you BUY / HOLD / SELL, then sizes the trade.

**Engine:** Brain v2 = a logistic-regression model over a 36-point on/off checklist.
The old hand-weighted 8-section score is only a fallback when no model is trained.

---

## The pipeline, step by step

Each box = one step: **what happens** and **what's used**.

```
┌─ STEP 1 ── FETCH DATA ───────────────────────────────────────────┐
│ Pull 1y daily + 2y weekly candles + market index + fundamentals. │
│ Compute ~25 indicators (MAs, RSI, MACD, ATR, ADX, Bollinger,     │
│ volume, OBV, Stochastic, ROC...).                                │
│ Uses: data/engine.py (DataEngine, yfinance)                      │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ STEP 2 ── FIND PRICE LEVELS ────────────────────────────────────┐
│ Locate support / resistance / Fibonacci levels and cluster the   │
│ nearby ones into stronger levels.                                │
│ Uses: features/analyzers/support_resistance.py                   │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ STEP 3 ── RUN THE ANALYZERS ────────────────────────────────────┐
│ 8 scoring analyzers each answer yes/no checks and return a       │
│ 0-100 section score: trend, location, setup, volume, momentum,   │
│ candlesticks, risk/reward, market context.                       │
│ Plus: avoid_checker (red flags) and sell_signals (0-100 sell).   │
│ Uses: features/analyzers/*.py                                    │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ STEP 4 ── BUILD THE FEATURE VECTOR ─────────────────────────────┐
│ Turn all the checks + 11 extra signals (SMC, VWAP, ATR regime,   │
│ sector strength, earnings, fib) into a 36-number on/off vector.  │
│ Uses: features/live_features.py + features/spec.py               │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ STEP 5 ── SCORE WITH THE MODEL ─────────────────────────────────┐
│ score = sigmoid(weights · features) × 100  → a number 0-100.     │
│ Weights = trained pooled logistic model loaded from disk.        │
│ Uses: model/scorer.py + model/weights.py (_pooled.json)          │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ STEP 6 ── TURN SCORE INTO A VERDICT ────────────────────────────┐
│ ≥80 STRONG BUY · ≥65 BUY · ≥55 LEAN BUY · ≥45 HOLD ·             │
│ ≥35 LEAN SELL · ≥20 SELL · <20 AVOID.                            │
│ If VIX > 22, downgrade an actionable verdict one tier.           │
│ Uses: model/scorer.py (verdict_from_score, VIX guardrail)        │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ STEP 7 ── SIZE THE TRADE (only if BUY + real setup) ────────────┐
│ Compute 4 position sizes (fixed-risk, ATR parity, Kelly, cap)    │
│ and pick the SMALLEST (safety-first). Regime multiplier scales   │
│ it up or down based on the broad market.                         │
│ Uses: decision/position_sizer.py + decision/regime.py            │
└──────────────────────────────────────────────────────────────────┘
```

The whole thing is orchestrated by **`decision/advisor.py`** (`TradeAdvisor.analyze`).

---

## Key things to remember

- **Brain v2 is the engine.** Logistic regression on a 36-feature checklist. The
  8-section weighted average is only a fallback when no model file exists.
- **36 features are locked.** Their order in `features/spec.py` must never change, or
  saved model weights break.
- **VIX guardrail:** VIX > 22 downgrades a buy verdict one tier. Needs the VIX parquet;
  if missing, it's skipped and flagged (not silently assumed).
- **Position sizer always picks the smallest size** of four methods. It refuses trades
  with R:R < 1.5, no setup, or a bad stop.
- **Scores are cached** per ticker + date in `results/cache/brain_v2_scores/`.
- **All result paths resolve to `ismail_personal/results/`, not `istock/`.**
- **Point-in-time replay** works for price indicators (`as_of_date`), but fundamentals
  are always today's snapshot — yfinance has no historical fundamentals.
- **`ismail_p/` is legacy.** `istock/` is the clean current package.

Run it: `…/.venv/bin/streamlit run ismail_personal/istock/ui/app.py`
</content>
