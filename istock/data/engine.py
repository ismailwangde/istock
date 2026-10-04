"""
core.data_engine - Data fetching and preparation (OHLC, indicators, market index)

Extracted from core/trade_advisor.py (Session 2.3). Pure code relocation —
identical class body, no logic changes. Imports TradeConfig from
core.trade_advisor; trade_advisor imports DataEngine back from this
module at the BOTTOM of its file, so the cycle resolves cleanly
(TradeConfig is defined before that bottom import runs).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from istock.decision.types import TradeConfig


# ══════════════════════════════════════════════════════════════
# DATA ENGINE
# ══════════════════════════════════════════════════════════════

class DataEngine:
    """Fetches and prepares all data needed for analysis"""

    def __init__(self, symbol: str):
        self.symbol = symbol.upper()
        self.ticker = yf.Ticker(self.symbol)
        self.info = {}
        self.daily = pd.DataFrame()
        self.weekly = pd.DataFrame()
        self.index_daily = pd.DataFrame()
        self.is_indian = '.NS' in self.symbol or '.BO' in self.symbol
        self.is_valid = False

    def fetch_all(self, as_of_date: Optional[str] = None) -> bool:
        """Fetch all required data. Returns True if successful.

        If `as_of_date` (ISO date string, e.g. "2025-10-01") is provided,
        every price-derived frame is restricted to bars dated on or
        before that day, and indicators are computed only on that
        sliced history. This enables point-in-time replay of past
        analyses.

        Limitation: fundamentals (`self.info` from yfinance) are a
        current snapshot — yfinance does not expose point-in-time
        fundamentals. Only price-derived indicators are point-in-time.
        """
        print(f"  📡 Fetching data for {self.symbol}...")

        # Parse the cutoff once and reuse. None means "no slicing".
        cutoff_ts: Optional[pd.Timestamp] = None
        if as_of_date is not None:
            try:
                cutoff_ts = pd.to_datetime(as_of_date)
            except Exception:
                cutoff_ts = None

        def _slice(df: pd.DataFrame) -> pd.DataFrame:
            """Trim a frame to bars on or before the cutoff. No-op if
            cutoff_ts is None or df is empty."""
            if cutoff_ts is None or df is None or df.empty:
                return df
            cutoff = cutoff_ts
            if df.index.tz is not None and cutoff.tz is None:
                cutoff = cutoff.tz_localize(df.index.tz)
            return df[df.index <= cutoff]

        # When the user picks a past cutoff we widen the fetch window
        # so MA200 / weekly trend / etc. still have runway behind the
        # cutoff. Future / today cutoffs use the original period= path.
        from datetime import date as _date
        is_past = (
            cutoff_ts is not None
            and cutoff_ts.date() < _date.today()
        )

        # Cache only the live (current-date) path. Point-in-time replay needs
        # bespoke historical windows, so it always fetches fresh from yfinance.
        use_cache = not is_past
        if use_cache:
            try:
                from istock.config import USE_OHLC_CACHE
                use_cache = bool(USE_OHLC_CACHE)
            except Exception:
                use_cache = False

        try:
            # Stock info — current snapshot, not point-in-time.
            self.info = self.ticker.info or {}
            if not self.info.get('regularMarketPrice') and not self.info.get('currentPrice'):
                # Try to get from history
                pass

            # Daily data - 1 year (need 200+ candles for MA200)
            print(f"  📊 Loading daily data (1 year)...")
            if is_past:
                start = (cutoff_ts - pd.DateOffset(years=2)).date().isoformat()
                end = (cutoff_ts + pd.DateOffset(days=1)).date().isoformat()
                self.daily = self.ticker.history(
                    start=start, end=end, interval="1d",
                )
            elif use_cache:
                self.daily = self._cached_daily(self.symbol)
            else:
                self.daily = self.ticker.history(period="1y", interval="1d")
            self.daily = _slice(self.daily)

            if self.daily.empty or len(self.daily) < 50:
                if cutoff_ts is not None and (self.daily is None or self.daily.empty):
                    raise ValueError(
                        f"No data available for {self.symbol} on or before {as_of_date}"
                    )
                print(f"  ❌ Insufficient daily data for {self.symbol}")
                return False

            # Weekly data - 2 years (for trend context)
            print(f"  📊 Loading weekly data (2 years)...")
            if is_past:
                w_start = (cutoff_ts - pd.DateOffset(years=3)).date().isoformat()
                w_end = (cutoff_ts + pd.DateOffset(days=1)).date().isoformat()
                self.weekly = self.ticker.history(
                    start=w_start, end=w_end, interval="1wk",
                )
            elif use_cache and not self.daily.empty:
                # Resample cached daily → weekly; no extra network call.
                from istock.data.ohlc_cache import resample_daily_to_weekly
                self.weekly = resample_daily_to_weekly(self.daily)
            else:
                self.weekly = self.ticker.history(period="2y", interval="1wk")
            self.weekly = _slice(self.weekly)

            # Market index for context
            index_symbol = "^NSEI" if self.is_indian else "^GSPC"
            print(f"  📊 Loading market index ({index_symbol})...")
            try:
                if is_past:
                    idx_ticker = yf.Ticker(index_symbol)
                    i_start = (cutoff_ts - pd.DateOffset(years=1)).date().isoformat()
                    i_end = (cutoff_ts + pd.DateOffset(days=1)).date().isoformat()
                    self.index_daily = idx_ticker.history(
                        start=i_start, end=i_end, interval="1d",
                    )
                elif use_cache:
                    self.index_daily = self._cached_daily(index_symbol)
                else:
                    self.index_daily = yf.Ticker(index_symbol).history(
                        period="6mo", interval="1d")
                self.index_daily = _slice(self.index_daily)
            except Exception:
                self.index_daily = pd.DataFrame()

            # Add technical indicators to daily data
            self._add_indicators(self.daily)
            if not self.weekly.empty and len(self.weekly) > 20:
                self._add_indicators(self.weekly)

            self.is_valid = True
            print(f"  ✅ Data loaded: {len(self.daily)} daily, {len(self.weekly)} weekly candles")
            return True

        except ValueError:
            # Re-raise the as_of_date "no data" sentinel so callers /
            # tests can react. Other failure modes still return False.
            raise
        except Exception as e:
            print(f"  ❌ Error fetching {self.symbol}: {e}")
            return False

    @staticmethod
    def _cached_daily(symbol: str) -> pd.DataFrame:
        """Live-path daily fetch served from the parquet cache, topped-up with
        only the missing recent days. Falls back to a direct yfinance pull if
        the cache layer returns nothing (e.g. first run with no network)."""
        try:
            from istock.data.ohlc_cache import get_or_update_daily
            df = get_or_update_daily(symbol)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            print(f"  ⚠️ OHLC cache miss for {symbol}: {e}; falling back to yfinance")
        return yf.Ticker(symbol).history(period="1y", interval="1d")

    def _add_indicators(self, df: pd.DataFrame):
        """Add all technical indicators to a dataframe"""
        if len(df) < 20:
            return

        # Moving Averages
        df['MA10'] = df['Close'].rolling(10).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA50'] = df['Close'].rolling(50).mean()
        if len(df) >= 200:
            df['MA200'] = df['Close'].rolling(200).mean()
        else:
            df['MA200'] = df['Close'].rolling(len(df)).mean()

        # EMA
        df['EMA9'] = df['Close'].ewm(span=9).mean()
        df['EMA21'] = df['Close'].ewm(span=21).mean()

        # RSI — Wilder's smoothing (ewm alpha=1/n), matches TA-Lib.
        # (Was plain rolling-mean: ~12% off canonical, corr 0.89.)
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df['RSI'] = 100 - (100 / (1 + rs))

        # MACD
        ema12 = df['Close'].ewm(span=12).mean()
        ema26 = df['Close'].ewm(span=26).mean()
        df['MACD'] = ema12 - ema26
        df['MACD_Signal'] = df['MACD'].ewm(span=9).mean()
        df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

        # Bollinger Bands
        df['BB_Mid'] = df['Close'].rolling(20).mean()
        bb_std = df['Close'].rolling(20).std()
        df['BB_Upper'] = df['BB_Mid'] + 2 * bb_std
        df['BB_Lower'] = df['BB_Mid'] - 2 * bb_std
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Mid'] * 100

        # ATR
        high_low = df['High'] - df['Low']
        high_close = (df['High'] - df['Close'].shift()).abs()
        low_close = (df['Low'] - df['Close'].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        # Wilder's smoothing (matches TA-Lib); was plain rolling-mean (~7% off).
        df['ATR'] = true_range.ewm(alpha=1 / TradeConfig.ATR_PERIOD,
                                   adjust=False, min_periods=TradeConfig.ATR_PERIOD).mean()
        df['ATR_PCT'] = df['ATR'] / df['Close'] * 100

        # ADX
        df['ADX'] = self._calculate_adx(df)

        # Volume indicators
        df['Vol_MA'] = df['Volume'].rolling(TradeConfig.VOLUME_AVG_PERIOD).mean()
        df['Vol_Ratio'] = df['Volume'] / df['Vol_MA']

        # OBV (On-Balance Volume)
        df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).cumsum()
        df['OBV_MA'] = df['OBV'].rolling(20).mean()

        # Stochastic — standard SLOW stochastic to match TA-Lib STOCH(14,3,3):
        # slow %K = 3-SMA of fast %K, slow %D = 3-SMA of slow %K.
        low_14 = df['Low'].rolling(14).min()
        high_14 = df['High'].rolling(14).max()
        fast_k = ((df['Close'] - low_14) / (high_14 - low_14).replace(0, np.nan)) * 100
        df['Stoch_K'] = fast_k.rolling(3).mean()
        df['Stoch_D'] = df['Stoch_K'].rolling(3).mean()

        # Rate of Change
        df['ROC_5'] = df['Close'].pct_change(5) * 100
        df['ROC_10'] = df['Close'].pct_change(10) * 100
        df['ROC_20'] = df['Close'].pct_change(20) * 100

        # Candle analysis
        df['Body'] = df['Close'] - df['Open']
        df['Body_Abs'] = df['Body'].abs()
        df['Range'] = df['High'] - df['Low']
        df['Upper_Wick'] = df['High'] - df[['Open', 'Close']].max(axis=1)
        df['Lower_Wick'] = df[['Open', 'Close']].min(axis=1) - df['Low']
        df['Body_Pct'] = df['Body_Abs'] / df['Range'].replace(0, np.nan) * 100
        df['Upper_Wick_Pct'] = df['Upper_Wick'] / df['Range'].replace(0, np.nan) * 100
        df['Lower_Wick_Pct'] = df['Lower_Wick'] / df['Range'].replace(0, np.nan) * 100
        df['Is_Green'] = df['Close'] > df['Open']
        df['Day_Change_Pct'] = df['Close'].pct_change() * 100

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """ADX with Wilder's smoothing throughout — matches TA-Lib.
        (Was plain rolling-mean at every stage: ~45% off canonical, corr 0.74.)"""
        try:
            high, low, close = df['High'], df['Low'], df['Close']

            up = high.diff()
            down = -low.diff()
            plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
            minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)

            tr1 = high - low
            tr2 = (high - close.shift()).abs()
            tr3 = (low - close.shift()).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            # Wilder smoothing (recursive EMA, alpha = 1/period)
            a = 1 / period
            atr = tr.ewm(alpha=a, adjust=False, min_periods=period).mean()
            plus_di = 100 * (plus_dm.ewm(alpha=a, adjust=False, min_periods=period).mean()
                             / atr.replace(0, np.nan))
            minus_di = 100 * (minus_dm.ewm(alpha=a, adjust=False, min_periods=period).mean()
                              / atr.replace(0, np.nan))

            dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
            adx = dx.ewm(alpha=a, adjust=False, min_periods=period).mean()
            return adx

        except Exception:
            return pd.Series(index=df.index, dtype=float)

    @property
    def current_price(self) -> float:
        """Get the latest price"""
        if not self.daily.empty:
            return float(self.daily['Close'].iloc[-1])
        return float(self.info.get('currentPrice',
                     self.info.get('regularMarketPrice', 0)))

    @property
    def prev_close(self) -> float:
        if len(self.daily) >= 2:
            return float(self.daily['Close'].iloc[-2])
        return self.current_price

    @property
    def company_name(self) -> str:
        return self.info.get('shortName', self.info.get('longName', self.symbol))
