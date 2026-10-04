"""v2-only trade advisor orchestrator.

Flow:
  1. DataEngine fetches OHLC + frames
  2. All analyzers run → sections with passed_checks (the 25 A-D features)
  3. compute_live_features → 11 E+F features
  4. analysis_to_trade_dict + extract_features → 36-dim feature vector
  5. model/scorer → score (0-100) + verdict (with VIX guardrail)
  6. Position sizing if verdict contains BUY
"""

from __future__ import annotations

import sys
from datetime import date as _date, datetime
from typing import Optional

from istock.decision.types import FullAnalysis, TradeConfig, TradeSetup
from istock.features.analyzers.trend import TrendAnalyzer
from istock.features.analyzers.location import LocationAnalyzer
from istock.features.analyzers.setup_detector import SetupDetector
from istock.features.analyzers.volume import VolumeAnalyzer
from istock.features.analyzers.momentum import MomentumAnalyzer
from istock.features.analyzers.candlesticks import CandlestickAnalyzer
from istock.features.analyzers.market_context import MarketContextAnalyzer
from istock.features.analyzers.risk_reward import RiskRewardCalculator
from istock.features.analyzers.avoid_checker import AvoidChecker
from istock.features.analyzers.sell_signals import SellSignalChecker
from istock.features.analyzers.support_resistance import SupportResistanceEngine
from istock.data.engine import DataEngine
from istock.features.spec import FEATURE_NAMES, extract_features
from istock.features.live_features import (
    VixDataUnavailable,
    analysis_to_trade_dict,
    compute_live_features,
    load_score_cache,
    save_score_cache,
)
from istock.model.scorer import HIGH_VIX_THRESHOLD, apply_vix_guardrail, score, verdict_from_score
from istock.model.weights import find_weight_for_ticker


