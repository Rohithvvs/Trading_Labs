"""Momentum_252, eligibility, and deterministic rank/select."""

from __future__ import annotations

import math
from typing import Iterable

from .identity import MAX_SELECTED, MOMENTUM_GATE


def momentum_252(close_t: float | None, close_t_minus_252: float | None) -> float | None:
    if close_t is None or close_t_minus_252 is None:
        return None
    try:
        ct = float(close_t)
        prev = float(close_t_minus_252)
    except (TypeError, ValueError):
        return None
    if prev == 0 or not math.isfinite(ct) or not math.isfinite(prev):
        return None
    value = ct / prev - 1.0
    if not math.isfinite(value):
        return None
    return value


def is_eligible(mom: float | None) -> bool:
    return mom is not None and math.isfinite(mom) and mom > MOMENTUM_GATE


def rank_eligible(
    pairs: Iterable[tuple[str, float]],
) -> list[tuple[str, float, int]]:
    """Sort eligible (symbol, momentum) by momentum desc, ticker asc.

    Returns (symbol, momentum, rank) with rank starting at 1.
    """
    eligible = [(str(sym), float(mom)) for sym, mom in pairs if is_eligible(mom)]
    eligible.sort(key=lambda item: (-item[1], item[0]))
    return [(sym, mom, idx + 1) for idx, (sym, mom) in enumerate(eligible)]


def select_top(
    ranked: list[tuple[str, float, int]],
    n: int = MAX_SELECTED,
) -> list[tuple[str, float, int]]:
    return ranked[:n]
