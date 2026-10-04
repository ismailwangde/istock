# Brain v2 — Training Diagnostics

_Fold: **fold2_train_2023-05-11-2024-05-09_val_2024-05-10-2024-11-07_test_2024-11-08-2025-11-07** — fit at 2026-05-18T21:04:39._

All PF / WR / avg_pnl values below are **net of the 0.20% round-trip cost** (§5b).

## Roster outcome

| State | Count |
|---|---:|
| Per-ticker confident | 2 |
| Pooled fallback | 55 |
| Disabled (no recommendation) | 0 |
| **Total** | **57** |

## Pooled model

| Metric | Value |
|---|---:|
| C (L2 strength) | 0.10 |
| n_train / val / test | 8242 / 4463 / 7181 |
| Train PF (net) | 1.38 |
| Val PF (net) | 1.40 |
| Test PF (net) | 1.24 |
| Test PF bootstrap 5th / 95th | 1.17 / 1.32 |
| VIX-stratified test PF (low/mid/high) | 1.28 / 1.22 / 0.97 |

## Top 5 per-ticker confident models (by test PF net)

| Ticker | n_test | Train PF | Test PF | Test PF p5 | C |
|---|---:|---:|---:|---:|---:|
| PCRHY | 2 | 1.01 | inf | inf | 1.00 |
| MU | 82 | 2.90 | 2.38 | 1.44 | 1.00 |

## Full per-ticker outcome

