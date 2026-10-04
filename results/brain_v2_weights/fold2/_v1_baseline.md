# Brain v1 vs Brain v2 — Test-Window Baseline (S23a, fold2)

_Test window: **2024-11-08 → 2025-11-07** (frozen, fold2)._ All figures **net of the 0.20% round-trip cost** (§5b). v1 baseline uses the verdict already recorded in every trade row (brain v1 ran at simulation time, results live in `trade['verdict']` / `trade['pnl_pct']`).

## Brain v1 baseline (test window, net of costs)

### Aggregate — cohort B (STRONG BUY + BUY + LEAN BUY = every actionable v1 verdict)

| Metric | Value |
|---|---:|
| N trades | 7181 |
| Net PF | **0.91** |
| Bootstrap p5 / p95 | 0.87 / 0.95 |
| Net WR | 48.6% |
| Avg PnL / trade (net %) | -0.064 |

### Aggregate — cohort A (STRONG BUY + BUY only, higher-conviction subset)

| Metric | Value |
|---|---:|
| N trades | 3277 |
| Net PF | **0.91** |
| Bootstrap p5 / p95 | 0.85 / 0.97 |
| Net WR | 48.5% |
| Avg PnL / trade (net %) | -0.063 |

### VIX stratified (cohort B — every actionable v1 verdict)

| Regime | v1 PF | v2 pooled PF | Delta |
|---|---:|---:|---:|
| low (<17 / 17-22 / >22) | 0.90 | 1.28 | +41.6% |
| mid (<17 / 17-22 / >22) | 0.94 | 1.22 | +29.3% |
| high (<17 / 17-22 / >22) | 0.64 | 0.97 | +51.2% |

### VIX stratified (cohort A — STRONG BUY + BUY only)

| Regime | v1 PF | v2 pooled PF | Delta |
|---|---:|---:|---:|
| low (<17 / 17-22 / >22) | 0.89 | 1.28 | +43.2% |
| mid (<17 / 17-22 / >22) | 0.93 | 1.22 | +30.4% |
| high (<17 / 17-22 / >22) | 0.92 | 0.97 | +6.0% |

## vs Brain v2 pooled (aggregate)

| Metric | v1 (cohort B) | v2 pooled | Delta |
|---|---:|---:|---:|
| Aggregate net PF | 0.91 | 1.24 | +36.7% |
| Bootstrap p5 | 0.87 | 1.17 | +33.8% |
| Net WR | 48.6% | 56.8% | — |
| High-VIX PF | 0.64 | 0.97 | +51.2% |

## Per-ticker comparison (v1 = all eligible test trades; v2 = picked-as-win)

Per-ticker confident tickers this fold: **MU, PCRHY** (N=2). They use their own per-ticker v2 model. The remaining tickers use the pooled v2 model applied to their test trades.

