# Brain v2 — Cross-Fold Comparison (S23a Gate 5)

_This file is the canonical Gate 5 verdict per §8 r2. Single-fold gate evaluations live in each fold dir's `_r2_gate_evaluation.md`; this file reads BOTH folds and answers whether the v2-beats-v1 result replicates._

## Fold definitions

| Fold | Train | Val | Test | Anchor |
|---|---|---|---|---|
| fold1 (S22) | 18m from start | 6m | last 12m | end_of_data |
| fold2 (S23a) | 12m from start | 6m | next 12m (contiguous) | start_of_data |

Fold 2 test (2024-11-08 → 2025-11-07) overlaps fold 1 test (2025-05-09 → 2026-05-07) by ~6 months. The unique-to-fold-2 test data is the 6 months 2024-11 → 2025-05. This is the unavoidable cost of Option A on a 3-year dataset; **Gate 5 is therefore weaker evidence than two fully-disjoint folds would be.** A genuinely-disjoint second fold requires either more historical data or a tighter walk-forward (brain v2.1+).

## Side-by-side: v1 baseline + v2 pooled, both folds

| Metric | fold1 v1 | fold1 v2 | fold2 v1 | fold2 v2 |
|---|---:|---:|---:|---:|
| Aggregate net PF | 0.99 | **1.32** | 0.91 | **1.24** |
| Bootstrap p5 | 0.95 | 1.24 | 0.87 | 1.17 |
| Bootstrap p95 | 1.03 | 1.40 | 0.95 | 1.32 |
| Net WR | 49.8% | 57.2% | 48.6% | 56.8% |
| VIX low PF | 0.97 | 1.35 | 0.90 | 1.28 |
| VIX mid PF | 1.05 | 1.33 | 0.94 | 1.22 |
| VIX high PF | 0.70 | 0.96 | 0.64 | 0.97 |
| v2-beats-v1 tally | — | 45 / 57 | — | 49 / 57 |

## Gate outcomes, fold-by-fold

| Gate | Rule | fold1 | fold2 |
|---|---|:---:|:---:|
| 1 | Aggregate ≥ 1.20× v1 baseline | ✅ (1.32 vs 1.19) | ✅ (1.24 vs 1.09) |
| 2 | Bootstrap p5 ≥ 1.10× v1 p5 | ✅ (1.24 vs 1.04) | ✅ (1.17 vs 0.96) |
| 3 | Per-ticker tally ≥ 40/57 | ✅ (45/57) | ✅ (49/57) |
| 4 | v2 beats v1 in every VIX stratum | ✅ | ✅ |

## Gate 5 verdict (cross-fold replication, r3 split)

Per `docs/brain_v2_architecture.md` r3 (S23a-cleanup), Gate 5 has been **split** into two:

- **Gate 5a (aggregate)** — gates 1-4 replicate on both folds: **✅ PASS.** Pooled v2 is cleared to ship behind a feature flag (S23b).
- **Gate 5b (per-ticker)** — confident-ticker intersection ≥ 50% of fold-1 confident set: **❌ FAIL** (1/4 = 25%). Per-ticker layer archived to `_archive/per_ticker_attempt/`; deferred to brain v2.1.

## Confident per-ticker overlap

- **fold1 confident:** ['AMD', 'CAT', 'MU', 'WDC'] (N=4)
- **fold2 confident:** ['MU', 'PCRHY'] (N=2)
- **Overlap (both folds):** ['MU']
- **Only fold1:** ['AMD', 'CAT', 'WDC']
- **Only fold2:** ['PCRHY']

> ⚠️ **Per-ticker confidence is NOT replicating across folds.** Most tickers that were 'confident' in fold1 dropped to pooled in fold2. Two possible explanations: (a) the per-ticker fits are fold-specific noise (the gate is too forgiving for the per-ticker data sample sizes), or (b) the per-ticker edge is real but unstable across regimes. Either way, **shipping per-ticker `<TICKER>.json` files based on a single fold's confidence is unsafe**. Recommendation: under the current r2 gates, ship POOLED ONLY and treat the fold1 confident-4 (AMD/CAT/MU/WDC) and fold2 confident-N as advisory diagnostics, not deployed weights. Brain v2.1 should require per-ticker confidence to replicate across BOTH folds before a `<TICKER>.json` is written.

## Aggregate delta — v2 vs v1, both folds

| Fold | v1 PF | v2 PF | Δ% | v1 high-VIX | v2 high-VIX | high-VIX Δ% |
|---|---:|---:|---:|---:|---:|---:|
| fold1 | 0.99 | 1.32 | +33.3% | 0.70 | 0.96 | +37.7% |
| fold2 | 0.91 | 1.24 | +36.5% | 0.64 | 0.97 | +51.7% |

## Final ship decision (post-S23a-cleanup, r3)

| Artifact | Ship plan |
|---|---|
| `_pooled.json` (fold 1) | **Active** — wired into live system in S23b behind a default-off feature flag. The only weight file `find_weight_for_ticker` returns. |
| `<TICKER>.json` (fold 1: AMD/CAT/MU/WDC) | **Archived** → `results/brain_v2_weights/_archive/per_ticker_attempt/fold1/`. Not loaded. |
| `<TICKER>.json` (fold 2: MU/PCRHY) | **Archived** → `results/brain_v2_weights/_archive/per_ticker_attempt/fold2/`. Not loaded. |
| Brain v1 | **Stays in repo.** Gate 5a clears it for archival in principle, but architect approval is required before any v1 deletion; defer until pooled has accumulated live evidence or until brain v2.1 ships. |

v2.1 entry criteria for restoring the per-ticker layer (Gate 5b):
- A ticker's per-ticker fit must pass the absolute §5/§7 gates on **both** walk-forward folds before its `<TICKER>.json` is written, OR
- The trainer switches to hierarchical regression with a pooled prior so per-ticker coefficients borrow strength from pooled (in which case the per-ticker layer becomes a refinement, not an independent model, and Gate 5b's intersection criterion is replaced).
