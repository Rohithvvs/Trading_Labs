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
