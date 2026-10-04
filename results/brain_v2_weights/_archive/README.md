# Archived per-ticker weight attempt

These files were produced during S22-S23a but failed **Gate 5b** of the
brain v2 architecture (per-ticker replication).

## Why archived

| Fold | Confident tickers (per absolute §5/§7 gates) |
|---|---|
| fold 1 (S22) | AMD, CAT, MU, WDC |
| fold 2 (S23a) | MU, PCRHY |

Confident-ticker **intersection across folds = {MU} = 25%**, below the
Gate 5b 50% bar. Three of fold 1's four confident tickers (AMD, CAT, WDC)
dropped to pooled fallback on fold 2; fold 2's PCRHY was a noise artifact
(n_picked = 1, bootstrap PF = ∞).

## Status

Kept for v2.1 research. **Not loaded by `find_weight_for_ticker`** —
the resolver returns `_pooled.json` for every ticker as of r3.

## Restoring per-ticker resolution

If brain v2.1 fixes per-ticker non-replication (e.g., hierarchical
regression with pooled prior, or a cross-fold confidence test in the
trainer), un-comment the per-ticker block in
`core/brain_v2/weights.py:find_weight_for_ticker` and move the chosen
weight files back to `results/brain_v2_weights/<TICKER>.json`.

## See also

- `docs/brain_v2_architecture.md` §8 (Gate 5a / 5b) and §11 (Known limitations)
- `results/brain_v2_weights/fold2/_fold_comparison.md` (canonical Gate 5 verdict)
