# Brain v2 — r2 Gate Evaluation (S22c, fold1)

_Evaluated against the v1 baseline measured on this fold's test window._  Source data: `_run_summary.json` (trainer fits) + `_v1_baseline.md` (v1 measurement). §8 r2 gates from `docs/brain_v2_architecture.md`.

## v1 baseline (§8.5, frozen until next fold)

| Metric | Value |
|---|---:|
| Aggregate net PF | **0.99** |
| Bootstrap p5 / p95 | 0.95 / 1.03 |
| Net WR | 49.8% |
| VIX low / mid / high PF | 0.97 / 1.05 / 0.70 |
| v2-beats-v1 ticker tally (S22b) | 45 / 57 |

## v2 pooled (S22 fits, evaluated against r2 §8 gates)

| Metric | Value |
|---|---:|
| C (L2 strength) | 1.00 |
| n_train / val / test | 12705 / 2985 / 7575 |
| Aggregate net PF | **1.32** |
| Bootstrap p5 / p95 | 1.24 / 1.40 |
| Net WR | 57.2% |
| VIX low / mid / high PF | 1.35 / 1.33 / 0.96 |

## r2 gate outcomes (pooled is the canonical brain-wide subject)

| Gate | Rule | Threshold | Measured | Pass? |
|---|---|---:|---:|:---:|
| **1** | Aggregate net PF ≥ 1.2× v1 baseline (0.99) | 1.19 | 1.32 | ✅ |
| **2** | Bootstrap p5 ≥ 1.1× v1 baseline p5 (0.95) | 1.04 | 1.24 | ✅ |
| **3** | v2 beats v1 on ≥ 40 / 57 tickers | 40 / 57 | 45 / 57 | ✅ |
| **4** | v2 beats v1 in every VIX stratum | every | see below | ✅ |
| **5** | Gates 1-4 replicate on a second walk-forward fold | both folds | 1 of 2 done | ⏳ S23+ |

### Gate 4 detail (VIX strata, both net of costs)

| Stratum | v1 PF | v2 PF | Delta | v2 > v1? |
|---|---:|---:|---:|:---:|
| low | 0.97 | 1.35 | +39.5% | ✅ |
| mid | 1.05 | 1.33 | +26.3% | ✅ |
| high | 0.70 | 0.96 | +37.7% | ✅ |

## Per-ticker `<TICKER>.json` writes (absolute thresholds from §5/§7)

Per-ticker absolute gates (raw test PF ≥ 1.40 AND bootstrap p5 ≥ 1.20) are unchanged by r2 — they decide whether a ticker is safe to ship *its own* model rather than fall back to pooled. The r1 numbers stand:

| Ticker | n_test | Train PF | Test PF | Test PF p5 | C | max\|coef\| | Status |
|---|---:|---:|---:|---:|---:|---:|:---:|
| MU | 140 | 1.64 | **2.10** | 1.46 | 0.10 | 0.44 | ✅ |
| AMD | 126 | 1.63 | **2.05** | 1.30 | 0.10 | 0.64 | ✅ |
| WDC | 135 | 1.79 | **1.89** | 1.22 | 3.00 | 1.80 | ✅ |
| CAT | 200 | 2.09 | **1.84** | 1.23 | 1.00 | 1.54 | ✅ |

**Tally:** 4 tickers get their own per-ticker weight files (MU, AMD, WDC, CAT). The other 53 use pooled at inference time via `find_weight_for_ticker`. 0 disabled.

## Bottom line

**Gates 1-4: ALL PASS on fold1.** Pooled is cleared. Gate 5 status (two-fold replication) is determined by the cross-fold `_fold_comparison.md`, not by this single-fold file.
