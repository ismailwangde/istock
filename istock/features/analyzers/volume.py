"""
analyzers.volume - Volume confirmation: OBV, accumulation, spike detection

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
# VOLUME ANALYZER
# ══════════════════════════════════════════════════════════════

class VolumeAnalyzer:
    """Analyzes volume patterns for confirmation"""

    def __init__(self, data: DataEngine):
        self.df = data.daily
        self.price = data.current_price

    def analyze(self) -> SectionResult:
        checks = []

        # Current volume vs average
        vol_ratio = self._get('Vol_Ratio')
        if vol_ratio:
            above_avg = vol_ratio > 1.0
            checks.append(CheckItem(
                name="Volume above average",
                passed=above_avg,
                detail=f"Volume ratio: {vol_ratio:.2f}x ({vol_ratio*100:.0f}% of average)",
                weight=2.0,
                value=vol_ratio
            ))

            spike = vol_ratio > TradeConfig.VOLUME_SPIKE_MULT
            checks.append(CheckItem(
                name=f"Volume spike (>{TradeConfig.VOLUME_SPIKE_MULT}x)",
                passed=spike,
                detail=f"{'SPIKE DETECTED' if spike else 'Normal volume'}",
                weight=1.0
            ))

        # Volume trend (increasing over 3 candles)
        if 'Volume' in self.df.columns and len(self.df) >= 4:
            vol_3 = self.df['Volume'].tail(3).values
            vol_increasing = all(vol_3[i] >= vol_3[i-1] for i in range(1, len(vol_3)))
            checks.append(CheckItem(
                name="Volume increasing over last 3 candles",
                passed=vol_increasing,
                detail=f"Last 3: {[f'{v/1e6:.1f}M' for v in vol_3]}",
                weight=1.5
            ))

        # OBV trend (confirming price direction)
        if 'OBV' in self.df.columns and 'OBV_MA' in self.df.columns:
            obv = float(self.df['OBV'].iloc[-1])
            obv_ma = float(self.df['OBV_MA'].iloc[-1])
            obv_bullish = obv > obv_ma
            checks.append(CheckItem(
                name="OBV above its MA (money flowing in)",
                passed=obv_bullish,
                detail=f"OBV: {obv/1e6:.1f}M | OBV MA: {obv_ma/1e6:.1f}M",
                weight=2.0
            ))

        # Volume on up days vs down days (last 10)
        if 'Is_Green' in self.df.columns and len(self.df) >= 10:
            last_10 = self.df.tail(10)
            up_vol = last_10[last_10['Is_Green']]['Volume'].mean()
            down_vol = last_10[~last_10['Is_Green']]['Volume'].mean()
            if pd.notna(up_vol) and pd.notna(down_vol) and down_vol > 0:
                up_stronger = up_vol > down_vol
                checks.append(CheckItem(
                    name="More volume on up days than down days",
                    passed=up_stronger,
                    detail=f"Up vol avg: {up_vol/1e6:.1f}M | Down vol avg: {down_vol/1e6:.1f}M",
                    weight=1.5
                ))

        # Dry up in volume (could precede breakout)
        if 'BB_Width' in self.df.columns:
            bb_width = float(self.df['BB_Width'].iloc[-1])
            bb_width_avg = float(self.df['BB_Width'].tail(50).mean())
            squeeze = bb_width < bb_width_avg * 0.7
            checks.append(CheckItem(
                name="Bollinger squeeze (low volatility → breakout likely)",
                passed=squeeze,
                detail=f"BB Width: {bb_width:.2f} vs Avg: {bb_width_avg:.2f}",
                weight=1.0
            ))

        score = self._calc_score(checks)
        summary = "STRONG VOLUME CONFIRMATION" if score > 75 else \
                  "GOOD VOLUME" if score > 55 else \
                  "NEUTRAL VOLUME" if score > 35 else "WEAK VOLUME"

        return SectionResult(name="Volume Analysis", score=score,
                           checks=checks, summary=summary)

    def _get(self, name):
        if name in self.df.columns:
            val = self.df[name].iloc[-1]
            return float(val) if pd.notna(val) else None
        return None

    def _calc_score(self, checks):
        total_w = sum(c.weight for c in checks)
        if total_w == 0: return 50
        return round(sum(c.weight for c in checks if c.passed) / total_w * 100, 1)
