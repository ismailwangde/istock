"""
execution.live_monitor - Continuous live monitor loop

Moved from core/trade_advisor.py (Session 2.4.c). Wraps the main
polling loop that watches held positions + watchlist, runs the
analyze() pipeline on each tick, and fires alerts via AlertManager
when verdicts change or loss rules trigger.

Zero logic change — identical class body, relocated.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from istock.decision.types import TradeConfig

# ══════════════════════════════════════════════════════════════
# ADDITION 4: Live Monitor (The Main Loop)
# (Add this AFTER AlertManager)
# ══════════════════════════════════════════════════════════════

class LiveMonitor:
    """
    Continuously monitors stocks and your positions.
    Alerts you when to SELL based on:
      1. Technical analysis verdict changes to SELL
      2. Your loss tolerance is breached
      3. Trailing stop is hit
      4. Avoid conditions appear
    """

    def __init__(self, symbols: List[str]):
        self.symbols = [s.upper() for s in symbols]
        self.advisor = TradeAdvisor()
        self.position_tracker = PositionTracker()
        self.alert_manager = AlertManager()
        self.cfg = TradeConfig()
        self.run_count = 0
        self.last_results = {}

    def is_market_open(self) -> Tuple[bool, str]:
        """Check if any relevant market is open"""
        if not self.cfg.MARKET_HOURS_ONLY:
            return True, "Always-on mode"

        now = datetime.now()
        hour, minute = now.hour, now.minute
        current_minutes = hour * 60 + minute

        # Check Indian market
        india_open = self.cfg.INDIA_MARKET_OPEN[0] * 60 + self.cfg.INDIA_MARKET_OPEN[1]
        india_close = self.cfg.INDIA_MARKET_CLOSE[0] * 60 + self.cfg.INDIA_MARKET_CLOSE[1]

        # Check US market (IST times)
        us_open = self.cfg.US_MARKET_OPEN_IST[0] * 60 + self.cfg.US_MARKET_OPEN_IST[1]
        us_close = self.cfg.US_MARKET_CLOSE_IST[0] * 60 + self.cfg.US_MARKET_CLOSE_IST[1]

        indian_stocks = any('.NS' in s or '.BO' in s for s in self.symbols)
        us_stocks = any('.NS' not in s and '.BO' not in s for s in self.symbols)

        india_live = indian_stocks and india_open <= current_minutes <= india_close
        # US market crosses midnight in IST
        us_live = us_stocks and (current_minutes >= us_open or current_minutes <= us_close)

        if india_live and us_live:
            return True, "Both markets open"
        elif india_live:
            return True, "Indian market open"
        elif us_live:
            return True, "US market open"

        # Find next opening
        if indian_stocks and current_minutes < india_open:
            wait = india_open - current_minutes
            return False, f"Indian market opens in {wait} minutes"
        elif us_stocks and current_minutes < us_open:
            wait = us_open - current_minutes
            return False, f"US market opens in {wait} minutes"

        return False, "Markets closed"

    def run_single_check(self) -> Dict[str, Any]:
        """Run one complete check cycle"""
        self.run_count += 1
        cycle_results = {
            'time': datetime.now().strftime('%H:%M:%S'),
            'analyses': {},
            'positions': {},
            'alerts': [],
            'sell_signals': []
        }

        C = TerminalDisplay

        # ── STEP 1: Check all positions for loss tolerance ──
        print(f"\n  {C.BOLD}💰 CHECKING YOUR POSITIONS...{C.RESET}")
        print(f"  {'─'*50}")

        for symbol in self.symbols:
            if symbol in self.cfg.MY_POSITIONS:
                try:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period="6mo")
                    if hist.empty:
                        continue

                    price = float(hist['Close'].iloc[-1])
                    status = self.position_tracker.evaluate_position(
                        symbol, price, hist)

                    if status:
                        cycle_results['positions'][symbol] = status

                        # Color based on P&L
                        if status.unrealized_pnl_pct >= 0:
                            color = C.GREEN
                        elif status.unrealized_pnl_pct > -self.cfg.MAX_LOSS_PCT * 0.7:
                            color = C.YELLOW
                        else:
                            color = C.RED

                        print(f"  {color}{symbol:<10} "
                              f"Buy: {status.buy_price:<10.2f} "
                              f"Now: {status.current_price:<10.2f} "
                              f"P&L: {status.unrealized_pnl_pct:>+6.1f}% "
                              f"{'🚨' if status.hit_max_loss else '⚠️' if status.hit_trailing_stop else '✅'}"
                              f"{C.RESET}")
                        print(f"           {status.loss_action}")

                        # ALERT if loss threshold hit
                        if status.hit_max_loss:
                            alert_msg = f"🚨 MAX LOSS HIT: {symbol} at {status.unrealized_pnl_pct:+.1f}%"
                            cycle_results['alerts'].append(alert_msg)
                            cycle_results['sell_signals'].append(symbol)
                            self.alert_manager.sound_alert(urgent=True)
                            self.alert_manager.send_telegram(
                                self.alert_manager.format_position_alert(status))
                            self.alert_manager.log_alert(alert_msg)

                        elif status.hit_trailing_stop:
                            alert_msg = f"⚠️ TRAILING STOP: {symbol} dropped {status.drawdown_from_peak:.1f}% from peak"
                            cycle_results['alerts'].append(alert_msg)
                            self.alert_manager.sound_alert(urgent=False)
                            self.alert_manager.log_alert(alert_msg)

                except Exception as e:
                    print(f"  ⚠️ Error checking {symbol}: {e}")

        # Check total portfolio loss
        all_positions = list(cycle_results['positions'].values())
        if all_positions:
            total_loss = self.position_tracker.get_portfolio_total_loss(all_positions)
            if total_loss < -self.cfg.TOTAL_PORTFOLIO_MAX_LOSS:
                alert_msg = f"🚨🚨 PORTFOLIO MAX LOSS: Total loss ₹{abs(total_loss):,.0f} exceeds ₹{self.cfg.TOTAL_PORTFOLIO_MAX_LOSS:,}"
                cycle_results['alerts'].append(alert_msg)
                self.alert_manager.sound_alert(urgent=True)
                self.alert_manager.send_telegram(alert_msg)
                print(f"\n  {C.RED}{C.BOLD}{alert_msg}{C.RESET}")

        # ── STEP 2: Run technical analysis on all symbols ──
        print(f"\n  {C.BOLD}📊 RUNNING TECHNICAL ANALYSIS...{C.RESET}")
        print(f"  {'─'*50}")

        for symbol in self.symbols:
            try:
                result = self.advisor.analyze(symbol)
                if result is None:
                    continue

                cycle_results['analyses'][symbol] = result

                # Check for verdict change
                change = self.alert_manager.check_verdict_change(
                    symbol, result.verdict)

                # Display compact result
                if 'BUY' in result.verdict:
                    color = C.GREEN
                elif 'SELL' in result.verdict or 'AVOID' in result.verdict:
                    color = C.RED
                else:
                    color = C.YELLOW

                print(f"\n  {color}{C.BOLD}{symbol:<10} "
                      f"→ {result.verdict:<14} "
                      f"Buy:{result.buy_score:>5.0f} "
                      f"Sell:{result.sell_score:>5.0f} "
                      f"R:R 1:{result.setup.risk_reward:.1f}"
                      f"{C.RESET}")

                # Show key levels
                if result.setup.setup_type != 'none':
                    s = result.setup
                    print(f"           Entry: {s.entry:.2f} | "
                          f"SL: {s.stop_loss:.2f} | "
                          f"T1: {s.targets[0]:.2f}")

                # Verdict change alert
                if change:
                    print(f"  {C.BOLD}{C.YELLOW}{change}{C.RESET}")
                    cycle_results['alerts'].append(change)
                    self.alert_manager.log_alert(change)

                    # If changed TO sell → urgent alert
                    if 'SELL' in result.verdict:
                        self.alert_manager.sound_alert(urgent=True)
                        sell_msg = self.alert_manager.format_sell_alert(
                            symbol, f"Verdict changed to {result.verdict}",
                            result.current_price, result)
                        self.alert_manager.send_telegram(sell_msg)
                        cycle_results['sell_signals'].append(symbol)

                # If current verdict is SELL (even without change)
                if 'SELL' in result.verdict and symbol in self.cfg.MY_POSITIONS:
                    if symbol not in cycle_results['sell_signals']:
                        cycle_results['sell_signals'].append(symbol)
                        print(f"  {C.RED}{C.BOLD}  ⚠️ You hold this stock and verdict is SELL!{C.RESET}")

                # Avoid flags
                if result.avoid_flags:
                    for flag in result.avoid_flags[:2]:
                        print(f"           {flag}")

                self.last_results[symbol] = result

            except Exception as e:
                print(f"  ⚠️ Error analyzing {symbol}: {e}")

        return cycle_results

    def display_monitor_summary(self, results: Dict):
        """Display summary after each check cycle"""
        C = TerminalDisplay

        print(f"\n{'='*60}")
        print(f"  {C.BOLD}📋 MONITOR SUMMARY (Check #{self.run_count} at {results['time']}){C.RESET}")
        print(f"{'='*60}")

        # Alerts
        if results['alerts']:
            print(f"\n  {C.RED}{C.BOLD}🔔 ALERTS:{C.RESET}")
            for alert in results['alerts']:
                print(f"     {C.RED}{alert}{C.RESET}")

        # Sell signals
        if results['sell_signals']:
            print(f"\n  {C.RED}{C.BOLD}🚨 SELL NOW:{C.RESET}")
            for sym in results['sell_signals']:
                pos = results['positions'].get(sym)
                analysis = results['analyses'].get(sym)
                if pos:
                    print(f"     {C.RED}{sym}: P&L {pos.unrealized_pnl_pct:+.1f}% | "
                          f"{pos.loss_action}{C.RESET}")
                elif analysis:
                    print(f"     {C.RED}{sym}: {analysis.verdict} | "
                          f"Score {analysis.buy_score:.0f}/{analysis.sell_score:.0f}{C.RESET}")
        else:
            print(f"\n  {C.GREEN}  ✅ No sell signals. All positions within tolerance.{C.RESET}")

        # Position summary table
        if results['positions']:
            print(f"\n  {C.BOLD}📊 POSITIONS:{C.RESET}")
            print(f"  {'Symbol':<10} {'Buy':>8} {'Now':>8} {'P&L%':>7} {'P&L':>10} {'Status':<8}")
            print(f"  {'─'*55}")

            total_invested = 0
            total_current = 0

            for sym, pos in results['positions'].items():
                color = C.GREEN if pos.unrealized_pnl_pct >= 0 else C.RED
                status = "🚨" if pos.hit_max_loss else "⚠️" if pos.hit_trailing_stop else "✅"

                # Convert to INR for display
                inv = pos.invested_value * (self.cfg.USD_TO_INR if pos.currency == 'USD' else 1)
                cur = pos.position_value * (self.cfg.USD_TO_INR if pos.currency == 'USD' else 1)
                pnl = cur - inv

                print(f"  {color}{sym:<10} {pos.buy_price:>8.2f} {pos.current_price:>8.2f} "
                      f"{pos.unrealized_pnl_pct:>+6.1f}% ₹{pnl:>+8,.0f} {status}{C.RESET}")

                total_invested += inv
                total_current += cur

            total_pnl = total_current - total_invested
            total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0
            color = C.GREEN if total_pnl >= 0 else C.RED
            print(f"  {'─'*55}")
            print(f"  {color}{C.BOLD}{'TOTAL':<10} {'':>8} {'':>8} "
                  f"{total_pnl_pct:>+6.1f}% ₹{total_pnl:>+8,.0f}{C.RESET}")

        # Next check
        next_check = datetime.now() + timedelta(minutes=self.cfg.REFRESH_INTERVAL_MINUTES)
        print(f"\n  ⏰ Next check at: {next_check.strftime('%H:%M:%S')} "
              f"(every {self.cfg.REFRESH_INTERVAL_MINUTES} min)")
        print(f"  Press Ctrl+C to stop monitoring")
        print(f"{'='*60}\n")

    def start(self):
        """Start the monitoring loop"""
        import time

        C = TerminalDisplay
        interval = self.cfg.REFRESH_INTERVAL_MINUTES * 60  # Convert to seconds

        print(f"\n{'='*60}")
        print(f"  {C.BOLD}🔴 LIVE MONITOR STARTED{C.RESET}")
        print(f"  {'─'*50}")
        print(f"  📊 Watching: {', '.join(self.symbols)}")
        print(f"  ⏰ Refresh: Every {self.cfg.REFRESH_INTERVAL_MINUTES} minutes")
        print(f"  📉 Max Loss: {self.cfg.MAX_LOSS_PCT}% or ₹{self.cfg.MAX_LOSS_AMOUNT:,}")
        print(f"  📈 Trailing Stop: {self.cfg.TRAILING_STOP_PCT}% from peak")
        print(f"  🔔 Sound: {'ON' if self.cfg.ENABLE_SOUND_ALERT else 'OFF'}")
        print(f"  📱 Telegram: {'ON' if self.cfg.ENABLE_TELEGRAM else 'OFF'}")
        print(f"  🕐 Market Hours Only: {'YES' if self.cfg.MARKET_HOURS_ONLY else 'NO'}")

        # Show positions being tracked
        if self.cfg.MY_POSITIONS:
            print(f"\n  💼 Tracking {len(self.cfg.MY_POSITIONS)} positions:")
            for sym, pos in self.cfg.MY_POSITIONS.items():
                print(f"     {sym}: {pos['quantity']} shares @ {pos['buy_price']}")
        else:
            print(f"\n  ⚠️ No positions configured in MY_POSITIONS")
            print(f"  💡 Add your positions in TradeConfig.MY_POSITIONS")

        print(f"\n  Press Ctrl+C to stop")
        print(f"{'='*60}")

        try:
            while True:
                # Check market hours
                market_open, status = self.is_market_open()

                if not market_open and self.cfg.MARKET_HOURS_ONLY:
                    print(f"\r  💤 {status}. Waiting... "
                          f"(Ctrl+C to stop)      ", end='', flush=True)
                    time.sleep(60)  # Check every minute when market is closed
                    continue

                print(f"\n  🔄 Running check #{self.run_count + 1} "
                      f"({status})...")

                # Run the check
                results = self.run_single_check()

                # Display summary
                self.display_monitor_summary(results)

                # Wait for next interval
                # Show countdown
                for remaining in range(interval, 0, -1):
                    mins, secs = divmod(remaining, 60)
                    print(f"\r  ⏳ Next check in: {mins:02d}:{secs:02d} "
                          f"(Ctrl+C to stop)   ", end='', flush=True)
                    time.sleep(1)

        except KeyboardInterrupt:
            print(f"\n\n  {C.YELLOW}⏹ Monitor stopped by user.{C.RESET}")

            # Save final state
            try:
                os.makedirs('results', exist_ok=True)
                state = {
                    'stopped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'total_checks': self.run_count,
                    'last_verdicts': {s: self.alert_manager.previous_verdicts.get(s, 'N/A')
                                     for s in self.symbols},
                    'alerts': self.alert_manager.alert_log[-20:]
                }
                with open('results/monitor_state.json', 'w') as f:
                    json.dump(state, f, indent=2, default=str)
                print(f"  💾 Monitor state saved to results/monitor_state.json")
            except:
                pass

            print(f"  👋 Goodbye!")
