# QuantConnect algorithm — paste into a new Python algorithm at quantconnect.com
# Purpose: the SURVIVORSHIP-FREE test of our momentum ranker.
#
# Why QuantConnect: its US equity data includes DELISTED companies and its
# universe selection is point-in-time — so the stocks it ranks each month are
# the ones that were actually liquid THEN, bankruptcies and all. This is the
# honest version of istock/training/factor_ranker.py, which is inflated because
# our 268-name list only contains today's survivors.
#
# What it does (identical logic to our local ranker):
#   1. Each month, take the ~500 most liquid US stocks (point-in-time).
#   2. Score each by 12-1 momentum (return from ~12mo ago to ~1mo ago).
#   3. Hold the top 20 equal-weight; rebalance monthly.
#   4. Benchmark = SPY total return.
#
# Expected outcome that would VALIDATE the edge: momentum still beats SPY by a
# few pp/yr here (survivorship-free). If the edge collapses to ~0, our local
# +17pp was pure survivorship illusion. Either way, we finally know.

from AlgorithmImports import *


class MomentumRanker(QCAlgorithm):

    def initialize(self):
        self.set_start_date(1999, 1, 1)   # extended per stress test: must include 2000-02 and 2008-09
        self.set_end_date(2026, 5, 31)
        self.set_cash(100_000)

        self.top_n = 20            # try 10 for the concentrated version
        self.lookback = 252        # ~12 months of trading days
        self.skip = 21             # ~1 month skipped (12-1 momentum)
        self.universe_size = 500   # liquid names to rank each month

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # realistic-ish costs; QC default fee model + a little slippage
        self.set_security_initializer(
            lambda s: s.set_slippage_model(ConstantSlippageModel(0.0005)))

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self._coarse_selection)

        self._selected = []
        # rebalance once a month, shortly after the open
        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self._rebalance)

    def _coarse_selection(self, coarse):
        """Point-in-time top-N liquid US stocks (survivorship-free)."""
        liquid = [c for c in coarse if c.has_fundamental_data and c.price > 5]
        liquid.sort(key=lambda c: c.dollar_volume, reverse=True)
        self._selected = [c.symbol for c in liquid[:self.universe_size]]
        return self._selected

    def _rebalance(self):
        if not self._selected:
            return
        # pull enough history to measure 12-1 momentum
        hist = self.history(self._selected, self.lookback + self.skip + 5,
                            Resolution.DAILY)
        if hist.empty or "close" not in hist.columns:
            return
        closes = hist["close"].unstack(level=0)

        scores = {}
        for sym in closes.columns:
            s = closes[sym].dropna()
            if len(s) >= self.lookback + self.skip:
                past = s.iloc[-(self.lookback + self.skip)]   # ~12mo ago
                recent = s.iloc[-self.skip]                    # ~1mo ago
                if past > 0:
                    scores[sym] = recent / past - 1.0
        if not scores:
            return

        winners = [sym for sym, _ in
                   sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:self.top_n]]

        # sell anything that dropped out of the top list
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in winners:
                self.liquidate(holding.symbol)

        # equal-weight the winners
        weight = 1.0 / len(winners)
        for sym in winners:
            self.set_holdings(sym, weight)
