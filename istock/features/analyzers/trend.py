"""
analyzers.trend - Trend analysis on daily/weekly timeframes (MAs, EMA, ADX, HH/HL)

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
# TREND ANALYZER
# ══════════════════════════════════════════════════════════════

class TrendAnalyzer:
    """Analyzes trend on daily and weekly timeframes"""

    def __init__(self, data: DataEngine):
        self.data = data
        self.df = data.daily
        self.wk = data.weekly
        self.price = data.current_price

    def analyze(self) -> SectionResult:
        checks = []
        cfg = TradeConfig

        # --- MA Position Checks ---
        ma20 = self._get_ma('MA20')
        ma50 = self._get_ma('MA50')
        ma200 = self._get_ma('MA200')

        checks.append(CheckItem(
            name="Price > MA20",
            passed=self.price > ma20 if ma20 else False,
            detail=f"{self.price:.2f} {'>' if self.price > ma20 else '<'} {ma20:.2f}" if ma20 else "N/A",
            weight=1.5
        ))

        checks.append(CheckItem(
            name="Price > MA50",
            passed=self.price > ma50 if ma50 else False,
            detail=f"{self.price:.2f} {'>' if self.price > ma50 else '<'} {ma50:.2f}" if ma50 else "N/A",
            weight=1.5
        ))

        checks.append(CheckItem(
            name="Price > MA200",
            passed=self.price > ma200 if ma200 else False,
            detail=f"{self.price:.2f} {'>' if self.price > ma200 else '<'} {ma200:.2f}" if ma200 else "N/A",
            weight=2.0
        ))

        # --- MA Alignment ---
        if ma20 and ma50:
            checks.append(CheckItem(
                name="MA20 > MA50 (short-term bullish)",
                passed=ma20 > ma50,
                detail=f"{ma20:.2f} {'>' if ma20 > ma50 else '<'} {ma50:.2f}",
                weight=1.5
            ))

        if ma50 and ma200:
            golden = ma50 > ma200
            checks.append(CheckItem(
                name="MA50 > MA200 (Golden Cross zone)",
                passed=golden,
                detail=f"{ma50:.2f} {'>' if golden else '<'} {ma200:.2f}",
                weight=2.0
            ))

        # --- EMA Trend ---
        ema9 = self._get_val('EMA9')
        ema21 = self._get_val('EMA21')
        if ema9 and ema21:
            checks.append(CheckItem(
                name="EMA9 > EMA21 (short-term momentum)",
                passed=ema9 > ema21,
                detail=f"{ema9:.2f} {'>' if ema9 > ema21 else '<'} {ema21:.2f}",
                weight=1.0
            ))

        # --- Higher Highs / Higher Lows ---
        hh, hl = self._check_higher_highs_lows()
        checks.append(CheckItem(
            name="Higher Highs forming",
            passed=hh,
            detail="Last 5 swing highs increasing" if hh else "No higher high pattern",
            weight=1.5
        ))
        checks.append(CheckItem(
            name="Higher Lows forming",
            passed=hl,
            detail="Last 5 swing lows increasing" if hl else "No higher low pattern",
            weight=1.5
        ))

        # --- ADX (Trend Strength) ---
        adx = self._get_val('ADX')
        if adx:
            strong = adx > cfg.ADX_STRONG_TREND
            checks.append(CheckItem(
                name=f"ADX > {cfg.ADX_STRONG_TREND} (strong trend)",
                passed=strong,
                detail=f"ADX = {adx:.1f} ({'Strong' if adx > cfg.ADX_VERY_STRONG else 'Moderate' if strong else 'Weak'})",
                weight=1.5,
                value=adx
            ))

        # --- Weekly Trend Confirmation ---
        weekly_bullish = self._check_weekly_trend()
        checks.append(CheckItem(
            name="Weekly trend bullish",
            passed=weekly_bullish,
            detail="Weekly MAs aligned bullish" if weekly_bullish else "Weekly trend not confirmed",
            weight=2.0
        ))

        # --- MA Slope (is MA20 going up?) ---
        ma20_rising = self._check_ma_slope('MA20', 5)
        checks.append(CheckItem(
            name="MA20 slope rising",
            passed=ma20_rising,
            detail="Short-term MA trending up" if ma20_rising else "Short-term MA flat/declining",
            weight=1.0
        ))

        # Calculate section score
        score = self._calc_section_score(checks)

        # Determine trend label
        bullish_count = sum(1 for c in checks if c.passed)
        total = len(checks)
        if bullish_count >= total * 0.8:
            summary = "STRONG UPTREND"
        elif bullish_count >= total * 0.6:
            summary = "UPTREND"
        elif bullish_count >= total * 0.4:
            summary = "NEUTRAL / SIDEWAYS"
        elif bullish_count >= total * 0.2:
            summary = "DOWNTREND"
        else:
            summary = "STRONG DOWNTREND"

        return SectionResult(
            name="Trend Analysis",
            score=score,
            checks=checks,
            summary=summary
        )

    def _get_ma(self, name: str) -> Optional[float]:
        if name in self.df.columns:
            val = self.df[name].iloc[-1]
            return float(val) if pd.notna(val) else None
        return None

    def _get_val(self, name: str) -> Optional[float]:
        if name in self.df.columns:
            val = self.df[name].iloc[-1]
            return float(val) if pd.notna(val) else None
        return None

    def _check_higher_highs_lows(self) -> Tuple[bool, bool]:
        """Check if last N swing highs/lows are increasing"""
        try:
            window = 5
            n_points = TradeConfig.HIGHER_HIGH_LOOKBACK

            highs = []
            lows = []
            arr_high = self.df['High'].values
            arr_low = self.df['Low'].values

            for i in range(window, len(self.df) - window):
                if arr_high[i] == max(arr_high[max(0, i-window):i+window+1]):
                    highs.append(arr_high[i])
                if arr_low[i] == min(arr_low[max(0, i-window):i+window+1]):
                    lows.append(arr_low[i])

            # Check last N points
            recent_highs = highs[-n_points:] if len(highs) >= n_points else highs
            recent_lows = lows[-n_points:] if len(lows) >= n_points else lows

            hh = all(recent_highs[i] >= recent_highs[i-1]
                     for i in range(1, len(recent_highs))) if len(recent_highs) >= 2 else False
            hl = all(recent_lows[i] >= recent_lows[i-1]
                     for i in range(1, len(recent_lows))) if len(recent_lows) >= 2 else False

            return hh, hl
        except:
            return False, False

    def _check_weekly_trend(self) -> bool:
        """Check if weekly timeframe is bullish"""
        try:
            if self.wk.empty or len(self.wk) < 20:
                return False
            wk_ma20 = self.wk['MA20'].iloc[-1] if 'MA20' in self.wk.columns else None
            wk_close = self.wk['Close'].iloc[-1]
            return wk_close > wk_ma20 if wk_ma20 and pd.notna(wk_ma20) else False
        except:
            return False

    def _check_ma_slope(self, ma_name: str, periods: int) -> bool:
        """Check if MA is rising over last N periods"""
        try:
            if ma_name not in self.df.columns:
                return False
            ma_vals = self.df[ma_name].dropna().tail(periods)
            if len(ma_vals) < 2:
                return False
            return float(ma_vals.iloc[-1]) > float(ma_vals.iloc[0])
        except:
            return False

    def _calc_section_score(self, checks: List[CheckItem]) -> float:
        total_weight = sum(c.weight for c in checks)
        if total_weight == 0:
            return 50
        passed_weight = sum(c.weight for c in checks if c.passed)
        return round(passed_weight / total_weight * 100, 1)
