# istock

**Give it a stock ticker → it scores the stock 0–100 with a trained model, tells you BUY / HOLD / SELL.**

A stock technical-analysis and trade-recommendation system for US equities. You give it a ticker (e.g. `AAPL`); it fetches price data, runs technical checks, scores the stock 0–100 with a trained logistic-regression model ("Brain v2"), turns that score into a verdict (STRONG BUY → AVOID), and sizes a position if it's a BUY.

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

The system reads the last year of daily candles and computes ~25 technical indicators (moving averages, RSI, MACD, ATR, ADX, Bollinger Bands, volume, OBV, etc.). A set of analyzers each answer one yes/no question ("Is price above MA200?", "Bullish MACD crossover?", "Volume above average?"). Their answers, plus 11 extra computed signals, become a **36-number on/off feature vector**. A trained model turns that vector into a single **0–100 score**, which maps to a **verdict**. If it's a BUY, a position sizer works out how many shares to buy — always choosing the safest (smallest) size.

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
  ▼  7. SIZE THE TRADE    4 sizing methods (fixed-risk, ATR parity, Kelly, cap) → smallest wins
verdict + position
```

The whole thing is orchestrated by `decision/advisor.py` (`TradeAdvisor.analyze`).

---

## Highlights

- **Brain v2 engine.** Logistic regression over a locked 36-feature checklist. A hand-weighted 8-section score is kept only as a fallback when no model is trained.
- **Safety-first sizing.** Four position-sizing methods run in parallel; the smallest wins. Trades with R:R < 1.5, no setup, or a bad stop are refused outright.
- **VIX guardrail.** When VIX > 22, any actionable buy verdict is downgraded one tier. If the VIX data is missing, the guardrail is *skipped and flagged* — never silently assumed.
- **Market regime detector.** Reads five broad-market signals (volatility, trend, slope, breadth, yield curve) to decide whether it's even a good time to be buying, and scales position size accordingly.
- **Point-in-time replay.** Price indicators can be recomputed as of a past date (fundamentals remain today's snapshot — yfinance has no historical fundamentals).
- **Per-(ticker, date) score cache** so repeat lookups are instant.

---

## Tech stack

Python · Streamlit · pandas / numpy · [`ta`](https://github.com/bukosabino/ta) (technical indicators) · yfinance (data)

---

## Getting started

```bash
# clone
git clone <your-repo-url> istock
cd istock

# install deps
pip install numpy pandas yfinance ta streamlit

# run the app
streamlit run ui/app.py
```

Then open the local URL Streamlit prints and enter a ticker.

---

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

See [ARCHITECTURE.md](ARCHITECTURE.md) for a full walkthrough of the pipeline, the 36 features, the analyzers, and the training scheme.

---

## Disclaimer

This is a personal research project for educational purposes. It is **not** financial advice. Do your own research before making any investment decisions.
