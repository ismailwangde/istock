"""
ui.terminal_display - Pretty ANSI terminal output for trade analyses.

Moved out of core/trade_advisor.py (Session 2.1). The TradeConfig import
inside `display()` is deliberately lazy to avoid a circular import
(core.trade_advisor → ui.terminal_display → core.trade_advisor).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.trade_advisor import FullAnalysis


class TerminalDisplay:
    """Beautiful terminal output for the analysis"""

    # Color codes
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

    @classmethod
    def display(cls, result: FullAnalysis):
        """Display complete analysis in terminal"""
        from core.trade_advisor import TradeConfig

        v = result.verdict
        score = result.buy_score

        # Verdict color
        if 'BUY' in v:
            vc = cls.GREEN
            emoji = "🟢"
        elif 'SELL' in v:
            vc = cls.RED
            emoji = "🔴"
        elif 'AVOID' in v:
            vc = cls.RED
            emoji = "⛔"
        else:
            vc = cls.YELLOW
            emoji = "🟡"

        # Header box
        print()
        print(f"{cls.BOLD}╔{'═'*62}╗{cls.RESET}")
        print(f"{cls.BOLD}║  {emoji} TRADE ADVISOR: {result.symbol:<20} {result.timestamp:>20} ║{cls.RESET}")
        print(f"{cls.BOLD}╠{'═'*62}╣{cls.RESET}")
        print(f"{cls.BOLD}║  {vc}VERDICT: {v:<15}{cls.RESET}{cls.BOLD} │ Buy Score: {score:.0f}/100 │ Confidence: {result.confidence:<6}║{cls.RESET}")
        print(f"{cls.BOLD}║  Price: {result.current_price:<10.2f} ({result.day_change_pct:+.2f}%){'':>31}║{cls.RESET}")

        if result.setup.setup_type != 'none':
            s = result.setup
            print(f"{cls.BOLD}╠{'─'*62}╣{cls.RESET}")
            print(f"{cls.BOLD}║  {cls.CYAN}Entry: {s.entry:<10.2f}│ Stop: {s.stop_loss:<10.2f}│ Risk: {s.risk_pct:.1f}%{'':<13}{cls.RESET}{cls.BOLD}║{cls.RESET}")
            print(f"{cls.BOLD}║  {cls.GREEN}T1: {s.targets[0]:<10.2f} │ T2: {s.targets[1]:<10.2f}│ T3: {s.targets[2]:<10.2f}{'':<4}{cls.RESET}{cls.BOLD}║{cls.RESET}")
            print(f"{cls.BOLD}║  R:R = 1:{s.risk_reward:<5.1f} │ Setup: {s.setup_type.upper():<20}{'':<14}║{cls.RESET}")

        print(f"{cls.BOLD}╚{'═'*62}╝{cls.RESET}")
        print()

        # Section Details
        for key, section in result.sections.items():
            sc = section.score
            if sc >= 70: color = cls.GREEN
            elif sc >= 50: color = cls.YELLOW
            else: color = cls.RED

            icon = {
                'trend': '🧭', 'location': '📍', 'setup': '🔥',
                'volume': '📊', 'momentum': '⚡', 'candles': '🕯️',
                'risk_reward': '💰', 'market_context': '🌍'
            }.get(key, '📋')

            weight = TradeConfig.WEIGHTS.get(key, 0)

            print(f"  {cls.BOLD}{icon} {section.name.upper()} "
                  f"{color}[{sc:.0f}/100]{cls.RESET} "
                  f"{cls.DIM}(weight: {weight}%){cls.RESET} "
                  f"→ {section.summary}")

            for check in section.checks:
                status = f"{cls.GREEN}✅{cls.RESET}" if check.passed else f"{cls.RED}❌{cls.RESET}"
                print(f"     {status} {check.name}")
                if check.detail:
                    print(f"        {cls.DIM}{check.detail}{cls.RESET}")

            print()

        # Support / Resistance Map
        print(f"  {cls.BOLD}📍 SUPPORT / RESISTANCE MAP{cls.RESET}")
        print(f"  {'─'*50}")

        # Resistance levels (top to bottom)
        for r in reversed(result.resistance_levels[:3]):
            bar = "█" * min(int(r.strength * 4), 20)
            print(f"  {cls.RED}  R  {r.price:>10.2f}  │{bar}│ {r.distance_pct:+.1f}% | {r.source}{cls.RESET}")

        print(f"  {cls.WHITE}{cls.BOLD}  ▶  {result.current_price:>10.2f}  │{'▓' * 10}│ ◀ CURRENT PRICE{cls.RESET}")

        for s in result.support_levels[:3]:
            bar = "█" * min(int(s.strength * 4), 20)
            print(f"  {cls.GREEN}  S  {s.price:>10.2f}  │{bar}│ {s.distance_pct:-.1f}% | {s.source}{cls.RESET}")

        print()

        # Fibonacci Levels
        print(f"  {cls.BOLD}📐 FIBONACCI LEVELS{cls.RESET}")
        for name, price in result.fibonacci_levels.items():
            marker = " ◀◀" if abs(price - result.current_price) / result.current_price < 0.01 else ""
            print(f"     {name:>10}: {price:>10.2f}{marker}")
        print()

        # Avoid Flags
        if result.avoid_flags:
            print(f"  {cls.BOLD}{cls.RED}⚠️  AVOID FLAGS{cls.RESET}")
            for flag in result.avoid_flags:
                print(f"     {cls.RED}{flag}{cls.RESET}")
            print()

        # Sell Signals Summary
        print(f"  {cls.BOLD}🔴 SELL PRESSURE: {result.sell_score:.0f}/100{cls.RESET}")
        if result.sell_score > 40:
            print(f"     {cls.RED}Significant sell signals present - be cautious{cls.RESET}")
        elif result.sell_score > 20:
            print(f"     {cls.YELLOW}Some sell signals - monitor closely{cls.RESET}")
        else:
            print(f"     {cls.GREEN}Low sell pressure - favorable{cls.RESET}")
        print()

        # Key Observations
        print(f"  {cls.BOLD}🧠 KEY OBSERVATIONS{cls.RESET}")
        for obs in result.key_observations:
            print(f"     {obs}")
        print()

        # Final Action Box
        print(f"  {cls.BOLD}{'─'*58}{cls.RESET}")
        if 'BUY' in result.verdict and result.setup.setup_type != 'none':
            s = result.setup
            print(f"  {cls.GREEN}{cls.BOLD}📋 ACTION PLAN:{cls.RESET}")
            print(f"  {cls.GREEN}  1. Set BUY order at: {s.entry:.2f}{cls.RESET}")
            print(f"  {cls.GREEN}  2. Set STOP LOSS at: {s.stop_loss:.2f} ({s.risk_pct:.1f}% risk){cls.RESET}")
            print(f"  {cls.GREEN}  3. Target 1: {s.targets[0]:.2f} (book 50% profits){cls.RESET}")
            print(f"  {cls.GREEN}  4. Target 2: {s.targets[1]:.2f} (trail stop to entry){cls.RESET}")
            print(f"  {cls.GREEN}  5. Target 3: {s.targets[2]:.2f} (let remaining ride){cls.RESET}")

            # Position sizing suggestion
            risk_per_trade = 2500  # ₹2500 max risk per trade (10% of monthly investment)
            shares = int(risk_per_trade / (s.entry - s.stop_loss)) if s.entry > s.stop_loss else 0
            position_value = shares * s.entry

            print(f"  {cls.CYAN}  📊 Position Size (₹2,500 risk): {shares} shares (₹{position_value:,.0f}){cls.RESET}")

        elif 'SELL' in result.verdict:
            print(f"  {cls.RED}{cls.BOLD}📋 ACTION: SELL / EXIT POSITION{cls.RESET}")
            print(f"  {cls.RED}  Multiple sell signals active. Protect capital.{cls.RESET}")

        elif 'AVOID' in result.verdict:
            print(f"  {cls.RED}{cls.BOLD}📋 ACTION: DO NOT ENTER - Multiple red flags{cls.RESET}")

        else:
            print(f"  {cls.YELLOW}{cls.BOLD}📋 ACTION: WAIT for better setup{cls.RESET}")
            print(f"  {cls.YELLOW}  Add to watchlist and monitor daily.{cls.RESET}")
            if result.support_levels:
                print(f"  {cls.YELLOW}  Better entry near: {result.support_levels[0].price:.2f}{cls.RESET}")

        print(f"  {cls.BOLD}{'─'*58}{cls.RESET}")
        print()
