"""
execution.alert_manager - In-process alert dispatch (sound, terminal, telegram)

Moved from core/trade_advisor.py (Session 2.4.b). This is the in-process
alert engine used by LiveMonitor during a session. It is distinct from
execution/alerts.py which is the external, multi-channel alert engine
used by scheduler.py for scheduled reports.

Zero logic change — identical class body, relocated.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from istock.decision.types import TradeConfig

# ══════════════════════════════════════════════════════════════
# ADDITION 3: Alert Manager
# (Add this AFTER PositionTracker)
# ══════════════════════════════════════════════════════════════

class AlertManager:
    """Handles alerts: terminal, sound, telegram"""

    def __init__(self):
        self.cfg = TradeConfig()
        self.previous_verdicts = {}  # Track verdict changes
        self.alert_log = []

    def check_verdict_change(self, symbol: str, new_verdict: str) -> Optional[str]:
        """Detect if verdict changed since last check"""
        old = self.previous_verdicts.get(symbol)
        self.previous_verdicts[symbol] = new_verdict

        if old is None:
            return None  # First check, no change

        if old != new_verdict:
            return f"⚡ VERDICT CHANGED: {symbol} → {old} → {new_verdict}"
        return None

    def sound_alert(self, urgent: bool = False):
        """Make a sound alert"""
        if not self.cfg.ENABLE_SOUND_ALERT:
            return
        try:
            if urgent:
                # Multiple beeps for SELL
                for _ in range(5):
                    print('\a', end='', flush=True)
                    import time
                    time.sleep(0.3)
            else:
                print('\a', end='', flush=True)
        except:
            pass

    def send_telegram(self, message: str):
        """Send Telegram alert"""
        if not self.cfg.ENABLE_TELEGRAM:
            return
        if not self.cfg.TELEGRAM_BOT_TOKEN or not self.cfg.TELEGRAM_CHAT_ID:
            return

        try:
            import requests
            url = f"https://api.telegram.org/bot{self.cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': self.cfg.TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"  ⚠️ Telegram alert failed: {e}")

    def format_sell_alert(self, symbol: str, reason: str,
                         price: float, analysis: FullAnalysis = None) -> str:
        """Format a sell alert message"""
        msg = f"""
🚨🚨🚨 SELL ALERT 🚨🚨🚨

Symbol: {symbol}
Price: {price:.2f}
Reason: {reason}

"""
        if analysis:
            msg += f"""Buy Score: {analysis.buy_score:.0f}/100
Sell Score: {analysis.sell_score:.0f}/100
Verdict: {analysis.verdict}
"""
            if analysis.setup.stop_loss:
                msg += f"Stop Loss: {analysis.setup.stop_loss:.2f}\n"

            if analysis.avoid_flags:
                msg += "\nAvoid Flags:\n"
                for flag in analysis.avoid_flags:
                    msg += f"  {flag}\n"

        msg += f"\nTime: {datetime.now().strftime('%H:%M:%S')}"
        return msg

    def format_position_alert(self, status: PositionStatus) -> str:
        """Format position loss alert"""
        msg = f"""
🚨 POSITION ALERT: {status.symbol}

Buy Price: {status.buy_price:.2f}
Current: {status.current_price:.2f}
P&L: {status.unrealized_pnl_pct:+.1f}% ({status.unrealized_pnl:+.2f} {status.currency})
Peak Since Buy: {status.max_price_since_buy:.2f}
Trailing Stop: {status.trailing_stop_price:.2f}

Action: {status.loss_action}
Time: {datetime.now().strftime('%H:%M:%S')}
"""
        return msg

    def log_alert(self, message: str):
        """Log alert with timestamp"""
        entry = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message': message
        }
        self.alert_log.append(entry)

        # Also save to file
        try:
            os.makedirs('results', exist_ok=True)
            log_file = 'results/alert_log.json'
            existing = []
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    existing = json.load(f)
            existing.append(entry)
            # Keep last 500 alerts
            existing = existing[-500:]
            with open(log_file, 'w') as f:
                json.dump(existing, f, indent=2)
        except:
            pass