| Ticker | Status | n_train | n_test | Train PF | Test PF | Test PF p5 | Max \|coef\| | Reason |
|---|---|---:|---:|---:|---:|---:|---:|---|
| AAPL | pooled | 155 | 149 | 2.25 | 1.49 | 0.88 | 0.72 | pf_bootstrap_fail |
| ABBV | pooled | 127 | 159 | 3.15 | 1.05 | 0.72 | 3.33 | pf_raw_fail |
| ABT | pooled | 139 | 187 | 1.82 | 0.70 | 0.44 | 0.42 | pf_raw_fail |
| ACN | pooled | 167 | 76 | 2.39 | 0.75 | 0.42 | 2.00 | pf_raw_fail |
| ADBE | pooled | 165 | 33 | 2.75 | 0.56 | 0.13 | 0.38 | pf_raw_fail |
| AMD | pooled | 148 | 91 | 1.53 | 1.22 | 0.75 | 0.41 | pf_raw_fail |
| AMZN | pooled | 224 | 184 | 2.36 | 0.87 | 0.61 | 2.39 | pf_raw_fail |
| AVGO | pooled | 195 | 150 | 3.53 | 1.78 | 1.20 | 0.85 | train_test_stability_fail |
| BAC | pooled | 138 | 156 | 2.49 | 1.00 | 0.70 | 3.24 | pf_raw_fail |
| BE | pooled | 54 | 103 | 5.92 | 1.26 | 0.68 | 1.07 | pf_raw_fail |
| BRK-B | pooled | 211 | 170 | 4.60 | 0.87 | 0.62 | 2.81 | pf_raw_fail |
| CAT | pooled | 171 | 131 | 2.60 | 1.81 | 1.11 | 0.34 | pf_bootstrap_fail |
| COST | pooled | 201 | 140 | 3.47 | 0.51 | 0.33 | 0.41 | pf_raw_fail |
| CRM | pooled | 171 | 101 | 2.54 | 0.85 | 0.47 | 1.73 | pf_raw_fail |
| CSCO | pooled | 134 | 189 | 2.14 | 1.48 | 0.97 | 1.00 | pf_bootstrap_fail |
| CVX | pooled | 116 | 128 | 1.89 | 0.88 | 0.55 | 0.51 | pf_raw_fail |
| DHR | pooled | 143 | 81 | 2.41 | 0.70 | 0.41 | 1.17 | pf_raw_fail |
| FANUY | pooled | 92 | 115 | 2.91 | 0.82 | 0.42 | 0.63 | pf_raw_fail |
| GOOGL | pooled | 209 | 156 | 1.53 | 1.74 | 1.18 | 0.37 | pf_bootstrap_fail |
| GS | pooled | 141 | 187 | 8.03 | 1.36 | 0.92 | 3.64 | pf_raw_fail |
| HD | pooled | 159 | 139 | 3.39 | 0.69 | 0.45 | 2.11 | pf_raw_fail |
| HON | pooled | 122 | 115 | 3.70 | 1.04 | 0.70 | 2.04 | pf_raw_fail |
| IBM | pooled | 169 | 184 | 2.91 | 1.88 | 1.31 | 0.51 | train_test_stability_fail |
| INTC | pooled | 153 | 98 | 1.93 | 2.04 | 1.08 | 0.36 | pf_bootstrap_fail |
| JNJ | pooled | 84 | 133 | 1.62 | 0.91 | 0.61 | 0.33 | pf_raw_fail |
| JPM | pooled | 184 | 193 | 2.87 | 1.60 | 1.06 | 1.19 | pf_bootstrap_fail |
| KO | pooled | 105 | 140 | 2.21 | 1.11 | 0.67 | 1.18 | pf_raw_fail |
| LIN | pooled | 163 | 148 | 1.60 | 0.85 | 0.54 | 2.86 | pf_raw_fail |
| LLY | pooled | 185 | 82 | 2.37 | 1.03 | 0.58 | 2.19 | pf_raw_fail |
| MA | pooled | 195 | 174 | 1.28 | 0.74 | 0.50 | 0.33 | pf_raw_fail |
| MCD | pooled | 116 | 146 | 1.24 | 0.31 | 0.16 | 0.30 | pf_raw_fail |
| META | pooled | 207 | 175 | 1.72 | 1.21 | 0.78 | 0.35 | pf_raw_fail |
| MRK | pooled | 140 | 73 | 2.04 | 0.47 | 0.24 | 0.40 | pf_raw_fail |
| MSFT | pooled | 199 | 140 | 4.14 | 1.28 | 0.83 | 2.41 | pf_raw_fail |
| MU | confident | 197 | 82 | 2.90 | 2.38 | 1.44 | 1.09 | ok |
| NEE | pooled | 71 | 112 | 3.63 | 1.07 | 0.65 | 3.86 | pf_raw_fail |
| NFLX | pooled | 181 | 163 | 3.00 | 0.99 | 0.70 | 1.25 | pf_raw_fail |
| NOW | pooled | 160 | 113 | 1.59 | 0.80 | 0.52 | 0.33 | pf_raw_fail |
| NVDA | pooled | 181 | 155 | 1.77 | 0.90 | 0.63 | 2.31 | pf_raw_fail |
| ORCL | pooled | 161 | 133 | 1.41 | 1.31 | 0.86 | 1.56 | pf_raw_fail |
| PCRHY | confident | 155 | 2 | 1.01 | inf | inf | 1.36 | ok |
| PEP | pooled | 111 | 68 | 3.35 | 0.95 | 0.44 | 1.58 | pf_raw_fail |
| PG | pooled | 168 | 79 | 2.30 | 1.15 | 0.69 | 4.90 | pf_raw_fail |
| PM | pooled | 99 | 148 | 3.35 | 0.95 | 0.64 | 0.71 | pf_raw_fail |
| QCOM | pooled | 162 | 124 | 3.25 | 2.04 | 1.29 | 0.57 | train_test_stability_fail |
| SNDK | pooled | 90 | 0 | — | — | — | — | low_n |
| STX | pooled | 177 | 94 | 2.17 | 1.37 | 0.89 | 0.40 | pf_raw_fail |
| TMO | pooled | 137 | 89 | 2.37 | 0.79 | 0.44 | 1.66 | pf_raw_fail |
| TSLA | pooled | 113 | 132 | 2.01 | 1.06 | 0.64 | 2.12 | pf_raw_fail |
| TXN | pooled | 130 | 70 | 1.96 | 0.57 | 0.31 | 3.49 | pf_raw_fail |
| UNH | pooled | 114 | 67 | 2.78 | 1.89 | 0.96 | 3.51 | pf_bootstrap_fail |
| UPS | pooled | 72 | 59 | 8.27 | 1.31 | 0.54 | 2.85 | pf_raw_fail |
| V | pooled | 210 | 160 | 3.44 | 0.64 | 0.43 | 2.09 | pf_raw_fail |
| WDC | pooled | 196 | 92 | 2.03 | 1.27 | 0.76 | 0.58 | pf_raw_fail |
| WFC | pooled | 153 | 171 | 1.33 | 1.20 | 0.86 | 0.34 | pf_raw_fail |
| WMT | pooled | 213 | 185 | 3.03 | 1.31 | 0.95 | 1.50 | pf_raw_fail |
| XOM | pooled | 97 | 111 | 3.54 | 0.84 | 0.55 | 0.56 | pf_raw_fail |

## System-wide correlation flags (|r| ≥ 0.7 across ≥ 5 tickers)

| Pair A | Pair B | Median r | N tickers |
|---|---|---:|---:|
| Price near support | Setup detected: BOUNCE | 0.970 | 56 |
| Price near support | Setup detected: PULLBACK | -0.950 | 56 |
| Setup detected: BOUNCE | Setup detected: PULLBACK | -0.920 | 55 |
