"""Shared dataclasses and configuration used across the analysis pipeline."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class CheckItem:
    """Single checklist item result"""
    name: str
    passed: bool
    detail: str
    weight: float = 1.0     # importance within its section
    value: float = 0.0      # raw numeric value if applicable


@dataclass
class SectionResult:
    """Result of one analysis section"""
    name: str
    score: float            # 0-100
    max_score: float = 100
    checks: List[CheckItem] = field(default_factory=list)
    summary: str = ""


@dataclass
class PriceLevel:
    """A support or resistance level"""
    price: float
    level_type: str         # 'support' or 'resistance'
    strength: int           # 1-5 (how many times tested)
    source: str             # 'swing', 'pivot', 'fibonacci', 'volume', 'ma'
    distance_pct: float = 0 # distance from current price


class TradeConfig:
    """All tunable parameters in one place."""

    # Trend
    MA_SHORT = 20
    MA_MID = 50
    MA_LONG = 200
    ADX_STRONG_TREND = 25
    ADX_VERY_STRONG = 40
    HIGHER_HIGH_LOOKBACK = 5

    # Location / Support-Resistance
    SR_SWING_WINDOW = 10
    SR_CLUSTER_PCT = 1.5
    NEAR_SUPPORT_PCT = 3.0
    NEAR_RESISTANCE_PCT = 3.0
    DEAD_ZONE_PCT = 40

    # Pullback
    PULLBACK_MIN_PCT = 2.0
    PULLBACK_MAX_PCT = 12.0
    PULLBACK_MA_TOUCH_PCT = 1.5

    # Breakout
    BREAKOUT_CONFIRM_PCT = 0.5
    BREAKOUT_VOLUME_MULT = 1.5
    MAX_UPPER_WICK_PCT = 40

    # Volume
    VOLUME_AVG_PERIOD = 20
    VOLUME_SPIKE_MULT = 2.0
    VOLUME_HIGH_MULT = 1.3

    # Momentum
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    RSI_HEALTHY_LOW = 40
    RSI_HEALTHY_HIGH = 60
    RSI_BULLISH_ZONE = 55

    # Risk Management
    MIN_RISK_REWARD = 2.0
    MAX_STOP_DISTANCE_PCT = 8.0
    ATR_STOP_MULTIPLIER = 2.0
    ATR_PERIOD = 14

    # Avoid Conditions
    SPIKE_THRESHOLD_PCT = 5.0
    WICK_REJECTION_COUNT = 3
    CHOPPY_ADX_THRESHOLD = 20

    # Scoring Weights (must sum to 100)
    WEIGHTS = {
        'trend': 18,
        'location': 20,
        'setup': 15,
        'volume': 10,
        'momentum': 15,
        'candles': 7,
        'risk_reward': 10,
        'market_context': 5,
    }

    # Decision Thresholds
    STRONG_BUY_SCORE = 75
    BUY_SCORE = 60
    LEAN_BUY_SCORE = 50
    HOLD_SCORE = 40
    LEAN_SELL_SCORE = 30
    SELL_SCORE = 20

    # Loss Tolerance
    MAX_LOSS_PCT = 5.0
    MAX_LOSS_AMOUNT = 2500
    TOTAL_PORTFOLIO_MAX_LOSS = 10000
    TRAILING_STOP_PCT = 3.0

    # Monitoring
    REFRESH_INTERVAL_MINUTES = 0.5
    MARKET_HOURS_ONLY = True
    INDIA_MARKET_OPEN = (9, 15)
    INDIA_MARKET_CLOSE = (15, 30)
    US_MARKET_OPEN_IST = (19, 0)
    US_MARKET_CLOSE_IST = (1, 30)

    # Alerts
    ENABLE_SOUND_ALERT = True
    ENABLE_TELEGRAM = False
    TELEGRAM_BOT_TOKEN = ""
    TELEGRAM_CHAT_ID = ""

    USD_TO_INR = 95


@dataclass
class TradeSetup:
    """Detected trade setup."""
    setup_type: str         # 'pullback', 'breakout', 'reversal', 'bounce', 'none'
    confidence: float
    entry: float
    stop_loss: float
    targets: List[float]
    risk_reward: float
    risk_pct: float
    description: str


@dataclass
class FullAnalysis:
    """Complete analysis result returned by the advisor."""
    symbol: str
    company_name: str
    current_price: float
    previous_close: float
    day_change_pct: float

    verdict: str            # 'STRONG BUY', 'BUY', 'LEAN BUY', 'HOLD', 'LEAN SELL', 'SELL', 'AVOID'
    buy_score: float        # 0-100
    sell_score: float
    net_score: float
    confidence: str         # 'HIGH', 'MEDIUM', 'LOW'

    setup: TradeSetup
    sections: Dict[str, SectionResult] = field(default_factory=dict)

    support_levels: List[PriceLevel] = field(default_factory=list)
    resistance_levels: List[PriceLevel] = field(default_factory=list)
    fibonacci_levels: Dict[str, float] = field(default_factory=dict)

    avoid_flags: List[str] = field(default_factory=list)
    key_observations: List[str] = field(default_factory=list)

    weekly_trend: str = ""
    daily_trend: str = ""
    sector: str = ""
    market_cap: str = ""
    timestamp: str = ""

    # v2 scoring fields
    v2_verdict: Optional[str] = None
    v2_score: Optional[float] = None
    v2_source: Optional[str] = None
    v2_vix_guardrail_applied: Optional[bool] = None
    v2_skipped_reason: Optional[str] = None
