"""Deterministic OHLCV indicators. Values at bar t use only bars 0..t inclusive.

No future candle is read. Prior N-day High/Low exclude the current bar so a
close-vs-high comparison is not tautological and does not leak today's high
into a "prior range" test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from .schema import Operand


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value))


def _as_float(value: float | None) -> float | None:
    if not _finite(value):
        return None
    return float(value)


def sma(values: Sequence[float | None], period: int) -> list[float | None]:
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return out
    cur_sum = 0.0
    valid_count = 0
    for i in range(period):
        v = values[i]
        if _finite(v):
            cur_sum += float(v)  # type: ignore[arg-type]
            valid_count += 1
    if valid_count == period:
        out[period - 1] = cur_sum / period
    for i in range(period, n):
        old_v = values[i - period]
        new_v = values[i]
        if _finite(old_v):
            cur_sum -= float(old_v)  # type: ignore[arg-type]
            valid_count -= 1
        if _finite(new_v):
            cur_sum += float(new_v)  # type: ignore[arg-type]
            valid_count += 1
        if valid_count == period:
            out[i] = cur_sum / period
    return out


def ema(values: Sequence[float | None], period: int) -> list[float | None]:
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0:
        return out
    seed = sma(values, period)
    k = 2.0 / (period + 1.0)
    prev: float | None = None
    for i, raw in enumerate(values):
        if not _finite(raw):
            prev = None
            continue
        if prev is None:
            if seed[i] is None:
                continue
            prev = seed[i]
            out[i] = prev
            continue
        prev = float(raw) * k + prev * (1.0 - k)
        out[i] = prev
    return out


def wma(values: Sequence[float | None], period: int) -> list[float | None]:
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0:
        return out
    denom = period * (period + 1) / 2.0
    for i in range(period - 1, n):
        window = values[i - period + 1 : i + 1]
        if not all(_finite(v) for v in window):
            continue
        total = 0.0
        for w, v in enumerate(window, start=1):
            total += w * float(v)  # type: ignore[arg-type]
        out[i] = total / denom
    return out


def rsi(values: Sequence[float | None], period: int = 14) -> list[float | None]:
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0 or n < period + 1:
        return out
    gains = 0.0
    losses = 0.0
    prev = values[0]
    for i in range(1, period + 1):
        cur = values[i]
        if not _finite(prev) or not _finite(cur):
            return out
        delta = float(cur) - float(prev)  # type: ignore[arg-type]
        if delta >= 0:
            gains += delta
        else:
            losses += -delta
        prev = cur
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100.0 - (100.0 / (1.0 + rs))
    for i in range(period + 1, n):
        cur = values[i]
        if not _finite(prev) or not _finite(cur):
            prev = cur
            continue
        delta = float(cur) - float(prev)  # type: ignore[arg-type]
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))
        prev = cur
    return out


def macd_components(values: Sequence[float | None]) -> tuple[list[float | None], list[float | None], list[float | None]]:
    fast = ema(values, 12)
    slow = ema(values, 26)
    line: list[float | None] = [None] * len(values)
    for i, (a, b) in enumerate(zip(fast, slow)):
        if _finite(a) and _finite(b):
            line[i] = float(a) - float(b)  # type: ignore[arg-type]
    signal = ema(line, 9)
    hist: list[float | None] = [None] * len(values)
    for i, (a, b) in enumerate(zip(line, signal)):
        if _finite(a) and _finite(b):
            hist[i] = float(a) - float(b)  # type: ignore[arg-type]
    return line, signal, hist


def true_range(high: float | None, low: float | None, prev_close: float | None) -> float | None:
    if not _finite(high) or not _finite(low):
        return None
    span = float(high) - float(low)  # type: ignore[arg-type]
    if not _finite(prev_close):
        return span
    pc = float(prev_close)  # type: ignore[arg-type]
    return max(span, abs(float(high) - pc), abs(float(low) - pc))  # type: ignore[arg-type]


def atr(highs: Sequence[float | None], lows: Sequence[float | None], closes: Sequence[float | None], period: int = 14) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    trs: list[float | None] = [None] * n
    for i in range(n):
        prev = closes[i - 1] if i else None
        trs[i] = true_range(highs[i] if i < len(highs) else None, lows[i] if i < len(lows) else None, prev)
    seed = sma(trs, period)
    prev_atr = None
    for i in range(n):
        if seed[i] is not None and prev_atr is None:
            prev_atr = seed[i]
            out[i] = prev_atr
            continue
        if prev_atr is None or not _finite(trs[i]):
            continue
        prev_atr = (prev_atr * (period - 1) + float(trs[i])) / period  # type: ignore[arg-type]
        out[i] = prev_atr
    return out


def bollinger(
    values: Sequence[float | None],
    period: int = 20,
    std_mult: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None], list[float | None]]:
    mid = sma(values, period)
    n = len(values)
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    width: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return upper, mid, lower, width

    cur_sum_sq = 0.0
    valid_count = 0
    for i in range(period):
        v = values[i]
        if _finite(v):
            cur_sum_sq += float(v) * float(v)  # type: ignore[arg-type]
            valid_count += 1
    if valid_count == period and mid[period - 1] is not None:
        mean = float(mid[period - 1])  # type: ignore[arg-type]
        var = max(0.0, (cur_sum_sq / period) - (mean * mean))
        sd = math.sqrt(var)
        upper[period - 1] = mean + std_mult * sd
        lower[period - 1] = mean - std_mult * sd
        if mean != 0:
            width[period - 1] = (upper[period - 1] - lower[period - 1]) / mean  # type: ignore[operator]

    for i in range(period, n):
        old_v = values[i - period]
        new_v = values[i]
        if _finite(old_v):
            cur_sum_sq -= float(old_v) * float(old_v)  # type: ignore[arg-type]
            valid_count -= 1
        if _finite(new_v):
            cur_sum_sq += float(new_v) * float(new_v)  # type: ignore[arg-type]
            valid_count += 1
        if valid_count == period and mid[i] is not None:
            mean = float(mid[i])  # type: ignore[arg-type]
            var = max(0.0, (cur_sum_sq / period) - (mean * mean))
            sd = math.sqrt(var)
            upper[i] = mean + std_mult * sd
            lower[i] = mean - std_mult * sd
            if mean != 0:
                width[i] = (upper[i] - lower[i]) / mean  # type: ignore[operator]
    return upper, mid, lower, width


def stochastic(
    highs: Sequence[float | None],
    lows: Sequence[float | None],
    closes: Sequence[float | None],
    period: int = 14,
    smooth: int = 3,
) -> tuple[list[float | None], list[float | None]]:
    n = len(closes)
    k_raw: list[float | None] = [None] * n
    for i in range(period - 1, n):
        h_win = highs[i - period + 1 : i + 1]
        l_win = lows[i - period + 1 : i + 1]
        if not all(_finite(v) for v in h_win) or not all(_finite(v) for v in l_win) or not _finite(closes[i]):
            continue
        hh = max(float(v) for v in h_win)  # type: ignore[arg-type]
        ll = min(float(v) for v in l_win)  # type: ignore[arg-type]
        if hh == ll:
            k_raw[i] = 50.0
        else:
            k_raw[i] = (float(closes[i]) - ll) / (hh - ll) * 100.0  # type: ignore[arg-type]
    k = sma(k_raw, 1) if smooth <= 1 else sma(k_raw, smooth)
    d = sma(k, smooth)
    return k, d


def roc(values: Sequence[float | None], period: int = 12) -> list[float | None]:
    n = len(values)
    out: list[float | None] = [None] * n
    for i in range(period, n):
        prev = values[i - period]
        cur = values[i]
        if not _finite(prev) or not _finite(cur) or float(prev) == 0:  # type: ignore[arg-type]
            continue
        out[i] = (float(cur) - float(prev)) / float(prev) * 100.0  # type: ignore[arg-type]
    return out


def historical_volatility(values: Sequence[float | None], period: int = 20) -> list[float | None]:
    n = len(values)
    out: list[float | None] = [None] * n
    log_ret: list[float | None] = [None] * n
    for i in range(1, n):
        prev = values[i - 1]
        cur = values[i]
        if not _finite(prev) or not _finite(cur) or float(prev) <= 0 or float(cur) <= 0:  # type: ignore[arg-type]
            continue
        log_ret[i] = math.log(float(cur) / float(prev))  # type: ignore[arg-type]
    for i in range(period, n):
        window = log_ret[i - period + 1 : i + 1]
        if not all(_finite(v) for v in window):
            continue
        mean = sum(float(v) for v in window) / period  # type: ignore[arg-type]
        var = sum((float(v) - mean) ** 2 for v in window) / period  # type: ignore[arg-type]
        out[i] = math.sqrt(var) * math.sqrt(252.0) * 100.0
    return out


def rolling_vwap(
    highs: Sequence[float | None],
    lows: Sequence[float | None],
    closes: Sequence[float | None],
    volumes: Sequence[float | None],
    period: int | None = None,
) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    cum_pv = 0.0
    cum_v = 0.0
    typical: list[float | None] = [None] * n
    for i in range(n):
        if _finite(highs[i]) and _finite(lows[i]) and _finite(closes[i]):
            typical[i] = (float(highs[i]) + float(lows[i]) + float(closes[i])) / 3.0  # type: ignore[arg-type]
        vol = float(volumes[i]) if _finite(volumes[i]) else 0.0
        if period is None:
            if typical[i] is None:
                continue
            cum_pv += typical[i] * vol  # type: ignore[operator]
            cum_v += vol
            if cum_v > 0:
                out[i] = cum_pv / cum_v
        else:
            if i < period - 1:
                continue
            pv = 0.0
            vv = 0.0
            ok = True
            for j in range(i - period + 1, i + 1):
                if typical[j] is None:
                    ok = False
                    break
                vj = float(volumes[j]) if _finite(volumes[j]) else 0.0
                pv += typical[j] * vj  # type: ignore[operator]
                vv += vj
            if ok and vv > 0:
                out[i] = pv / vv
    return out


def prior_nday_extreme(values: Sequence[float | None], period: int, *, extreme: str) -> list[float | None]:
    """Max/min of the previous `period` bars, excluding the current bar."""
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0:
        return out
    for i in range(period, n):
        window = values[i - period : i]
        if not all(_finite(v) for v in window):
            continue
        nums = [float(v) for v in window]  # type: ignore[arg-type]
        out[i] = max(nums) if extreme == "high" else min(nums)
    return out


def shift(values: Sequence[float | None], lag: int = 1) -> list[float | None]:
    n = len(values)
    out: list[float | None] = [None] * n
    for i in range(lag, n):
        out[i] = _as_float(values[i - lag])
    return out


def pct_change(values: Sequence[float | None], lag: int = 1) -> list[float | None]:
    n = len(values)
    out: list[float | None] = [None] * n
    for i in range(lag, n):
        prev = values[i - lag]
        cur = values[i]
        if not _finite(prev) or not _finite(cur) or float(prev) == 0:  # type: ignore[arg-type]
            continue
        out[i] = (float(cur) - float(prev)) / float(prev) * 100.0  # type: ignore[arg-type]
    return out


@dataclass
class BarSeries:
    dates: list[date]
    open: list[float | None]
    high: list[float | None]
    low: list[float | None]
    close: list[float | None]
    volume: list[float | None]
    cache: dict[str, list[float | None]] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.dates)

    def index_on_or_after(self, day: date) -> int | None:
        for i, d in enumerate(self.dates):
            if d >= day:
                return i
        return None

    def index_on_or_before(self, day: date) -> int | None:
        found = None
        for i, d in enumerate(self.dates):
            if d <= day:
                found = i
            else:
                break
        return found

    def series_for(self, operand: Operand) -> list[float | None]:
        if operand.kind != "series" or not operand.name:
            raise ValueError("literal operand has no series")
        key = operand.key()
        if key in self.cache:
            return self.cache[key]
        values = self._compute(operand)
        self.cache[key] = values
        return values

    def value_at(self, operand: Operand, t: int) -> float | None:
        if operand.kind == "literal":
            return operand.value
        series = self.series_for(operand)
        if t < 0 or t >= len(series):
            return None
        return _as_float(series[t])

    def snapshot(self, t: int, extras: Sequence[Operand] | None = None) -> dict[str, float | None]:
        wanted = [
            Operand(kind="series", name="CLOSE"),
            Operand(kind="series", name="OPEN"),
            Operand(kind="series", name="HIGH"),
            Operand(kind="series", name="LOW"),
            Operand(kind="series", name="VOLUME"),
            Operand(kind="series", name="PREV_CLOSE"),
            Operand(kind="series", name="RSI", period=14),
            Operand(kind="series", name="SMA", period=20),
            Operand(kind="series", name="SMA", period=50),
            Operand(kind="series", name="SMA", period=200),
            Operand(kind="series", name="AVG_VOLUME", period=20),
            Operand(kind="series", name="HIGH", period=252),
            Operand(kind="series", name="ATR", period=14),
            Operand(kind="series", name="MACD"),
            Operand(kind="series", name="MACD_SIGNAL"),
        ]
        if extras:
            wanted.extend(extras)
        out: dict[str, float | None] = {}
        for operand in wanted:
            out[operand.key().lower()] = self.value_at(operand, t)
        return out

    def _compute(self, operand: Operand) -> list[float | None]:
        name = (operand.name or "").upper()
        period = operand.period
        if name == "BENCHMARK_CLOSE":
            # Only reached when this BarSeries IS the benchmark index series;
            # stock-series snapshots exclude benchmark leaves (see schema.collect_series_keys).
            return list(self.close)
        if name == "OPEN":
            return list(self.open)
        if name == "HIGH":
            if period:
                return prior_nday_extreme(self.high, period, extreme="high")
            return list(self.high)
        if name == "LOW":
            if period:
                return prior_nday_extreme(self.low, period, extreme="low")
            return list(self.low)
        if name == "CLOSE":
            return list(self.close)
        if name == "VOLUME":
            return list(self.volume)
        if name == "PREV_CLOSE":
            return shift(self.close, 1)
        if name == "PREV_HIGH":
            return shift(self.high, 1)
        if name == "DAILY_RETURN":
            return pct_change(self.close, 1)
        if name == "GAP_PCT":
            n = len(self.close)
            out: list[float | None] = [None] * n
            for i in range(1, n):
                prev = self.close[i - 1]
                op = self.open[i]
                if not _finite(prev) or not _finite(op) or float(prev) == 0:  # type: ignore[arg-type]
                    continue
                out[i] = (float(op) - float(prev)) / float(prev) * 100.0  # type: ignore[arg-type]
            return out
        if name == "SMA":
            return sma(self.close, period or 50)
        if name == "EMA":
            return ema(self.close, period or 20)
        if name == "WMA":
            return wma(self.close, period or 20)
        if name == "RSI":
            return rsi(self.close, period or 14)
        if name == "MACD":
            line, _, _ = macd_components(self.close)
            return line
        if name == "MACD_SIGNAL":
            _, signal, _ = macd_components(self.close)
            return signal
        if name == "MACD_HISTOGRAM":
            _, _, hist = macd_components(self.close)
            return hist
        if name == "STOCH_K":
            k, _ = stochastic(self.high, self.low, self.close, period or 14)
            return k
        if name == "STOCH_D":
            _, d = stochastic(self.high, self.low, self.close, period or 14)
            return d
        if name == "ROC":
            return roc(self.close, period or 12)
        if name == "ATR":
            return atr(self.high, self.low, self.close, period or 14)
        if name == "BB_UPPER":
            upper, _, _, _ = bollinger(self.close, period or 20, operand.std or 2.0)
            return upper
        if name == "BB_MIDDLE":
            _, mid, _, _ = bollinger(self.close, period or 20, operand.std or 2.0)
            return mid
        if name == "BB_LOWER":
            _, _, lower, _ = bollinger(self.close, period or 20, operand.std or 2.0)
            return lower
        if name == "BB_WIDTH":
            _, _, _, width = bollinger(self.close, period or 20, operand.std or 2.0)
            return width
        if name == "HV":
            return historical_volatility(self.close, period or 20)
        if name == "VWAP":
            return rolling_vwap(self.high, self.low, self.close, self.volume, period)
        if name == "AVG_VOLUME":
            return sma(self.volume, period or 20)
        if name == "REL_VOLUME":
            avg = sma(self.volume, period or 20)
            out = [None] * len(self.volume)
            for i, (v, a) in enumerate(zip(self.volume, avg)):
                if _finite(v) and _finite(a) and float(a) != 0:  # type: ignore[arg-type]
                    out[i] = float(v) / float(a)  # type: ignore[arg-type]
            return out
        if name == "VOLUME_CHANGE_PCT":
            return pct_change(self.volume, 1)
        raise ValueError(f"Unknown series {name}")
