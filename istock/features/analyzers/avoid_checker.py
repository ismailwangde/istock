"""
analyzers.avoid_checker - Red-flag checks that veto an entry (overextension, earnings window, etc.)

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
# AVOID CONDITION CHECKER
# ══════════════════════════════════════════════════════════════

class AvoidChecker:
    """Checks for conditions that should prevent entry"""

    def __init__(self, data: DataEngine):
        self.df = data.daily
        self.price = data.current_price

    def check(self) -> List[str]:
        """Returns list of avoid reasons (empty = all clear)"""
        flags = []
        cfg = TradeConfig

        try:
            # 1. Recent spike (> 5% in 1 day)
            last_change = float(self.df['Day_Change_Pct'].iloc[-1]) if 'Day_Change_Pct' in self.df.columns else 0
            if abs(last_change) > cfg.SPIKE_THRESHOLD_PCT:
                flags.append(f"🚫 SPIKE: Last candle moved {last_change:+.1f}% (>{cfg.SPIKE_THRESHOLD_PCT}%)")

            # 2. Multiple rejection wicks
            if 'Upper_Wick_Pct' in self.df.columns:
                last_5 = self.df.tail(5)
                long_wicks = sum(1 for _, r in last_5.iterrows() if float(r['Upper_Wick_Pct']) > 40)
                if long_wicks >= cfg.WICK_REJECTION_COUNT:
                    flags.append(f"🚫 REJECTION: {long_wicks} rejection wicks in last 5 candles")

            # 3. Choppy market (ADX very low)
            adx = self.df['ADX'].iloc[-1] if 'ADX' in self.df.columns else None
            if adx and pd.notna(adx) and float(adx) < cfg.CHOPPY_ADX_THRESHOLD:
                flags.append(f"⚠️ CHOPPY: ADX = {float(adx):.1f} (no clear trend)")

            # 4. Resistance right above (< 2% upside to resistance)
            # This is checked in location analyzer

            # 5. Extremely overbought
            rsi = self.df['RSI'].iloc[-1] if 'RSI' in self.df.columns else None
            if rsi and pd.notna(rsi) and float(rsi) > 80:
                flags.append(f"🚫 EXTREMELY OVERBOUGHT: RSI = {float(rsi):.1f}")

            # 6. Below ALL major MAs (strong downtrend)
            ma20 = self.df['MA20'].iloc[-1] if 'MA20' in self.df.columns else None
            ma50 = self.df['MA50'].iloc[-1] if 'MA50' in self.df.columns else None
            ma200 = self.df['MA200'].iloc[-1] if 'MA200' in self.df.columns else None

            below_all = True
            for ma in [ma20, ma50, ma200]:
                if ma and pd.notna(ma) and self.price > float(ma):
                    below_all = False
                    break
            if below_all and ma200:
                flags.append("🚫 STRONG DOWNTREND: Price below ALL major MAs")

            # 7. Parabolic move (>15% in 5 days)
            if 'ROC_5' in self.df.columns:
                roc5 = float(self.df['ROC_5'].iloc[-1])
                if roc5 > 15:
                    flags.append(f"🚫 PARABOLIC MOVE: +{roc5:.1f}% in 5 days - chasing risk")

            # 8. Volume declining on price increase (distribution)
            if 'Vol_Ratio' in self.df.columns and 'Is_Green' in self.df.columns:
                last_5 = self.df.tail(5)
                if all(last_5['Is_Green']):
                    vol_declining = all(last_5['Volume'].iloc[i] < last_5['Volume'].iloc[i-1]
                                      for i in range(1, len(last_5)))
                    if vol_declining:
                        flags.append("⚠️ DISTRIBUTION: Price rising but volume declining")

            # 9. Extreme volatility
            if 'ATR_PCT' in self.df.columns:
                atr_pct = float(self.df['ATR_PCT'].iloc[-1])
                atr_avg = float(self.df['ATR_PCT'].tail(50).mean())
                if atr_pct > atr_avg * 2:
                    flags.append(f"⚠️ HIGH VOLATILITY: ATR = {atr_pct:.1f}% (2x normal)")

        except Exception as e:
            pass

        return flags
