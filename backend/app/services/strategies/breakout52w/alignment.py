"""Per-symbol trading-session alignment for 52W indicators.

A missing calendar date for one symbol must not insert a None candle into
another symbol's lookback. Indicator functions still receive a dense sequence
of that symbol's own valid sessions; they are not changed to skip holes.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from .identity import HIGH_LOOKBACK


def native_prefix(
    values: Sequence[float | None],
    t: int,
) -> tuple[list[float | None], int | None]:
    """Compact a calendar-aligned series through index ``t``.

    ``None`` means the symbol did not trade that calendar date and is omitted.
    Non-finite numbers are kept so indicator validation still fails on bad bars.
    """
    if t < 0 or not values:
        return [], None
    compact: list[float | None] = []
    today_idx: int | None = None
    end = min(t + 1, len(values))
    for i in range(end):
        v = values[i]
        if v is None:
            continue
        if i == t:
            today_idx = len(compact)
        compact.append(v)
    return compact, today_idx


def prior_high_index(today_idx: int | None, native_len: int) -> int:
    """``t`` for ``prior_high_252``: today's bar is excluded when present."""
    if today_idx is not None:
        return today_idx
    return native_len


def native_prior_session_count(series: Mapping[date, object], asof: date) -> int:
    """Count this symbol's own sessions strictly before ``asof``."""
    return sum(1 for d in series if d < asof)


def history_valid_native(
    series: Mapping[date, object],
    asof: date,
    *,
    lookback: int = HIGH_LOOKBACK,
) -> bool:
    """True when the symbol has ``lookback`` of its own sessions before ``asof``."""
    return native_prior_session_count(series, asof) >= lookback


@dataclass(frozen=True)
class NativeSeries:
    """Chronological valid sessions for one symbol (no calendar padding)."""

    dates: list[date]
    values: list[float]

    @classmethod
    def from_map(cls, series: Mapping[date, float]) -> "NativeSeries":
        dates = sorted(series)
        return cls(dates, [float(series[d]) for d in dates])

    def prefix(self, asof: date) -> tuple[list[float], int | None]:
        if not self.dates:
            return [], None
        i = bisect_right(self.dates, asof) - 1
        if i < 0:
            return [], None
        vals = self.values[: i + 1]
        today = i if self.dates[i] == asof else None
        return vals, today
