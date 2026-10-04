"""Feature extraction for brain v2.

This module is the **single source of truth** for the 36-column feature
vector. The trainer, scorer, and on-disk weight files all import
`FEATURE_NAMES` from here — never hardcode a list anywhere else.

Column order is LOCKED. Adding or reordering columns is a breaking change
that invalidates every saved weight file. If the roster grows in brain v2.1,
append at the end and re-train; do not insert in the middle.

The 36-column layout follows `docs/brain_v2_inventory.md` categories:

- A1-A14 (14)   Validated brain checks read from `trade.indicators.passed_checks`
- B1-B2  (2)    Library-swap checks (Stochastic, ADX) — also read from passed_checks
                in S22; the data_engine swap to TA-Lib happens in S23
- C1     (1)    Breakout (rebuilt detector) — read from passed_checks for now;
                the rebuilt detector lands in S23
- D1-D8  (8)    In-house only checks — read from passed_checks
- E1-E4  (4)    SMC features — read from S21.5-backfilled columns
- F1-F5  (7 columns) Other new features. F1 (VWAP) keeps both backfill
                columns (vwap_above is a bullish-trend signal,
                vwap_band_stretched is an overstretched-risk signal — not
                redundant). F2 (ATR regime) one-hots two of the three
                buckets: atr_regime_low (calm tape) and atr_regime_high
                (fast tape); atr_regime_mid is implicit when both are 0
                (reference category — standard dummy-variable practice).

Capacity: 36 features × 57 tickers = 2,052 weights on 23,265 eligible
trades = 11.3 trades / weight. ~12% below the §5 capacity ceiling of
~12.9; safe given the L2 + pooled-fallback guards.

Net win classification (`extract_target`) applies the cost model before
labelling: a trade is a win iff `pnl_pct - 0.60% > 0` (0.30% brokerage per
side). The bootstrap PF gate in §8 also uses this net pnl.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Sequence

import numpy as np

# --------------------------------------------------------------------------- #
# Cost model (locked at §5b of architecture doc)
# --------------------------------------------------------------------------- #
COST_PER_SIDE_PCT: float = 0.30  # 30 bps each side (user's actual brokerage)
COST_ROUND_TRIP_PCT: float = 2 * COST_PER_SIDE_PCT  # 0.60 — subtracted from pnl_pct


def apply_costs(pnl_pct: float) -> float:
    """Return pnl_pct net of the 0.60% round-trip cost (0.30% per side)."""
    return pnl_pct - COST_ROUND_TRIP_PCT


# --------------------------------------------------------------------------- #
# The 36-column feature roster (LOCKED ORDER)
# --------------------------------------------------------------------------- #
FEATURE_NAMES: List[str] = [
    # ---- Category A: validated brain checks (14) ----
    "Hammer pattern (bullish reversal)",                       # A1
    "Bullish Engulfing pattern",                               # A2
    "Morning Star pattern (3-candle reversal)",                # A3
    "Three White Soldiers (strong bullish)",                   # A4
    "NO Bearish Engulfing ⚠️",                                 # A5  (inverted polarity)
    "NO Shooting Star / Hanging Man ⚠️",                       # A6  (inverted polarity)
    "No Doji (indecision candle)",                             # A7  (inverted polarity)
    "MACD bullish crossover",                                  # A8
    "MACD histogram increasing",                               # A9
    "Volume spike (>2.0x)",                                    # A10
    "OBV above its MA (money flowing in)",                     # A11
    "Bollinger squeeze (low volatility → breakout likely)",    # A12
    "MA20 slope rising",                                       # A13
    "Stock outperforming market (20-day)",                     # A14
    # ---- Category B: library-swap checks (2) ----
    "Stochastic bullish (%K > %D, not overbought)",            # B1
    "ADX > 25 (strong trend)",                                 # B2
    # ---- Category C: rebuilt detector (1) ----
    "Setup detected: BREAKOUT",                                # C1
    # ---- Category D: in-house only (8) ----
    "NO multiple rejection wicks ⚠️",                          # D1  (inverted polarity)
    "Bullish RSI divergence",                                  # D2
    "Setup detected: PULLBACK",                                # D3
    "Setup detected: BOUNCE",                                  # D4
    "Setup detected: REVERSAL",                                # D5
    "Higher Highs + Higher Lows",                              # D6  (SYNTHETIC AND of two checks)
    "Price near support",                                      # D7
    "Support level is strong (tested 3+ times)",               # D8
    # ---- Category E: SMC (4 — from S21.5 backfill) ----
    "smc_order_block_bullish",                                 # E1
    "smc_fvg_bullish",                                         # E2
    "smc_bos_bullish",                                         # E3
    "smc_choch_bullish",                                       # E4
    # ---- Category F: other new (7 columns, 5 logical signals) ----
    "vwap_above",                                              # F1a
    "vwap_band_stretched",                                     # F1b
    "atr_regime_low",                                          # F2a (mid is reference)
    "atr_regime_high",                                         # F2b (mid is reference)
    "sector_relative_strength_20d",                            # F3
    "earnings_within_5d",                                      # F4
    "fib_retracement_near",                                    # F5
]

N_FEATURES: int = 36

assert len(FEATURE_NAMES) == N_FEATURES, (
    f"FEATURE_NAMES must be exactly {N_FEATURES} (got {len(FEATURE_NAMES)}). "
    "See brain_v2_inventory.md / brain_v2_architecture.md §3."
)
assert len(set(FEATURE_NAMES)) == N_FEATURES, "FEATURE_NAMES must be unique"


# --------------------------------------------------------------------------- #
# Synthetic features (AND of multiple passed_checks)
# --------------------------------------------------------------------------- #
_SYNTHETIC_AND_FEATURES: Dict[str, List[str]] = {
    "Higher Highs + Higher Lows": ["Higher Highs forming", "Higher Lows forming"],
}

_FLAT_KEY_FEATURES: frozenset = frozenset([
    "smc_order_block_bullish", "smc_fvg_bullish",
    "smc_bos_bullish", "smc_choch_bullish",
    "vwap_above", "vwap_band_stretched",
    "atr_regime_low", "atr_regime_high",
    "sector_relative_strength_20d",
    "earnings_within_5d", "fib_retracement_near",
])

ELIGIBLE_OUTCOMES: frozenset = frozenset(["hit_t1", "hit_t2", "hit_stop"])


# --------------------------------------------------------------------------- #
# Trade-row -> feature/target extraction
# --------------------------------------------------------------------------- #
def _all_passed_checks(trade: Mapping) -> set:
    out = set()
    ind = trade.get("indicators") or {}
    for sec_data in ind.values():
        if isinstance(sec_data, dict):
            for c in sec_data.get("passed_checks") or []:
                out.add(c)
    return out


def extract_features(trade: Mapping) -> np.ndarray:
    """Read the 36 binary features from a trade row → np.ndarray of shape (36,)."""
    passed = _all_passed_checks(trade)
    vec = np.zeros(N_FEATURES, dtype=np.int8)
    for i, name in enumerate(FEATURE_NAMES):
        if name in _FLAT_KEY_FEATURES:
            vec[i] = int(bool(trade.get(name, 0)))
        elif name in _SYNTHETIC_AND_FEATURES:
            required = _SYNTHETIC_AND_FEATURES[name]
            vec[i] = int(all(r in passed for r in required))
        else:
            vec[i] = int(name in passed)
    return vec


def extract_target(trade: Mapping) -> int:
    """Return 1 if the trade is a NET win (pnl_pct - 0.60% > 0), else 0."""
    if not is_eligible_trade(trade):
        return 0
    pnl = trade.get("pnl_pct")
    if pnl is None:
        return 0
    return int(apply_costs(float(pnl)) > 0.0)


def is_eligible_trade(trade: Mapping) -> bool:
    return trade.get("outcome") in ELIGIBLE_OUTCOMES


def verify_feature_names_against_dataset(trades: Sequence[Mapping]) -> None:
    """Assert every FEATURE_NAME resolves in the dataset. Raises ValueError on mismatch."""
    all_passed: set = set()
    all_top_keys: set = set()
    for t in trades:
        for k in t.keys():
            all_top_keys.add(k)
        all_passed |= _all_passed_checks(t)

    unresolved: List[str] = []
    known_broken = {"Setup detected: BREAKOUT"}  # C1 — broken in brain v1
    warnings_list: List[str] = []

    for name in FEATURE_NAMES:
        if name in _FLAT_KEY_FEATURES:
            if name not in all_top_keys:
                unresolved.append(f"{name!r} (flat-key feature, but no trade has this top-level key — S21.5 backfill missing?)")
            continue
        if name in _SYNTHETIC_AND_FEATURES:
            for req in _SYNTHETIC_AND_FEATURES[name]:
                if req not in all_passed:
                    unresolved.append(f"{name!r} (synthetic AND, but underlying check {req!r} never appears in passed_checks)")
            continue
        if name not in all_passed:
            if name in known_broken:
                warnings_list.append(f"{name!r} (known-broken brain check — C1; column will be all-zero)")
            else:
                unresolved.append(f"{name!r} (not found in any trade's passed_checks)")

    if unresolved:
        details = "\n  - ".join(unresolved)
        raise ValueError(
            "FEATURE_NAMES roster does not match dataset.\n"
            "Unresolved names:\n  - " + details
        )

    if warnings_list:
        import warnings as _w
        for msg in warnings_list:
            _w.warn(msg, RuntimeWarning, stacklevel=2)
