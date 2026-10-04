# Brain v2 — Training Diagnostics

_Fold: **train_2023-05-11-2024-11-07_val_2024-11-08-2025-05-08_test_2025-05-09-2026-05-07** — fit at 2026-05-18T20:47:58._

All PF / WR / avg_pnl values below are **net of the 0.20% round-trip cost** (§5b).

## Roster outcome

| State | Count |
|---|---:|
| Per-ticker confident | 4 |
| Pooled fallback | 53 |
| Disabled (no recommendation) | 0 |
| **Total** | **57** |

## Pooled model

| Metric | Value |
|---|---:|
| C (L2 strength) | 1.00 |
| n_train / val / test | 12705 / 2985 / 7575 |
| Train PF (net) | 1.38 |
| Val PF (net) | 1.10 |
| Test PF (net) | 1.32 |
| Test PF bootstrap 5th / 95th | 1.24 / 1.40 |
| VIX-stratified test PF (low/mid/high) | 1.35 / 1.33 / 0.96 |

## Top 5 per-ticker confident models (by test PF net)

| Ticker | n_test | Train PF | Test PF | Test PF p5 | C |
|---|---:|---:|---:|---:|---:|
| MU | 140 | 1.64 | 2.10 | 1.46 | 0.10 |
| AMD | 126 | 1.63 | 2.05 | 1.30 | 0.10 |
| WDC | 135 | 1.79 | 1.89 | 1.22 | 3.00 |
| CAT | 200 | 2.09 | 1.84 | 1.23 | 1.00 |

## Full per-ticker outcome

