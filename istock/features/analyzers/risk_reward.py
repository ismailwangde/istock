"""
analyzers.risk_reward - Risk/reward ratio and stop-distance evaluation

Extracted from core/trade_advisor.py (Session 2). Pure code relocation —
identical class body, no logic changes. DataEngine and TradeConfig are
imported from core.trade_advisor (the analyzer-class imports in
trade_advisor.py live at the BOTTOM of that file so these names are
fully defined by the time this module loads — avoids circular refs).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from istock.decision.types import CheckItem, PriceLevel, SectionResult
from istock.decision.types import TradeConfig, TradeSetup


# ══════════════════════════════════════════════════════════════
# RISK / REWARD CALCULATOR
# ══════════════════════════════════════════════════════════════

class RiskRewardCalculator:
    """Calculates entry, stop loss, targets, and R:R ratio"""

    def __init__(self, data: DataEngine, supports: List[PriceLevel],
                 resistances: List[PriceLevel], setup_type: str):
        self.data = data
        self.df = data.daily
        self.price = data.current_price
        self.supports = supports
        self.resistances = resistances
        self.setup_type = setup_type

    def calculate(self) -> Tuple[SectionResult, TradeSetup]:
        checks = []
        cfg = TradeConfig

        # === ENTRY PRICE ===
        entry = self.price  # For now, entry at current price

        # === STOP LOSS (Retrain-1 geometry redesign) ===
        # The old "tightest of 4 candidate stops" produced hair-trigger stops
        # (median 1.23% risk, median 1-day hold) where the 0.60% round-trip
        # cost consumed the edge — honest backtest PF 0.575 (see MODEL.md §15).
        # New rule: volatility-scaled stop (2×ATR), floored at MIN_RISK_PCT so
        # one day of normal noise can't kill the trade.
        MIN_RISK_PCT = 2.5   # stop never tighter than this
        atr = self._get('ATR')
        if atr and atr > 0:
            stop_loss = entry - cfg.ATR_STOP_MULTIPLIER * atr
        else:
            # ATR unavailable → fall back to recent swing low
            recent_low = float(self.df['Low'].tail(10).min())
            stop_loss = recent_low * 0.995

        # Floor: enforce minimum stop distance
        min_stop = entry * (1 - MIN_RISK_PCT / 100)
        stop_loss = min(stop_loss, min_stop)

        # Ensure stop is sane (below entry, not absurdly wide)
        if stop_loss >= entry or stop_loss <= 0:
            stop_loss = entry * (1 - MIN_RISK_PCT / 100)

        risk_pct = (entry - stop_loss) / entry * 100
        risk_amount = entry - stop_loss

        # === TARGETS (minimum 2R; structure only beyond 2R) ===
        # Old design used nearest resistance as T1 — often closer than 1R,
        # capping winners below the cost hurdle. New rule: T1 is at least
        # entry + 2×risk; a resistance level is used only if it lies beyond.
        t1_floor = entry + 2 * risk_amount
        res_beyond = [r.price for r in self.resistances if r.price >= t1_floor]
        t1 = min(res_beyond) if res_beyond else t1_floor

        t2 = entry + 3 * risk_amount
        res_beyond_t2 = [r for r in res_beyond if r > t1]
        if res_beyond_t2:
            t2 = max(t2, min(res_beyond_t2))

        t3 = entry + 4 * risk_amount

        targets = sorted([t1, t2, t3])

        # === RISK:REWARD RATIO ===
        reward = targets[0] - entry  # Use first target
        risk = entry - stop_loss
        rr_ratio = reward / risk if risk > 0 else 0

        # === CHECKLIST ===
        checks.append(CheckItem(
            name="Stop loss defined",
            passed=True,
            detail=f"SL: {stop_loss:.2f} ({risk_pct:.1f}% risk)",
            weight=2.0
        ))

        checks.append(CheckItem(
            name="Targets defined",
            passed=True,
            detail=f"T1: {targets[0]:.2f} | T2: {targets[1]:.2f} | T3: {targets[2]:.2f}",
            weight=1.5
        ))

        rr_good = rr_ratio >= cfg.MIN_RISK_REWARD
        checks.append(CheckItem(
            name=f"Risk:Reward >= {cfg.MIN_RISK_REWARD}",
            passed=rr_good,
            detail=f"R:R = 1:{rr_ratio:.2f} {'✅' if rr_good else '❌ POOR R:R'}",
            weight=3.0,
            value=rr_ratio
        ))

        stop_tight = risk_pct <= cfg.MAX_STOP_DISTANCE_PCT
        checks.append(CheckItem(
            name=f"Stop distance < {cfg.MAX_STOP_DISTANCE_PCT}%",
            passed=stop_tight,
            detail=f"Stop distance: {risk_pct:.1f}% {'✅' if stop_tight else '❌ TOO WIDE'}",
            weight=2.0,
            value=risk_pct
        ))

        # Reward potential
        upside_pct = (targets[0] - entry) / entry * 100
        good_upside = upside_pct > 3
        checks.append(CheckItem(
            name="Upside potential > 3%",
            passed=good_upside,
            detail=f"Potential upside to T1: {upside_pct:.1f}%",
            weight=1.5
        ))

        score = self._calc_score(checks)

        setup = TradeSetup(
            setup_type=self.setup_type,
            confidence=score,
            entry=round(entry, 2),
            stop_loss=round(stop_loss, 2),
            targets=[round(t, 2) for t in targets],
            risk_reward=round(rr_ratio, 2),
            risk_pct=round(risk_pct, 2),
            description=self._get_setup_description()
        )

        summary = f"R:R = 1:{rr_ratio:.1f} | Risk: {risk_pct:.1f}%"

        return SectionResult(name="Risk/Reward", score=score,
                           checks=checks, summary=summary), setup

    def _get_setup_description(self) -> str:
        descs = {
            'pullback': "Buy on pullback to moving average in uptrend",
            'breakout': "Buy on resistance breakout with volume",
            'bounce': "Buy on bounce from strong support",
            'reversal': "Buy on potential reversal from oversold levels",
            'none': "No clear setup - consider waiting"
        }
        return descs.get(self.setup_type, "Custom entry")

    def _get(self, name):
        if name in self.df.columns:
            val = self.df[name].iloc[-1]
            return float(val) if pd.notna(val) else None
        return None

    def _calc_score(self, checks):
        total_w = sum(c.weight for c in checks)
        if total_w == 0: return 50
        return round(sum(c.weight for c in checks if c.passed) / total_w * 100, 1)
