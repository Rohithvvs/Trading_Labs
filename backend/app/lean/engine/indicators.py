"""QuantConnect LEAN Indicator Framework."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime
import math
from typing import Any

from .qc_algorithm import RollingWindow, TradeBar


class IndicatorBase(ABC):
    def __init__(self, name: str, period: int) -> None:
        self.name = name
        self.period = period
        self.samples = 0
        self._current_value: float = 0.0
        self._current_time: datetime = datetime.min

    @property
    def is_ready(self) -> bool:
        return self.samples >= self.period

    @property
    def value(self) -> float:
        return self._current_value

    @property
    def current(self) -> float:
        return self._current_value

    @abstractmethod
    def update(self, time: datetime, value: float) -> bool:
        pass

    def __float__(self) -> float:
        return self._current_value

    def __repr__(self) -> str:
        return f"{self.name}(period={self.period}, value={self._current_value:.4f}, ready={self.is_ready})"


class SimpleMovingAverage(IndicatorBase):
    """LEAN SimpleMovingAverage indicator."""

    def __init__(self, period: int, name: str = "SMA") -> None:
        super().__init__(name, period)
        self._window: deque[float] = deque(maxlen=period)
        self._sum: float = 0.0

    def update(self, time: datetime, value: float) -> bool:
        if value is None or math.isnan(value) or math.isinf(value):
            return self.is_ready
        self.samples += 1
        self._current_time = time
        if len(self._window) == self.period:
            self._sum -= self._window[0]
        self._window.append(float(value))
        self._sum += float(value)
        self._current_value = self._sum / len(self._window)
        return self.is_ready


class ExponentialMovingAverage(IndicatorBase):
    """LEAN ExponentialMovingAverage indicator."""

    def __init__(self, period: int, name: str = "EMA") -> None:
        super().__init__(name, period)
        self._k = 2.0 / (period + 1.0)
        self._initialized = False

    def update(self, time: datetime, value: float) -> bool:
        if value is None or math.isnan(value) or math.isinf(value):
            return self.is_ready
        self.samples += 1
        self._current_time = time
        val = float(value)
        if not self._initialized:
            self._current_value = val
            self._initialized = True
        else:
            self._current_value = (val * self._k) + (self._current_value * (1.0 - self._k))
        return self.is_ready


class Maximum(IndicatorBase):
    """LEAN Maximum indicator (rolling max over N periods, including current bar)."""

    def __init__(self, period: int, name: str = "MAX") -> None:
        super().__init__(name, period)
        self._window: deque[float] = deque(maxlen=period)

    def update(self, time: datetime, value: float) -> bool:
        if value is None or math.isnan(value) or math.isinf(value):
            return self.is_ready
        self.samples += 1
        self._current_time = time
        self._window.append(float(value))
        self._current_value = max(self._window)
        return self.is_ready


class PriorSessionMaximum(IndicatorBase):
    """Prior N-session Maximum (STRICTLY excludes current bar t; uses t-N to t-1)."""

    def __init__(self, period: int = 252, name: str = "PriorHigh252") -> None:
        super().__init__(name, period)
        self._history: deque[float] = deque(maxlen=period + 1)

    def update(self, time: datetime, value: float) -> bool:
        if value is None or math.isnan(value) or math.isinf(value):
            return self.is_ready
        self.samples += 1
        self._current_time = time
        self._history.append(float(value))
        if len(self._history) >= self.period + 1:
            # Exclude the latest item (index -1)
            past_items = list(self._history)[:-1]
            self._current_value = max(past_items)
        elif len(self._history) == self.period:
            # Exactly 252 bars, past 251 bars known; once 253rd bar arrives, ready
            self._current_value = max(list(self._history)[:-1]) if len(self._history) > 1 else self._history[0]
        return self.is_ready

    @property
    def is_ready(self) -> bool:
        return self.samples > self.period


class RelativeStrengthIndex(IndicatorBase):
    """LEAN RelativeStrengthIndex indicator with Wilder smoothing."""

    def __init__(self, period: int = 14, name: str = "RSI") -> None:
        super().__init__(name, period)
        self._prev_price: float | None = None
        self._avg_gain: float = 0.0
        self._avg_loss: float = 0.0

    def update(self, time: datetime, value: float) -> bool:
        if value is None or math.isnan(value) or math.isinf(value):
            return self.is_ready
        val = float(value)
        self._current_time = time
        if self._prev_price is None:
            self._prev_price = val
            return False

        change = val - self._prev_price
        self._prev_price = val
        gain = max(0.0, change)
        loss = max(0.0, -change)
        self.samples += 1

        if self.samples <= self.period:
            self._avg_gain = (self._avg_gain * (self.samples - 1) + gain) / self.samples
            self._avg_loss = (self._avg_loss * (self.samples - 1) + loss) / self.samples
        else:
            self._avg_gain = (self._avg_gain * (self.period - 1) + gain) / self.period
            self._avg_loss = (self._avg_loss * (self.period - 1) + loss) / self.period

        if self._avg_loss == 0.0:
            self._current_value = 100.0 if self._avg_gain > 0 else 50.0
        else:
            rs = self._avg_gain / self._avg_loss
            self._current_value = 100.0 - (100.0 / (1.0 + rs))

        return self.is_ready


class AverageTrueRange:
    """LEAN AverageTrueRange indicator (SMA of True Range)."""

    def __init__(self, period: int = 14, name: str = "ATR") -> None:
        self.name = name
        self.period = period
        self.samples = 0
        self._window: deque[float] = deque(maxlen=period)
        self._prev_close: float | None = None
        self._current_value: float = 0.0

    @property
    def is_ready(self) -> bool:
        return self.samples >= self.period

    @property
    def value(self) -> float:
        return self._current_value

    def update(self, bar: TradeBar) -> bool:
        high = float(bar.high)
        low = float(bar.low)
        span = high - low
        if self._prev_close is not None:
            tr = max(span, abs(high - self._prev_close), abs(low - self._prev_close))
        else:
            tr = span

        self._prev_close = float(bar.close)
        self.samples += 1
        self._window.append(tr)
        self._current_value = sum(self._window) / len(self._window)
        return self.is_ready