| Ticker | Status | n_train | n_test | Train PF | Test PF | Test PF p5 | Max \|coef\| | Reason |
|---|---|---:|---:|---:|---:|---:|---:|---|
| AAPL | pooled | 267 | 163 | 2.10 | 0.91 | 0.57 | 1.53 | pf_raw_fail |
| ABBV | pooled | 222 | 134 | 1.98 | 1.28 | 0.86 | 0.87 | pf_raw_fail |
| ABT | pooled | 210 | 97 | 1.90 | 0.56 | 0.27 | 0.64 | pf_raw_fail |
| ACN | pooled | 233 | 61 | 1.85 | 1.66 | 0.78 | 0.59 | pf_bootstrap_fail |
| ADBE | pooled | 206 | 23 | 2.43 | 0.51 | 0.18 | 1.45 | pf_raw_fail |
| AMD | confident | 201 | 126 | 1.63 | 2.05 | 1.30 | 0.64 | ok |
| AMZN | pooled | 322 | 158 | 1.53 | 1.10 | 0.76 | 0.55 | pf_raw_fail |
| AVGO | pooled | 284 | 160 | 1.72 | 1.72 | 1.14 | 0.40 | pf_bootstrap_fail |
| BAC | pooled | 234 | 162 | 2.23 | 1.30 | 0.91 | 2.45 | pf_raw_fail |
| BE | pooled | 83 | 89 | 3.06 | 1.38 | 0.69 | 0.27 | pf_raw_fail |
| BRK-B | pooled | 324 | 118 | 2.95 | 0.42 | 0.26 | 1.68 | pf_raw_fail |
| CAT | confident | 257 | 200 | 2.09 | 1.84 | 1.23 | 1.54 | ok |
| COST | pooled | 302 | 110 | 3.32 | 0.42 | 0.24 | 2.49 | pf_raw_fail |
| CRM | pooled | 236 | 59 | 2.71 | 0.80 | 0.34 | 1.18 | pf_raw_fail |
| CSCO | pooled | 196 | 204 | 1.71 | 1.27 | 0.89 | 1.54 | pf_raw_fail |
| CVX | pooled | 161 | 154 | 1.54 | 1.14 | 0.74 | 3.03 | pf_raw_fail |
| DHR | pooled | 214 | 112 | 1.60 | 0.68 | 0.42 | 0.33 | pf_raw_fail |
| FANUY | pooled | 133 | 155 | — | — | — | — | val_wr_fail |
| GOOGL | pooled | 310 | 183 | 2.10 | 1.51 | 1.03 | 0.72 | pf_bootstrap_fail |
| GS | pooled | 250 | 183 | 2.77 | 1.65 | 1.13 | 0.65 | pf_bootstrap_fail |
| HD | pooled | 245 | 118 | 1.90 | 0.44 | 0.28 | 0.70 | pf_raw_fail |
| HON | pooled | 209 | 136 | 2.52 | 0.89 | 0.61 | 0.47 | pf_raw_fail |
| IBM | pooled | 278 | 138 | 3.33 | 1.60 | 1.09 | 0.73 | pf_bootstrap_fail |
| INTC | pooled | 189 | 131 | — | — | — | — | val_wr_fail |
| JNJ | pooled | 153 | 159 | 1.58 | 0.95 | 0.68 | 0.34 | pf_raw_fail |
| JPM | pooled | 293 | 171 | 2.20 | 1.56 | 1.02 | 0.40 | pf_bootstrap_fail |
| KO | pooled | 215 | 160 | 2.27 | 1.18 | 0.79 | 3.93 | pf_raw_fail |
| LIN | pooled | 249 | 166 | 1.27 | 1.05 | 0.72 | 0.66 | pf_raw_fail |
| LLY | pooled | 265 | 103 | 1.62 | 0.80 | 0.46 | 0.54 | pf_raw_fail |
| MA | pooled | 293 | 105 | 1.55 | 0.99 | 0.65 | 0.80 | pf_raw_fail |
| MCD | pooled | 182 | 132 | 2.93 | 0.48 | 0.30 | 0.71 | pf_raw_fail |
| META | pooled | 310 | 132 | 1.91 | 0.78 | 0.47 | 0.29 | pf_raw_fail |
| MRK | pooled | 188 | 158 | 2.02 | 0.68 | 0.44 | 0.77 | pf_raw_fail |
| MSFT | pooled | 285 | 136 | 2.20 | 1.27 | 0.85 | 2.03 | pf_raw_fail |
| MU | confident | 264 | 140 | 1.64 | 2.10 | 1.46 | 0.44 | ok |
| NEE | pooled | 169 | 172 | 2.29 | 1.07 | 0.75 | 0.31 | pf_raw_fail |
| NFLX | pooled | 274 | 106 | 2.71 | 0.96 | 0.61 | 0.70 | pf_raw_fail |
| NOW | pooled | 262 | 53 | 2.06 | 0.53 | 0.26 | 2.60 | pf_raw_fail |
| NVDA | pooled | 264 | 174 | 1.69 | 1.39 | 0.98 | 0.37 | pf_raw_fail |
| ORCL | pooled | 259 | 98 | 1.77 | 1.63 | 0.99 | 0.52 | pf_bootstrap_fail |
| PCRHY | pooled | 252 | 0 | — | — | — | — | low_n |
| PEP | pooled | 186 | 138 | 1.61 | 0.54 | 0.34 | 1.58 | pf_raw_fail |
| PG | pooled | 276 | 65 | 1.71 | 1.42 | 0.79 | 0.55 | pf_bootstrap_fail |
| PM | pooled | 204 | 123 | 3.25 | 1.12 | 0.73 | 2.00 | pf_raw_fail |
| QCOM | pooled | 213 | 128 | 2.82 | 1.05 | 0.66 | 1.26 | pf_raw_fail |
| SNDK | pooled | 90 | 0 | — | — | — | — | low_n |
| STX | pooled | 281 | 116 | 1.83 | 1.43 | 0.89 | 0.51 | pf_bootstrap_fail |
| TMO | pooled | 211 | 133 | — | — | — | — | val_wr_fail |
| TSLA | pooled | 186 | 142 | 1.93 | 1.06 | 0.66 | 0.47 | pf_raw_fail |
| TXN | pooled | 228 | 118 | 2.14 | 1.27 | 0.72 | 0.28 | pf_raw_fail |
| UNH | pooled | 186 | 67 | 1.68 | 0.98 | 0.51 | 0.35 | pf_raw_fail |
| UPS | pooled | 88 | 115 | 6.44 | 0.64 | 0.31 | 1.81 | pf_raw_fail |
| V | pooled | 273 | 97 | 2.89 | 0.34 | 0.20 | 1.01 | pf_raw_fail |
| WDC | confident | 270 | 135 | 1.79 | 1.89 | 1.22 | 1.80 | ok |
| WFC | pooled | 226 | 165 | 1.76 | 1.18 | 0.82 | 1.41 | pf_raw_fail |
| WMT | pooled | 317 | 213 | 2.61 | 0.94 | 0.69 | 0.48 | pf_raw_fail |
| XOM | pooled | 167 | 164 | 1.77 | 1.23 | 0.84 | 2.50 | pf_raw_fail |

## System-wide correlation flags (|r| ≥ 0.7 across ≥ 5 tickers)

| Pair A | Pair B | Median r | N tickers |
|---|---|---:|---:|
| Price near support | Setup detected: BOUNCE | 0.972 | 52 |
| Price near support | Setup detected: PULLBACK | -0.941 | 52 |
| Setup detected: BOUNCE | Setup detected: PULLBACK | -0.914 | 52 |
