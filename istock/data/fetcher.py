"""
data_fetcher.py - UPDATED: Suppresses harmless ETF 404 errors
Detects if symbol is ETF vs Stock and handles accordingly
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import warnings
import logging
import os
import sys
from io import StringIO

warnings.filterwarnings('ignore')

# Suppress yfinance internal HTTP error messages
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
logging.getLogger('peewee').setLevel(logging.CRITICAL)

class DataFetcher:
    """Fetches stock/ETF data from Yahoo Finance"""

    def __init__(self):
        self.cache = {}
        self.failed_symbols = []

    def get_stock_data(self, symbol: str, period: str = "2y") -> dict:
        """
        Fetches comprehensive data for a single stock/ETF
        Suppresses non-critical errors for ETFs
        """
        if symbol in self.cache:
            return self.cache[symbol]

        try:
            # Suppress stderr temporarily to hide yfinance 404 messages
            old_stderr = sys.stderr
            sys.stderr = StringIO()

            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
            finally:
                # Restore stderr
                sys.stderr = old_stderr

            # Check if we got ANY data
            current_price = info.get('regularMarketPrice') or info.get(
                'previousClose') or info.get('navPrice')

            if not current_price:
                # Try getting price from history as fallback
                try:
                    hist_check = ticker.history(period="5d")
                    if not hist_check.empty:
                        current_price = hist_check['Close'].iloc[-1]
                        info['regularMarketPrice'] = current_price
                        info['longName'] = info.get('longName', symbol)
                except Exception:
                    pass

            if not current_price:
                self.failed_symbols.append(symbol)
                return None

            # Determine if this is an ETF or Stock
            quote_type = info.get('quoteType', 'UNKNOWN')
            is_etf = quote_type == 'ETF' or symbol in self._known_etfs()

            # Get price history
            old_stderr = sys.stderr
            sys.stderr = StringIO()
            try:
                history = ticker.history(period=period)
            finally:
                sys.stderr = old_stderr

            if history.empty:
                self.failed_symbols.append(symbol)
                return None

            # Get financial statements (stocks only)
            financials = None
            balance_sheet = None
            cashflow = None

            if not is_etf:
                old_stderr = sys.stderr
                sys.stderr = StringIO()
                try:
                    financials = ticker.financials
                    balance_sheet = ticker.balance_sheet
                    cashflow = ticker.cashflow
                except Exception:
                    pass
                finally:
                    sys.stderr = old_stderr

            # Get analyst recommendations
            recommendations = None
            try:
                old_stderr = sys.stderr
                sys.stderr = StringIO()
                try:
                    recommendations = ticker.recommendations
                except Exception:
                    pass
                finally:
                    sys.stderr = old_stderr
            except Exception:
                pass

            stock_data = {
                "symbol": symbol,
                "info": info,
                "history": history,
                "financials": financials,
                "balance_sheet": balance_sheet,
                "cashflow": cashflow,
                "recommendations": recommendations,
                "is_etf": is_etf,
                "quote_type": quote_type,
                "fetch_time": datetime.now().isoformat(),
            }

            self.cache[symbol] = stock_data
            return stock_data

        except Exception as e:
            print(f"  ❌ Error fetching {symbol}: {str(e)}")
            self.failed_symbols.append(symbol)
            return None

    def get_batch_data(self, symbols: list, period: str = "2y") -> dict:
        """Fetch data for multiple symbols with progress tracking"""
        results = {}
        total = len(symbols)

        print(f"\n📊 Fetching data for {total} symbols...")
        print("─" * 50)

        for i, symbol in enumerate(symbols, 1):
            print(f"  [{i}/{total}] {symbol:20s}", end=" ")
            data = self.get_stock_data(symbol, period)

            if data:
                asset_type = "ETF" if data.get('is_etf') else "Stock"
                results[symbol] = data
                print(f"✅ ({asset_type})")
            else:
                print("❌ (Failed)")

            # Rate limiting
            if i % 5 == 0:
                time.sleep(1)

        success = len(results)
        failed = total - success
        print(f"\n{'─' * 50}")
        print(f"  ✅ Success: {success}/{total}", end="")
        if failed > 0:
            print(f"  |  ❌ Failed: {failed}", end="")
        print()

        return results

    def get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol"""
        try:
            old_stderr = sys.stderr
            sys.stderr = StringIO()
            try:
                ticker = yf.Ticker(symbol)
                price = ticker.info.get('regularMarketPrice', 0)
            finally:
                sys.stderr = old_stderr
            return price or 0
        except Exception:
            return 0

    def get_market_indices(self) -> dict:
        """Fetch major market indices for context"""
        indices = {
            "^GSPC": "S&P 500",
            "^IXIC": "NASDAQ",
            "^DJI": "Dow Jones",
            "^NSEI": "Nifty 50",
            "^BSESN": "Sensex",
            "^VIX": "VIX (Fear Index)",
            "GC=F": "Gold",
            "CL=F": "Crude Oil",
            "^TNX": "US 10Y Treasury",
            "DX-Y.NYB": "Dollar Index",
        }

        print("\n🌍 Fetching Market Overview...")
        results = {}

        old_stderr = sys.stderr
        sys.stderr = StringIO()
        try:
            for symbol, name in indices.items():
                try:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period="5d")
                    if not hist.empty and len(hist) >= 2:
                        current = hist['Close'].iloc[-1]
                        prev = hist['Close'].iloc[0]
                        change_pct = ((current - prev) / prev) * 100
                        results[name] = {
                            "price": round(current, 2),
                            "weekly_change": round(change_pct, 2),
                        }
                except Exception:
                    pass
        finally:
            sys.stderr = old_stderr

        return results

    @staticmethod
    def _known_etfs() -> set:
        """List of known ETF symbols to help detection"""
        return {
            # US ETFs
            "VOO", "QQQ", "VTI", "SCHD", "VUG", "VTV",
            "SPY", "IVV", "IWM", "DIA", "VEA", "VXUS",
            "XLK", "XLV", "XLF", "XLE", "XLI", "XLY", "XLP",
            "XLU", "XLRE", "XLC", "XLB",
            "SOXX", "ARKK", "HACK", "ICLN", "BOTZ", "IBB",
            "BND", "AGG", "TLT", "LQD",
            "GLD", "IAU", "SLV",
            "VNQ", "SCHH",
            "UCO", "OILU",
            # Indian ETFs
            "NIFTYBEES.NS", "JUNIORBEES.NS", "GOLDBEES.NS",
            "BANKBEES.NS", "SILVERBEES.NS",
            "NIFTYBEES.BO", "JUNIORBEES.BO", "GOLDBEES.BO",
        }

    @staticmethod
    def safe_get(info: dict, key: str, default=None):
        """Safely get a value from info dict"""
        value = info.get(key, default)
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        return value