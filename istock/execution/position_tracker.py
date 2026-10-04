"""
execution.position_tracker - Live-monitor position tracking (per-session)

Moved from core/trade_advisor.py (Session 2.4.a). This is the
tracker used by LiveMonitor for in-session P&L / drawdown / trailing
stops. It is distinct from execution/portfolio_tracker.py, which
handles persistent portfolio-level holdings and allocation.

Zero logic change — identical class bodies, relocated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from istock.decision.types import TradeConfig

# ══════════════════════════════════════════════════════════════
# ADDITION 2: Position Tracker
# (Add this AFTER the FullAnalysis dataclass, BEFORE DataEngine)
# ══════════════════════════════════════════════════════════════

@dataclass
class PositionStatus:
    """Real-time status of a held position"""
    symbol: str
    buy_price: float
    current_price: float
    quantity: int
    currency: str

    # Calculated fields
    unrealized_pnl: float = 0
    unrealized_pnl_pct: float = 0
    position_value: float = 0
    invested_value: float = 0

    # Loss tracking
    max_price_since_buy: float = 0
    drawdown_from_peak: float = 0
    trailing_stop_price: float = 0

    # Flags
    hit_max_loss: bool = False
    hit_trailing_stop: bool = False
    hit_target: bool = False

    # Action
    loss_action: str = ""  # What to do based on loss rules


class PositionTracker:
    """Tracks your positions and checks loss tolerance"""

    def __init__(self):
        self.cfg = TradeConfig()
        self.position_history = {}  # Track peak prices

    def evaluate_position(self, symbol: str, current_price: float,
                         daily_df: pd.DataFrame = None) -> Optional[PositionStatus]:
        """Evaluate a single position against loss rules"""

        positions = self.cfg.MY_POSITIONS
        if symbol.upper() not in positions:
            return None

        pos = positions[symbol.upper()]
        buy_price = pos['buy_price']
        quantity = pos['quantity']
        currency = pos.get('currency', 'USD')

        # Calculate P&L
        invested = buy_price * quantity
        current_val = current_price * quantity
        pnl = current_val - invested
        pnl_pct = (current_price - buy_price) / buy_price * 100

        # Convert to INR if needed for absolute loss check
        if currency == 'USD':
            pnl_inr = pnl * self.cfg.USD_TO_INR
            invested_inr = invested * self.cfg.USD_TO_INR
            current_val_inr = current_val * self.cfg.USD_TO_INR
        else:
            pnl_inr = pnl
            invested_inr = invested
            current_val_inr = current_val

        # Track peak price since buy (for trailing stop)
        if daily_df is not None and not daily_df.empty:
            # Find max price since buy date
            buy_date = pos.get('buy_date', '')
            if buy_date:
                try:
                    mask = daily_df.index >= pd.Timestamp(buy_date)
                    if mask.any():
                        peak = float(daily_df.loc[mask, 'High'].max())
                    else:
                        peak = current_price
                except:
                    peak = max(current_price, buy_price)
            else:
                peak = max(current_price, buy_price)
        else:
            # Use stored peak or current
            prev_peak = self.position_history.get(symbol, {}).get('peak', buy_price)
            peak = max(prev_peak, current_price)

        # Store peak
        if symbol not in self.position_history:
            self.position_history[symbol] = {}
        self.position_history[symbol]['peak'] = peak

        # Drawdown from peak
        drawdown = (peak - current_price) / peak * 100 if peak > 0 else 0

        # Trailing stop price
        trailing_stop = peak * (1 - self.cfg.TRAILING_STOP_PCT / 100)

        # ── CHECK LOSS RULES ──

        hit_max_loss_pct = pnl_pct <= -self.cfg.MAX_LOSS_PCT
        hit_max_loss_amt = pnl_inr <= -self.cfg.MAX_LOSS_AMOUNT
        hit_trailing = (current_price < trailing_stop and
                       current_price > buy_price)  # only if was in profit

        # Determine action
        action = ""
        if hit_max_loss_pct:
            action = f"🚨 SELL NOW: Loss {pnl_pct:.1f}% exceeds your max {self.cfg.MAX_LOSS_PCT}%"
        elif hit_max_loss_amt:
            action = f"🚨 SELL NOW: Loss ₹{abs(pnl_inr):,.0f} exceeds your max ₹{self.cfg.MAX_LOSS_AMOUNT:,}"
        elif hit_trailing:
            action = f"⚠️ TRAILING STOP HIT: Peaked at {peak:.2f}, now {current_price:.2f} ({drawdown:.1f}% drop)"
        elif pnl_pct > 0:
            action = f"✅ IN PROFIT: +{pnl_pct:.1f}% | Trailing stop at {trailing_stop:.2f}"
        else:
            remaining_loss = self.cfg.MAX_LOSS_PCT - abs(pnl_pct)
            action = f"📊 Monitoring: {pnl_pct:+.1f}% | {remaining_loss:.1f}% room before max loss"

        return PositionStatus(
            symbol=symbol.upper(),
            buy_price=buy_price,
            current_price=current_price,
            quantity=quantity,
            currency=currency,
            unrealized_pnl=round(pnl, 2),
            unrealized_pnl_pct=round(pnl_pct, 2),
            position_value=round(current_val, 2),
            invested_value=round(invested, 2),
            max_price_since_buy=round(peak, 2),
            drawdown_from_peak=round(drawdown, 2),
            trailing_stop_price=round(trailing_stop, 2),
            hit_max_loss=hit_max_loss_pct or hit_max_loss_amt,
            hit_trailing_stop=hit_trailing,
            loss_action=action
        )

    def evaluate_all_positions(self) -> List[PositionStatus]:
        """Evaluate all positions in config"""
        results = []
        for symbol in self.cfg.MY_POSITIONS:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="6mo")
                if not hist.empty:
                    price = float(hist['Close'].iloc[-1])
                    status = self.evaluate_position(symbol, price, hist)
                    if status:
                        results.append(status)
            except Exception as e:
                print(f"  ⚠️ Could not evaluate {symbol}: {e}")
        return results

    def get_portfolio_total_loss(self, statuses: List[PositionStatus]) -> float:
        """Total unrealized loss across all positions (in INR)"""
        total = 0
        for s in statuses:
            pnl = s.unrealized_pnl
            if s.currency == 'USD':
                pnl *= self.cfg.USD_TO_INR
            total += pnl
        return total
