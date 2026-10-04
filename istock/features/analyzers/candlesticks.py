"""
analyzers.candlesticks - Candlestick pattern detection (hammer, engulfing, doji, etc.)

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
# CANDLESTICK PATTERN ANALYZER
# ══════════════════════════════════════════════════════════════

class CandlestickAnalyzer:
    """Detects candlestick patterns"""

    def __init__(self, data: DataEngine):
        self.df = data.daily

    def analyze(self) -> SectionResult:
        checks = []

        if len(self.df) < 5:
            return SectionResult(name="Candlestick Patterns", score=50,
                               checks=[], summary="Insufficient data")

        # Hammer (bullish reversal)
        is_hammer = self._check_hammer()
        checks.append(CheckItem(
            name="Hammer pattern (bullish reversal)",
            passed=is_hammer,
            detail="Long lower wick, small body at top" if is_hammer else "Not detected",
            weight=1.5
        ))

        # Bullish Engulfing
        is_engulfing = self._check_bullish_engulfing()
        checks.append(CheckItem(
            name="Bullish Engulfing pattern",
            passed=is_engulfing,
            detail="Green candle fully engulfs previous red" if is_engulfing else "Not detected",
            weight=2.0
        ))

        # Morning Star (3-candle reversal)
        is_morning_star = self._check_morning_star()
        checks.append(CheckItem(
            name="Morning Star pattern (3-candle reversal)",
            passed=is_morning_star,
            detail="Red → Small → Big Green pattern" if is_morning_star else "Not detected",
            weight=2.0
        ))

        # Three White Soldiers
        is_soldiers = self._check_three_white_soldiers()
        checks.append(CheckItem(
            name="Three White Soldiers (strong bullish)",
            passed=is_soldiers,
            detail="Three consecutive green candles with higher closes" if is_soldiers else "Not detected",
            weight=1.5
        ))

        # NEGATIVE patterns (reduce buy score)
        # Bearish Engulfing
        is_bearish_eng = self._check_bearish_engulfing()
        checks.append(CheckItem(
            name="NO Bearish Engulfing ⚠️",
            passed=not is_bearish_eng,
            detail="BEARISH ENGULFING DETECTED!" if is_bearish_eng else "Clear",
            weight=2.0
        ))

        # Shooting Star / Hanging Man
        is_shooting = self._check_shooting_star()
        checks.append(CheckItem(
            name="NO Shooting Star / Hanging Man ⚠️",
            passed=not is_shooting,
            detail="REJECTION PATTERN DETECTED!" if is_shooting else "Clear",
            weight=1.5
        ))

        # Multiple upper wicks (rejection)
        rejection_wicks = self._check_rejection_wicks()
        checks.append(CheckItem(
            name="NO multiple rejection wicks ⚠️",
            passed=not rejection_wicks,
            detail="Multiple upper wick rejections in last 5 candles!" if rejection_wicks else "Clear",
            weight=1.5
        ))

        # Doji (indecision - not necessarily bad but means wait)
        is_doji = self._check_doji()
        checks.append(CheckItem(
            name="No Doji (indecision candle)",
            passed=not is_doji,
            detail="DOJI: Market indecisive, wait for confirmation" if is_doji else "Clear",
            weight=0.5
        ))

        score = self._calc_score(checks)

        # Count bullish vs bearish patterns
        bullish = sum(1 for c in checks[:4] if c.passed)
        bearish = sum(1 for c in checks[4:] if not c.passed)

        summary = f"BULLISH PATTERNS ({bullish} detected)" if bullish >= 2 else \
                  f"BEARISH WARNING ({bearish} negative patterns)" if bearish >= 2 else \
                  "NEUTRAL (no strong patterns)"

        return SectionResult(name="Candlestick Patterns", score=score,
                           checks=checks, summary=summary)

    def _check_hammer(self) -> bool:
        try:
            c = self.df.iloc[-1]
            return (float(c['Lower_Wick_Pct']) > 60 and
                    float(c['Body_Pct']) < 30 and
                    float(c['Upper_Wick_Pct']) < 15)
        except: return False

    def _check_bullish_engulfing(self) -> bool:
        try:
            curr, prev = self.df.iloc[-1], self.df.iloc[-2]
            return (not prev['Is_Green'] and curr['Is_Green'] and
                    float(curr['Close']) > float(prev['Open']) and
                    float(curr['Open']) < float(prev['Close']))
        except: return False

    def _check_bearish_engulfing(self) -> bool:
        try:
            curr, prev = self.df.iloc[-1], self.df.iloc[-2]
            return (prev['Is_Green'] and not curr['Is_Green'] and
                    float(curr['Close']) < float(prev['Open']) and
                    float(curr['Open']) > float(prev['Close']))
        except: return False

    def _check_morning_star(self) -> bool:
        try:
            c1, c2, c3 = self.df.iloc[-3], self.df.iloc[-2], self.df.iloc[-1]
            return (not c1['Is_Green'] and float(c1['Body_Pct']) > 50 and
                    float(c2['Body_Pct']) < 25 and  # small body
                    c3['Is_Green'] and float(c3['Body_Pct']) > 50 and
                    float(c3['Close']) > (float(c1['Open']) + float(c1['Close'])) / 2)
        except: return False

    def _check_three_white_soldiers(self) -> bool:
        try:
            last_3 = self.df.tail(3)
            all_green = all(last_3['Is_Green'])
            higher_closes = all(last_3['Close'].iloc[i] > last_3['Close'].iloc[i-1]
                              for i in range(1, 3))
            decent_bodies = all(float(last_3['Body_Pct'].iloc[i]) > 40 for i in range(3))
            return all_green and higher_closes and decent_bodies
        except: return False

    def _check_shooting_star(self) -> bool:
        try:
            c = self.df.iloc[-1]
            return (float(c['Upper_Wick_Pct']) > 60 and
                    float(c['Body_Pct']) < 30 and
                    float(c['Lower_Wick_Pct']) < 15)
        except: return False

    def _check_rejection_wicks(self) -> bool:
        """Multiple upper wicks in last 5 candles"""
        try:
            last_5 = self.df.tail(5)
            long_upper_wicks = sum(1 for _, row in last_5.iterrows()
                                 if float(row['Upper_Wick_Pct']) > 40)
            return long_upper_wicks >= TradeConfig.WICK_REJECTION_COUNT
        except: return False

    def _check_doji(self) -> bool:
        try:
            c = self.df.iloc[-1]
            return float(c['Body_Pct']) < 10 and float(c['Range']) > 0
        except: return False

    def _calc_score(self, checks):
        total_w = sum(c.weight for c in checks)
        if total_w == 0: return 50
        return round(sum(c.weight for c in checks if c.passed) / total_w * 100, 1)
