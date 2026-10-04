"""
technical_analyzer.py - Technical analysis with indicators and signals
Uses the 'ta' library for technical indicator calculations
"""

import pandas as pd
import numpy as np
import ta
from ta.trend import MACD, EMAIndicator, SMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator, StochRSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange


class TechnicalAnalyzer:
    """Technical analysis engine"""

    def analyze(self, stock_data: dict) -> dict:
        """
        Complete technical analysis

        Args:
            stock_data: Dictionary from DataFetcher with 'history' key

        Returns:
            Dict with all technical indicators and score
        """
        if not stock_data or 'history' not in stock_data:
            return None

        df = stock_data['history'].copy()
        if len(df) < 50:
            return {"symbol": stock_data['symbol'], "technical_score": 50,
                    "error": "Insufficient data"}

        symbol = stock_data['symbol']

        analysis = {"symbol": symbol}

        # Calculate all indicators
        analysis["moving_averages"] = self._moving_averages(df)
        analysis["rsi"] = self._rsi_analysis(df)
        analysis["macd"] = self._macd_analysis(df)
        analysis["bollinger"] = self._bollinger_analysis(df)
        analysis["volume"] = self._volume_analysis(df)
        analysis["momentum"] = self._momentum_analysis(df)
        analysis["volatility"] = self._volatility_analysis(df)
        analysis["support_resistance"] = self._support_resistance(df)

        # Generate technical score
        analysis["technical_score"] = self._calculate_tech_score(analysis)

        # Generate signal
        score = analysis["technical_score"]
        if score >= 70:
            analysis["signal"] = "BULLISH"
        elif score >= 55:
            analysis["signal"] = "SLIGHTLY BULLISH"
        elif score >= 45:
            analysis["signal"] = "NEUTRAL"
        elif score >= 30:
            analysis["signal"] = "SLIGHTLY BEARISH"
        else:
            analysis["signal"] = "BEARISH"

        return analysis

    def _moving_averages(self, df: pd.DataFrame) -> dict:
        """Calculate moving averages and crossover signals"""
        close = df['Close']
        current_price = close.iloc[-1]

        sma_20 = SMAIndicator(close, window=20).sma_indicator().iloc[-1]
        sma_50 = SMAIndicator(close, window=50).sma_indicator().iloc[-1]
        sma_200 = None
        if len(df) >= 200:
            sma_200 = SMAIndicator(close, window=200).sma_indicator().iloc[-1]

        ema_12 = EMAIndicator(close, window=12).ema_indicator().iloc[-1]
        ema_26 = EMAIndicator(close, window=26).ema_indicator().iloc[-1]

        # Golden/Death Cross detection
        cross_signal = "NONE"
        if sma_200 is not None:
            sma_50_series = SMAIndicator(close, window=50).sma_indicator()
            sma_200_series = SMAIndicator(close, window=200).sma_indicator()
            if len(sma_50_series.dropna()) >= 2 and len(sma_200_series.dropna()) >= 2:
                recent_50 = sma_50_series.dropna().iloc[-2:]
                recent_200 = sma_200_series.dropna().iloc[-2:]
                if len(recent_50) == 2 and len(recent_200) == 2:
                    if (recent_50.iloc[-2] < recent_200.iloc[-2] and
                            recent_50.iloc[-1] > recent_200.iloc[-1]):
                        cross_signal = "GOLDEN CROSS (Bullish)"
                    elif (recent_50.iloc[-2] > recent_200.iloc[-2] and
                          recent_50.iloc[-1] < recent_200.iloc[-1]):
                        cross_signal = "DEATH CROSS (Bearish)"

        return {
            "current_price": round(current_price, 2),
            "sma_20": round(sma_20, 2) if sma_20 else None,
            "sma_50": round(sma_50, 2) if sma_50 else None,
            "sma_200": round(sma_200, 2) if sma_200 else None,
            "ema_12": round(ema_12, 2),
            "ema_26": round(ema_26, 2),
            "above_sma_50": current_price > sma_50 if sma_50 else None,
            "above_sma_200": current_price > sma_200 if sma_200 else None,
            "sma_50_above_200": sma_50 > sma_200 if (sma_50 and sma_200) else None,
            "cross_signal": cross_signal,
            "distance_from_sma200_pct": round(
                ((current_price - sma_200) / sma_200) * 100, 2
            ) if sma_200 else None,
        }

    def _rsi_analysis(self, df: pd.DataFrame) -> dict:
        """RSI and Stochastic RSI analysis"""
        close = df['Close']

        rsi = RSIIndicator(close, window=14).rsi()
        current_rsi = rsi.iloc[-1]

        stoch_rsi = StochRSIIndicator(close)
        stoch_k = stoch_rsi.stochrsi_k().iloc[-1]
        stoch_d = stoch_rsi.stochrsi_d().iloc[-1]

        if current_rsi > 70:
            signal = "OVERBOUGHT - Caution"
        elif current_rsi > 60:
            signal = "STRONG"
        elif current_rsi > 40:
            signal = "NEUTRAL"
        elif current_rsi > 30:
            signal = "WEAK"
        else:
            signal = "OVERSOLD - Potential opportunity"

        return {
            "rsi_14": round(current_rsi, 2),
            "rsi_signal": signal,
            "stoch_rsi_k": round(stoch_k * 100, 2) if not np.isnan(stoch_k) else None,
            "stoch_rsi_d": round(stoch_d * 100, 2) if not np.isnan(stoch_d) else None,
        }

    def _macd_analysis(self, df: pd.DataFrame) -> dict:
        """MACD analysis"""
        close = df['Close']
        macd_indicator = MACD(close)

        macd_line = macd_indicator.macd().iloc[-1]
        signal_line = macd_indicator.macd_signal().iloc[-1]
        histogram = macd_indicator.macd_diff().iloc[-1]

        if macd_line > signal_line and histogram > 0:
            signal = "BULLISH"
        elif macd_line < signal_line and histogram < 0:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        # Check for crossover in last 5 days
        macd_series = macd_indicator.macd().iloc[-5:]
        signal_series = macd_indicator.macd_signal().iloc[-5:]
        crossover = "NONE"
        for i in range(1, len(macd_series)):
            if (macd_series.iloc[i-1] < signal_series.iloc[i-1] and
                    macd_series.iloc[i] > signal_series.iloc[i]):
                crossover = "BULLISH CROSSOVER (recent)"
            elif (macd_series.iloc[i-1] > signal_series.iloc[i-1] and
                  macd_series.iloc[i] < signal_series.iloc[i]):
                crossover = "BEARISH CROSSOVER (recent)"

        return {
            "macd_line": round(macd_line, 4),
            "signal_line": round(signal_line, 4),
            "histogram": round(histogram, 4),
            "signal": signal,
            "crossover": crossover,
        }

    def _bollinger_analysis(self, df: pd.DataFrame) -> dict:
        """Bollinger Bands analysis"""
        close = df['Close']
        bb = BollingerBands(close)

        upper = bb.bollinger_hband().iloc[-1]
        middle = bb.bollinger_mavg().iloc[-1]
        lower = bb.bollinger_lband().iloc[-1]
        current = close.iloc[-1]

        # Position within bands (0 = at lower, 1 = at upper)
        bb_position = (current - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
        bandwidth = ((upper - lower) / middle) * 100

        if bb_position > 0.95:
            signal = "ABOVE UPPER BAND - Overbought"
        elif bb_position > 0.8:
            signal = "NEAR UPPER BAND"
        elif bb_position > 0.5:
            signal = "ABOVE MIDDLE"
        elif bb_position > 0.2:
            signal = "BELOW MIDDLE"
        elif bb_position > 0.05:
            signal = "NEAR LOWER BAND"
        else:
            signal = "BELOW LOWER BAND - Oversold"

        return {
            "upper": round(upper, 2),
            "middle": round(middle, 2),
            "lower": round(lower, 2),
            "position": round(bb_position, 3),
            "bandwidth": round(bandwidth, 2),
            "signal": signal,
        }

    def _volume_analysis(self, df: pd.DataFrame) -> dict:
        """Volume analysis"""
        vol = df['Volume']
        avg_20 = vol.rolling(20).mean().iloc[-1]
        current_vol = vol.iloc[-1]
        ratio = current_vol / avg_20 if avg_20 > 0 else 1

        if ratio > 2:
            signal = "VERY HIGH VOLUME"
        elif ratio > 1.5:
            signal = "HIGH VOLUME"
        elif ratio > 0.8:
            signal = "NORMAL"
        elif ratio > 0.5:
            signal = "LOW VOLUME"
        else:
            signal = "VERY LOW VOLUME"

        return {
            "current_volume": int(current_vol),
            "avg_20_volume": int(avg_20) if not np.isnan(avg_20) else 0,
            "volume_ratio": round(ratio, 2),
            "signal": signal,
        }

    def _momentum_analysis(self, df: pd.DataFrame) -> dict:
        """Price momentum across timeframes"""
        close = df['Close']
        current = close.iloc[-1]

        periods = {
            "1_week": 5,
            "1_month": 21,
            "3_month": 63,
            "6_month": 126,
            "1_year": 252,
        }

        returns = {}
        for name, days in periods.items():
            if len(close) > days:
                past_price = close.iloc[-days]
                ret = ((current - past_price) / past_price) * 100
                returns[name] = round(ret, 2)
            else:
                returns[name] = None

        # 52-week high/low
        if len(close) >= 252:
            high_52w = close.iloc[-252:].max()
            low_52w = close.iloc[-252:].min()
        else:
            high_52w = close.max()
            low_52w = close.min()

        return {
            "returns": returns,
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "pct_from_52w_high": round(
                ((current - high_52w) / high_52w) * 100, 2
            ),
            "pct_from_52w_low": round(
                ((current - low_52w) / low_52w) * 100, 2
            ),
        }

    def _volatility_analysis(self, df: pd.DataFrame) -> dict:
        """Volatility metrics"""
        close = df['Close']
        returns = close.pct_change().dropna()

        daily_vol = returns.std()
        annual_vol = daily_vol * np.sqrt(252)

        atr = AverageTrueRange(df['High'], df['Low'], df['Close'])
        current_atr = atr.average_true_range().iloc[-1]

        # Max drawdown in last year
        if len(close) >= 252:
            recent = close.iloc[-252:]
        else:
            recent = close
        running_max = recent.cummax()
        drawdown = ((recent - running_max) / running_max) * 100
        max_drawdown = drawdown.min()

        if annual_vol < 0.15:
            risk_level = "LOW VOLATILITY"
        elif annual_vol < 0.25:
            risk_level = "MODERATE VOLATILITY"
        elif annual_vol < 0.40:
            risk_level = "HIGH VOLATILITY"
        else:
            risk_level = "VERY HIGH VOLATILITY"

        return {
            "daily_volatility": round(daily_vol * 100, 2),
            "annual_volatility": round(annual_vol * 100, 2),
            "atr": round(current_atr, 2),
            "max_drawdown_1y": round(max_drawdown, 2),
            "risk_level": risk_level,
        }

    def _support_resistance(self, df: pd.DataFrame) -> dict:
        """Basic support and resistance levels"""
        close = df['Close']
        high = df['High']
        low = df['Low']
        current = close.iloc[-1]

        recent_high = high.iloc[-20:].max()
        recent_low = low.iloc[-20:].min()

        # Simple pivot points
        pivot = (high.iloc[-1] + low.iloc[-1] + close.iloc[-1]) / 3
        support_1 = (2 * pivot) - high.iloc[-1]
        resistance_1 = (2 * pivot) - low.iloc[-1]
        support_2 = pivot - (high.iloc[-1] - low.iloc[-1])
        resistance_2 = pivot + (high.iloc[-1] - low.iloc[-1])

        return {
            "pivot": round(pivot, 2),
            "support_1": round(support_1, 2),
            "support_2": round(support_2, 2),
            "resistance_1": round(resistance_1, 2),
            "resistance_2": round(resistance_2, 2),
            "recent_high_20d": round(recent_high, 2),
            "recent_low_20d": round(recent_low, 2),
        }

    def _calculate_tech_score(self, analysis: dict) -> float:
        """Calculate composite technical score (0-100)"""
        score = 50  # Start neutral

        # Moving Average signals (+/- 15)
        ma = analysis.get("moving_averages", {})
        if ma.get("above_sma_200"):
            score += 8
        elif ma.get("above_sma_200") is False:
            score -= 8
        if ma.get("above_sma_50"):
            score += 5
        elif ma.get("above_sma_50") is False:
            score -= 5
        if ma.get("sma_50_above_200"):
            score += 5
        elif ma.get("sma_50_above_200") is False:
            score -= 5

        cross = ma.get("cross_signal", "NONE")
        if "GOLDEN" in cross:
            score += 10
        elif "DEATH" in cross:
            score -= 10

        # RSI signals (+/- 10)
        rsi_data = analysis.get("rsi", {})
        rsi = rsi_data.get("rsi_14")
        if rsi is not None:
            if 30 <= rsi <= 50:
                score += 8       # Good buying zone
            elif 50 < rsi <= 65:
                score += 5       # Healthy uptrend
            elif rsi < 30:
                score += 3       # Oversold (could bounce)
            elif rsi > 70:
                score -= 8       # Overbought

        # MACD signals (+/- 10)
        macd_data = analysis.get("macd", {})
        if macd_data.get("signal") == "BULLISH":
            score += 7
        elif macd_data.get("signal") == "BEARISH":
            score -= 7
        if "BULLISH" in macd_data.get("crossover", ""):
            score += 5
        elif "BEARISH" in macd_data.get("crossover", ""):
            score -= 5

        # Volume signals (+/- 5)
        vol = analysis.get("volume", {})
        vol_ratio = vol.get("volume_ratio", 1)
        if vol_ratio > 1.5:
            score += 3       # High volume confirms trend
        elif vol_ratio < 0.5:
            score -= 3       # Low volume is suspicious

        # Momentum signals (+/- 10)
        mom = analysis.get("momentum", {})
        returns = mom.get("returns", {})
        m3 = returns.get("3_month")
        if m3 is not None:
            if m3 > 15:
                score += 5
            elif m3 > 5:
                score += 3
            elif m3 < -15:
                score -= 5
            elif m3 < -5:
                score -= 3

        return max(0, min(100, round(score, 1)))