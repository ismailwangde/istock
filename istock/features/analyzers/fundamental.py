"""
fundamental_analyzer.py - Analyzes fundamental metrics of stocks
Calculates scores for valuation, profitability, growth, and health
"""

import numpy as np
import pandas as pd
from istock.data.fetcher import DataFetcher


class FundamentalAnalyzer:
    """Analyzes stock fundamentals and generates scores"""

    def __init__(self):
        self.safe_get = DataFetcher.safe_get

    def analyze(self, stock_data: dict) -> dict:
        """
        Complete fundamental analysis of a stock

        Returns dict with all metrics and scores
        """
        if not stock_data or 'info' not in stock_data:
            return None

        info = stock_data['info']
        symbol = stock_data['symbol']

        analysis = {
            "symbol": symbol,
            "name": self.safe_get(info, 'longName', symbol),
            "sector": self.safe_get(info, 'sector', 'N/A'),
            "industry": self.safe_get(info, 'industry', 'N/A'),
            "market_cap": self.safe_get(info, 'marketCap', 0),
            "currency": self.safe_get(info, 'currency', 'USD'),
            "current_price": self.safe_get(info, 'regularMarketPrice', 0),
        }

        # Calculate all metric categories
        analysis["valuation"] = self._valuation_metrics(info)
        analysis["profitability"] = self._profitability_metrics(info)
        analysis["growth"] = self._growth_metrics(info)
        analysis["financial_health"] = self._health_metrics(info)
        analysis["dividend"] = self._dividend_metrics(info)
        analysis["analyst"] = self._analyst_metrics(info)

        # Calculate category scores
        analysis["valuation_score"] = self._score_valuation(analysis["valuation"])
        analysis["profitability_score"] = self._score_profitability(analysis["profitability"])
        analysis["growth_score"] = self._score_growth(analysis["growth"])
        analysis["health_score"] = self._score_health(analysis["financial_health"])

        # Weighted fundamental score (out of 100)
        analysis["fundamental_score"] = round(
            analysis["valuation_score"] * 0.25 +
            analysis["profitability_score"] * 0.30 +
            analysis["growth_score"] * 0.25 +
            analysis["health_score"] * 0.20,
            1
        )

        # Market cap category
        mcap = analysis["market_cap"]
        if mcap > 200e9:
            analysis["cap_category"] = "MEGA CAP"
        elif mcap > 10e9:
            analysis["cap_category"] = "LARGE CAP"
        elif mcap > 2e9:
            analysis["cap_category"] = "MID CAP"
        elif mcap > 300e6:
            analysis["cap_category"] = "SMALL CAP"
        else:
            analysis["cap_category"] = "MICRO CAP"

        return analysis

    def _valuation_metrics(self, info: dict) -> dict:
        """Extract valuation metrics"""
        return {
            "pe_ratio": self.safe_get(info, 'trailingPE'),
            "forward_pe": self.safe_get(info, 'forwardPE'),
            "peg_ratio": self.safe_get(info, 'pegRatio'),
            "pb_ratio": self.safe_get(info, 'priceToBook'),
            "ps_ratio": self.safe_get(info, 'priceToSalesTrailing12Months'),
            "ev_ebitda": self.safe_get(info, 'enterpriseToEbitda'),
            "ev_revenue": self.safe_get(info, 'enterpriseToRevenue'),
            "price_to_fcf": self._calc_price_to_fcf(info),
        }

    def _profitability_metrics(self, info: dict) -> dict:
        """Extract profitability metrics"""
        return {
            "roe": self._pct(self.safe_get(info, 'returnOnEquity')),
            "roa": self._pct(self.safe_get(info, 'returnOnAssets')),
            "profit_margin": self._pct(self.safe_get(info, 'profitMargins')),
            "operating_margin": self._pct(self.safe_get(info, 'operatingMargins')),
            "gross_margin": self._pct(self.safe_get(info, 'grossMargins')),
            "ebitda_margin": self._calc_ebitda_margin(info),
        }

    def _growth_metrics(self, info: dict) -> dict:
        """Extract growth metrics"""
        return {
            "revenue_growth": self._pct(self.safe_get(info, 'revenueGrowth')),
            "earnings_growth": self._pct(self.safe_get(info, 'earningsGrowth')),
            "quarterly_revenue_growth": self._pct(
                self.safe_get(info, 'revenueQuarterlyGrowth')
            ),
            "quarterly_earnings_growth": self._pct(
                self.safe_get(info, 'earningsQuarterlyGrowth')
            ),
        }

    def _health_metrics(self, info: dict) -> dict:
        """Extract financial health metrics"""
        return {
            "debt_to_equity": self.safe_get(info, 'debtToEquity'),
            "current_ratio": self.safe_get(info, 'currentRatio'),
            "quick_ratio": self.safe_get(info, 'quickRatio'),
            "total_debt": self.safe_get(info, 'totalDebt', 0),
            "total_cash": self.safe_get(info, 'totalCash', 0),
            "free_cashflow": self.safe_get(info, 'freeCashflow', 0),
            "operating_cashflow": self.safe_get(info, 'operatingCashflow', 0),
            "cash_to_debt_ratio": self._calc_cash_to_debt(info),
        }

    def _dividend_metrics(self, info: dict) -> dict:
        """Extract dividend metrics"""
        return {
            "dividend_yield": self._pct(self.safe_get(info, 'dividendYield')),
            "payout_ratio": self._pct(self.safe_get(info, 'payoutRatio')),
            "trailing_dividend": self.safe_get(info, 'trailingAnnualDividendYield'),
            "five_year_avg_yield": self.safe_get(info, 'fiveYearAvgDividendYield'),
        }

    def _analyst_metrics(self, info: dict) -> dict:
        """Extract analyst consensus"""
        return {
            "recommendation": self.safe_get(info, 'recommendationKey', 'N/A'),
            "recommendation_mean": self.safe_get(info, 'recommendationMean'),
            "target_price": self.safe_get(info, 'targetMeanPrice'),
            "target_high": self.safe_get(info, 'targetHighPrice'),
            "target_low": self.safe_get(info, 'targetLowPrice'),
            "num_analysts": self.safe_get(info, 'numberOfAnalystOpinions', 0),
        }

    # ============================================================
    # SCORING FUNCTIONS (each returns 0-100)
    # ============================================================

    def _score_valuation(self, val: dict) -> float:
        """Score valuation metrics (lower P/E, P/B = better for value)"""
        score = 50  # Start neutral

        pe = val.get("pe_ratio")
        if pe is not None:
            if pe < 0:
                score -= 15          # Negative earnings
            elif pe < 12:
                score += 20          # Undervalued
            elif pe < 20:
                score += 10          # Fair
            elif pe < 30:
                score += 0           # Slightly expensive
            elif pe < 50:
                score -= 10          # Expensive
            else:
                score -= 20          # Very expensive

        peg = val.get("peg_ratio")
        if peg is not None:
            if 0 < peg < 1:
                score += 15          # Great growth at reasonable price
            elif 1 <= peg < 1.5:
                score += 10
            elif 1.5 <= peg < 2:
                score += 5
            elif peg >= 3:
                score -= 10

        pb = val.get("pb_ratio")
        if pb is not None:
            if 0 < pb < 1:
                score += 10          # Trading below book value
            elif pb < 3:
                score += 5
            elif pb > 10:
                score -= 10

        return max(0, min(100, score))

    def _score_profitability(self, prof: dict) -> float:
        """Score profitability metrics (higher margins/returns = better)"""
        score = 50

        roe = prof.get("roe")
        if roe is not None:
            if roe > 25:
                score += 20
            elif roe > 15:
                score += 15
            elif roe > 10:
                score += 5
            elif roe > 0:
                score += 0
            else:
                score -= 15

        margin = prof.get("profit_margin")
        if margin is not None:
            if margin > 25:
                score += 15
            elif margin > 15:
                score += 10
            elif margin > 5:
                score += 5
            elif margin > 0:
                score += 0
            else:
                score -= 10

        op_margin = prof.get("operating_margin")
        if op_margin is not None:
            if op_margin > 30:
                score += 10
            elif op_margin > 20:
                score += 5
            elif op_margin < 0:
                score -= 10

        return max(0, min(100, score))

    def _score_growth(self, growth: dict) -> float:
        """Score growth metrics (higher growth = better)"""
        score = 50

        rev_growth = growth.get("revenue_growth")
        if rev_growth is not None:
            if rev_growth > 30:
                score += 20
            elif rev_growth > 15:
                score += 15
            elif rev_growth > 5:
                score += 5
            elif rev_growth > 0:
                score += 0
            elif rev_growth > -10:
                score -= 5
            else:
                score -= 15

        earn_growth = growth.get("earnings_growth")
        if earn_growth is not None:
            if earn_growth > 30:
                score += 20
            elif earn_growth > 15:
                score += 10
            elif earn_growth > 0:
                score += 5
            else:
                score -= 10

        return max(0, min(100, score))

    def _score_health(self, health: dict) -> float:
        """Score financial health (lower debt, higher cash = better)"""
        score = 50

        de = health.get("debt_to_equity")
        if de is not None:
            if de < 10:
                score += 15         # Very low debt
            elif de < 50:
                score += 10
            elif de < 100:
                score += 5
            elif de < 200:
                score -= 5
            else:
                score -= 15         # Heavy debt

        cr = health.get("current_ratio")
        if cr is not None:
            if cr > 2:
                score += 10
            elif cr > 1.5:
                score += 5
            elif cr > 1:
                score += 0
            else:
                score -= 10         # Liquidity concern

        fcf = health.get("free_cashflow")
        if fcf is not None:
            if fcf > 0:
                score += 10         # Positive FCF is good
            else:
                score -= 10

        return max(0, min(100, score))

    # ============================================================
    # HELPER FUNCTIONS
    # ============================================================

    @staticmethod
    def _pct(value) -> float:
        """Convert decimal to percentage"""
        if value is None:
            return None
        try:
            return round(float(value) * 100, 2)
        except (TypeError, ValueError):
            return None

    def _calc_price_to_fcf(self, info: dict) -> float:
        mcap = self.safe_get(info, 'marketCap', 0)
        fcf = self.safe_get(info, 'freeCashflow', 0)
        if mcap and fcf and fcf > 0:
            return round(mcap / fcf, 2)
        return None

    def _calc_ebitda_margin(self, info: dict) -> float:
        ebitda = self.safe_get(info, 'ebitda', 0)
        revenue = self.safe_get(info, 'totalRevenue', 0)
        if ebitda and revenue and revenue > 0:
            return round((ebitda / revenue) * 100, 2)
        return None

    def _calc_cash_to_debt(self, info: dict) -> float:
        cash = self.safe_get(info, 'totalCash', 0)
        debt = self.safe_get(info, 'totalDebt', 0)
        if cash and debt and debt > 0:
            return round(cash / debt, 2)
        return None