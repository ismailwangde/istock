# Brain v1 vs Brain v2 — Test-Window Baseline (S22b)

_Test window: **2025-05-09 → 2026-05-07** (frozen)._ All figures **net of the 0.20% round-trip cost** (§5b). v1 baseline uses the verdict already recorded in every trade row (brain v1 ran at simulation time, results live in `trade['verdict']` / `trade['pnl_pct']`).

## Brain v1 baseline (test window, net of costs)

### Aggregate — cohort B (STRONG BUY + BUY + LEAN BUY = every actionable v1 verdict)

| Metric | Value |
|---|---:|
| N trades | 7575 |
| Net PF | **0.99** |
| Bootstrap p5 / p95 | 0.95 / 1.03 |
| Net WR | 49.8% |
| Avg PnL / trade (net %) | -0.005 |

### Aggregate — cohort A (STRONG BUY + BUY only, higher-conviction subset)

| Metric | Value |
|---|---:|
| N trades | 3485 |
| Net PF | **1.03** |
| Bootstrap p5 / p95 | 0.97 / 1.10 |
| Net WR | 50.0% |
| Avg PnL / trade (net %) | 0.021 |

### VIX stratified (cohort B — every actionable v1 verdict)

| Regime | v1 PF | v2 pooled PF | Delta |
|---|---:|---:|---:|
| low (<17 / 17-22 / >22) | 0.97 | 1.35 | +39.3% |
| mid (<17 / 17-22 / >22) | 1.05 | 1.33 | +26.9% |
| high (<17 / 17-22 / >22) | 0.70 | 0.96 | +37.9% |

### VIX stratified (cohort A — STRONG BUY + BUY only)

| Regime | v1 PF | v2 pooled PF | Delta |
|---|---:|---:|---:|
| low (<17 / 17-22 / >22) | 0.99 | 1.35 | +36.8% |
| mid (<17 / 17-22 / >22) | 1.11 | 1.33 | +19.5% |
| high (<17 / 17-22 / >22) | 0.72 | 0.96 | +34.5% |

## vs Brain v2 pooled (aggregate)

| Metric | v1 (cohort B) | v2 pooled | Delta |
|---|---:|---:|---:|
| Aggregate net PF | 0.99 | 1.32 | +32.9% |
| Bootstrap p5 | 0.95 | 1.24 | +30.5% |
| Net WR | 49.8% | 57.2% | — |
| High-VIX PF | 0.70 | 0.96 | +37.9% |

## Per-ticker comparison (v1 = all eligible test trades; v2 = picked-as-win)

Confident-4 tickers (AMD, CAT, MU, WDC) use their per-ticker v2 model. The other 53 use the pooled v2 model applied to their test trades.

