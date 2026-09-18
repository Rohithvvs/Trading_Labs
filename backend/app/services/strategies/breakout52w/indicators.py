"""52W indicators: prior 252-high, Vol SMA20, SMA ATR14 (not Wilder), MarketOK, Momentum_60."""

from __future__ import annotations

import math
from typing import Sequence

from .identity import ATR_PERIOD, HIGH_LOOKBACK, MARKET_SMA_PERIOD, RANK_LOOKBACK, VOL_SMA_PERIOD


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value))


def prior_high_252(highs: Sequence[float | None], t: int) -> float | None:
    """Max high over the 252 sessions ending on t-1 (today's high excluded)."""
    if t < HIGH_LOOKBACK:
        return None
    window = highs[t - HIGH_LOOKBACK : t]
    if len(window) < HIGH_LOOKBACK:
        return None
    vals: list[float] = []
    for h in window:
        if not _finite(h):
            return None
        vals.append(float(h))
    return max(vals)


def vol_sma20(volumes: Sequence[float | None], t: int) -> float | None:
    """Mean volume over 20 sessions ending on t (today included)."""
    if t < VOL_SMA_PERIOD - 1:
        return None
    window = volumes[t - (VOL_SMA_PERIOD - 1) : t + 1]
    if len(window) < VOL_SMA_PERIOD:
        return None
    vals: list[float] = []
    for v in window:
        if not _finite(v):
            return None
        vals.append(float(v))
    return sum(vals) / VOL_SMA_PERIOD


def true_range(high: float | None, low: float | None, prev_close: float | None) -> float | None:
    if not _finite(high) or not _finite(low):
        return None
    span = float(high) - float(low)
    if not _finite(prev_close):
        return span
    pc = float(prev_close)
    return max(span, abs(float(high) - pc), abs(float(low) - pc))


def atr14(
    highs: Sequence[float | None],
    lows: Sequence[float | None],
    closes: Sequence[float | None],
    t: int,
) -> float | None:
    """SMA of true range over 14 sessions ending on t (today included). Not Wilder."""
    if t < ATR_PERIOD - 1:
        return None
    trs: list[float] = []
    start = t - (ATR_PERIOD - 1)
    for i in range(start, t + 1):
        prev = closes[i - 1] if i > 0 else None
        tr = true_range(highs[i], lows[i], prev)
        if tr is None:
            return None
        trs.append(tr)
    if len(trs) < ATR_PERIOD:
        return None
    return sum(trs) / ATR_PERIOD


def wilder_atr14(
    highs: Sequence[float | None],
    lows: Sequence[float | None],
    closes: Sequence[float | None],
    t: int,
) -> float | None:
    """Wilder / RMA ATR — provided only so tests can prove it differs from SMA ATR."""
    if t < ATR_PERIOD - 1:
        return None
    first = atr14(highs, lows, closes, ATR_PERIOD - 1)
    if first is None:
        return None
    value = first
    for i in range(ATR_PERIOD, t + 1):
        prev = closes[i - 1] if i > 0 else None
        tr = true_range(highs[i], lows[i], prev)
        if tr is None:
            return None
        value = (value * (ATR_PERIOD - 1) + tr) / ATR_PERIOD
    return value


def market_sma50(benchmark: Sequence[float | None], t: int) -> float | None:
    if t < MARKET_SMA_PERIOD - 1:
        return None
    window = benchmark[t - (MARKET_SMA_PERIOD - 1) : t + 1]
    if len(window) < MARKET_SMA_PERIOD:
        return None
    vals: list[float] = []
    for v in window:
        if not _finite(v):
            return None
        vals.append(float(v))
    return sum(vals) / MARKET_SMA_PERIOD


def market_ok(benchmark: Sequence[float | None], t: int) -> bool | None:
    """True iff benchmark close is strictly greater than its 50-session SMA."""
    if t < 0 or t >= len(benchmark) or not _finite(benchmark[t]):
        return None
    sma = market_sma50(benchmark, t)
    if sma is None:
        return None
    return float(benchmark[t]) > sma


def momentum_60(closes: Sequence[float | None], t: int) -> float | None:
    if t < RANK_LOOKBACK:
        return None
    today = closes[t]
    prev = closes[t - RANK_LOOKBACK]
    if not _finite(today) or not _finite(prev) or float(prev) == 0:
        return None
    return float(today) / float(prev) - 1.0
