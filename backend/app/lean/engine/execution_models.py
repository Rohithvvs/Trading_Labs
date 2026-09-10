"""QuantConnect LEAN Order Execution Models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
import logging
from typing import Any, TYPE_CHECKING

from .fee_models import IFeeModel, NseFeeModel
from .qc_algorithm import (
    Order,
    OrderDirection,
    OrderEvent,
    OrderStatus,
    OrderTicket,
    QCAlgorithm,
    Security,
    Slice,
    Symbol,
)
from .slippage_models import ConstantSlippageModel, ISlippageModel

if TYPE_CHECKING:
    pass

logger = logging.getLogger("app.lean.execution")


class IExecutionModel(ABC):
    @abstractmethod
    def execute_pending_orders(
        self,
        algorithm: QCAlgorithm,
        current_slice: Slice,
        fee_model: IFeeModel,
        slippage_model: ISlippageModel,
    ) -> list[OrderEvent]:
        pass


class NextBarOpenExecutionModel(IExecutionModel):
    """Fills pending orders at the next trading bar's Open price + slippage."""

    def execute_pending_orders(
        self,
        algorithm: QCAlgorithm,
        current_slice: Slice,
        fee_model: IFeeModel,
        slippage_model: ISlippageModel,
    ) -> list[OrderEvent]:
        events: list[OrderEvent] = []
        remaining_orders: list[Order] = []

        for order in algorithm._pending_orders:
            symbol = order.symbol
            if not current_slice.contains_key(symbol):
                # Bar not present in current slice, keep pending
                remaining_orders.append(order)
                continue

            bar = current_slice[symbol]
            security = algorithm.securities[symbol]
            base_price = float(bar.open)

            # Apply slippage
            slippage = slippage_model.get_slippage_approximation(order, security, base_price)
            fill_price = base_price + slippage
            qty = order.quantity

            if order.direction == OrderDirection.BUY:
                # Sizing / Cash check
                fee = fee_model.get_order_fee(order, fill_price, qty)
                required_cash = (qty * fill_price) + fee

                # Reduce qty if cash insufficient
                while qty > 0 and (qty * fill_price + fee) > algorithm.portfolio.cash:
                    qty -= 1
                    fee = fee_model.get_order_fee(order, fill_price, qty)

                if qty <= 0:
                    order.status = OrderStatus.INVALID
                    continue

                # Execute BUY
                cost = (qty * fill_price) + fee
                algorithm.portfolio.cash -= cost
                algorithm.portfolio.total_fees += fee

                prev_qty = security.holdings.quantity
                prev_avg = security.holdings.average_price
                new_qty = prev_qty + qty
                new_avg = ((prev_qty * prev_avg) + (qty * fill_price)) / new_qty if new_qty > 0 else fill_price

                security.holdings.quantity = new_qty
                security.holdings.average_price = new_avg
                security.holdings.total_fees += fee

                # Track trade entry
                algorithm._open_positions_trade_info[symbol] = {
                    "entry_date": bar.time.strftime("%Y-%m-%d"),
                    "entry_price": fill_price,
                    "quantity": qty,
                    "entry_reason": order.tag or "Signal Entry",
                    "entry_fee": fee,
                    "entry_slippage": abs(slippage) * qty,
                    "entry_bar_time": bar.time,
                }

                order.status = OrderStatus.FILLED
                event = OrderEvent(
                    order_id=order.order_id,
                    symbol=symbol,
                    time=bar.time,
                    status=OrderStatus.FILLED,
                    fill_price=fill_price,
                    fill_quantity=qty,
                    order_fee=fee,
                    direction=OrderDirection.BUY,
                    message=f"Filled at {fill_price:.2f}",
                )
                events.append(event)
                algorithm.on_order_event(event)

            elif order.direction == OrderDirection.SELL:
                curr_qty = security.holdings.quantity
                fill_qty = min(qty, curr_qty) if curr_qty > 0 else qty
                if fill_qty <= 0:
                    order.status = OrderStatus.INVALID
                    continue

                fee = fee_model.get_order_fee(order, fill_price, fill_qty)
                proceeds = (fill_qty * fill_price) - fee
                algorithm.portfolio.cash += proceeds
                algorithm.portfolio.total_fees += fee

                # Calculate closed trade metrics
                entry_info = algorithm._open_positions_trade_info.pop(symbol, None)
                if entry_info:
                    entry_price = entry_info["entry_price"]
                    entry_date = entry_info["entry_date"]
                    entry_fee = entry_info.get("entry_fee", 0.0)
                    entry_slippage = entry_info.get("entry_slippage", 0.0)
                    holding_days = max(1, (bar.time - entry_info["entry_bar_time"]).days)
                    entry_reason = entry_info.get("entry_reason", "Signal")
                else:
                    entry_price = security.holdings.average_price
                    entry_date = bar.time.strftime("%Y-%m-%d")
                    entry_fee = 0.0
                    entry_slippage = 0.0
                    holding_days = 1
                    entry_reason = "Unknown"

                gross_pnl = (fill_price - entry_price) * fill_qty
                total_trade_fee = entry_fee + fee
                total_trade_slippage = entry_slippage + (abs(slippage) * fill_qty)
                net_pnl = gross_pnl - total_trade_fee - total_trade_slippage
                cost_basis = (entry_price * fill_qty) + entry_fee
                return_pct = (net_pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0

                algorithm._trade_id_counter += 1
                closed_trade = {
                    "trade_id": algorithm._trade_id_counter,
                    "symbol": symbol.value,
                    "entry_date": entry_date,
                    "entry_price": round(entry_price, 2),
                    "exit_date": bar.time.strftime("%Y-%m-%d"),
                    "exit_price": round(fill_price, 2),
                    "quantity": fill_qty,
                    "direction": "LONG",
                    "gross_pnl": round(gross_pnl, 2),
                    "commission": round(total_trade_fee, 2),
                    "slippage": round(total_trade_slippage, 2),
                    "net_pnl": round(net_pnl, 2),
                    "return_pct": round(return_pct, 2),
                    "holding_period": holding_days,
                    "entry_reason": entry_reason,
                    "exit_reason": order.tag or "Signal Exit",
                    "is_open": False,
                }
                algorithm._closed_trades.append(closed_trade)
                algorithm.portfolio.realized_pnl += net_pnl

                security.holdings.quantity -= fill_qty
                if security.holdings.quantity <= 0:
                    security.holdings.quantity = 0
                    security.holdings.average_price = 0.0

                order.status = OrderStatus.FILLED
                event = OrderEvent(
                    order_id=order.order_id,
                    symbol=symbol,
                    time=bar.time,
                    status=OrderStatus.FILLED,
                    fill_price=fill_price,
                    fill_quantity=fill_qty,
                    order_fee=fee,
                    direction=OrderDirection.SELL,
                    message=f"Sold at {fill_price:.2f}",
                )
                events.append(event)
                algorithm.on_order_event(event)

        algorithm._pending_orders = remaining_orders
        return events
