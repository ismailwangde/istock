"""V2 exit rules — stub; real implementation pending.

Rule (per bar):
    if low <= stop_floored:       EXIT ('stop')
    elif verdict is bearish:      EXIT ('verdict_bearish')
    else:                         hold

stop_floored = max(orig_stop, 2.0 × ATR14, entry × 1.5%)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass
class ExitDecision:
    should_exit: bool
    reason: str       # "stop" | "verdict_bearish" | "hold"
    exit_price: float


def stop_with_floor(
    entry: float,
    orig_stop: float,
    atr14: float,
    floor_pct: float = 1.5,
    atr_mult: float = 2.0,
) -> float:
    raise NotImplementedError("Stub — implementation pending")


def check_exit(
    position: Mapping,
    today_bar: Mapping,
    today_verdict: str,
) -> ExitDecision:
    raise NotImplementedError("Stub — implementation pending")
