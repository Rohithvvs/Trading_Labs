"""Explicit technical-analysis helpers. No eval, no lookahead."""

from __future__ import annotations

import math
from typing import Sequence

Scalar = float | bool | str | None


def _finite(value: Scalar) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def as_float(value: Scalar) -> float | None:
    if _finite(value):
        return float(value)  # type: ignore[arg-type]
    return None


def shift(values: Sequence[Scalar], offset: int) -> list[Scalar]:
    n = len(values)
    out: list[Scalar] = [None] * n
    if offset < 0:
        return out
    for i in range(offset, n):
        out[i] = values[i - offset]
    return out


def sma(values: Sequence[Scalar], length: int) -> list[Scalar]:
    n = len(values)
    out: list[Scalar] = [None] * n
    if length <= 0:
        return out
    window = 0.0
    valid = 0
    for i in range(n):
        cur = as_float(values[i])
        if cur is not None:
            window += cur
            valid += 1
        if i >= length:
            old = as_float(values[i - length])
            if old is not None:
                window -= old
                valid -= 1
        if i >= length - 1 and valid == length:
            out[i] = window / length
    return out


def ema(values: Sequence[Scalar], length: int) -> list[Scalar]:
    n = len(values)
    out: list[Scalar] = [None] * n
    if length <= 0:
        return out
    seed = sma(values, length)
    k = 2.0 / (length + 1.0)
    prev: float | None = None
    for i, raw in enumerate(values):
        cur = as_float(raw)
        if cur is None:
            prev = None
            continue
        if prev is None:
            seeded = as_float(seed[i])
            if seeded is None:
                continue
            prev = seeded
            out[i] = prev
            continue
        prev = cur * k + prev * (1.0 - k)
        out[i] = prev
    return out


def rma(values: Sequence[Scalar], length: int) -> list[Scalar]:
    n = len(values)
    out: list[Scalar] = [None] * n
    if length <= 0:
        return out
    seed = sma(values, length)
    prev: float | None = None
    for i, raw in enumerate(values):
        cur = as_float(raw)
        if cur is None:
            prev = None
            continue
        if prev is None:
            seeded = as_float(seed[i])
            if seeded is None:
                continue
            prev = seeded
            out[i] = prev
            continue
        prev = (prev * (length - 1) + cur) / length
        out[i] = prev
    return out


def rolling_extreme(values: Sequence[Scalar], length: int, *, high: bool) -> list[Scalar]:
    n = len(values)
    out: list[Scalar] = [None] * n
    if length <= 0:
        return out
    for i in range(length - 1, n):
        window = [as_float(values[j]) for j in range(i - length + 1, i + 1)]
        if any(v is None for v in window):
            continue
        nums = [float(v) for v in window]  # type: ignore[arg-type]
        out[i] = max(nums) if high else min(nums)
    return out


def true_range(highs: Sequence[Scalar], lows: Sequence[Scalar], closes: Sequence[Scalar]) -> list[Scalar]:
    n = len(closes)
    out: list[Scalar] = [None] * n
    for i in range(n):
        high = as_float(highs[i] if i < len(highs) else None)
        low = as_float(lows[i] if i < len(lows) else None)
        if high is None or low is None:
            continue
        span = high - low
        prev = as_float(closes[i - 1]) if i else None
        if prev is None:
            out[i] = span
            continue
        out[i] = max(span, abs(high - prev), abs(low - prev))
    return out


def atr(highs: Sequence[Scalar], lows: Sequence[Scalar], closes: Sequence[Scalar], length: int) -> list[Scalar]:
    return rma(true_range(highs, lows, closes), length)


def rsi(values: Sequence[Scalar], length: int) -> list[Scalar]:
    n = len(values)
    out: list[Scalar] = [None] * n
    if length <= 0 or n < length + 1:
        return out
    gains = 0.0
    losses = 0.0
    prev = as_float(values[0])
    for i in range(1, length + 1):
        cur = as_float(values[i])
        if prev is None or cur is None:
            return out
        delta = cur - prev
        if delta >= 0:
            gains += delta
        else:
            losses += -delta
        prev = cur
    avg_gain = gains / length
    avg_loss = losses / length
    out[length] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    for i in range(length + 1, n):
        cur = as_float(values[i])
        if prev is None or cur is None:
            prev = cur
            continue
        delta = cur - prev
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0
        avg_gain = (avg_gain * (length - 1) + gain) / length
        avg_loss = (avg_loss * (length - 1) + loss) / length
        out[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        prev = cur
    return out


def crossover(a: Sequence[Scalar], b: Sequence[Scalar]) -> list[Scalar]:
    n = min(len(a), len(b))
    out: list[Scalar] = [None] * len(a)
    for i in range(n):
        if i == 0:
            out[i] = False
            continue
        a0 = as_float(a[i])
        b0 = as_float(b[i])
        a1 = as_float(a[i - 1])
        b1 = as_float(b[i - 1])
        if a0 is None or b0 is None or a1 is None or b1 is None:
            out[i] = False
            continue
        out[i] = a1 <= b1 and a0 > b0
    return out


def crossunder(a: Sequence[Scalar], b: Sequence[Scalar]) -> list[Scalar]:
    n = min(len(a), len(b))
    out: list[Scalar] = [None] * len(a)
    for i in range(n):
        if i == 0:
            out[i] = False
            continue
        a0 = as_float(a[i])
        b0 = as_float(b[i])
        a1 = as_float(a[i - 1])
        b1 = as_float(b[i - 1])
        if a0 is None or b0 is None or a1 is None or b1 is None:
            out[i] = False
            continue
        out[i] = a1 >= b1 and a0 < b0
    return out
