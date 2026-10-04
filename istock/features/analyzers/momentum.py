"""
analyzers.momentum - Momentum indicators: RSI, MACD, Stochastic, ROC

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
# MOMENTUM ANALYZER
# ══════════════════════════════════════════════════════════════

class MomentumAnalyzer:
    """RSI, MACD, Stochastic, Rate of Change"""

    def __init__(self, data: DataEngine):
        self.df = data.daily
        self.price = data.current_price

    def analyze(self) -> SectionResult:
        checks = []
        cfg = TradeConfig

        # RSI Analysis
        rsi = self._get('RSI')
        if rsi:
            # RSI in healthy zone
            healthy = cfg.RSI_HEALTHY_LOW <= rsi <= cfg.RSI_HEALTHY_HIGH
            checks.append(CheckItem(
                name=f"RSI in healthy zone ({cfg.RSI_HEALTHY_LOW}-{cfg.RSI_HEALTHY_HIGH})",
                passed=healthy,
                detail=f"RSI: {rsi:.1f}",
                weight=1.5,
                value=rsi
            ))

            # RSI not overbought
            not_ob = rsi < cfg.RSI_OVERBOUGHT
            checks.append(CheckItem(
                name=f"RSI not overbought (<{cfg.RSI_OVERBOUGHT})",
                passed=not_ob,
                detail=f"RSI: {rsi:.1f} {'⚠️ OVERBOUGHT' if not not_ob else '✓'}",
                weight=2.0
            ))

            # RSI above 50 (bullish momentum)
            above_50 = rsi > 50
            checks.append(CheckItem(
                name="RSI > 50 (bullish momentum)",
                passed=above_50,
                detail=f"RSI: {rsi:.1f}",
                weight=1.0
            ))

            # RSI divergence check
            rsi_div = self._check_rsi_divergence()
            if rsi_div:
                checks.append(CheckItem(
                    name="Bullish RSI divergence",
                    passed=rsi_div == 'bullish',
                    detail=f"{'Bullish' if rsi_div == 'bullish' else 'Bearish'} divergence detected",
                    weight=2.0
                ))

        # MACD Analysis
        macd = self._get('MACD')
        macd_signal = self._get('MACD_Signal')
        macd_hist = self._get('MACD_Hist')

        if macd is not None and macd_signal is not None:
            # MACD bullish crossover
            bullish_cross = False
            if len(self.df) >= 2 and 'MACD_Hist' in self.df.columns:
                curr = float(self.df['MACD_Hist'].iloc[-1])
                prev = float(self.df['MACD_Hist'].iloc[-2])
                bullish_cross = curr > 0 and prev <= 0
                bearish_cross = curr < 0 and prev >= 0

            checks.append(CheckItem(
                name="MACD bullish crossover",
                passed=bullish_cross,
                detail=f"MACD: {macd:.3f} | Signal: {macd_signal:.3f} | Hist: {macd_hist:.3f}",
                weight=2.0
            ))

            # MACD above zero
            checks.append(CheckItem(
                name="MACD above zero line",
                passed=macd > 0,
                detail=f"MACD: {macd:.3f}",
                weight=1.0
            ))

            # MACD histogram increasing
            if len(self.df) >= 3 and 'MACD_Hist' in self.df.columns:
                hist_vals = self.df['MACD_Hist'].tail(3).values
                hist_increasing = hist_vals[-1] > hist_vals[-2]
                checks.append(CheckItem(
                    name="MACD histogram increasing",
                    passed=hist_increasing,
                    detail=f"Last 3: {[f'{v:.3f}' for v in hist_vals]}",
                    weight=1.0
                ))

        # Stochastic
        stoch_k = self._get('Stoch_K')
        stoch_d = self._get('Stoch_D')
        if stoch_k and stoch_d:
            stoch_bullish = stoch_k > stoch_d and stoch_k < 80
            checks.append(CheckItem(
                name="Stochastic bullish (%K > %D, not overbought)",
                passed=stoch_bullish,
                detail=f"%K: {stoch_k:.1f} | %D: {stoch_d:.1f}",
                weight=1.0
            ))

        # Price making higher highs (momentum confirmation)
        if 'ROC_20' in self.df.columns:
            roc20 = float(self.df['ROC_20'].iloc[-1])
            positive_roc = roc20 > 0
            checks.append(CheckItem(
                name="Positive 20-day momentum",
                passed=positive_roc,
                detail=f"20-day ROC: {roc20:+.1f}%",
                weight=1.0,
                value=roc20
            ))

        score = self._calc_score(checks)
        summary = "STRONG BULLISH MOMENTUM" if score > 75 else \
                  "BULLISH MOMENTUM" if score > 55 else \
                  "NEUTRAL MOMENTUM" if score > 35 else "BEARISH MOMENTUM"

        return SectionResult(name="Momentum Analysis", score=score,
                           checks=checks, summary=summary)

    def _check_rsi_divergence(self) -> Optional[str]:
        """Check for RSI divergence over last 20 candles"""
        try:
            if 'RSI' not in self.df.columns or len(self.df) < 20:
                return None

            last_20 = self.df.tail(20)
            prices = last_20['Close'].values
            rsi_vals = last_20['RSI'].values

            # Simple check: price making lower low but RSI making higher low
            price_ll = prices[-1] < prices[-10]
            rsi_hl = rsi_vals[-1] > rsi_vals[-10]

            if price_ll and rsi_hl:
                return 'bullish'

            # Price making higher high but RSI making lower high
            price_hh = prices[-1] > prices[-10]
            rsi_lh = rsi_vals[-1] < rsi_vals[-10]

            if price_hh and rsi_lh:
                return 'bearish'

            return None
        except:
            return None

    def _get(self, name):
        if name in self.df.columns:
            val = self.df[name].iloc[-1]
            return float(val) if pd.notna(val) else None
        return None

    def _calc_score(self, checks):
        total_w = sum(c.weight for c in checks)
        if total_w == 0: return 50
        return round(sum(c.weight for c in checks if c.passed) / total_w * 100, 1)
