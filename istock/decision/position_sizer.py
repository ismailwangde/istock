#!/usr/bin/env python3
"""
position_sizer.py - Intelligent Position Sizing Engine
═══════════════════════════════════════════════════════
Given a trade setup from trade_advisor.py, calculates the EXACT
number of shares to buy using multiple blended sizing methods:

  1. Fixed Fractional Risk    (conviction-scaled risk %)
  2. Volatility-Adjusted      (ATR parity — high-vol gets less)
  3. Fractional Kelly         (25% Kelly based on win-rate & R:R)
  4. Max Position Cap         (hard ceiling per portfolio %)

The SMALLEST of the four wins (safety-first). Then applies:
  • Hard rules (stop sanity, R:R floor, portfolio heat cap, etc.)
  • Sector concentration check
  • Cash availability check
  • Currency conversion (USD ↔ INR)

Usage:
    from core.position_sizer import size_position_from_analysis
    sizing = size_position_from_analysis(analysis, portfolio_inr,
                                         cash_inr, open_positions)
    print(sizing.format_for_terminal())

Author: Built for Ismail's Investment Analysis System
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from istock.decision.regime import get_regime_multiplier

# Integrate with the existing system
from istock.decision.types import (
    TradeConfig,
    FullAnalysis,
    TradeSetup,
)
from istock.ui.terminal_display import TerminalDisplay

try:
    from config import USER_PROFILE, TARGET_ALLOCATION, CURRENT_HOLDINGS
except ImportError:
    USER_PROFILE = {"risk_category": "AGGRESSIVE", "usd_inr_rate": 85.5}
    TARGET_ALLOCATION = {}
    CURRENT_HOLDINGS = []


# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

class SizingConfig:
    """All tunable sizing parameters in one place"""

    # Base risk per trade (of portfolio)
    BASE_RISK_PCT = 0.01  # 1% of portfolio per trade (conservative base)

    # Volatility targeting
    TARGET_DAILY_VOL_PCT = 0.005  # 0.5% daily portfolio vol per position

    # Kelly
    KELLY_FRACTION = 0.25  # standard pro practice: 25% Kelly
    KELLY_MAX_WIN_RATE = 0.75  # cap calibrated win rate

    # Max single position size (by risk category)
    MAX_POSITION_PCT = {
        "AGGRESSIVE":   0.15,
        "MODERATE":     0.10,
        "CONSERVATIVE": 0.05,
    }

    # Hard rules
    MIN_STOP_PCT = 0.005   # stop must be >= 0.5% away
    MAX_STOP_PCT = 0.10    # stop must be <= 10% away
    MIN_SCORE = 50
    MIN_RR = 1.5
    MAX_PORTFOLIO_HEAT_PCT = 0.06  # 6% total open risk cap
    MAX_SECTOR_EXPOSURE_PCT = 0.35  # 35% in one sector

    # Setup-type default win rates (used when no calibrated history)
    SETUP_WIN_RATES = {
        "pullback": 0.55,
        "breakout": 0.40,
        "bounce":   0.60,
        "reversal": 0.45,
        "none":     0.00,
    }


# ══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════

@dataclass
class SizingInput:
    """All inputs required to size a position"""
    # From FullAnalysis / TradeSetup
    symbol: str
    entry_price: float
    stop_loss: float
    current_price: float
    composite_score: float         # buy_score (0-100)
    confidence: str                # HIGH | MEDIUM | LOW
    setup_type: str                # pullback | breakout | bounce | reversal | none
    risk_reward: float             # R:R from TradeSetup
    atr_pct: float                 # daily ATR as % of price

    # Portfolio context
    portfolio_value_inr: float
    cash_available_inr: float
    currency: str = "INR"          # 'INR' or 'USD'
    usd_inr_rate: float = 85.5

    # Risk / regime
    risk_category: str = "AGGRESSIVE"  # AGGRESSIVE | MODERATE | CONSERVATIVE
    regime_multiplier: float = 1.0     # hook for future regime_detector

    # Positions & sector
    open_positions: List[Dict] = field(default_factory=list)
    # Each: {symbol, current_risk_inr, sector}
    sector: str = "Unknown"


@dataclass
class SizingOutput:
    """Complete sizing recommendation with full reasoning"""
    # Final recommendation
    shares: int = 0
    position_value_inr: float = 0.0
    position_value_native: float = 0.0
    risk_amount_inr: float = 0.0
    risk_pct_of_portfolio: float = 0.0

    # Breakdown
    method_results: Dict[str, float] = field(default_factory=dict)
    winning_method: str = ""

    # Explanations
    reasoning: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Go / no-go
    approved: bool = False
    rejection_reason: str = ""

    # Scaling info
    conviction_multiplier: float = 1.0
    volatility_multiplier: float = 1.0
    heat_multiplier: float = 1.0

    # Context (for display)
    symbol: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    currency: str = "INR"
    usd_inr_rate: float = 85.5
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # ──────────────────────────────────────────────────────
    # Terminal display
    # ──────────────────────────────────────────────────────
    def format_for_terminal(self) -> str:
        """Format sizing output for terminal display (colored boxes)"""
        C = TerminalDisplay
        lines = []

        header_color = C.GREEN if self.approved else C.RED
        status = "✅ APPROVED" if self.approved else "⛔ REJECTED"

        lines.append("")
        lines.append(f"{C.BOLD}╔{'═'*62}╗{C.RESET}")
        lines.append(f"{C.BOLD}║  💰 POSITION SIZER — {self.symbol:<20} {self.timestamp:>17} ║{C.RESET}")
        lines.append(f"{C.BOLD}╠{'═'*62}╣{C.RESET}")
        lines.append(f"{C.BOLD}║  {header_color}{status:<15}{C.RESET}{C.BOLD}"
                     f" │ Shares: {self.shares:<6} │ Method: {self.winning_method:<15}  ║{C.RESET}")
        lines.append(f"{C.BOLD}║  Position: {self.position_value_native:>10,.2f} {self.currency:<3}"
                     f" (≈ ₹{self.position_value_inr:>10,.0f}){' ':<14}║{C.RESET}")
        lines.append(f"{C.BOLD}║  Risk:     ₹{self.risk_amount_inr:>10,.0f}"
                     f"  ({self.risk_pct_of_portfolio:>5.2f}% of portfolio){' ':<16}║{C.RESET}")
        lines.append(f"{C.BOLD}╚{'═'*62}╝{C.RESET}")
        lines.append("")

        if not self.approved:
            lines.append(f"  {C.RED}{C.BOLD}🚫 REJECTION REASON:{C.RESET}")
            lines.append(f"     {C.RED}{self.rejection_reason}{C.RESET}")
            lines.append("")

        # Multipliers
        lines.append(f"  {C.BOLD}🎚️  SCALING FACTORS{C.RESET}")
        lines.append(f"     Conviction multiplier:  {self.conviction_multiplier:.2f}x")
        lines.append(f"     Volatility multiplier:  {self.volatility_multiplier:.2f}x")
        lines.append(f"     Heat multiplier:        {self.heat_multiplier:.2f}x")
        lines.append("")

        # Method breakdown
        lines.append(f"  {C.BOLD}🧮 METHOD RESULTS (smallest wins){C.RESET}")
        lines.append(f"  {'─'*56}")
        for name, shares in self.method_results.items():
            marker = f"  {C.GREEN}◀ BINDING{C.RESET}" if name == self.winning_method else ""
            lines.append(f"     {name:<28} → {shares:>7.1f} shares{marker}")
        lines.append("")

        # Reasoning
        if self.reasoning:
            lines.append(f"  {C.BOLD}🧠 REASONING{C.RESET}")
            for r in self.reasoning:
                lines.append(f"     {r}")
            lines.append("")

        # Warnings
        if self.warnings:
            lines.append(f"  {C.BOLD}{C.YELLOW}⚠️  WARNINGS{C.RESET}")
            for w in self.warnings:
                lines.append(f"     {C.YELLOW}{w}{C.RESET}")
            lines.append("")

        # Action plan
        lines.append(f"  {C.BOLD}{'─'*58}{C.RESET}")
        if self.approved:
            lines.append(f"  {C.GREEN}{C.BOLD}📋 EXECUTE:{C.RESET}")
            lines.append(f"  {C.GREEN}  BUY {self.shares} shares of {self.symbol} "
                         f"@ {self.entry_price:.2f}{C.RESET}")
            lines.append(f"  {C.GREEN}  Stop loss: {self.stop_loss:.2f}{C.RESET}")
            lines.append(f"  {C.GREEN}  Capital deployed: ₹{self.position_value_inr:,.0f}{C.RESET}")
            lines.append(f"  {C.GREEN}  Max loss if stopped: ₹{self.risk_amount_inr:,.0f} "
                         f"({self.risk_pct_of_portfolio:.2f}%){C.RESET}")
        else:
            lines.append(f"  {C.RED}{C.BOLD}📋 DO NOT ENTER{C.RESET}")
            lines.append(f"  {C.RED}  {self.rejection_reason}{C.RESET}")
        lines.append(f"  {C.BOLD}{'─'*58}{C.RESET}")
        lines.append("")

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# POSITION SIZER (MAIN ENGINE)
# ══════════════════════════════════════════════════════════════

class PositionSizer:
    """
    Intelligent position sizing that blends multiple methods.

    Philosophy:
      • Calculate ALL 4 methods, pick the SMALLEST (safety-first)
      • Scale by conviction (high score → larger size)
      • Scale by volatility (high ATR → smaller size)
      • Respect portfolio heat cap (never exceed 6% total open risk)
      • Never silently oversize — always explain
    """

    def __init__(self, sizing_config: Optional[SizingConfig] = None):
        self.cfg = sizing_config or SizingConfig()

    # ──────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────
    def size(self, inp: SizingInput) -> SizingOutput:
        """Calculate position size with full reasoning."""
        out = SizingOutput(
            symbol=inp.symbol,
            entry_price=inp.entry_price,
            stop_loss=inp.stop_loss,
            currency=inp.currency,
            usd_inr_rate=inp.usd_inr_rate,
        )

        # ── STEP 1: Currency — work in native currency for share calc ──
        is_usd = (inp.currency == "USD")
        if is_usd:
            portfolio_native = inp.portfolio_value_inr / inp.usd_inr_rate
            cash_native = inp.cash_available_inr / inp.usd_inr_rate
        else:
            portfolio_native = inp.portfolio_value_inr
            cash_native = inp.cash_available_inr

        # ── STEP 2: Hard rule pre-checks (reject early) ──
        rejection = self._check_hard_rules_early(inp)
        if rejection:
            out.approved = False
            out.rejection_reason = rejection
            out.reasoning.append(f"❌ Pre-check failed: {rejection}")
            return out

        risk_per_share = inp.entry_price - inp.stop_loss  # in native currency
        risk_pct_of_entry = risk_per_share / inp.entry_price

        # ── STEP 3: Calculate conviction multiplier ──
        conviction_mult = self._conviction_multiplier(
            inp.composite_score, inp.confidence)
        out.conviction_multiplier = conviction_mult

        if conviction_mult == 0.0:
            out.approved = False
            out.rejection_reason = (
                f"Composite score {inp.composite_score:.0f} too low "
                f"(conviction multiplier = 0)")
            return out

        # ── STEP 4: Volatility multiplier (informational) ──
        # High ATR → smaller size (handled naturally by Method 2)
        vol_mult = min(1.0, 2.0 / max(inp.atr_pct, 0.5))  # ~1.0 at 2% ATR
        out.volatility_multiplier = round(vol_mult, 2)

        # ── STEP 5: Heat multiplier — how much of 6% cap is already used? ──
        total_open_risk_inr = sum(
            p.get("current_risk_inr", 0) for p in inp.open_positions)
        heat_used = total_open_risk_inr / max(inp.portfolio_value_inr, 1)
        heat_remaining = max(0, self.cfg.MAX_PORTFOLIO_HEAT_PCT - heat_used)
        # If we have only 2% of 6% left, heat_mult = 2/6 = 0.33
        heat_mult = min(1.0, heat_remaining / self.cfg.MAX_PORTFOLIO_HEAT_PCT)
        out.heat_multiplier = round(heat_mult, 2)

        if heat_remaining <= 0:
            out.approved = False
            out.rejection_reason = (
                f"Portfolio heat cap exceeded: {heat_used*100:.1f}% "
                f"open risk already (max {self.cfg.MAX_PORTFOLIO_HEAT_PCT*100:.0f}%)")
            out.reasoning.append(
                f"❌ Already {heat_used*100:.1f}% at risk across open positions")
            return out

        # ── STEP 6: Calculate all 4 methods (native currency) ──
        m1 = self._method_1_fixed_fractional(
            portfolio_native, risk_per_share, conviction_mult,
            inp.regime_multiplier, heat_mult)
        m2 = self._method_2_volatility_parity(
            portfolio_native, inp.atr_pct, inp.entry_price)
        m3 = self._method_3_kelly(
            portfolio_native, inp.setup_type, inp.composite_score,
            inp.risk_reward, inp.entry_price)
        m4 = self._method_4_max_cap(
            portfolio_native, inp.entry_price, inp.risk_category)

        out.method_results = {
            "Method 1: Fixed Fractional":   round(m1, 1),
            "Method 2: Volatility Parity":  round(m2, 1),
            "Method 3: Fractional Kelly":   round(m3, 1),
            "Method 4: Max Position Cap":   round(m4, 1),
        }

        # ── STEP 7: Pick smallest (binding constraint) ──
        methods_sorted = sorted(out.method_results.items(), key=lambda x: x[1])
        winning_name, candidate_shares = methods_sorted[0]
        out.winning_method = winning_name
        out.reasoning.append(
            f"🔒 Binding constraint: {winning_name} "
            f"({candidate_shares:.1f} shares)")

        # ── STEP 8: Floor to integer shares ──
        final_shares = int(math.floor(candidate_shares))

        # ── STEP 9: Cash availability check ──
        required_cash_native = final_shares * inp.entry_price
        if required_cash_native > cash_native:
            # Scale down to fit cash
            affordable_shares = int(math.floor(cash_native / inp.entry_price))
            if affordable_shares < final_shares:
                out.warnings.append(
                    f"Cash-constrained: reduced from {final_shares} to "
                    f"{affordable_shares} shares (available cash: "
                    f"{cash_native:,.2f} {inp.currency})")
                final_shares = affordable_shares
                out.winning_method = "Cash Available (override)"

        # ── STEP 10: Minimum share check ──
        if final_shares < 1:
            out.approved = False
            out.rejection_reason = (
                f"Position too small: computed {candidate_shares:.2f} shares "
                f"(< 1 share after flooring)")
            out.reasoning.append(
                "❌ Size too small — not worth the commission/slippage")
            return out

        # ── STEP 11: Calculate final values ──
        position_native = final_shares * inp.entry_price
        risk_native = final_shares * risk_per_share

        if is_usd:
            position_inr = position_native * inp.usd_inr_rate
            risk_inr = risk_native * inp.usd_inr_rate
        else:
            position_inr = position_native
            risk_inr = risk_native

        risk_pct_of_portfolio = risk_inr / inp.portfolio_value_inr * 100

        # ── STEP 12: Post-hoc heat check (did we push total over 6%?) ──
        projected_total_risk_inr = total_open_risk_inr + risk_inr
        projected_heat_pct = (projected_total_risk_inr /
                              inp.portfolio_value_inr * 100)
        if projected_heat_pct > self.cfg.MAX_PORTFOLIO_HEAT_PCT * 100:
            out.approved = False
            out.rejection_reason = (
                f"Would push portfolio heat to {projected_heat_pct:.2f}% "
                f"(cap: {self.cfg.MAX_PORTFOLIO_HEAT_PCT*100:.0f}%)")
            return out

        # ── STEP 13: Sector exposure check ──
        sector_rejection = self._check_sector_exposure(
            inp, position_inr)
        if sector_rejection:
            out.approved = False
            out.rejection_reason = sector_rejection
            return out

        # ── STEP 14: Already-holding check ──
        held = next((p for p in inp.open_positions
                     if p.get("symbol", "").upper() == inp.symbol.upper()), None)
        if held:
            existing_value = held.get("position_value_inr", 0)
            if existing_value >= inp.portfolio_value_inr * \
                    self.cfg.MAX_POSITION_PCT.get(inp.risk_category, 0.10):
                out.approved = False
                out.rejection_reason = (
                    f"Already holding {inp.symbol} at max position size "
                    f"(₹{existing_value:,.0f})")
                return out
            out.warnings.append(
                f"Already holding {inp.symbol} — this is a scale-in")

        # ── STEP 15: Populate final output ──
        out.shares = final_shares
        out.position_value_native = round(position_native, 2)
        out.position_value_inr = round(position_inr, 2)
        out.risk_amount_inr = round(risk_inr, 2)
        out.risk_pct_of_portfolio = round(risk_pct_of_portfolio, 3)
        out.approved = True

        # ── STEP 16: Add explanatory reasoning ──
        out.reasoning.extend([
            f"📊 Composite score: {inp.composite_score:.0f} ({inp.confidence}) "
            f"→ conviction multiplier {conviction_mult:.2f}x",
            f"📉 ATR {inp.atr_pct:.2f}% → volatility multiplier "
            f"{vol_mult:.2f}x",
            f"🔥 Portfolio heat used: {heat_used*100:.2f}% of "
            f"{self.cfg.MAX_PORTFOLIO_HEAT_PCT*100:.0f}% cap "
            f"→ heat multiplier {heat_mult:.2f}x",
            f"🎯 Setup: {inp.setup_type}  |  R:R = 1:{inp.risk_reward:.1f}",
            f"💵 Risk per share: {risk_per_share:.2f} {inp.currency} "
            f"({risk_pct_of_entry*100:.2f}% of entry)",
        ])

        # Warnings for edge cases
        if risk_pct_of_portfolio > 1.5:
            out.warnings.append(
                f"Risk {risk_pct_of_portfolio:.2f}% is above 1.5% — "
                f"consider scaling down")
        if inp.atr_pct > 5:
            out.warnings.append(
                f"High volatility ({inp.atr_pct:.1f}% ATR) — expect whipsaw")
        if position_inr > inp.portfolio_value_inr * 0.12:
            out.warnings.append(
                f"Position is {position_inr/inp.portfolio_value_inr*100:.1f}% "
                f"of portfolio — concentration risk")

        return out

    # ──────────────────────────────────────────────────────
    # Hard rule checker (pre-calculation)
    # ──────────────────────────────────────────────────────
    def _check_hard_rules_early(self, inp: SizingInput) -> str:
        """Return rejection reason string, or empty string if all pass."""
        if inp.stop_loss >= inp.entry_price:
            return (f"Stop loss ({inp.stop_loss:.2f}) not below entry "
                    f"({inp.entry_price:.2f})")

        risk_pct = (inp.entry_price - inp.stop_loss) / inp.entry_price
        if risk_pct < self.cfg.MIN_STOP_PCT:
            return (f"Stop too tight: {risk_pct*100:.2f}% risk "
                    f"(min {self.cfg.MIN_STOP_PCT*100:.1f}%)")
        if risk_pct > self.cfg.MAX_STOP_PCT:
            return (f"Stop too wide: {risk_pct*100:.2f}% risk "
                    f"(max {self.cfg.MAX_STOP_PCT*100:.0f}%)")

        if inp.composite_score < self.cfg.MIN_SCORE:
            return (f"Composite score {inp.composite_score:.0f} below "
                    f"minimum {self.cfg.MIN_SCORE}")

        if inp.risk_reward < self.cfg.MIN_RR:
            return (f"R:R {inp.risk_reward:.2f} below minimum "
                    f"{self.cfg.MIN_RR}")

        if inp.setup_type == "none":
            return "No valid setup detected"

        if inp.portfolio_value_inr <= 0:
            return "Portfolio value must be positive"

        return ""

    # ──────────────────────────────────────────────────────
    # Conviction scaling
    # ──────────────────────────────────────────────────────
    def _conviction_multiplier(self, score: float, confidence: str) -> float:
        """Scale up position size for high-conviction trades."""
        if score < 50:
            return 0.0
        if score >= 80 and confidence == "HIGH":
            return 1.5
        if score >= 70:
            return 1.2
        if score >= 60:
            return 1.0
        if score >= 50:
            return 0.6
        return 0.0

    # ──────────────────────────────────────────────────────
    # Method 1: Fixed Fractional Risk
    # ──────────────────────────────────────────────────────
    def _method_1_fixed_fractional(
        self,
        portfolio_native: float,
        risk_per_share: float,
        conviction_mult: float,
        regime_mult: float,
        heat_mult: float,
    ) -> float:
        """
        Risk a fixed % of portfolio, scaled by conviction + regime + heat.

        risk_amount = portfolio × base% × conviction × regime × heat
        shares      = risk_amount / risk_per_share
        """
        if risk_per_share <= 0:
            return 0.0
        risk_amount = (portfolio_native * self.cfg.BASE_RISK_PCT
                       * conviction_mult * regime_mult * heat_mult)
        return risk_amount / risk_per_share

    # ──────────────────────────────────────────────────────
    # Method 2: Volatility-Adjusted (ATR Parity)
    # ──────────────────────────────────────────────────────
    def _method_2_volatility_parity(
        self,
        portfolio_native: float,
        atr_pct: float,
        entry_price: float,
    ) -> float:
        """
        Target a fixed daily vol contribution from this position.

        Higher ATR → smaller position (so daily $ move is constant).
        """
        if atr_pct <= 0 or entry_price <= 0:
            return 0.0
        target_daily_move = portfolio_native * self.cfg.TARGET_DAILY_VOL_PCT
        stock_daily_move_per_share = (atr_pct / 100) * entry_price
        return target_daily_move / max(stock_daily_move_per_share, 0.01)

    # ──────────────────────────────────────────────────────
    # Method 3: Fractional Kelly
    # ──────────────────────────────────────────────────────
    def _method_3_kelly(
        self,
        portfolio_native: float,
        setup_type: str,
        composite_score: float,
        risk_reward: float,
        entry_price: float,
    ) -> float:
        """
        Kelly Criterion with 25% fractional scaling (safer).

        kelly_f = p - (1-p) / R
        where p = win rate, R = average R:R
        """
        if entry_price <= 0 or risk_reward <= 0:
            return 0.0

        base_wr = self.cfg.SETUP_WIN_RATES.get(setup_type, 0.45)
        # Nudge win rate up/down based on score (centered on 65)
        adjusted_wr = base_wr + (composite_score - 65) * 0.005
        win_rate = min(self.cfg.KELLY_MAX_WIN_RATE, max(0.0, adjusted_wr))

        kelly_f = win_rate - (1 - win_rate) / risk_reward
        kelly_f = max(0.0, kelly_f)
        fractional = kelly_f * self.cfg.KELLY_FRACTION

        position_value = portfolio_native * fractional
        return position_value / entry_price

    # ──────────────────────────────────────────────────────
    # Method 4: Max Position Cap
    # ──────────────────────────────────────────────────────
    def _method_4_max_cap(
        self,
        portfolio_native: float,
        entry_price: float,
        risk_category: str,
    ) -> float:
        """Hard ceiling — never more than X% of portfolio in one name."""
        if entry_price <= 0:
            return 0.0
        cap_pct = self.cfg.MAX_POSITION_PCT.get(
            risk_category.upper(), 0.10)
        return (portfolio_native * cap_pct) / entry_price

    # ──────────────────────────────────────────────────────
    # Sector exposure check
    # ──────────────────────────────────────────────────────
    def _check_sector_exposure(
        self,
        inp: SizingInput,
        new_position_inr: float,
    ) -> str:
        """Return rejection reason if sector would exceed cap, else ''."""
        if not inp.sector or inp.sector == "Unknown":
            return ""

        same_sector_value = sum(
            p.get("position_value_inr", 0) for p in inp.open_positions
            if p.get("sector", "").lower() == inp.sector.lower()
        )
        projected = same_sector_value + new_position_inr
        projected_pct = projected / inp.portfolio_value_inr

        if projected_pct > self.cfg.MAX_SECTOR_EXPOSURE_PCT:
            return (f"Sector '{inp.sector}' would be "
                    f"{projected_pct*100:.1f}% of portfolio "
                    f"(cap: {self.cfg.MAX_SECTOR_EXPOSURE_PCT*100:.0f}%)")
        return ""


# ══════════════════════════════════════════════════════════════
# CONVENIENCE WRAPPER (integration with trade_advisor)
# ══════════════════════════════════════════════════════════════

def size_position_from_analysis(
    analysis: FullAnalysis,
    portfolio_value_inr: float,
    cash_available_inr: float,
    open_positions: Optional[List[Dict]] = None,
    regime_multiplier: Optional[float] = None,
    risk_category: Optional[str] = None,
    usd_inr_rate: Optional[float] = None,
) -> SizingOutput:
    """
    Convenience wrapper: takes a FullAnalysis from trade_advisor and returns
    a fully-reasoned SizingOutput.

    Designed to be called at the end of trade_advisor.analyze() so the
    terminal display can include sizing alongside the verdict.
    """
    # Derive currency from symbol (Indian tickers have .NS / .BO)
    is_indian = ".NS" in analysis.symbol.upper() or ".BO" in analysis.symbol.upper()
    currency = "INR" if is_indian else "USD"

    # Fallbacks from config
    rc = (risk_category or USER_PROFILE.get("risk_category", "AGGRESSIVE")).upper()
    ui = usd_inr_rate or USER_PROFILE.get("usd_inr_rate", 85.5)
    rm = regime_multiplier if regime_multiplier is not None \
        else get_regime_multiplier()

    # Grab ATR% from the analysis (trend section has no ATR, pull from daily df
    # if available — else estimate from risk_pct as a reasonable proxy)
    atr_pct = _extract_atr_pct(analysis)

    inp = SizingInput(
        symbol=analysis.symbol,
        entry_price=analysis.setup.entry,
        stop_loss=analysis.setup.stop_loss,
        current_price=analysis.current_price,
        composite_score=analysis.buy_score,
        confidence=analysis.confidence,
        setup_type=analysis.setup.setup_type,
        risk_reward=analysis.setup.risk_reward,
        atr_pct=atr_pct,
        portfolio_value_inr=portfolio_value_inr,
        cash_available_inr=cash_available_inr,
        currency=currency,
        usd_inr_rate=ui,
        risk_category=rc,
        regime_multiplier=rm,
        open_positions=open_positions or [],
        sector=analysis.sector,
    )

    sizer = PositionSizer()
    return sizer.size(inp)


def _extract_atr_pct(analysis: FullAnalysis) -> float:
    """Best-effort ATR% extraction — falls back to setup risk% if unavailable."""
    # Look inside section checks for an ATR value
    for section in analysis.sections.values():
        for check in section.checks:
            if "ATR" in check.name.upper() and check.value:
                return float(check.value)
    # Fallback: use stop-loss distance as a crude volatility proxy
    return max(1.5, analysis.setup.risk_pct)


# ══════════════════════════════════════════════════════════════
# CLI / DEMO
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Quick self-test / demo
    demo = SizingInput(
        symbol="DEMO.NS",
        entry_price=100.0,
        stop_loss=95.0,
        current_price=100.0,
        composite_score=78,
        confidence="HIGH",
        setup_type="pullback",
        risk_reward=2.5,
        atr_pct=3.0,
        portfolio_value_inr=500_000,
        cash_available_inr=200_000,
        currency="INR",
        risk_category="AGGRESSIVE",
        open_positions=[],
        sector="Finance",
    )
    result = PositionSizer().size(demo)
    print(result.format_for_terminal())