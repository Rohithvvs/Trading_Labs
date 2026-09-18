"""Mode B: 10% of current equity per name, max 10, next-ranked substitute."""

from __future__ import annotations

import math

from .identity import ALLOC_PCT, MAX_POSITIONS


def free_slots(n_holdings: int, *, max_positions: int = MAX_POSITIONS) -> int:
    return max(0, max_positions - n_holdings)


def target_notional(equity: float, *, alloc_pct: float = ALLOC_PCT) -> float:
    return max(0.0, float(equity) * alloc_pct)


def shares_from_notional(notional: float, fill: float, *, whole_shares: bool = False) -> float:
    if fill <= 0 or notional <= 0:
        return 0.0
    raw = notional / fill
    if whole_shares:
        return float(math.floor(raw))
    return raw


def shares_for_order(
    fill: float,
    *,
    order_size_type: str = "percent_equity",
    default_order_size: float = 0.0,
    equity: float = 0.0,
    cash: float = 0.0,
    alloc_pct: float = ALLOC_PCT,
    apply_costs: bool = True,
    whole_shares: bool = False,
) -> float:
    """Qty from tester config, else 038 percent-of-equity sizing."""
    if (order_size_type or "percent_equity") == "quantity" and float(default_order_size) > 0:
        sh = float(default_order_size)
        if whole_shares:
            return float(math.floor(sh))
        return sh
    alloc = min(target_notional(equity, alloc_pct=alloc_pct), max(float(cash), 0.0))
    fee_est = alloc * 0.002 if apply_costs else 0.0
    investable = max(0.0, min(float(cash) - fee_est, alloc))
    return shares_from_notional(investable, fill, whole_shares=whole_shares)


def take_ranked(ranked: list[tuple[str, float, int]], n: int, *, unbuyable: set[str] | None = None) -> list[str]:
    """Take the first n buyable names (skip halted/banned, substitute next-ranked)."""
    skip = set(unbuyable or ())
    taken: list[str] = []
    for sym, _mom, _rank in ranked:
        if sym in skip:
            continue
        taken.append(sym)
        if len(taken) >= n:
            break
    return taken
