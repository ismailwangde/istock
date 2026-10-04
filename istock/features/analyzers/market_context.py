"""
analyzers.market_context - Per-stock broad-market context check.

Section 8 of the live verdict pipeline. Checks index trend (S&P 500 or
Nifty 50 depending on the ticker's market), VIX level, and the stock's
20-day relative strength vs the index. Produces a SectionResult that
weights into TradeAdvisor.analyze's composite buy_score.

Session 15 cleanup note:
    The legacy MacroAnalyzer class (sector rotation, FRED data,
    cycle-phase voting) and its SECTOR_ROTATION dict used to live in
    this file. They were never wired into the live verdict and have
    been removed. Macro reporting is being rebuilt in a future session.
"""

from __future__ import annotations

import warnings

import yfinance as yf

warnings.filterwarnings("ignore")

from istock.decision.types import CheckItem, SectionResult


# ══════════════════════════════════════════════════════════════
# MARKET CONTEXT ANALYZER
# ══════════════════════════════════════════════════════════════

class MarketContextAnalyzer:
    """Checks broader market conditions"""

    def __init__(self, data: "DataEngine"):
        self.data = data
        self.index_df = data.index_daily
        self.is_indian = data.is_indian

    def analyze(self) -> SectionResult:
        checks = []

        # Index trend
        if not self.index_df.empty and len(self.index_df) >= 50:
            idx_close = float(self.index_df['Close'].iloc[-1])
            idx_ma50 = float(self.index_df['Close'].rolling(50).mean().iloc[-1])
            idx_ma20 = float(self.index_df['Close'].rolling(20).mean().iloc[-1])

            idx_bullish = idx_close > idx_ma50
            checks.append(CheckItem(
                name=f"Market index above MA50 ({'Nifty' if self.is_indian else 'S&P 500'})",
                passed=idx_bullish,
                detail=f"Index: {idx_close:.0f} | MA50: {idx_ma50:.0f}",
                weight=2.0
            ))

            idx_short_bullish = idx_close > idx_ma20
            checks.append(CheckItem(
                name="Market index above MA20 (short-term)",
                passed=idx_short_bullish,
                detail=f"Index: {idx_close:.0f} | MA20: {idx_ma20:.0f}",
                weight=1.5
            ))

            # Index momentum
            idx_5d = (idx_close - float(self.index_df['Close'].iloc[-6])) / float(self.index_df['Close'].iloc[-6]) * 100
            idx_positive = idx_5d > 0
            checks.append(CheckItem(
                name="Market 5-day return positive",
                passed=idx_positive,
                detail=f"5-day return: {idx_5d:+.1f}%",
                weight=1.0,
                value=idx_5d
            ))

        # VIX check (if available)
        try:
            vix_symbol = "^INDIAVIX" if self.is_indian else "^VIX"
            vix_data = yf.Ticker(vix_symbol).history(period="5d")
            if not vix_data.empty:
                vix = float(vix_data['Close'].iloc[-1])
                low_fear = vix < 25
                checks.append(CheckItem(
                    name="VIX < 25 (low fear environment)",
                    passed=low_fear,
                    detail=f"VIX: {vix:.1f} ({'LOW FEAR' if vix < 20 else 'MODERATE' if vix < 25 else 'HIGH FEAR' if vix < 35 else 'EXTREME FEAR'})",
                    weight=2.0,
                    value=vix
                ))
        except Exception:
            pass

        # Sector strength (compare stock vs index)
        if not self.index_df.empty and len(self.data.daily) >= 20:
            try:
                stock_20d = float(self.data.daily['Close'].pct_change(20).iloc[-1]) * 100
                idx_20d = float(self.index_df['Close'].pct_change(20).iloc[-1]) * 100
                outperforming = stock_20d > idx_20d
                checks.append(CheckItem(
                    name="Stock outperforming market (20-day)",
                    passed=outperforming,
                    detail=f"Stock: {stock_20d:+.1f}% vs Market: {idx_20d:+.1f}%",
                    weight=1.5
                ))
            except Exception:
                pass

        score = self._calc_score(checks)
        summary = "FAVORABLE MARKET" if score > 65 else \
                  "NEUTRAL MARKET" if score > 40 else "UNFAVORABLE MARKET"

        return SectionResult(name="Market Context", score=score,
                           checks=checks, summary=summary)

    def _calc_score(self, checks):
        total_w = sum(c.weight for c in checks)
        if total_w == 0:
            return 50
        return round(sum(c.weight for c in checks if c.passed) / total_w * 100, 1)
