"""
config.py - UPDATED: Fixed tickers and added market context settings
"""

# ============================================================
# FEATURE FLAGS
# ============================================================
# Position sizing is gated off everywhere (deep-dive display, picks/tracker,
# and the advisor's post-verdict step). Flip to True to bring it back.
ENABLE_POSITION_SIZING = False

# High-VIX guardrail (downgrade verdict one tier when VIX > 22): DISABLED
# 2026-07-06 by user decision. Rolling-eval evidence (MODEL.md §15): blocking
# VIX>22 entries cut through-cycle PF from 1.13 to 1.04 — high-VIX bounce
# entries are this system's most profitable trades. Flip to True to restore.
ENABLE_VIX_GUARDRAIL = False

# Serve daily/weekly OHLC from the parquet cache (results/cache/), fetching
# only the missing recent days from yfinance on repeat visits. Applies to the
# live (current-date) path only; point-in-time backtest replay always fetches
# fresh. Flip to False to always hit yfinance.
USE_OHLC_CACHE = True

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

# Transaction cost assumptions.
# NOTE: currently unused by istock — the live cost path is
# features.spec.apply_costs (0.30% per side / 0.60% round-trip). Kept aligned
# here so this block doesn't contradict the real model if something reads it.
TRANSACTION_COSTS = {
    "commission_pct":    0.0030,   # 0.30% per side (user's actual brokerage)
    "slippage_pct":      0.0000,   # folded into brokerage assumption for now
    "total_round_trip":  0.0060,   # 0.60% total round-trip drag
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


# ============================================================
# EXTENDED BACKTEST UNIVERSE (~200 liquid US large/mid caps)
# Used by istock/training/backtester.py for Retrain-2 data collection.
# NOTE: this is TODAY'S liquid universe — backtests on older periods
# carry survivorship bias (these names are winners by construction).
# Excludes names delisted/acquired before 2026 (PXD, HES, ATVI, SPLK…).
# ============================================================
BACKTEST_UNIVERSE_LARGE = [
    # --- Mega/large tech ---
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
    "ORCL", "CRM", "ADBE", "AMD", "INTC", "QCOM", "TXN", "CSCO", "IBM",
    "NOW", "INTU", "AMAT", "MU", "LRCX", "KLAC", "ADI", "SNPS", "CDNS",
    "PANW", "CRWD", "FTNT", "ANET", "MRVL", "NXPI", "ON", "MCHP",
    "HPQ", "DELL", "WDC", "STX", "ADSK", "WDAY", "TEAM", "DDOG", "NET",
    "SNOW", "ZS", "PLTR",
    # --- Comms / media ---
    "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR", "EA", "TTWO",
    # --- Financials ---
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "V",
    "MA", "PYPL", "COF", "USB", "PNC", "TFC", "BK", "SPGI", "MCO",
    "ICE", "CME", "AON", "MMC", "AJG", "PGR", "CB", "TRV", "ALL",
    "MET", "PRU", "AIG", "AFL", "KKR", "BX",
    # --- Healthcare ---
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR",
    "BMY", "AMGN", "GILD", "VRTX", "REGN", "ISRG", "SYK", "BSX", "MDT",
    "EW", "ZTS", "CI", "ELV", "HUM", "CVS", "MCK", "CAH", "HCA", "BDX",
    "A", "IDXX", "IQV", "BIIB", "DXCM", "RMD",
    # --- Consumer discretionary ---
    "HD", "LOW", "MCD", "SBUX", "NKE", "TJX", "BKNG", "ABNB", "MAR",
    "HLT", "CMG", "YUM", "DPZ", "ROST", "ORLY", "AZO", "GM", "F",
    "LULU", "DECK", "RCL", "CCL", "LVS", "MGM", "EBAY",
    # --- Staples ---
    "WMT", "COST", "PG", "KO", "PEP", "PM", "MO", "CL", "KMB", "GIS",
    "HSY", "STZ", "KDP", "MDLZ", "MNST", "TGT", "DG", "DLTR", "KR",
    "SYY", "ADM",
    # --- Energy ---
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY",
    "KMI", "WMB", "OKE", "HAL", "BKR", "DVN", "FANG",
    # --- Industrials ---
    "BA", "CAT", "DE", "HON", "UPS", "FDX", "GE", "RTX", "LMT", "NOC",
    "GD", "LHX", "UNP", "CSX", "NSC", "EMR", "ETN", "ITW", "PH", "CMI",
    "PCAR", "MMM", "DOV", "ROK", "CARR", "OTIS", "WM", "RSG", "URI",
    "PWR", "TT", "JCI", "GWW", "FAST", "AME", "TDG", "HWM", "AXON",
    # --- Materials ---
    "LIN", "APD", "SHW", "ECL", "FCX", "NEM", "NUE", "STLD", "DOW",
    "DD", "PPG", "VMC", "MLM",
    # --- REITs ---
    "PLD", "AMT", "CCI", "EQIX", "PSA", "O", "SPG", "WELL", "DLR",
    "VICI", "AVB", "EQR",
    # --- Utilities ---
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL", "ED", "WEC",
    "PEG", "PCG",
    # --- User-traded extras (kept from scanner universe) ---
    "BRK-B", "ACN", "BE", "FANUY", "PCRHY", "SNDK",
    # --- User-requested additions (2026-07-06) ---
    "ADDYY",   # Adidas ADR
    "GLW",     # Corning
    "GEV",     # GE Vernova (spun off Apr 2024 — short history)
    # NOTE: GOOG (class C) deliberately excluded — GOOGL (class A) is already
    # in and the two share a near-identical price series; including both would
    # double-weight Alphabet in training.
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