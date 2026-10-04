"""Trade Review — did trading beat doing nothing?

Pure math, no network: callers pass in today's prices and benchmark closes.
For every holding we compare three outcomes on the SAME dollars:

  actual      what really happened: value still held + cash from sells − cash put in
  never_sold  every share bought held until today (shows what the sells did)
  benchmark   each buy's cash put into the index (SPY / Nifty) that day, held until today

Assumption (MVP): cash from sells earns nothing, and no trading costs or taxes
are modelled. All amounts are in the holding's native currency.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def _price(t: Dict[str, Any]) -> float:
    p = t.get("price_inr") if "price_inr" in t else t.get("price_usd")
    return float(p or 0)


def review_holding(
    holding: Dict[str, Any],
    price_now: float,
    bench_on: Callable[[str], Optional[float]],
    bench_now: Optional[float],
) -> Optional[Dict[str, Any]]:
    """Three-way comparison for one holding. `bench_on(iso_date)` returns the
    benchmark close on/before that date (None if unknown)."""
    trades = holding.get("trades") or []
    buys = [t for t in trades if str(t.get("action", "BUY")).upper() == "BUY"]
    sells = [t for t in trades if str(t.get("action", "")).upper() == "SELL"]
    if not buys or not price_now:
        return None

    bought_qty = sum(float(t.get("qty", 0)) for t in buys)
    sold_qty = min(sum(float(t.get("qty", 0)) for t in sells), bought_qty)
    bought_cash = sum(float(t.get("qty", 0)) * _price(t) for t in buys)
    if bought_cash <= 0:
        return None
    # Proceeds scaled down if the record sells more than was bought.
    raw_sold = sum(float(t.get("qty", 0)) for t in sells)
    sold_cash = sum(float(t.get("qty", 0)) * _price(t) for t in sells)
    if raw_sold > bought_qty and raw_sold > 0:
        sold_cash *= bought_qty / raw_sold

    actual = (bought_qty - sold_qty) * price_now + sold_cash - bought_cash
    never_sold = bought_qty * price_now - bought_cash

    bench: Optional[float] = None
    if bench_now:
        total = 0.0
        for t in buys:
            b0 = bench_on(str(t.get("date")))
            if not b0:
                total = None
                break
            total += float(t.get("qty", 0)) * _price(t) * (bench_now / b0)
        if total is not None:
            bench = total - bought_cash

    return {
        "symbol": holding.get("symbol", "?"),
        "n_buys": len(buys),
        "n_sells": len(sells),
        "invested": bought_cash,
        "actual": actual,
        "never_sold": never_sold,
        "benchmark": bench,
    }


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Win/loss stats over positions (open + closed), using actual P&L.
    `rows` must already be in ONE currency (the caller converts)."""
    pnls = [r["actual"] for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    return {
        "positions": len(pnls),
        "winners": len(wins),
        "losers": len(losses),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": (avg_win / abs(avg_loss)) if (avg_win and avg_loss) else None,
        "trades": sum(r["n_buys"] + r["n_sells"] for r in rows),
    }