| Ticker | n_test | v1 PF | v1 p5 | v2 kind | v2 n_pick | v2 PF | v2 p5 | Winner |
|---|---:|---:|---:|---|---:|---:|---:|---|
| AAPL | 163 | 0.68 | 0.52 | pooled | 97 | 0.85 | 0.57 | v2 |
| ABBV | 142 | 0.93 | 0.68 | pooled | 78 | 1.16 | 0.77 | v2 |
| ABT | 98 | 0.55 | 0.37 | pooled | 34 | 0.53 | 0.26 | v1 |
| ACN | 61 | 0.87 | 0.55 | pooled | 34 | 0.89 | 0.46 | v2 |
| ADBE | 23 | 0.61 | 0.25 | pooled | 16 | 0.86 | 0.34 | v2 |
| AMD | 126 | 1.32 | 0.96 | **per-ticker** | 66 | 2.05 | 1.30 | v2 |
| AMZN | 158 | 0.87 | 0.66 | pooled | 94 | 0.83 | 0.58 | v1 |
| AVGO | 160 | 1.18 | 0.89 | pooled | 102 | 1.85 | 1.29 | v2 |
| BAC | 162 | 1.15 | 0.86 | pooled | 98 | 1.52 | 1.07 | v2 |
| BE | 95 | 1.26 | 0.85 | pooled | 54 | 1.78 | 1.10 | v2 |
| BRK-B | 118 | 0.47 | 0.33 | pooled | 53 | 0.51 | 0.30 | v2 |
| CAT | 200 | 1.54 | 1.19 | **per-ticker** | 77 | 1.84 | 1.23 | v2 |
| COST | 110 | 0.47 | 0.32 | pooled | 54 | 0.43 | 0.25 | v1 |
| CRM | 59 | 0.63 | 0.40 | pooled | 27 | 0.68 | 0.33 | v2 |
| CSCO | 204 | 1.18 | 0.92 | pooled | 110 | 2.27 | 1.63 | v2 |
| CVX | 154 | 1.03 | 0.76 | pooled | 81 | 1.18 | 0.80 | v2 |
| DHR | 118 | 0.75 | 0.54 | pooled | 64 | 1.02 | 0.65 | v2 |
| FANUY | 155 | 1.10 | 0.83 | pooled | 74 | 1.89 | 1.25 | v2 |
| GOOGL | 183 | 1.31 | 1.00 | pooled | 112 | 1.58 | 1.12 | v2 |
| GS | 186 | 1.19 | 0.91 | pooled | 110 | 1.88 | 1.33 | v2 |
| HD | 118 | 0.51 | 0.34 | pooled | 64 | 0.77 | 0.48 | v2 |
| HON | 136 | 0.76 | 0.56 | pooled | 79 | 0.94 | 0.63 | v2 |
| IBM | 140 | 1.39 | 1.03 | pooled | 71 | 1.49 | 1.00 | v2 |
| INTC | 131 | 1.36 | 0.97 | pooled | 62 | 2.36 | 1.37 | v2 |
| JNJ | 159 | 0.95 | 0.71 | pooled | 106 | 1.35 | 0.98 | v2 |
| JPM | 171 | 1.05 | 0.81 | pooled | 83 | 1.86 | 1.24 | v2 |
| KO | 160 | 0.86 | 0.65 | pooled | 64 | 1.33 | 0.87 | v2 |
| LIN | 166 | 0.78 | 0.60 | pooled | 96 | 1.10 | 0.79 | v2 |
| LLY | 103 | 0.83 | 0.57 | pooled | 60 | 1.06 | 0.65 | v2 |
| MA | 105 | 1.01 | 0.72 | pooled | 46 | 1.24 | 0.74 | v2 |
| MCD | 132 | 0.50 | 0.37 | pooled | 56 | 0.89 | 0.55 | v2 |
| META | 132 | 0.84 | 0.61 | pooled | 62 | 0.78 | 0.49 | v1 |
| MRK | 158 | 0.90 | 0.68 | pooled | 97 | 1.27 | 0.87 | v2 |
| MSFT | 136 | 1.21 | 0.90 | pooled | 78 | 1.42 | 0.93 | v2 |
| MU | 140 | 1.59 | 1.18 | **per-ticker** | 101 | 2.10 | 1.46 | v2 |
| NEE | 173 | 1.24 | 0.95 | pooled | 95 | 1.68 | 1.14 | v2 |
| NFLX | 106 | 1.08 | 0.76 | pooled | 45 | 1.25 | 0.76 | v2 |
| NOW | 53 | 0.78 | 0.45 | pooled | 30 | 0.55 | 0.27 | v1 |
| NVDA | 174 | 1.02 | 0.77 | pooled | 103 | 1.30 | 0.90 | v2 |
| ORCL | 98 | 1.78 | 1.22 | pooled | 58 | 1.66 | 1.03 | v1 |
| PCRHY | 165 | 0.58 | 0.43 | pooled | 0 | 0.00 | 0.00 | v1 |
| PEP | 138 | 0.74 | 0.53 | pooled | 86 | 0.68 | 0.45 | v1 |
| PG | 65 | 1.23 | 0.78 | pooled | 41 | 1.55 | 0.90 | v2 |
| PM | 140 | 0.90 | 0.66 | pooled | 65 | 0.79 | 0.49 | v1 |
| QCOM | 135 | 1.28 | 0.95 | pooled | 79 | 2.13 | 1.44 | v2 |
| SNDK | 87 | 1.52 | 0.99 | pooled | 0 | 0.00 | 0.00 | v1 |
| STX | 116 | 1.41 | 1.03 | pooled | 69 | 1.51 | 0.97 | v2 |
| TMO | 133 | 0.74 | 0.53 | pooled | 62 | 1.97 | 1.26 | v2 |
| TSLA | 142 | 0.85 | 0.62 | pooled | 78 | 0.80 | 0.51 | v1 |
| TXN | 119 | 1.54 | 1.12 | pooled | 80 | 2.52 | 1.66 | v2 |
| UNH | 67 | 0.95 | 0.62 | pooled | 45 | 1.22 | 0.69 | v2 |
| UPS | 121 | 0.87 | 0.60 | pooled | 76 | 0.99 | 0.66 | v2 |
| V | 97 | 0.41 | 0.27 | pooled | 43 | 0.40 | 0.22 | v1 |
| WDC | 135 | 1.45 | 1.07 | **per-ticker** | 69 | 1.89 | 1.22 | v2 |
| WFC | 166 | 0.81 | 0.62 | pooled | 74 | 1.22 | 0.83 | v2 |
| WMT | 213 | 0.90 | 0.71 | pooled | 120 | 1.15 | 0.83 | v2 |
| XOM | 170 | 1.15 | 0.90 | pooled | 105 | 1.45 | 1.00 | v2 |

**Tally:** v2 wins **45** tickers, v1 wins **12**, ties **0** (threshold: ±0.01 PF). §8 gate 4 requires v2 to beat v1 on **≥ 40 / 57** tickers; this dataset gives the answer.

## Summary

- v1 aggregate net PF (cohort B) = **0.99** (p5 0.95 / p95 1.03)
- v2 pooled aggregate net PF = **1.32** (p5 1.24)
- v2 vs v1 aggregate delta: +32.9% (v2 better)
- v1 high-VIX PF: 0.70 | v2 high-VIX PF: 0.96
- v2 beats v1 on 45 / 57 tickers (§8 gate 4 requires ≥40)
