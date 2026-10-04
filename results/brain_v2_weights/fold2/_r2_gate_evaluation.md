# Brain v2 — r2 Gate Evaluation (S23a, fold2)

_Evaluated against the v1 baseline measured on this fold's test window._  Source data: `_run_summary.json` (trainer fits) + `_v1_baseline.md` (v1 measurement). §8 r2 gates from `docs/brain_v2_architecture.md`.

## v1 baseline (§8.5, frozen until next fold)

| Metric | Value |
|---|---:|
| Aggregate net PF | **0.91** |
| Bootstrap p5 / p95 | 0.87 / 0.95 |
| Net WR | 48.6% |
| VIX low / mid / high PF | 0.90 / 0.94 / 0.64 |
| v2-beats-v1 ticker tally (S22b) | 49 / 57 |

## v2 pooled (S22 fits, evaluated against r2 §8 gates)

| Metric | Value |
|---|---:|
| C (L2 strength) | 0.10 |
| n_train / val / test | 8242 / 4463 / 7181 |
| Aggregate net PF | **1.24** |
| Bootstrap p5 / p95 | 1.17 / 1.32 |
| Net WR | 56.8% |
| VIX low / mid / high PF | 1.28 / 1.22 / 0.97 |

## r2 gate outcomes (pooled is the canonical brain-wide subject)

| Gate | Rule | Threshold | Measured | Pass? |
|---|---|---:|---:|:---:|
| **1** | Aggregate net PF ≥ 1.2× v1 baseline (0.91) | 1.09 | 1.24 | ✅ |
| **2** | Bootstrap p5 ≥ 1.1× v1 baseline p5 (0.87) | 0.96 | 1.17 | ✅ |
| **3** | v2 beats v1 on ≥ 40 / 57 tickers | 40 / 57 | 49 / 57 | ✅ |
| **4** | v2 beats v1 in every VIX stratum | every | see below | ✅ |
| **5** | Gates 1-4 replicate on a second walk-forward fold | both folds | 1 of 2 done | ⏳ S23+ |

### Gate 4 detail (VIX strata, both net of costs)

| Stratum | v1 PF | v2 PF | Delta | v2 > v1? |
|---|---:|---:|---:|:---:|
| low | 0.90 | 1.28 | +42.1% | ✅ |
| mid | 0.94 | 1.22 | +29.3% | ✅ |
| high | 0.64 | 0.97 | +51.7% | ✅ |

## Per-ticker `<TICKER>.json` writes (absolute thresholds from §5/§7)

Per-ticker absolute gates (raw test PF ≥ 1.40 AND bootstrap p5 ≥ 1.20) are unchanged by r2 — they decide whether a ticker is safe to ship *its own* model rather than fall back to pooled. The r1 numbers stand:

| Ticker | n_test | Train PF | Test PF | Test PF p5 | C | max\|coef\| | Status |
|---|---:|---:|---:|---:|---:|---:|:---:|
| PCRHY | 2 | 1.01 | **inf** | inf | 1.00 | 1.36 | ✅ |
| MU | 82 | 2.90 | **2.38** | 1.44 | 1.00 | 1.09 | ✅ |

**Tally:** 2 tickers get their own per-ticker weight files (PCRHY, MU). The other 55 use pooled at inference time via `find_weight_for_ticker`. 0 disabled.

## Bottom line

**Gates 1-4: ALL PASS on fold2.** Pooled is cleared. Gate 5 status (two-fold replication) is determined by the cross-fold `_fold_comparison.md`, not by this single-fold file.
