# → istock/config.py  (move the whole file — stays at package root)
"""
config.py - UPDATED: Fixed tickers and added market context settings
"""

USER_PROFILE = {
    "name": "Investor",
    "monthly_investment": 25000,
    "risk_score": 7.5,
    "investment_horizon_years": 15,
    "risk_category": "AGGRESSIVE",
    "currency": "INR",
    "usd_inr_rate": 85.5,
}

CURRENT_HOLDINGS = [
    {
        "symbol": "VDE",
        "name": "Energy ETF Vanguard",
        "type": "ETF",
        "market": "US",
        "trades": [
            {"date": "2026-03-30", "qty": 2.71, "price_usd": 477.5, "action": "BUY"},
            # Add future buys here:
            # {"date": "2026-04-15", "qty": 0.03, "price_usd": 580.00, "action": "BUY"},
        ],
        "notes": "Energy"
    },

]

# ============================================================
# BACKTEST UNIVERSE
# Liquid large-cap stocks across sectors for strategy testing.
# ETFs are excluded here — mean-reversion signals need individual
# stock volatility, not diversified baskets.
# ============================================================
BACKTEST_UNIVERSE = {
    "US_LIQUID_LARGECAP": [
        # Tech
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
        "AMD", "CRM", "ADBE", "ORCL", "CSCO",
        # Financials
        "JPM", "BAC", "WFC", "GS", "MS", "BLK", "C",
        # Healthcare
        "JNJ", "PFE", "UNH", "ABBV", "LLY", "MRK", "TMO",
        # Energy
        "XOM", "CVX", "COP", "SLB",
        # Consumer
        "WMT", "HD", "COST", "NKE", "MCD", "SBUX", "TGT",
        # Payments / Media
        "V", "MA", "PYPL", "DIS", "NFLX",
        # Staples
        "KO", "PEP", "PG", "CL",
        # Industrials
        "BA", "CAT", "GE", "HON", "UPS",
    ],
    "INDIA_NIFTY_LIQUID": [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS",
        "INFY.NS", "HINDUNILVR.NS", "ITC.NS", "SBIN.NS",
        "BHARTIARTL.NS", "KOTAKBANK.NS", "LT.NS", "AXISBANK.NS",
        "ASIANPAINT.NS", "MARUTI.NS", "BAJFINANCE.NS",
        "HCLTECH.NS", "WIPRO.NS", "ULTRACEMCO.NS",
        "TITAN.NS", "NESTLEIND.NS", "SUNPHARMA.NS",
        "POWERGRID.NS", "NTPC.NS", "M&M.NS",
        "TATAMOTORS.NS", "JSWSTEEL.NS", "TATASTEEL.NS",
        "ADANIENT.NS", "ADANIPORTS.NS", "GRASIM.NS",
        "DRREDDY.NS", "CIPLA.NS", "BAJAJFINSV.NS",
        "HDFCLIFE.NS", "SBILIFE.NS", "BRITANNIA.NS",
        "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS",
        "INDUSINDBK.NS",
    ],
}

# Transaction cost assumptions (applied in backtester)
TRANSACTION_COSTS = {
    "commission_pct":    0.0005,   # 0.05% per side (brokerage + STT/SEC)
    "slippage_pct":      0.0010,   # 0.10% per side (market impact)
    "total_round_trip":  0.0030,   # 0.30% total round-trip drag
}

# ============================================================
# SIP / MUTUAL FUND HOLDINGS
# Update monthly as you invest
# ============================================================
SIP_HOLDINGS = [
    # Uncomment and update as you start SIPs
    # {
    #     "name": "UTI Nifty 50 Index Fund",
    #     "symbol": None,
    #     "type": "MUTUAL_FUND",
    #     "category": "Equity",
    #     "market": "INDIA",
    #     "monthly_sip": 5000,
    #     "invested": 5000,        # Total invested so far
    #     "current_value": 5000,   # Check on your app
    #     "units": None,
    #     "months_invested": 1,
    # },

]

TARGET_ALLOCATION = {
    "indian_equity": 0.30,
    "us_equity": 0.60,
    "gold": 0.08,
    "cash": 0.02,
}

