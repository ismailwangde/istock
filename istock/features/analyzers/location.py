"""
analyzers.location - Support/resistance distance + Fibonacci/Bollinger position

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
from istock.decision.types import TradeConfig


# ══════════════════════════════════════════════════════════════
# LOCATION ANALYZER (Support / Resistance Position)
# ══════════════════════════════════════════════════════════════

class LocationAnalyzer:
    """Determines if current price is at a good location for entry"""

    def __init__(self, data: DataEngine, supports: List[PriceLevel],
                 resistances: List[PriceLevel]):
        self.data = data
        self.price = data.current_price
        self.supports = supports
        self.resistances = resistances
        self.df = data.daily

    def analyze(self) -> SectionResult:
        checks = []
        cfg = TradeConfig

        nearest_support = self.supports[0].price if self.supports else None
        nearest_resistance = self.resistances[0].price if self.resistances else None

        # --- Distance from Support ---
        if nearest_support:
            dist_support = (self.price - nearest_support) / self.price * 100
            near_support = dist_support < cfg.NEAR_SUPPORT_PCT
            checks.append(CheckItem(
                name=f"Near support (within {cfg.NEAR_SUPPORT_PCT}%)",
                passed=near_support,
                detail=f"Support: {nearest_support:.2f} | Distance: {dist_support:.1f}%",
                weight=2.5,
                value=dist_support
            ))

            # Support strength
            if self.supports:
                strong_support = self.supports[0].strength >= 3
                checks.append(CheckItem(
                    name="Support level is strong (tested 3+ times)",
                    passed=strong_support,
                    detail=f"Strength: {self.supports[0].strength}/5 | Sources: {self.supports[0].source}",
                    weight=1.5
                ))

        # --- Distance from Resistance ---
        if nearest_resistance:
            dist_resistance = (nearest_resistance - self.price) / self.price * 100
            far_from_resistance = dist_resistance > cfg.NEAR_RESISTANCE_PCT
            checks.append(CheckItem(
                name=f"Away from resistance (>{cfg.NEAR_RESISTANCE_PCT}%)",
                passed=far_from_resistance,
                detail=f"Resistance: {nearest_resistance:.2f} | Distance: {dist_resistance:.1f}%",
                weight=2.0,
                value=dist_resistance
            ))

        # --- Not in Dead Zone ---
        if nearest_support and nearest_resistance:
            sr_range = nearest_resistance - nearest_support
            if sr_range > 0:
                position_in_range = (self.price - nearest_support) / sr_range * 100
                dead_zone_low = (100 - cfg.DEAD_ZONE_PCT) / 2
                dead_zone_high = 100 - dead_zone_low
                not_in_dead_zone = position_in_range < dead_zone_low or position_in_range > dead_zone_high
                checks.append(CheckItem(
                    name="Not in dead zone (middle of S/R range)",
                    passed=not_in_dead_zone,
                    detail=f"Position: {position_in_range:.0f}% from support to resistance",
                    weight=2.0,
                    value=position_in_range
                ))
            else:
                checks.append(CheckItem(
                    name="Not in dead zone",
                    passed=True,
                    detail="S/R range too narrow, N/A",
                    weight=0.5
                ))

        # --- Bollinger Band Position ---
        if 'BB_Lower' in self.df.columns:
            bb_lower = float(self.df['BB_Lower'].iloc[-1])
            bb_upper = float(self.df['BB_Upper'].iloc[-1])
            bb_mid = float(self.df['BB_Mid'].iloc[-1])

            near_bb_lower = self.price < bb_mid and (self.price - bb_lower) / self.price * 100 < 2
            checks.append(CheckItem(
                name="Near lower Bollinger Band (oversold zone)",
                passed=near_bb_lower,
                detail=f"BB Lower: {bb_lower:.2f} | Price: {self.price:.2f} | BB Upper: {bb_upper:.2f}",
                weight=1.5
            ))

        # --- Near breakout level ---
        if nearest_resistance:
            dist_to_breakout = (nearest_resistance - self.price) / self.price * 100
            near_breakout = dist_to_breakout < 2.0 and dist_to_breakout > 0
            checks.append(CheckItem(
                name="Near breakout level (within 2% of resistance)",
                passed=near_breakout,
                detail=f"Breakout level: {nearest_resistance:.2f} | {dist_to_breakout:.1f}% away",
                weight=1.5
            ))

        # --- Above key MA (price location relative to MA200) ---
        ma200 = self.df['MA200'].iloc[-1] if 'MA200' in self.df.columns else None
        if ma200 and pd.notna(ma200):
            above_200 = self.price > float(ma200)
            dist_200 = (self.price - float(ma200)) / self.price * 100
            checks.append(CheckItem(
                name="Price above MA200 (bullish territory)",
                passed=above_200,
                detail=f"MA200: {float(ma200):.2f} | Distance: {dist_200:+.1f}%",
                weight=2.0
            ))

        score = self._calc_score(checks)
        summary = "EXCELLENT ENTRY ZONE" if score > 75 else \
                  "GOOD LOCATION" if score > 55 else \
                  "NEUTRAL ZONE" if score > 40 else \
                  "POOR LOCATION (near resistance)" if score > 20 else \
                  "DANGER ZONE"

        return SectionResult(name="Location Analysis", score=score,
                           checks=checks, summary=summary)

    def _calc_score(self, checks):
        total_w = sum(c.weight for c in checks)
        if total_w == 0:
            return 50
        return round(sum(c.weight for c in checks if c.passed) / total_w * 100, 1)
