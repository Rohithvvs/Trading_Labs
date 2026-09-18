"""Mode A (default) and Mode B sizing. Whole shares for live; fractional research."""

from __future__ import annotations

import math

from .identity import DEFAULT_MODE, MAX_SELECTED


def target_notionals(
    *,
    selected: list[str],
    cash_after_sells: float,
    equity: float,
    mode: str = DEFAULT_MODE,
    skip: set[str] | None = None,
    whole_shares: bool = False,
    prices: dict[str, float] | None = None,
) -> dict[str, float]:
    """Return target notional per selected name.

    Unbuyable names in ``skip`` are omitted. Mode A redistributes cash across
    remaining names. Mode B leaves that slot in cash (10% × remaining).
    """
    names = [s for s in selected if s not in (skip or set())]
    if not names:
        return {}
    mode_u = (mode or DEFAULT_MODE).upper()
    if mode_u == "B":
        slot = float(equity) * 0.10
        notionals = {s: slot for s in names[:MAX_SELECTED]}
    else:
        each = float(cash_after_sells) / len(names)
        notionals = {s: each for s in names}

    if whole_shares and prices:
        rounded: dict[str, float] = {}
        for sym, notional in notionals.items():
            px = prices.get(sym)
            if px is None or px <= 0 or not math.isfinite(px):
                continue
            shares = math.floor(notional / px)
            if shares <= 0:
                continue
            rounded[sym] = shares * px
        return rounded
    return notionals


def shares_from_notional(notional: float, fill_price: float, *, whole_shares: bool) -> float:
    if fill_price <= 0 or not math.isfinite(fill_price) or notional <= 0:
        return 0.0
    raw = notional / fill_price
    if whole_shares:
        return float(math.floor(raw))
    return float(raw)
