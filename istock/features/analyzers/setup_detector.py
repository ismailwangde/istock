"""
analyzers.setup_detector - Classic setup patterns: pullback, breakout, reversal, bounce

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
# SETUP DETECTOR (Pullback, Breakout, Reversal)
# ══════════════════════════════════════════════════════════════

class SetupDetector:
    """Identifies trading setups: pullback, breakout, bounce, reversal"""

    def __init__(self, data: DataEngine, supports: List[PriceLevel],
                 resistances: List[PriceLevel]):
        self.data = data
        self.df = data.daily
        self.price = data.current_price
        self.supports = supports
        self.resistances = resistances

    def analyze(self) -> Tuple[SectionResult, str]:
        """Returns (SectionResult, detected_setup_type)"""
        checks = []

        # Check each setup type
        pb_score, pb_checks = self._check_pullback()
        bo_score, bo_checks = self._check_breakout()
        bounce_score, bounce_checks = self._check_bounce()
        rev_score, rev_checks = self._check_reversal()

        # Which setup is strongest?
        setups = {
            'pullback': (pb_score, pb_checks),
            'breakout': (bo_score, bo_checks),
            'bounce': (bounce_score, bounce_checks),
            'reversal': (rev_score, rev_checks)
        }

        best_setup = max(setups, key=lambda k: setups[k][0])
        best_score, best_checks = setups[best_setup]

        # Two deliberate thresholds:
        #   < 40  → setup_type = 'none' (no usable trade levels at all)
        #   >= 50 → the "Setup detected: X" feature fires (model-grade confidence)
        # 40-49 = weak setup: levels exist but the brain feature stays 0.
        if best_score < 40:
            best_setup = 'none'

        for check in best_checks:
            checks.append(check)

        # Add setup identification summary
        checks.append(CheckItem(
            name=f"Setup detected: {best_setup.upper()}",
            passed=best_score >= 50,
            detail=f"Confidence: {best_score:.0f}% | "
                   f"PB:{pb_score:.0f} BO:{bo_score:.0f} "
                   f"BNC:{bounce_score:.0f} REV:{rev_score:.0f}",
            weight=2.0,
            value=best_score
        ))

        score = self._calc_score(checks)
        summary = f"{best_setup.upper()} setup ({best_score:.0f}% confidence)" \
                  if best_setup != 'none' else "No clear setup detected"

        return SectionResult(name="Setup Detection", score=score,
                           checks=checks, summary=summary), best_setup

    def _check_pullback(self) -> Tuple[float, List[CheckItem]]:
        """Check for pullback setup in an uptrend"""
        checks = []
        cfg = TradeConfig

        # 1. Is there an uptrend?
        ma20 = self._get('MA20')
        ma50 = self._get('MA50')
        uptrend = False
        if ma20 and ma50:
            uptrend = ma20 > ma50 and self.price > ma50
        checks.append(CheckItem(
            name="Uptrend present (MA20 > MA50, price > MA50)",
            passed=uptrend,
            detail=f"MA20:{ma20:.2f} MA50:{ma50:.2f}" if ma20 and ma50 else "N/A",
            weight=2.0
        ))

        # 2. Price pulled back from recent high
        recent_high = float(self.df['High'].tail(30).max())
        pullback_pct = (recent_high - self.price) / recent_high * 100
        good_pullback = cfg.PULLBACK_MIN_PCT < pullback_pct < cfg.PULLBACK_MAX_PCT
        checks.append(CheckItem(
            name=f"Pullback {cfg.PULLBACK_MIN_PCT}-{cfg.PULLBACK_MAX_PCT}% from high",
            passed=good_pullback,
            detail=f"High: {recent_high:.2f} | Pullback: {pullback_pct:.1f}%",
            weight=2.0,
            value=pullback_pct
        ))

        # 3. Price touched MA20 or MA50
        touched_ma = False
        if ma20:
            dist_ma20 = abs(self.price - ma20) / self.price * 100
            touched_ma = dist_ma20 < cfg.PULLBACK_MA_TOUCH_PCT
        if ma50 and not touched_ma:
            dist_ma50 = abs(self.price - ma50) / self.price * 100
            touched_ma = dist_ma50 < cfg.PULLBACK_MA_TOUCH_PCT
        checks.append(CheckItem(
            name="Touched MA20 or MA50 during pullback",
            passed=touched_ma,
            detail=f"Dist to MA20: {dist_ma20:.1f}%" if ma20 else "N/A",
            weight=1.5
        ))

        # 4. Bullish candle forming after pullback
        last_candle_green = bool(self.df['Is_Green'].iloc[-1]) if 'Is_Green' in self.df.columns else False
        checks.append(CheckItem(
            name="Bullish candle after pullback",
            passed=last_candle_green,
            detail="Last candle is green (bullish)" if last_candle_green else "Last candle is red",
            weight=1.5
        ))

        # 5. Volume declining during pullback (healthy)
        vol_declining = False
        if 'Vol_Ratio' in self.df.columns:
            recent_vol = self.df['Vol_Ratio'].tail(5)
            vol_declining = float(recent_vol.mean()) < 1.0
        checks.append(CheckItem(
            name="Volume declining during pullback (healthy)",
            passed=vol_declining,
            detail=f"Avg vol ratio last 5 days: {float(recent_vol.mean()):.2f}" if 'Vol_Ratio' in self.df.columns else "N/A",
            weight=1.0
        ))

        score = sum(c.weight for c in checks if c.passed) / sum(c.weight for c in checks) * 100
        return score, checks

    def _check_breakout(self) -> Tuple[float, List[CheckItem]]:
        """Check for breakout setup"""
        checks = []
        cfg = TradeConfig

        if not self.resistances:
            return 0, [CheckItem("Breakout check", False, "No resistance levels found", 1.0)]

        nearest_r = self.resistances[0].price

        # 1. Price at or above resistance
        above_r = self.price >= nearest_r
        checks.append(CheckItem(
            name="Price at/above resistance",
            passed=above_r,
            detail=f"Price: {self.price:.2f} | Resistance: {nearest_r:.2f}",
            weight=2.5
        ))

        # 2. Close above resistance (not just wick)
        last_close = float(self.df['Close'].iloc[-1])
        close_above = last_close > nearest_r
        checks.append(CheckItem(
            name="Close above resistance (not just wick)",
            passed=close_above,
            detail=f"Close: {last_close:.2f} vs Resistance: {nearest_r:.2f}",
            weight=2.0
        ))

        # 3. Previous candle also held above (confirmation)
        if len(self.df) >= 2:
            prev_close = float(self.df['Close'].iloc[-2])
            held_above = close_above and prev_close > nearest_r * 0.995
            checks.append(CheckItem(
                name="Previous candle held near/above level",
                passed=held_above,
                detail=f"Prev close: {prev_close:.2f}",
                weight=1.5
            ))

        # 4. Volume spike on breakout
        vol_spike = False
        if 'Vol_Ratio' in self.df.columns:
            vol_spike = float(self.df['Vol_Ratio'].iloc[-1]) > cfg.BREAKOUT_VOLUME_MULT
        checks.append(CheckItem(
            name=f"Volume spike (>{cfg.BREAKOUT_VOLUME_MULT}x average)",
            passed=vol_spike,
            detail=f"Vol ratio: {float(self.df['Vol_Ratio'].iloc[-1]):.2f}x" if 'Vol_Ratio' in self.df.columns else "N/A",
            weight=2.0
        ))

        # 5. No excessive upper wick (rejection sign)
        no_rejection = True
        if 'Upper_Wick_Pct' in self.df.columns:
            wick_pct = float(self.df['Upper_Wick_Pct'].iloc[-1])
            no_rejection = wick_pct < cfg.MAX_UPPER_WICK_PCT
            checks.append(CheckItem(
                name=f"No rejection wick (<{cfg.MAX_UPPER_WICK_PCT}% upper wick)",
                passed=no_rejection,
                detail=f"Upper wick: {wick_pct:.0f}% of candle range",
                weight=1.5
            ))

        score = sum(c.weight for c in checks if c.passed) / sum(c.weight for c in checks) * 100
        return score, checks

    def _check_bounce(self) -> Tuple[float, List[CheckItem]]:
        """Check for bounce off support"""
        checks = []

        if not self.supports:
            return 0, [CheckItem("Bounce check", False, "No support levels found", 1.0)]

        nearest_s = self.supports[0].price

        # Price near support
        dist = (self.price - nearest_s) / self.price * 100
        near = dist < 3.0
        checks.append(CheckItem(
            name="Price near support",
            passed=near,
            detail=f"Support: {nearest_s:.2f} | Distance: {dist:.1f}%",
            weight=2.0
        ))

        # Bullish candle at support
        green = bool(self.df['Is_Green'].iloc[-1]) if 'Is_Green' in self.df.columns else False
        checks.append(CheckItem("Bullish candle at support", green, "", weight=1.5))

        # Long lower wick (buying pressure)
        long_lower = False
        if 'Lower_Wick_Pct' in self.df.columns:
            long_lower = float(self.df['Lower_Wick_Pct'].iloc[-1]) > 40
        checks.append(CheckItem("Long lower wick (buying pressure)", long_lower, "", weight=1.5))

        # RSI not overbought
        rsi = self._get('RSI')
        rsi_ok = rsi and rsi < 60
        checks.append(CheckItem("RSI < 60 (room to move up)", rsi_ok,
                               f"RSI: {rsi:.1f}" if rsi else "N/A", weight=1.0))

        score = sum(c.weight for c in checks if c.passed) / sum(c.weight for c in checks) * 100
        return score, checks

    def _check_reversal(self) -> Tuple[float, List[CheckItem]]:
        """Check for reversal (bottom) setup"""
        checks = []

        # Oversold RSI
        rsi = self._get('RSI')
        oversold = rsi and rsi < 35
        checks.append(CheckItem("RSI oversold (<35)", oversold,
                               f"RSI: {rsi:.1f}" if rsi else "N/A", weight=2.0))

        # MACD bullish crossover
        macd_cross = False
        if 'MACD_Hist' in self.df.columns and len(self.df) >= 2:
            curr_hist = float(self.df['MACD_Hist'].iloc[-1])
            prev_hist = float(self.df['MACD_Hist'].iloc[-2])
            macd_cross = curr_hist > 0 and prev_hist <= 0
        checks.append(CheckItem("MACD bullish crossover", macd_cross, "", weight=1.5))

        # Big drop in recent days (potential reversal setup)
        if 'ROC_10' in self.df.columns:
            roc = float(self.df['ROC_10'].iloc[-1])
            big_drop = roc < -8
            checks.append(CheckItem("Significant drop in 10 days (>8%)", big_drop,
                                   f"10-day change: {roc:.1f}%", weight=1.5))

        # Volume spike on potential reversal day
        if 'Vol_Ratio' in self.df.columns:
            high_vol = float(self.df['Vol_Ratio'].iloc[-1]) > 1.5
            checks.append(CheckItem("Volume spike on reversal candle", high_vol, "", weight=1.0))

        # Bullish engulfing or hammer
        bullish_pattern = self._check_bullish_pattern()
        checks.append(CheckItem("Bullish reversal pattern", bullish_pattern, "", weight=1.5))

        score = sum(c.weight for c in checks if c.passed) / sum(c.weight for c in checks) * 100
        return score, checks

    def _check_bullish_pattern(self) -> bool:
        """Simple check for hammer or engulfing"""
        try:
            last = self.df.iloc[-1]
            prev = self.df.iloc[-2]

            # Hammer: small body, long lower wick
            is_hammer = (float(last['Lower_Wick_Pct']) > 60 and
                        float(last['Body_Pct']) < 30)

            # Bullish engulfing: red then bigger green
            is_engulfing = (not prev['Is_Green'] and last['Is_Green'] and
                          float(last['Body_Abs']) > float(prev['Body_Abs']))

            return is_hammer or is_engulfing
        except:
            return False

    def _get(self, name):
        if name in self.df.columns:
            val = self.df[name].iloc[-1]
            return float(val) if pd.notna(val) else None
        return None

    def _calc_score(self, checks):
        total_w = sum(c.weight for c in checks)
        if total_w == 0: return 50
        return round(sum(c.weight for c in checks if c.passed) / total_w * 100, 1)
