"""
analyzers.sell_signals - Sell-signal scoring (breakdowns, MA cross-down, distribution)

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
# SELL SIGNAL CHECKER
# ══════════════════════════════════════════════════════════════

class SellSignalChecker:
    """Comprehensive sell signal analysis"""

    def __init__(self, data: DataEngine, supports: List[PriceLevel]):
        self.df = data.daily
        self.price = data.current_price
        self.supports = supports

    def analyze(self) -> Tuple[float, List[CheckItem]]:
        """Returns (sell_score 0-100, sell_checks)"""
        checks = []

        # === STRUCTURE BREAKDOWN ===
        # Price below support
        if self.supports:
            below_support = self.price < self.supports[0].price
            checks.append(CheckItem(
                name="Price below support",
                passed=below_support,
                detail=f"Support: {self.supports[0].price:.2f}" if self.supports else "N/A",
                weight=2.5
            ))

        # Lower low formed
        ll = self._check_lower_low()
        checks.append(CheckItem(
            name="Lower low formed",
            passed=ll,
            detail="Structure breakdown - lower low" if ll else "No lower low",
            weight=2.0
        ))

        # Lower high formed
        lh = self._check_lower_high()
        checks.append(CheckItem(
            name="Lower high formed",
            passed=lh,
            detail="Bearish structure - lower high" if lh else "No lower high",
            weight=2.0
        ))

        # === MOMENTUM WEAKNESS ===
        rsi = self._get('RSI')
        if rsi:
            rsi_weak = rsi < 40
            checks.append(CheckItem(
                name="RSI below 40 (weak momentum)",
                passed=rsi_weak,
                detail=f"RSI: {rsi:.1f}",
                weight=1.5
            ))

        # MACD bearish
        macd_hist = self._get('MACD_Hist')
        if macd_hist is not None:
            bearish_macd = macd_hist < 0
            checks.append(CheckItem(
                name="MACD histogram negative",
                passed=bearish_macd,
                detail=f"MACD Hist: {macd_hist:.3f}",
                weight=1.5
            ))

        # Bearish MACD crossover
        if 'MACD_Hist' in self.df.columns and len(self.df) >= 2:
            curr_h = float(self.df['MACD_Hist'].iloc[-1])
            prev_h = float(self.df['MACD_Hist'].iloc[-2])
            bearish_cross = curr_h < 0 and prev_h >= 0
            checks.append(CheckItem(
                name="MACD bearish crossover",
                passed=bearish_cross,
                detail="Just crossed bearish!" if bearish_cross else "No crossover",
                weight=2.0
            ))

        # === PRICE ACTION WEAKNESS ===
        # Failed breakout
        failed_bo = self._check_failed_breakout()
        checks.append(CheckItem(
            name="Failed breakout detected",
            passed=failed_bo,
            detail="Price broke above then fell back" if failed_bo else "No failed breakout",
            weight=2.0
        ))

        # Price below MA20 and MA50
        ma20 = self._get('MA20')
        ma50 = self._get('MA50')
        below_mas = False
        if ma20 and ma50:
            below_mas = self.price < ma20 and self.price < ma50
        checks.append(CheckItem(
            name="Price below MA20 and MA50",
            passed=below_mas,
            detail=f"Price: {self.price:.2f} | MA20: {ma20:.2f} | MA50: {ma50:.2f}" if ma20 and ma50 else "N/A",
            weight=2.0
        ))

        # Death cross (MA50 < MA200)
        ma200 = self._get('MA200')
        death_cross = False
        if ma50 and ma200:
            death_cross = ma50 < ma200
        checks.append(CheckItem(
            name="Death cross (MA50 < MA200)",
            passed=death_cross,
            detail="⚠️ DEATH CROSS - major bearish signal" if death_cross else "No death cross",
            weight=2.5
        ))

        # Volume climax (huge volume + drop)
        vol_climax = self._check_volume_climax()
        checks.append(CheckItem(
            name="Volume climax sell-off",
            passed=vol_climax,
            detail="Huge volume on down move" if vol_climax else "No climax",
            weight=1.5
        ))

        # Calculate sell score (higher = stronger sell signal)
        total_w = sum(c.weight for c in checks)
        passed_w = sum(c.weight for c in checks if c.passed)
        sell_score = round(passed_w / total_w * 100, 1) if total_w > 0 else 0

        return sell_score, checks

    def _check_lower_low(self) -> bool:
        try:
            lows = []
            window = 5
            arr = self.df['Low'].values
            for i in range(window, len(self.df) - window):
                if arr[i] == min(arr[max(0, i-window):i+window+1]):
                    lows.append(arr[i])
            if len(lows) >= 2:
                return lows[-1] < lows[-2]
            return False
        except: return False

    def _check_lower_high(self) -> bool:
        try:
            highs = []
            window = 5
            arr = self.df['High'].values
            for i in range(window, len(self.df) - window):
                if arr[i] == max(arr[max(0, i-window):i+window+1]):
                    highs.append(arr[i])
            if len(highs) >= 2:
                return highs[-1] < highs[-2]
            return False
        except: return False

    def _check_failed_breakout(self) -> bool:
        try:
            if len(self.df) < 5:
                return False
            high_3_ago = float(self.df['High'].iloc[-3])
            high_2_ago = float(self.df['High'].iloc[-2])
            close_now = float(self.df['Close'].iloc[-1])
            # Price went up then dropped back
            return high_2_ago > high_3_ago and close_now < high_3_ago
        except: return False

    def _check_volume_climax(self) -> bool:
        try:
            if 'Vol_Ratio' not in self.df.columns:
                return False
            last = self.df.iloc[-1]
            return (float(last['Vol_Ratio']) > 2.5 and
                    not last['Is_Green'])
        except: return False

    def _get(self, name):
        if name in self.df.columns:
            val = self.df[name].iloc[-1]
            return float(val) if pd.notna(val) else None
        return None