| Ticker | n_test | v1 PF | v1 p5 | v2 kind | v2 n_pick | v2 PF | v2 p5 | Winner |
|---|---:|---:|---:|---|---:|---:|---:|---|
| AAPL | 149 | 0.76 | 0.56 | pooled | 86 | 1.19 | 0.80 | v2 |
| ABBV | 145 | 0.70 | 0.51 | pooled | 101 | 1.06 | 0.74 | v2 |
| ABT | 188 | 0.61 | 0.46 | pooled | 72 | 0.93 | 0.61 | v2 |
| ACN | 76 | 0.58 | 0.37 | pooled | 35 | 0.68 | 0.34 | v2 |
| ADBE | 36 | 0.74 | 0.41 | pooled | 23 | 0.97 | 0.48 | v2 |
| AMD | 91 | 1.11 | 0.74 | pooled | 59 | 1.39 | 0.85 | v2 |
| AMZN | 184 | 0.94 | 0.72 | pooled | 90 | 1.38 | 0.95 | v2 |
| AVGO | 150 | 1.18 | 0.89 | pooled | 76 | 1.84 | 1.22 | v2 |
| BAC | 156 | 0.90 | 0.68 | pooled | 81 | 1.13 | 0.75 | v2 |
| BE | 98 | 1.35 | 0.95 | pooled | 67 | 1.16 | 0.74 | v1 |
| BRK-B | 170 | 0.79 | 0.60 | pooled | 87 | 1.07 | 0.75 | v2 |
| CAT | 130 | 1.34 | 0.95 | pooled | 78 | 2.35 | 1.59 | v2 |
| COST | 140 | 0.56 | 0.41 | pooled | 60 | 0.62 | 0.39 | v2 |
| CRM | 101 | 0.51 | 0.34 | pooled | 48 | 0.49 | 0.25 | v1 |
| CSCO | 189 | 1.11 | 0.86 | pooled | 98 | 1.84 | 1.28 | v2 |
| CVX | 138 | 0.86 | 0.64 | pooled | 69 | 1.02 | 0.66 | v2 |
| DHR | 63 | 0.75 | 0.47 | pooled | 51 | 0.85 | 0.50 | v2 |
| FANUY | 115 | 0.82 | 0.57 | pooled | 53 | 1.28 | 0.78 | v2 |
| GOOGL | 156 | 1.27 | 0.95 | pooled | 89 | 2.07 | 1.39 | v2 |
| GS | 187 | 1.01 | 0.77 | pooled | 104 | 1.60 | 1.10 | v2 |
| HD | 143 | 0.62 | 0.46 | pooled | 77 | 1.07 | 0.72 | v2 |
| HON | 115 | 0.86 | 0.62 | pooled | 63 | 0.80 | 0.52 | v1 |
| IBM | 181 | 1.06 | 0.82 | pooled | 111 | 1.51 | 1.08 | v2 |
| INTC | 98 | 1.10 | 0.77 | pooled | 42 | 1.28 | 0.72 | v2 |
| JNJ | 125 | 1.16 | 0.83 | pooled | 85 | 1.71 | 1.14 | v2 |
| JPM | 193 | 0.96 | 0.75 | pooled | 89 | 2.13 | 1.45 | v2 |
| KO | 140 | 0.80 | 0.59 | pooled | 61 | 0.86 | 0.56 | v2 |
| LIN | 148 | 0.64 | 0.48 | pooled | 62 | 1.06 | 0.69 | v2 |
| LLY | 82 | 1.01 | 0.68 | pooled | 49 | 1.62 | 1.00 | v2 |
| MA | 174 | 0.72 | 0.55 | pooled | 74 | 0.80 | 0.53 | v2 |
| MCD | 146 | 0.60 | 0.43 | pooled | 66 | 0.67 | 0.44 | v2 |
| META | 177 | 0.94 | 0.70 | pooled | 88 | 0.93 | 0.62 | tie |
| MRK | 73 | 0.58 | 0.37 | pooled | 39 | 0.81 | 0.44 | v2 |
| MSFT | 140 | 1.14 | 0.85 | pooled | 76 | 1.73 | 1.16 | v2 |
| MU | 82 | 1.69 | 1.15 | **per-ticker** | 54 | 2.38 | 1.44 | v2 |
| NEE | 112 | 0.93 | 0.67 | pooled | 63 | 1.28 | 0.81 | v2 |
| NFLX | 163 | 0.90 | 0.66 | pooled | 79 | 1.31 | 0.85 | v2 |
| NOW | 114 | 0.78 | 0.54 | pooled | 66 | 1.04 | 0.67 | v2 |
| NVDA | 155 | 0.95 | 0.70 | pooled | 98 | 1.17 | 0.80 | v2 |
| ORCL | 133 | 1.31 | 0.96 | pooled | 73 | 1.28 | 0.83 | v1 |
| PCRHY | 155 | 0.40 | 0.29 | **per-ticker** | 1 | ∞ | ∞ | v2 |
| PEP | 67 | 0.90 | 0.55 | pooled | 43 | 1.17 | 0.68 | v2 |
| PG | 79 | 1.05 | 0.70 | pooled | 29 | 1.65 | 0.85 | v2 |
| PM | 162 | 0.85 | 0.63 | pooled | 80 | 1.09 | 0.72 | v2 |
| QCOM | 114 | 1.54 | 1.10 | pooled | 72 | 2.61 | 1.68 | v2 |
| SNDK | 49 | 1.72 | 0.99 | pooled | 0 | 0.00 | 0.00 | v1 |
| STX | 93 | 1.42 | 0.96 | pooled | 59 | 1.40 | 0.88 | v1 |
| TMO | 70 | 0.76 | 0.49 | pooled | 31 | 2.27 | 1.20 | v2 |
| TSLA | 130 | 0.92 | 0.65 | pooled | 75 | 1.09 | 0.73 | v2 |
| TXN | 75 | 0.83 | 0.53 | pooled | 42 | 1.39 | 0.80 | v2 |
| UNH | 68 | 1.79 | 1.16 | pooled | 38 | 1.67 | 0.95 | v1 |
| UPS | 40 | 0.66 | 0.36 | pooled | 35 | 0.97 | 0.52 | v2 |
| V | 160 | 0.69 | 0.53 | pooled | 65 | 0.93 | 0.60 | v2 |
| WDC | 94 | 1.27 | 0.85 | pooled | 60 | 1.99 | 1.21 | v2 |
| WFC | 172 | 0.87 | 0.67 | pooled | 68 | 1.69 | 1.11 | v2 |
| WMT | 185 | 0.96 | 0.74 | pooled | 106 | 1.10 | 0.77 | v2 |
| XOM | 112 | 0.93 | 0.67 | pooled | 63 | 1.41 | 0.91 | v2 |

**Tally:** v2 wins **49** tickers, v1 wins **7**, ties **1** (threshold: ±0.01 PF). §8 gate 4 requires v2 to beat v1 on **≥ 40 / 57** tickers; this dataset gives the answer.

## Summary

- v1 aggregate net PF (cohort B) = **0.91** (p5 0.87 / p95 0.95)
- v2 pooled aggregate net PF = **1.24** (p5 1.17)
- v2 vs v1 aggregate delta: +36.7% (v2 better)
- v1 high-VIX PF: 0.64 | v2 high-VIX PF: 0.97
- v2 beats v1 on 49 / 57 tickers (§8 gate 4 requires ≥40)
