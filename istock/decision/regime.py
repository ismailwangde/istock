#!/usr/bin/env python3
"""
regime_detector.py - Market Regime Detection Engine
═══════════════════════════════════════════════════════
Detects current market regime from 5 observable signals and outputs:
  • A regime label (RISK_ON_TREND | RISK_ON_CHOP | TRANSITION | RISK_OFF | RECOVERY)
  • A regime_multiplier (0.3 to 1.5) for position_sizer.py
  • Weight-tilt recommendations for scoring_engine.py
  • A human-readable "why" explanation

Philosophy:
  • Pure data-driven (no subjective inputs)
  • Fail-soft (missing signals → lower confidence, never crash)
  • Cached (each regime check hits Yahoo once per session)
  • Stable (smoothed — won't flip on single-day noise)
  • Explainable (always show WHY)

Signals (Yahoo Finance):
  1. ^VIX           volatility index           (25%)
  2. SPY vs MA200   trend strength             (25%)
  3. SPY 20-DMA     slope / momentum            (15%)
  4. RSP vs SPY     breadth proxy              (20%)
  5. ^TNX - ^IRX    yield curve spread         (15%)

Author: Built for Ismail's Investment Analysis System
Usage:
    from core.regime_detector import get_current_regime
    reading = get_current_regime()
    print(reading.regime, reading.regime_multiplier)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

try:
    from ui.terminal_display import TerminalDisplay
except ImportError:
    # Fallback if trade_advisor not importable in test isolation
    class TerminalDisplay:
        GREEN = '\033[92m'
        RED = '\033[91m'
        YELLOW = '\033[93m'
        BLUE = '\033[94m'
        CYAN = '\033[96m'
        WHITE = '\033[97m'
        BOLD = '\033[1m'
        DIM = '\033[2m'
        RESET = '\033[0m'


# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

REGIME_MULTIPLIERS: Dict[str, float] = {
    "RISK_ON_TREND":  1.2,
    "RISK_ON_CHOP":   1.0,
    "TRANSITION":     0.7,
    "RISK_OFF":       0.4,
    "RECOVERY":       1.1,
}

REGIME_WEIGHT_TILTS: Dict[str, Dict[str, float]] = {
    "RISK_ON_TREND": {
        "momentum": +0.05, "mean_reversion": -0.05,
    },
    "RISK_ON_CHOP": {
        "momentum": -0.05, "mean_reversion": +0.05,
    },
    "TRANSITION": {
        "momentum": -0.10, "mean_reversion": 0.0, "risk": +0.10,
    },
    "RISK_OFF": {
        "momentum": -0.15, "mean_reversion": +0.10,
        "fundamental": +0.05,
    },
    "RECOVERY": {
        "momentum": -0.05, "mean_reversion": +0.10,
    },
}

REGIME_DESCRIPTIONS: Dict[str, List[str]] = {
    "RISK_ON_TREND": [
        "Size up good setups (1.2x normal)",
        "Favor momentum over mean-reversion",
        "Trail stops wider — trends persist",
    ],
    "RISK_ON_CHOP": [
        "Normal position sizing (1.0x)",
        "Favor mean-reversion over momentum",
        "Tighter stops — ranges break both ways",
    ],
    "TRANSITION": [
        "Reduce size (0.7x) — regime uncertain",
        "Tighten stops, avoid breakouts",
        "Increase weight on risk section",
    ],
    "RISK_OFF": [
        "Only A+ setups (0.4x size)",
        "Prefer quality + mean-reversion entries",
        "Raise cash, defensive posture",
    ],
    "RECOVERY": [
        "Aggressive on quality oversold (1.1x)",
        "Mean-reversion edge — fear unwinding",
        "Watch for regime confirmation",
    ],
}

SIGNAL_WEIGHTS: Dict[str, float] = {
    "vix":     0.22,
    "trend":   0.22,
    "slope":   0.13,
    "breadth": 0.16,
    "sector":  0.15,   # sector-ETF participation breadth (#5a)
    "curve":   0.12,
}

# The 11 SPDR sector ETFs — used for the sector-participation breadth signal.
# How many of these trade above their own 50-DMA tells us whether a move is
# broad (most sectors onside) or narrow (a handful of leaders carrying it).
SECTOR_ETFS: List[str] = [
    "XLK",  # Technology
    "XLF",  # Financials
    "XLV",  # Healthcare
    "XLE",  # Energy
    "XLI",  # Industrials
    "XLY",  # Consumer Discretionary
    "XLP",  # Consumer Staples
    "XLU",  # Utilities
    "XLB",  # Materials
    "XLRE", # Real Estate
    "XLC",  # Communication Services
]


# ══════════════════════════════════════════════════════════════
# DATA STRUCTURE
# ══════════════════════════════════════════════════════════════

@dataclass
class RegimeReading:
    """Full regime detection output"""
    # Core classification
    regime: str = "UNKNOWN"
    confidence: str = "LOW"

    # Trading implications
    regime_multiplier: float = 1.0
    weight_tilts: Dict[str, float] = field(default_factory=dict)

    # Raw signal values
    signals: Dict[str, float] = field(default_factory=dict)
    signal_scores: Dict[str, int] = field(default_factory=dict)

    # Explanation
    reasoning: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Metadata
    weighted_score: float = 0.0
    transition_flags: int = 0
    as_of: str = ""
    next_check_recommended: str = ""


# ══════════════════════════════════════════════════════════════
# REGIME DETECTOR
# ══════════════════════════════════════════════════════════════

class RegimeDetector:
    """Detects market regime from observable Yahoo signals."""

    def __init__(self, cache_minutes: int = 60):
        self._cache: Dict[str, tuple] = {}  # key → (timestamp, reading)
        self._cache_ttl = cache_minutes

    # ──────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────
    def detect(self, as_of_date: Optional[str] = None) -> RegimeReading:
        """Main entry point — classify current market regime."""
        cache_key = as_of_date or "today"

        # Cache check
        if cache_key in self._cache:
            ts, cached = self._cache[cache_key]
            age = (datetime.now() - ts).total_seconds() / 60
            if age < self._cache_ttl:
                return cached

        reading = self._compute(as_of_date)
        self._cache[cache_key] = (datetime.now(), reading)
        return reading

    # ──────────────────────────────────────────────────────
    # Core computation
    # ──────────────────────────────────────────────────────
    def _compute(self, as_of_date: Optional[str]) -> RegimeReading:
        reading = RegimeReading(
            as_of=as_of_date or datetime.now().strftime("%Y-%m-%d"),
            next_check_recommended=(datetime.now() + timedelta(days=1))
                                   .strftime("%Y-%m-%d"),
        )

        # ── Fetch all data (fail-soft) ──
        spy_df = self._fetch_history("SPY", "1y")
        vix_df = self._fetch_history("^VIX", "3mo")
        rsp_df = self._fetch_history("RSP", "3mo")
        tnx_df = self._fetch_history("^TNX", "5d")
        irx_df = self._fetch_history("^IRX", "5d")

        # ── Compute each signal ──
        vix_score, vix_val, vix_20d = self._signal_vix(vix_df, reading)
        trend_score, trend_pct = self._signal_trend(spy_df, reading)
        slope_score, slope_pct = self._signal_slope(spy_df, reading)
        breadth_score, breadth_diff = self._signal_breadth(
            spy_df, rsp_df, reading)
        sector_score, sector_frac = self._signal_sector(reading)
        curve_score, curve_spread = self._signal_curve(tnx_df, irx_df, reading)

        # ── Store raw signals & scores ──
        reading.signals = {
            "vix": vix_val,
            "vix_20d_avg": vix_20d,
            "spy_vs_ma200_pct": trend_pct,
            "spy_20dma_slope_pct": slope_pct,
            "breadth_diff_pct": breadth_diff * 100 if breadth_diff is not None else None,
            "sector_above_50dma_pct": sector_frac * 100 if sector_frac is not None else None,
            "yield_curve_spread": curve_spread,
        }
        reading.signal_scores = {
            "vix":     vix_score,
            "trend":   trend_score,
            "slope":   slope_score,
            "breadth": breadth_score,
            "sector":  sector_score,
            "curve":   curve_score,
        }

        # ── Compute weighted score (skip None signals, renormalize weights) ──
        weighted_score, signals_available = self._weighted_score(
            reading.signal_scores)
        reading.weighted_score = round(weighted_score, 3)

        # ── Check transition flags ──
        transition_flags = self._count_transition_flags(
            vix_val, vix_20d, trend_score, breadth_score,
            curve_score, reading.signal_scores)
        reading.transition_flags = transition_flags

        # ── Classify regime ──
        reading.regime = self._classify_regime(
            weighted_score, transition_flags,
            vix_score, trend_score, slope_score,
            vix_val, vix_20d)

        # ── Apply regime outputs ──
        reading.regime_multiplier = REGIME_MULTIPLIERS.get(reading.regime, 1.0)
        reading.weight_tilts = REGIME_WEIGHT_TILTS.get(reading.regime, {}).copy()

        # ── Determine confidence ──
        reading.confidence = self._confidence(
            signals_available, abs(weighted_score))

        # ── Build human-readable reasoning ──
        self._build_reasoning(reading)

        return reading

    # ──────────────────────────────────────────────────────
    # Data fetching (fail-soft)
    # ──────────────────────────────────────────────────────
    def _fetch_history(self, symbol: str, period: str) -> Optional[pd.DataFrame]:
        """Fetch yfinance history; return None + warn on failure."""
        try:
            df = yf.Ticker(symbol).history(period=period)
            if df is None or df.empty or "Close" not in df.columns:
                return None
            return df
        except Exception:
            return None

    # ──────────────────────────────────────────────────────
    # Signal 1: VIX
    # ──────────────────────────────────────────────────────
    def _signal_vix(self, vix_df: Optional[pd.DataFrame],
                    reading: RegimeReading) -> tuple:
        if vix_df is None or len(vix_df) < 1:
            reading.warnings.append("⚠️ VIX data unavailable")
            return None, None, None

        try:
            vix = float(vix_df["Close"].iloc[-1])
            vix_20d = float(vix_df["Close"].tail(20).mean()) \
                if len(vix_df) >= 20 else vix

            if vix < 15:    score = +2
            elif vix < 20:  score = +1
            elif vix < 25:  score = 0
            elif vix < 35:  score = -1
            else:           score = -2

            return score, round(vix, 2), round(vix_20d, 2)
        except Exception:
            reading.warnings.append("⚠️ VIX parse error")
            return None, None, None

    # ──────────────────────────────────────────────────────
    # Signal 2: SPY vs 200-DMA
    # ──────────────────────────────────────────────────────
    def _signal_trend(self, spy_df: Optional[pd.DataFrame],
                      reading: RegimeReading) -> tuple:
        if spy_df is None or len(spy_df) < 200:
            reading.warnings.append("⚠️ SPY trend (MA200) unavailable")
            return None, None

        try:
            spy = spy_df["Close"]
            ma200 = spy.rolling(200).mean().iloc[-1]
            current = spy.iloc[-1]
            if pd.isna(ma200) or ma200 == 0:
                return None, None

            pct = (current - ma200) / ma200 * 100

            if pct > 5:      score = +2
            elif pct > 0:    score = +1
            elif pct > -5:   score = -1
            elif pct > -15:  score = -2
            else:            score = -3

            return score, round(float(pct), 2)
        except Exception:
            reading.warnings.append("⚠️ SPY trend parse error")
            return None, None

    # ──────────────────────────────────────────────────────
    # Signal 3: SPY 20-DMA slope
    # ──────────────────────────────────────────────────────
    def _signal_slope(self, spy_df: Optional[pd.DataFrame],
                      reading: RegimeReading) -> tuple:
        if spy_df is None or len(spy_df) < 31:
            reading.warnings.append("⚠️ SPY 20-DMA slope unavailable")
            return None, None

        try:
            ma20 = spy_df["Close"].rolling(20).mean()
            now = ma20.iloc[-1]
            then = ma20.iloc[-11]  # 10 days ago
            if pd.isna(now) or pd.isna(then) or then == 0:
                return None, None

            slope_pct = (now - then) / then * 100

            if slope_pct > 2:     score = +2
            elif slope_pct > 0:   score = +1
            elif slope_pct > -2:  score = -1
            else:                 score = -2

            return score, round(float(slope_pct), 2)
        except Exception:
            reading.warnings.append("⚠️ SPY slope parse error")
            return None, None

    # ──────────────────────────────────────────────────────
    # Signal 4: Breadth (RSP vs SPY)
    # ──────────────────────────────────────────────────────
    def _signal_breadth(self, spy_df: Optional[pd.DataFrame],
                        rsp_df: Optional[pd.DataFrame],
                        reading: RegimeReading) -> tuple:
        if spy_df is None or rsp_df is None \
                or len(spy_df) < 22 or len(rsp_df) < 22:
            reading.warnings.append(
                "⚠️ Breadth (RSP vs SPY) unavailable — confidence capped at MEDIUM")
            return None, None

        try:
            spy_1m = spy_df["Close"].pct_change(21).iloc[-1]
            rsp_1m = rsp_df["Close"].pct_change(21).iloc[-1]
            if pd.isna(spy_1m) or pd.isna(rsp_1m):
                return None, None

            diff = rsp_1m - spy_1m  # positive = broad rally

            if diff > 0.01:     score = +2
            elif diff > 0:      score = +1
            elif diff > -0.01:  score = -1
            else:               score = -2

            return score, float(diff)
        except Exception:
            reading.warnings.append("⚠️ Breadth parse error")
            return None, None

    # ──────────────────────────────────────────────────────
    # Signal 5: Sector participation breadth (#5a)
    # ──────────────────────────────────────────────────────
    def _signal_sector(self, reading: RegimeReading) -> tuple:
        """Fraction of the 11 SPDR sector ETFs trading above their own 50-DMA.
        Broad participation (most sectors onside) = healthy risk-on; a narrow
        tape (few sectors carrying the index) = fragile. Served from the OHLC
        cache so the 11 reads are cheap on repeat detects."""
        try:
            from istock.data.ohlc_cache import get_or_update_daily
        except Exception:
            reading.warnings.append("⚠️ Sector breadth unavailable (cache import)")
            return None, None

        above = 0
        counted = 0
        for etf in SECTOR_ETFS:
            try:
                df = get_or_update_daily(etf)
                if df is None or df.empty or len(df) < 50 or "Close" not in df.columns:
                    continue
                ma50 = df["Close"].rolling(50).mean().iloc[-1]
                last = df["Close"].iloc[-1]
                if pd.isna(ma50) or ma50 == 0:
                    continue
                counted += 1
                if last > ma50:
                    above += 1
            except Exception:
                continue

        # Need a quorum of sectors to trust the reading.
        if counted < 6:
            reading.warnings.append(
                "⚠️ Sector breadth unavailable (too few sector ETFs fetched)")
            return None, None

        frac = above / counted

        if frac >= 0.70:    score = +2     # broad participation
        elif frac >= 0.55:  score = +1
        elif frac >= 0.40:  score = -1
        elif frac >= 0.25:  score = -2
        else:               score = -3     # almost everything below its 50-DMA

        return score, round(float(frac), 3)

    # ──────────────────────────────────────────────────────
    # Signal 6: Yield curve (10Y - 3M)
    # ──────────────────────────────────────────────────────
    def _signal_curve(self, tnx_df: Optional[pd.DataFrame],
                      irx_df: Optional[pd.DataFrame],
                      reading: RegimeReading) -> tuple:
        if tnx_df is None or irx_df is None \
                or len(tnx_df) < 1 or len(irx_df) < 1:
            reading.warnings.append("⚠️ Yield curve unavailable")
            return None, None

        try:
            tnx = float(tnx_df["Close"].iloc[-1])  # 10Y
            irx = float(irx_df["Close"].iloc[-1])  # 3M
            spread = tnx - irx

            if spread > 1.5:     score = +2
            elif spread > 0.5:   score = +1
            elif spread > 0:     score = 0
            elif spread > -1:    score = -1
            else:                score = -2

            return score, round(spread, 3)
        except Exception:
            reading.warnings.append("⚠️ Yield curve parse error")
            return None, None

    # ──────────────────────────────────────────────────────
    # Weighted score (renormalize missing signals)
    # ──────────────────────────────────────────────────────
    def _weighted_score(self, scores: Dict[str, Optional[int]]) -> tuple:
        total_weight = 0.0
        acc = 0.0
        available = 0

        for key, weight in SIGNAL_WEIGHTS.items():
            val = scores.get(key)
            if val is not None:
                acc += val * weight
                total_weight += weight
                available += 1

        if total_weight == 0:
            return 0.0, 0

        # Renormalize so score stays comparable when signals missing
        normalized = acc / total_weight * sum(SIGNAL_WEIGHTS.values())
        return normalized, available

    # ──────────────────────────────────────────────────────
    # Transition flag detection
    # ──────────────────────────────────────────────────────
    def _count_transition_flags(self, vix_val, vix_20d,
                                trend_score, breadth_score,
                                curve_score, scores) -> int:
        flags = 0
        # Flag 1: VIX spike (>= 1.5x its 20-day average)
        if vix_val is not None and vix_20d is not None and vix_20d > 0:
            if vix_val > vix_20d * 1.5:
                flags += 1

        # Flag 2: narrow rally (positive trend + negative breadth)
        if (trend_score is not None and trend_score > 0
                and breadth_score is not None and breadth_score < 0):
            flags += 1

        # Flag 3: inverted curve + elevated VIX
        if (curve_score is not None and curve_score <= -1
                and vix_val is not None and vix_val > 20):
            flags += 1

        return flags

    # ──────────────────────────────────────────────────────
    # Regime classification
    # ──────────────────────────────────────────────────────
    def _classify_regime(self, weighted_score: float, transition_flags: int,
                         vix_score, trend_score, slope_score,
                         vix_val, vix_20d) -> str:
        # TRANSITION takes priority when flags fire
        if transition_flags >= 2:
            return "TRANSITION"

        if weighted_score >= 1.0:
            return "RISK_ON_TREND"

        if weighted_score >= 0.3:
            if (vix_score is not None and vix_score > 0
                    and slope_score is not None and slope_score < 1):
                return "RISK_ON_CHOP"
            return "RISK_ON_TREND"

        if weighted_score >= -0.5:
            return "RISK_ON_CHOP"

        if weighted_score >= -1.5:
            # Negative but possibly improving — RECOVERY?
            if (vix_val is not None and vix_20d is not None
                    and vix_20d > 0 and vix_val < vix_20d * 0.8
                    and slope_score is not None and slope_score > 0):
                return "RECOVERY"
            return "TRANSITION"

        return "RISK_OFF"

    # ──────────────────────────────────────────────────────
    # Confidence
    # ──────────────────────────────────────────────────────
    def _confidence(self, signals_available: int,
                    abs_score: float) -> str:
        breadth_ok = signals_available == 5
        if breadth_ok and abs_score > 1.0:
            return "HIGH"
        if signals_available >= 4 and abs_score > 0.5:
            return "MEDIUM"
        return "LOW"

    # ──────────────────────────────────────────────────────
    # Build reasoning text
    # ──────────────────────────────────────────────────────
    def _build_reasoning(self, r: RegimeReading):
        s = r.signals
        sc = r.signal_scores

        def label(key: str) -> str:
            v = sc.get(key)
            if v is None:
                return "N/A"
            return f"[{v:+d}]"

        if s.get("vix") is not None:
            vix_desc = ("calm" if s["vix"] < 15 else
                        "normal" if s["vix"] < 20 else
                        "elevated" if s["vix"] < 25 else
                        "stressed" if s["vix"] < 35 else "panic")
            r.reasoning.append(
                f"VIX {s['vix']:.1f} ({vix_desc}) {label('vix')}")

        if s.get("spy_vs_ma200_pct") is not None:
            p = s["spy_vs_ma200_pct"]
            t_desc = ("strong uptrend" if p > 5 else
                      "mild uptrend" if p > 0 else
                      "mild downtrend" if p > -5 else
                      "strong downtrend" if p > -15 else "crash")
            r.reasoning.append(
                f"SPY vs MA200: {p:+.1f}% ({t_desc}) {label('trend')}")

        if s.get("spy_20dma_slope_pct") is not None:
            sl = s["spy_20dma_slope_pct"]
            sl_desc = ("rising" if sl > 0 else "falling")
            r.reasoning.append(
                f"20-DMA slope: {sl:+.2f}% ({sl_desc}) {label('slope')}")

        if s.get("breadth_diff_pct") is not None:
            b = s["breadth_diff_pct"]
            b_desc = ("broad rally" if b > 1 else
                      "healthy" if b > 0 else
                      "narrowing" if b > -1 else "very narrow")
            r.reasoning.append(
                f"Breadth (RSP-SPY 1M): {b:+.2f}% ({b_desc}) {label('breadth')}")

        if s.get("sector_above_50dma_pct") is not None:
            sp = s["sector_above_50dma_pct"]
            sp_desc = ("broad" if sp >= 70 else
                       "healthy" if sp >= 55 else
                       "mixed" if sp >= 40 else
                       "narrow" if sp >= 25 else "very narrow")
            r.reasoning.append(
                f"Sector breadth: {sp:.0f}% of sectors > 50-DMA ({sp_desc}) "
                f"{label('sector')}")

        if s.get("yield_curve_spread") is not None:
            c = s["yield_curve_spread"]
            c_desc = ("healthy" if c > 1.5 else
                      "mildly positive" if c > 0.5 else
                      "flat" if c > 0 else
                      "inverted" if c > -1 else "deeply inverted")
            r.reasoning.append(
                f"Yield curve (10Y-3M): {c:+.2f}% ({c_desc}) {label('curve')}")

        r.reasoning.append(
            f"Weighted score: {r.weighted_score:+.2f} "
            f"({r.transition_flags} transition flag"
            f"{'s' if r.transition_flags != 1 else ''})")

    # ──────────────────────────────────────────────────────
    # Terminal display
    # ──────────────────────────────────────────────────────
    def format_for_terminal(self, reading: RegimeReading) -> str:
        """Colored terminal display matching TerminalDisplay style."""
        C = TerminalDisplay
        lines = []

        # Color by regime
        regime_colors = {
            "RISK_ON_TREND": C.GREEN,
            "RISK_ON_CHOP":  C.YELLOW,
            "TRANSITION":    C.YELLOW,
            "RISK_OFF":      C.RED,
            "RECOVERY":      C.CYAN,
        }
        regime_emojis = {
            "RISK_ON_TREND": "🟢",
            "RISK_ON_CHOP":  "🟡",
            "TRANSITION":    "⚠️ ",
            "RISK_OFF":      "🔴",
            "RECOVERY":      "🔄",
        }
        rc = regime_colors.get(reading.regime, C.WHITE)
        em = regime_emojis.get(reading.regime, "❔")

        lines.append("")
        lines.append(f"{C.BOLD}╔{'═'*62}╗{C.RESET}")
        lines.append(f"{C.BOLD}║  🌊 MARKET REGIME: {rc}{reading.regime:<20}{C.RESET}"
                     f"{C.BOLD} {em}   {reading.as_of:>15}  ║{C.RESET}")
        lines.append(f"{C.BOLD}║  Confidence: {reading.confidence:<8}│ "
                     f"Position Multiplier: {reading.regime_multiplier:.2f}x"
                     f"{' ':<14}║{C.RESET}")
        lines.append(f"{C.BOLD}╠{'═'*62}╣{C.RESET}")

        s = reading.signals
        sc = reading.signal_scores

        def fmt_row(label_str: str, value_str: str, score) -> str:
            score_str = f"[{score:+d}]" if score is not None else "[N/A]"
            # color score
            if score is None:
                scolor = C.DIM
            elif score > 0:
                scolor = C.GREEN
            elif score < 0:
                scolor = C.RED
            else:
                scolor = C.YELLOW
            content = f"  {label_str:<16} {value_str:<24} "
            pad = 62 - len(content) - len(score_str) - 2
            return (f"{C.BOLD}║{content}{scolor}{score_str}{C.RESET}"
                    f"{C.BOLD}{' '*max(pad,1)}║{C.RESET}")

        # VIX row
        if s.get("vix") is not None:
            lines.append(fmt_row(
                "VIX:",
                f"{s['vix']:.2f} (20d avg {s.get('vix_20d_avg', 0):.1f})",
                sc.get("vix")))
        else:
            lines.append(fmt_row("VIX:", "unavailable", None))

        # Trend row
        if s.get("spy_vs_ma200_pct") is not None:
            lines.append(fmt_row(
                "SPY vs MA200:",
                f"{s['spy_vs_ma200_pct']:+.2f}%",
                sc.get("trend")))
        else:
            lines.append(fmt_row("SPY vs MA200:", "unavailable", None))

        # Slope row
        if s.get("spy_20dma_slope_pct") is not None:
            lines.append(fmt_row(
                "20-DMA Slope:",
                f"{s['spy_20dma_slope_pct']:+.2f}%",
                sc.get("slope")))
        else:
            lines.append(fmt_row("20-DMA Slope:", "unavailable", None))

        # Breadth row
        if s.get("breadth_diff_pct") is not None:
            lines.append(fmt_row(
                "Breadth (RSP-SPY):",
                f"{s['breadth_diff_pct']:+.2f}%",
                sc.get("breadth")))
        else:
            lines.append(fmt_row("Breadth:", "unavailable", None))

        # Curve row
        if s.get("yield_curve_spread") is not None:
            lines.append(fmt_row(
                "Yield Curve:",
                f"{s['yield_curve_spread']:+.2f}% (10Y-3M)",
                sc.get("curve")))
        else:
            lines.append(fmt_row("Yield Curve:", "unavailable", None))

        lines.append(f"{C.BOLD}║{' '*62}║{C.RESET}")
        lines.append(f"{C.BOLD}║  Weighted Score: "
                     f"{rc}{reading.weighted_score:+.2f}{C.RESET}"
                     f"{C.BOLD}  │  Transition Flags: "
                     f"{reading.transition_flags}/3"
                     f"{' ':<19}║{C.RESET}")
        lines.append(f"{C.BOLD}╠{'─'*62}╣{C.RESET}")
        lines.append(f"{C.BOLD}║  📋 TRADING IMPLICATIONS:{' ':<37}║{C.RESET}")
        for impl in REGIME_DESCRIPTIONS.get(reading.regime, []):
            lines.append(f"{C.BOLD}║    • {impl:<55}║{C.RESET}")

        # Weight tilts
        if reading.weight_tilts:
            lines.append(f"{C.BOLD}║{' '*62}║{C.RESET}")
            lines.append(f"{C.BOLD}║  ⚖️  SCORING WEIGHT TILTS:"
                         f"{' ':<36}║{C.RESET}")
            for k, v in reading.weight_tilts.items():
                sign = "+" if v >= 0 else ""
                entry = f"    • {k:<18} {sign}{v:+.2f}"
                lines.append(f"{C.BOLD}║  {entry:<60}║{C.RESET}")

        lines.append(f"{C.BOLD}╚{'═'*62}╝{C.RESET}")

        # Warnings (outside box)
        if reading.warnings:
            lines.append("")
            lines.append(f"  {C.YELLOW}{C.BOLD}⚠️  DATA WARNINGS:{C.RESET}")
            for w in reading.warnings:
                lines.append(f"     {C.YELLOW}{w}{C.RESET}")

        # Reasoning
        if reading.reasoning:
            lines.append("")
            lines.append(f"  {C.BOLD}🧠 WHY THIS REGIME:{C.RESET}")
            for r in reading.reasoning:
                lines.append(f"     • {r}")

        lines.append("")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS (integration hooks)
# ══════════════════════════════════════════════════════════════

_GLOBAL_DETECTOR: Optional[RegimeDetector] = None


def _detector() -> RegimeDetector:
    """Lazily instantiate a module-level detector for the convenience API."""
    global _GLOBAL_DETECTOR
    if _GLOBAL_DETECTOR is None:
        _GLOBAL_DETECTOR = RegimeDetector(cache_minutes=60)
    return _GLOBAL_DETECTOR


def get_current_regime() -> RegimeReading:
    """One-liner for other modules."""
    return _detector().detect()


def get_regime_multiplier() -> float:
    """For position_sizer.py"""
    try:
        return get_current_regime().regime_multiplier
    except Exception:
        return 1.0  # fail-safe neutral


def get_regime_weight_tilts() -> Dict[str, float]:
    """For scoring_engine.py"""
    try:
        return get_current_regime().weight_tilts
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("  📡 Fetching market regime data...")
    detector = RegimeDetector()
    reading = detector.detect()
    print(detector.format_for_terminal(reading))