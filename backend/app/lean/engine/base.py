"""Abstract BacktestEngine base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from ..models import LeanBacktestRequest, LeanBacktestResult
from .qc_algorithm import TradeBar


class BacktestEngine(ABC):
    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Returns the engine identifier (e.g. 'LEAN' or 'EXISTING')."""
        pass

    @abstractmethod
    async def run_backtest(
        self,
        request: LeanBacktestRequest,
        data_map: dict[str, list[TradeBar]],
        benchmark_bars: list[TradeBar] | None = None,
        progress_callback: Callable[[int, str], Any] | None = None,
    ) -> LeanBacktestResult:
        """Execute a backtest run and return normalized LeanBacktestResult."""
        pass