class TradeAdvisor:
    """Orchestrates a full v2 analysis for one symbol."""

    def __init__(self) -> None:
        self._regime_shown = False

    def analyze(
        self,
        symbol: str,
        as_of_date: Optional[str] = None,
    ) -> Optional[FullAnalysis]:
        """Run complete v2 analysis. Returns None if data is unavailable.

        `as_of_date` (ISO string, e.g. "2025-10-01") slices price history
        inside DataEngine so back-tests compute as if it were that date.
        Fundamentals and regime remain current snapshots.
        """
        if not self._regime_shown:
            self._print_regime()
            self._regime_shown = True

        print(f"\n{'='*60}")
        if as_of_date:
            print(f"  🔍 ANALYZING: {symbol.upper()}  (as of {as_of_date})")
        else:
            print(f"  🔍 ANALYZING: {symbol.upper()}")
        print(f"{'='*60}")

        # ── 1. Fetch data ────────────────────────────────────────────────────
        data = DataEngine(symbol)
        try:
            ok = data.fetch_all(as_of_date=as_of_date)
        except ValueError as exc:
            print(f"  ❌ {exc}")
            return None
        if not ok:
            print(f"  ❌ Could not fetch data for {symbol}")
            return None

        price = data.current_price
        prev = data.prev_close
        change_pct = (price - prev) / prev * 100 if prev > 0 else 0.0

        print(f"  💰 Price: {price:.2f} ({change_pct:+.2f}%)")
        print(f"  🏢 {data.company_name}")
        print()

        # ── 2. Support / Resistance ──────────────────────────────────────────
        print("  📍 Calculating Support/Resistance...")
        sr = SupportResistanceEngine(data)
        supports, resistances, fib_levels = sr.calculate_all()

        # ── 3. Run all analyzers ─────────────────────────────────────────────
        print("  🧭 Analyzing Trend...")
        trend_result = TrendAnalyzer(data).analyze()

        print("  📍 Analyzing Location...")
        location_result = LocationAnalyzer(data, supports, resistances).analyze()

        print("  🔥 Detecting Setup...")
        setup_result, setup_type = SetupDetector(data, supports, resistances).analyze()

        print("  📊 Analyzing Volume...")
        volume_result = VolumeAnalyzer(data).analyze()

        print("  ⚡ Analyzing Momentum...")
        momentum_result = MomentumAnalyzer(data).analyze()

        print("  🕯️ Analyzing Candlestick Patterns...")
        candle_result = CandlestickAnalyzer(data).analyze()

        print("  🌍 Checking Market Context...")
        market_result = MarketContextAnalyzer(data).analyze()

        print("  💰 Calculating Risk/Reward...")
        rr_result, trade_setup = RiskRewardCalculator(
            data, supports, resistances, setup_type
        ).calculate()

        print("  🚫 Checking Avoid Conditions...")
        avoid_flags = AvoidChecker(data).check()

        print("  🔴 Checking Sell Signals...")
        sell_score, sell_checks = SellSignalChecker(data, supports).analyze()

        sections = {
            "trend": trend_result,
            "location": location_result,
            "setup": setup_result,
            "volume": volume_result,
            "momentum": momentum_result,
            "candles": candle_result,
            "risk_reward": rr_result,
            "market_context": market_result,
        }

        # ── 4. V2 scoring ────────────────────────────────────────────────────
        ticker_uc = symbol.upper()
        aod = (
            datetime.strptime(as_of_date, "%Y-%m-%d").date()
            if as_of_date
            else _date.today()
        )

        v2_score, v2_verdict, v2_source, guardrail_applied, skipped_reason = (
            self._run_v2_scoring(
                ticker_uc, aod, data, sections, supports
            )
        )

        # ── 5. Assemble result ───────────────────────────────────────────────
        key_obs = self._generate_observations(
            sections, sell_score, sell_checks, avoid_flags, trade_setup
        )

        # Fallback: when v2 weights aren't trained yet, derive verdict from
        # section scores so the scanner still produces actionable output.
        if v2_verdict is None:
            fallback_score = self._section_score(sections)
            effective_verdict = self._verdict_from_section_score(fallback_score)
            effective_score = fallback_score
        else:
            effective_verdict = v2_verdict
            effective_score = v2_score

        result = FullAnalysis(
            symbol=ticker_uc,
            company_name=data.company_name,
            current_price=price,
            previous_close=prev,
            day_change_pct=round(change_pct, 2),
            verdict=effective_verdict,
            buy_score=effective_score,
            sell_score=round(sell_score, 1),
            net_score=round(effective_score - sell_score * 0.5, 1),
            confidence=self._confidence_from_score(effective_score),
            setup=trade_setup,
            sections=sections,
            support_levels=supports,
            resistance_levels=resistances,
            fibonacci_levels=fib_levels,
            avoid_flags=avoid_flags,
            key_observations=key_obs,
            weekly_trend=trend_result.summary,
            daily_trend=trend_result.summary,
            sector=data.info.get("sector", "N/A"),
            market_cap=self._format_market_cap(data.info.get("marketCap", 0)),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            v2_verdict=v2_verdict,
            v2_score=v2_score,
            v2_source=v2_source,
            v2_vix_guardrail_applied=guardrail_applied,
            v2_skipped_reason=skipped_reason,
        )

        # ── 6. Position sizing (BUY verdicts only; gated off by config) ───────
        try:
            from istock.config import ENABLE_POSITION_SIZING
        except Exception:
            ENABLE_POSITION_SIZING = False
        if (
            ENABLE_POSITION_SIZING
            and "BUY" in effective_verdict
            and trade_setup.setup_type != "none"
        ):
            self._try_position_sizing(result)

        return result

    # ── V2 scoring pipeline ──────────────────────────────────────────────────

    def _run_v2_scoring(self, ticker, aod, data, sections, supports):
        """Return (v2_score, v2_verdict, v2_source, guardrail_applied, skipped_reason)."""
        # Cache hit
        cached = load_score_cache(ticker, aod)
        if cached is not None:
            return (
                cached.get("v2_score"),
                cached.get("v2_verdict"),
                cached.get("v2_source"),
                cached.get("vix_guardrail_applied"),
                cached.get("v2_skipped_reason"),
            )

        # Weights
        ws = find_weight_for_ticker(ticker)
        if ws is None:
            return None, None, None, None, (
                "no pooled weights on disk — run scripts/train_brain_v2.py first"
            )

        # Feature extraction
        try:
            extra = compute_live_features(ticker, data.daily, as_of_date=aod)
            # Build a temporary FullAnalysis-like object just to reuse analysis_to_trade_dict.
            # We pass `sections` directly via a simple namespace.
            _proxy = _SectionsProxy(sections)
            trade_dict = analysis_to_trade_dict(
                _proxy, ticker,
                sample_date=aod.isoformat(),
                extra_keys=extra,
            )
            features_vec = extract_features(trade_dict)
        except Exception as exc:
            return None, None, None, None, f"feature extraction failed: {exc}"

        # Score
        try:
            raw_score = score(features_vec, ws)
            raw_verdict = verdict_from_score(raw_score)
        except Exception as exc:
            return None, None, None, None, f"v2 scoring failed: {exc}"

        # VIX guardrail — gated by config (disabled 2026-07-06: rolling-eval
        # evidence showed high-VIX entries are the system's best trades).
        skipped_reason = None
        guardrail_applied = False
        final_verdict = raw_verdict
        try:
            from istock.config import ENABLE_VIX_GUARDRAIL
        except Exception:
            ENABLE_VIX_GUARDRAIL = True
        if ENABLE_VIX_GUARDRAIL:
            try:
                current_vix = _get_vix(aod)
                final_verdict = apply_vix_guardrail(raw_verdict, current_vix)
                guardrail_applied = (
                    current_vix > HIGH_VIX_THRESHOLD and final_verdict != raw_verdict
                )
            except VixDataUnavailable as exc:
                skipped_reason = "vix_unavailable"
                print(f"  ⚠️  brain_v2 VIX unavailable: {exc}", file=sys.stderr)

        v2_score_rounded = round(float(raw_score), 1)

        # Write cache
        try:
            features_named = {name: int(features_vec[i]) for i, name in enumerate(FEATURE_NAMES)}
            save_score_cache({
                "ticker": ticker,
                "date": aod.isoformat(),
                "v2_score": v2_score_rounded,
                "v2_verdict": final_verdict,
                "v2_source": ws.source,
                "v2_features": features_named,
                "vix_at_compute": None if skipped_reason else None,
                "vix_guardrail_applied": guardrail_applied,
                "v2_skipped_reason": skipped_reason,
                "computed_at": datetime.now().isoformat(timespec="seconds"),
            })
        except Exception as exc:
            print(f"  ⚠️  brain_v2 score cache write failed: {exc}", file=sys.stderr)

        return v2_score_rounded, final_verdict, ws.source, guardrail_applied, skipped_reason

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _confidence_from_score(v2_score: Optional[float]) -> str:
        if v2_score is None:
            return "LOW"
        if v2_score >= 75 or v2_score <= 25:
            return "HIGH"
        if v2_score >= 60 or v2_score <= 40:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _print_regime() -> None:
        try:
            from istock.decision.regime import RegimeDetector
            reg = RegimeDetector()
            reading = reg.detect()
            print(reg.format_for_terminal(reading))
        except Exception as exc:
            print(f"  ⚠️ Regime detection skipped: {exc}")

    @staticmethod
    def _try_position_sizing(result: FullAnalysis) -> None:
        try:
            from istock.decision.position_sizer import size_position_from_analysis
            sizing = size_position_from_analysis(
                result,
                portfolio_value_inr=500_000,
                cash_available_inr=100_000,
                open_positions=[],
            )
            print(sizing.format_for_terminal())
        except Exception as exc:
            print(f"  ⚠️ Position sizing skipped: {exc}")

    @staticmethod
    def _generate_observations(sections, sell_score, sell_checks, avoid_flags, setup):
        obs = []
        best = max(sections.items(), key=lambda x: x[1].score)
        worst = min(sections.items(), key=lambda x: x[1].score)
        obs.append(f"💪 Strongest: {best[0].title()} ({best[1].score:.0f}/100)")
        obs.append(f"⚠️ Weakest: {worst[0].title()} ({worst[1].score:.0f}/100)")
        if setup.setup_type != "none":
            obs.append(f"📋 Setup: {setup.setup_type.upper()} (R:R = 1:{setup.risk_reward})")
        else:
            obs.append("📋 No clear trade setup - consider waiting")
        if setup.risk_pct > 5:
            obs.append(f"⚠️ Wide stop ({setup.risk_pct:.1f}%) - consider smaller position")
        if sell_score > 40:
            obs.append(f"🔴 Sell signals present ({sell_score:.0f}/100)")
            for c in [c for c in sell_checks if c.passed][:2]:
                obs.append(f"  → {c.name}")
        return obs

    @staticmethod
    def _section_score(sections: dict) -> float:
        """Weighted average of section scores — used as fallback when v2 weights aren't trained."""
        weights = {
            "trend": 18, "location": 20, "setup": 15, "volume": 10,
            "momentum": 15, "candles": 7, "risk_reward": 10, "market_context": 5,
        }
        total_w, total_s = 0.0, 0.0
        for key, w in weights.items():
            sec = sections.get(key)
            if sec is None:
                continue
            try:
                total_s += float(sec.score) * w
                total_w += w
            except (AttributeError, TypeError, ValueError):
                pass
        return round(total_s / total_w, 1) if total_w > 0 else 50.0

    @staticmethod
    def _verdict_from_section_score(score: float) -> str:
        if score >= 70:
            return "BUY"
        if score >= 58:
            return "LEAN BUY"
        if score <= 35:
            return "AVOID"
        return "HOLD"

    @staticmethod
    def _format_market_cap(mc) -> str:
        if not mc:
            return "N/A"
        if mc >= 1e12:
            return f"${mc/1e12:.1f}T"
        if mc >= 1e9:
            return f"${mc/1e9:.1f}B"
        if mc >= 1e6:
            return f"${mc/1e6:.0f}M"
        return f"${mc:,.0f}"


# ── Internal helpers ─────────────────────────────────────────────────────────

class _SectionsProxy:
    """Minimal duck-type so analysis_to_trade_dict can read sections."""
    def __init__(self, sections):
        self.sections = sections


def _get_vix(aod: _date) -> float:
    from istock.features.live_features import get_current_vix
    return get_current_vix(as_of_date=aod)