WATCHLIST = {
    "us_etfs_core": [
        "VOO",      # S&P 500
        "QQQ",      # Nasdaq 100
        "VTI",      # Total Market
        "SCHD",     # Dividend Growth
        "VUG",      # Growth
        "VTV",      # Value
        "BNO",      # Growth
        "OILU",      # Value
    ],
    # "us_etfs_sector": [
    #     "XLK",      # Technology
    #     "XLV",      # Healthcare
    #     "XLF",      # Financials
    #     "SOXX",     # Semiconductors
    #     "XLE",      # Energy
    #     "XLI",      # Industrials
    #     "XLY",      # Consumer Disc
    #     "XLP",      # Consumer Staples
    # ],

}

# ============================================================
# SCANNER UNIVERSE — single source of truth.
# Used by ui/app.py (Picks page scanner) and
# scripts/advisor_backtester.py (backtest universe).
# ============================================================
SCANNER_UNIVERSE_BASE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
    "LLY", "AVGO", "JPM", "V", "WMT", "XOM", "UNH", "MA", "HD", "PG",
    "COST", "JNJ", "ORCL", "ABBV", "BAC", "MRK", "CVX", "KO", "NFLX",
    "AMD", "CRM", "PEP", "TMO", "ADBE", "LIN", "ACN", "CSCO", "WFC",
    "MCD", "ABT", "DHR", "INTC", "IBM", "GS", "CAT", "QCOM", "TXN",
    "UPS", "HON", "NOW", "NEE", "PM",
    # Session 14: tickers the user has actively traded.
    "BE", "FANUY", "MU", "PCRHY", "SNDK", "STX", "WDC",
]


SCORING_WEIGHTS = {
    "fundamental":    0.25,   # quality baseline (always matters)
    "technical":      0.20,   # MA alignment + structure (Trend Follow best Sharpe)
    "valuation":      0.10,   # less decisive in trending markets
    "risk":           0.10,   # drawdown control
    "momentum":       0.20,   # RESTORED — 0.95 Sharpe in this regime
    "mean_reversion": 0.15,   # kept (quality-gated) as diversifier
}

THRESHOLDS = {
    "buy_score_min": 68,
    "sell_score_max": 32,
    "stop_loss_pct": -15,
    "trailing_stop_pct": -12,
    "rebalance_drift_pct": 5,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "min_volume_avg_ratio": 0.5,
}

# ============================================================
# MARKET REGIME THRESHOLDS
# ============================================================
MARKET_REGIME = {
    "vix_calm": 15,
    "vix_normal": 20,
    "vix_elevated": 25,
    "vix_panic": 35,
    "bull_threshold": 0,       # Index above 200 DMA
    "bear_threshold": -10,     # Index 10%+ below 200 DMA
}

# ============================================================
# FRED API (Optional - for deeper macro analysis)
# Get free key at: https://fred.stlouisfed.org/docs/api/api_key.html
# ============================================================
FRED_API_KEY = None    # Set to "your_key_here" after getting key

# ============================================================
# ALERT CONFIGURATION
# ============================================================
ALERTS_CONFIG = {
    # Telegram (recommended)
    "telegram_enabled": False,
    "telegram_bot_token": "YOUR_BOT_TOKEN_HERE",
    "telegram_chat_id": "YOUR_CHAT_ID_HERE",

    # Email
    "email_enabled": False,          # Set True after setup
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "your.email@gmail.com",
    "sender_password": "xxxx xxxx xxxx xxxx",  # App password
    "receiver_email": "your.email@gmail.com",  # Can be same

    # Alert Thresholds
    "daily_drop_alert_pct": -5,      # Alert if holding drops 5%+
    "daily_surge_alert_pct": 8,      # Alert if holding surges 8%+
    "vix_panic_threshold": 30,
    "rsi_overbought_alert": 78,
    "rsi_oversold_alert": 28,
    "score_danger_threshold": 35,
}

# ============================================================
# SCHEDULE CONFIGURATION
# ============================================================
SCHEDULE_CONFIG = {
    "daily_alert_time": "18:30",     # 6:30 PM IST
    "weekly_report_day": "sunday",
    "weekly_report_time": "10:00",   # 10 AM IST Sunday
}