"""
analyzers.support_resistance - Support/resistance level detection (swings, pivots, fibs, volume)

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
# SUPPORT / RESISTANCE ENGINE
# ══════════════════════════════════════════════════════════════

class SupportResistanceEngine:
    """Finds support and resistance levels using multiple methods"""

    def __init__(self, data: DataEngine):
        self.data = data
        self.df = data.daily
        self.price = data.current_price
        self.levels: List[PriceLevel] = []

    def calculate_all(self) -> Tuple[List[PriceLevel], List[PriceLevel], Dict]:
        """Returns (support_levels, resistance_levels, fibonacci_dict)"""
        self._find_swing_levels()
        self._find_pivot_levels()
        self._find_fibonacci_levels()
        self._find_volume_levels()
        self._find_ma_levels()
        self._find_round_number_levels()

        # Cluster nearby levels
        self._cluster_levels()

        # Separate into support and resistance
        supports = sorted(
            [l for l in self.levels if l.price < self.price],
            key=lambda x: x.price, reverse=True
        )
        resistances = sorted(
            [l for l in self.levels if l.price > self.price],
            key=lambda x: x.price
        )

        # Calculate distance from current price
        for level in supports + resistances:
            level.distance_pct = abs(level.price - self.price) / self.price * 100

        # Get fibonacci levels
        fib = self._get_fibonacci_dict()

        return supports[:5], resistances[:5], fib  # top 5 each

    def _find_swing_levels(self):
        """Find swing highs and lows"""
        window = TradeConfig.SR_SWING_WINDOW
        highs = self.df['High'].values
        lows = self.df['Low'].values

        for i in range(window, len(self.df) - window):
            # Swing high
            if highs[i] == max(highs[i-window:i+window+1]):
                self.levels.append(PriceLevel(
                    price=round(float(highs[i]), 2),
                    level_type='resistance' if highs[i] > self.price else 'support',
                    strength=1,
                    source='swing_high'
                ))
            # Swing low
            if lows[i] == min(lows[i-window:i+window+1]):
                self.levels.append(PriceLevel(
                    price=round(float(lows[i]), 2),
                    level_type='support' if lows[i] < self.price else 'resistance',
                    strength=1,
                    source='swing_low'
                ))

    def _find_pivot_levels(self):
        """Standard pivot points from last trading day"""
        if len(self.df) < 2:
            return
        last = self.df.iloc[-2]  # use previous day
        h, l, c = float(last['High']), float(last['Low']), float(last['Close'])

        pivot = (h + l + c) / 3
        s1 = 2 * pivot - h
        s2 = pivot - (h - l)
        s3 = l - 2 * (h - pivot)
        r1 = 2 * pivot - l
        r2 = pivot + (h - l)
        r3 = h + 2 * (pivot - l)

        for price, label in [(s3, 'S3'), (s2, 'S2'), (s1, 'S1'),
                             (pivot, 'Pivot'), (r1, 'R1'), (r2, 'R2'), (r3, 'R3')]:
            self.levels.append(PriceLevel(
                price=round(price, 2),
                level_type='support' if price < self.price else 'resistance',
                strength=2 if 'Pivot' in label else 1,
                source=f'pivot_{label}'
            ))

    def _find_fibonacci_levels(self):
        """Fibonacci retracement from recent 60-day high to low"""
        lookback = min(60, len(self.df) - 1)
        recent = self.df.tail(lookback)
        high = float(recent['High'].max())
        low = float(recent['Low'].min())
        diff = high - low

        if diff < 0.01:
            return

        fib_ratios = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]

        for ratio in fib_ratios:
            price = high - ratio * diff
            self.levels.append(PriceLevel(
                price=round(price, 2),
                level_type='support' if price < self.price else 'resistance',
                strength=2 if ratio in [0.382, 0.5, 0.618] else 1,
                source=f'fib_{ratio}'
            ))

    def _find_volume_levels(self):
        """Find price levels with highest volume concentration"""
        if len(self.df) < 20:
            return

        # Create price bins and find where most volume traded
        price_range = self.df['Close'].max() - self.df['Close'].min()
        if price_range < 0.01:
            return

        n_bins = 20
        bins = np.linspace(self.df['Close'].min(), self.df['Close'].max(), n_bins + 1)
        df_temp = self.df.copy()
        df_temp['Price_Bin'] = pd.cut(df_temp['Close'], bins=bins)

        vol_profile = df_temp.groupby('Price_Bin', observed=True)['Volume'].sum()

        if vol_profile.empty:
            return

        # Top 3 volume levels
        top_levels = vol_profile.nlargest(3)
        for interval in top_levels.index:
            mid_price = (interval.left + interval.right) / 2
            self.levels.append(PriceLevel(
                price=round(float(mid_price), 2),
                level_type='support' if mid_price < self.price else 'resistance',
                strength=3,  # volume levels are strong
                source='volume_cluster'
            ))

    def _find_ma_levels(self):
        """Moving averages as dynamic S/R"""
        for ma_name in ['MA20', 'MA50', 'MA200']:
            if ma_name in self.df.columns:
                val = self.df[ma_name].iloc[-1]
                if pd.notna(val):
                    self.levels.append(PriceLevel(
                        price=round(float(val), 2),
                        level_type='support' if val < self.price else 'resistance',
                        strength=3 if ma_name == 'MA200' else 2,
                        source=f'ma_{ma_name}'
                    ))

    def _find_round_number_levels(self):
        """Psychological round number levels"""
        price = self.price
        if price > 1000:
            step = 100
        elif price > 100:
            step = 50
        elif price > 10:
            step = 5
        else:
            step = 1

        nearest_below = int(price / step) * step
        nearest_above = nearest_below + step

        for p in [nearest_below, nearest_above]:
            dist = abs(p - price) / price * 100
            if dist < 5:  # only if within 5%
                self.levels.append(PriceLevel(
                    price=float(p),
                    level_type='support' if p < price else 'resistance',
                    strength=1,
                    source='round_number'
                ))

    def _cluster_levels(self):
        """Merge nearby levels and increase their strength"""
        if not self.levels:
            return

        clustered = []
        sorted_levels = sorted(self.levels, key=lambda x: x.price)
        used = set()

        for i, level in enumerate(sorted_levels):
            if i in used:
                continue

            cluster_prices = [level.price]
            cluster_strength = level.strength
            sources = {level.source}

            for j in range(i + 1, len(sorted_levels)):
                if j in used:
                    continue
                pct_diff = abs(sorted_levels[j].price - level.price) / level.price * 100
                if pct_diff < TradeConfig.SR_CLUSTER_PCT:
                    cluster_prices.append(sorted_levels[j].price)
                    cluster_strength += sorted_levels[j].strength
                    sources.add(sorted_levels[j].source)
                    used.add(j)

            avg_price = round(np.mean(cluster_prices), 2)
            clustered.append(PriceLevel(
                price=avg_price,
                level_type='support' if avg_price < self.price else 'resistance',
                strength=min(cluster_strength, 5),
                source='+'.join(sorted(sources))
            ))

        self.levels = clustered

    def _get_fibonacci_dict(self) -> Dict[str, float]:
        """Get fibonacci levels as a clean dictionary"""
        lookback = min(60, len(self.df) - 1)
        recent = self.df.tail(lookback)
        high = float(recent['High'].max())
        low = float(recent['Low'].min())
        diff = high - low

        return {
            'High (0%)': round(high, 2),
            '23.6%': round(high - 0.236 * diff, 2),
            '38.2%': round(high - 0.382 * diff, 2),
            '50.0%': round(high - 0.5 * diff, 2),
            '61.8%': round(high - 0.618 * diff, 2),
            '78.6%': round(high - 0.786 * diff, 2),
            'Low (100%)': round(low, 2)
        }
