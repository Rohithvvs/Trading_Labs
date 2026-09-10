"""QuantConnect LEAN Fee Models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .qc_algorithm import Order, OrderDirection, Security


class IFeeModel(ABC):
    @abstractmethod
    def get_order_fee(self, order: Order, fill_price: float, fill_qty: int) -> float:
        pass


class ZeroFeeModel(IFeeModel):
    def get_order_fee(self, order: Order, fill_price: float, fill_qty: int) -> float:
        return 0.0


class ConstantFeeModel(IFeeModel):
    def __init__(self, rate: float = 0.0005) -> None:
        self.rate = rate

    def get_order_fee(self, order: Order, fill_price: float, fill_qty: int) -> float:
        turnover = fill_price * fill_qty
        return turnover * self.rate


class NseFeeModel(IFeeModel):
    """Realistic Indian NSE Equity transaction costs (STT, Brokerage, Exchange, SEBI, GST, Stamp Duty, DP)."""

    def __init__(
        self,
        brokerage_rate: float = 0.0005,
        brokerage_flat_cap: float = 20.0,
        stt_rate_buy: float = 0.001,
        stt_rate_sell: float = 0.001,
        exchange_turnover_rate: float = 0.0000345,
        sebi_rate: float = 0.000001,
        stamp_duty_rate: float = 0.00015,
        gst_rate: float = 0.18,
        dp_charge_flat: float = 13.50,
    ) -> None:
        self.brokerage_rate = brokerage_rate
        self.brokerage_flat_cap = brokerage_flat_cap
        self.stt_rate_buy = stt_rate_buy
        self.stt_rate_sell = stt_rate_sell
        self.exchange_turnover_rate = exchange_turnover_rate
        self.sebi_rate = sebi_rate
        self.stamp_duty_rate = stamp_duty_rate
        self.gst_rate = gst_rate
        self.dp_charge_flat = dp_charge_flat

    def get_order_fee(self, order: Order, fill_price: float, fill_qty: int) -> float:
        turnover = fill_price * fill_qty
        if turnover <= 0 or fill_qty <= 0:
            return 0.0

        is_buy = order.direction == OrderDirection.BUY
        brokerage = min(turnover * self.brokerage_rate, self.brokerage_flat_cap) if self.brokerage_flat_cap > 0 else turnover * self.brokerage_rate
        stt = turnover * (self.stt_rate_buy if is_buy else self.stt_rate_sell)
        etc = turnover * self.exchange_turnover_rate
        sebi = turnover * self.sebi_rate
        stamp_duty = turnover * self.stamp_duty_rate if is_buy else 0.0
        gst = (brokerage + etc + sebi) * self.gst_rate
        dp_charge = self.dp_charge_flat if not is_buy else 0.0

        return float(brokerage + stt + etc + sebi + stamp_duty + gst + dp_charge)
