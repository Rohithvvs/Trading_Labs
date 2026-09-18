"""QuantConnect LEAN Slippage Models."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .qc_algorithm import Order, OrderDirection, Security


class ISlippageModel(ABC):
    @abstractmethod
    def get_slippage_approximation(self, order: Order, security: Security, base_price: float) -> float:
        pass


class ZeroSlippageModel(ISlippageModel):
    def get_slippage_approximation(self, order: Order, security: Security, base_price: float) -> float:
        return 0.0


class ConstantSlippageModel(ISlippageModel):
    """Constant percentage slippage (e.g. 5 bps = 0.0005)."""

    def __init__(self, percent: float = 0.0005) -> None:
        self.percent = percent

    def get_slippage_approximation(self, order: Order, security: Security, base_price: float) -> float:
        slippage_delta = base_price * self.percent
        if order.direction == OrderDirection.BUY:
            return slippage_delta
        return -slippage_delta
