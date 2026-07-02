# istock

**Give it a stock ticker → it scores the stock 0–100 with a trained model, tells you BUY / HOLD / SELL.**

A stock technical-analysis and trade-recommendation system for US equities. You give it a ticker (e.g. `AAPL`); it fetches price data, runs technical, fundamental and market context checks, scores the stock 0–100 with a trained logistic-regression model based on different features and turns that score into a verdict (STRONG BUY → AVOID)

---

<!-- Add screenshots — e.g. ![Deep dive](docs/screenshots/deep-dive.png) -->
### Quick Stock Insights
![Home](Quick%20Stock%20Insights.png)

### Price Chart with Supporting Verdicts
![Price Chart](Price%20Chart%20with%20supporting%20Verdicts.png)

### Stock Opportunities
![Stock Opportunities](Stock%20Opportunities.png)


---

## How it works

The system reads the last year of daily candles and computes ~25 technical indicators (moving averages, RSI, MACD, ATR, ADX, Bollinger Bands, volume, OBV, etc.). A trained model turns that vector into a single **0–100 score**, which maps to a **verdict**. 

```
ticker
  │
  ▼  1. FETCH DATA        1y daily + 2y weekly + market index + fundamentals; ~25 indicators
  ▼  2. PRICE LEVELS      support / resistance / Fibonacci, clustered into stronger levels
  ▼  3. ANALYZERS         8 scoring analyzers (trend, location, setup, volume, momentum,
  │                       candles, risk/reward, market context) + avoid & sell checks
  ▼  4. FEATURE VECTOR    all checks + 11 extra signals → 36-number on/off vector
  ▼  5. SCORE             sigmoid(weights · features) × 100  →  0–100
  ▼  6. VERDICT           ≥80 STRONG BUY · ≥65 BUY · ≥55 LEAN BUY · ≥45 HOLD ·
  │                       ≥35 LEAN SELL · ≥20 SELL · <20 AVOID   (VIX>22 downgrades one tier)
verdict + position
```

---

## Highlights

- **Market regime detector.** Reads five broad-market signals (volatility, trend, slope, breadth, yield curve) to decide whether it's even a good time to be buying, and scales position size accordingly.
- **Point-in-time replay.** Price indicators can be recomputed as of a past date (fundamentals remain today's snapshot — yfinance has no historical fundamentals).
- **Per-(ticker, date) score cache** so repeat lookups are instant.


## Project layout

```
istock/
├── data/         DataEngine — fetch OHLC + compute indicators
├── features/     the 36-feature spec, live signals, and 14 analyzers
├── model/        scorer, trained weights, exit rules
├── decision/     TradeAdvisor (orchestrator), position sizer, regime detector
├── execution/    live monitoring, alerts, P&L tracking
├── training/     offline Brain v2 training (walk-forward) + diagnostics
└── ui/           Streamlit app + terminal display
```

---

## Disclaimer

This is a personal research project for educational purposes. It is **not** financial advice. Do your own research before making any investment decisions.
