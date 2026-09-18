"""Official Python QCAlgorithm base classes and QuantConnect LEAN primitives."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
import math
from typing import Any, Generic, Iterator, Sequence, TypeVar

T = TypeVar("T")


class Resolution(str, Enum):
    DAILY = "Daily"
    HOUR = "Hour"
    MINUTE = "Minute"
    SECOND = "Second"
    TICK = "Tick"


class Market(str, Enum):
    INDIA = "india"
    USA = "usa"
    NSE = "nse"


class SecurityType(str, Enum):
    EQUITY = "equity"
    INDEX = "index"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    MARKET_ON_OPEN = "market_on_open"
    MARKET_ON_CLOSE = "market_on_close"


class OrderStatus(str, Enum):
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    INVALID = "invalid"


class OrderDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class Symbol:
    value: str
    security_type: SecurityType = SecurityType.EQUITY
    market: Market = Market.INDIA

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"Symbol({self.value})"

    def __hash__(self) -> int:
        return hash((self.value.upper(), self.security_type, self.market))

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Symbol):
            return self.value.upper() == other.value.upper()
        if isinstance(other, str):
            return self.value.upper() == other.upper()
        return False


@dataclass
class TradeBar:
    symbol: Symbol
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    period: timedelta = timedelta(days=1)

    @property
    def end_time(self) -> datetime:
        return self.time + self.period

    @property
    def price(self) -> float:
        return self.close

    @property
    def value(self) -> float:
        return self.close


class RollingWindow(Generic[T]):
    """Exact QuantConnect LEAN RollingWindow[T] implementation.
    
    Index 0 is the most recent item, index 1 is 1 step ago, index N-1 is N steps ago.
    """

    def __init__(self, size: int) -> None:
        if size <= 0:
            raise ValueError("RollingWindow size must be positive")
        self._size = size
        self._queue: deque[T] = deque(maxlen=size)

    @property
    def size(self) -> int:
        return self._size

    @property
    def count(self) -> int:
        return len(self._queue)

    @property
    def is_ready(self) -> bool:
        return len(self._queue) >= self._size

    def add(self, item: T) -> None:
        self._queue.appendleft(item)

    def __getitem__(self, index: int) -> T:
        if index < 0 or index >= len(self._queue):
            raise IndexError(f"RollingWindow index {index} out of range [0, {len(self._queue)-1}]")
        return self._queue[index]

    def __len__(self) -> int:
        return len(self._queue)

    def __iter__(self) -> Iterator[T]:
        return iter(self._queue)

    def __repr__(self) -> str:
        items = list(self._queue)
        return f"RollingWindow(size={self._size}, count={len(self._queue)}, items={items})"


class Slice:
    """QuantConnect LEAN Slice representing multi-asset data at a single timestamp."""

    def __init__(self, time: datetime, bars: dict[Symbol, TradeBar]) -> None:
        self.time = time
        self.bars = bars
        self._by_str: dict[str, TradeBar] = {str(k.value).upper(): v for k, v in bars.items()}

    def contains_key(self, key: Symbol | str) -> bool:
        if isinstance(key, Symbol):
            return key in self.bars
        return str(key).upper() in self._by_str

    def get(self, key: Symbol | str, default: Any = None) -> TradeBar | None:
        if isinstance(key, Symbol):
            return self.bars.get(key, default)
        return self._by_str.get(str(key).upper(), default)

    def __getitem__(self, key: Symbol | str) -> TradeBar:
        if isinstance(key, Symbol):
            return self.bars[key]
        sym = str(key).upper()
        if sym in self._by_str:
            return self._by_str[sym]
        raise KeyError(f"Symbol {key} not found in Slice at {self.time}")

    def __contains__(self, key: Symbol | str) -> bool:
        return self.contains_key(key)

    @property
    def symbols(self) -> list[Symbol]:
        return list(self.bars.keys())


@dataclass
class Order:
    order_id: int
    symbol: Symbol
    time: datetime
    type: OrderType
    direction: OrderDirection
    quantity: int
    price: float
    status: OrderStatus = OrderStatus.SUBMITTED
    tag: str = ""
    stop_price: float | None = None
    limit_price: float | None = None


@dataclass
class OrderEvent:
    order_id: int
    symbol: Symbol
    time: datetime
    status: OrderStatus
    fill_price: float
    fill_quantity: int
    order_fee: float
    direction: OrderDirection
    message: str = ""


@dataclass
class OrderTicket:
    order: Order
    status: OrderStatus = OrderStatus.SUBMITTED
    filled_quantity: int = 0
    average_fill_price: float = 0.0
    order_fee: float = 0.0

    @property
    def order_id(self) -> int:
        return self.order.order_id

    @property
    def symbol(self) -> Symbol:
        return self.order.symbol

    @property
    def quantity(self) -> int:
        return self.order.quantity


@dataclass
class SecurityHolding:
    symbol: Symbol
    quantity: int = 0
    average_price: float = 0.0
    total_fees: float = 0.0

    @property
    def invested(self) -> bool:
        return self.quantity != 0

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    def unrealized_pnl(self, current_price: float) -> float:
        if self.quantity == 0:
            return 0.0
        return (current_price - self.average_price) * self.quantity

    def market_value(self, current_price: float) -> float:
        return abs(self.quantity) * current_price


class Security:
    def __init__(self, symbol: Symbol) -> None:
        self.symbol = symbol
        self.holdings = SecurityHolding(symbol)
        self.open: float = 0.0
        self.high: float = 0.0
        self.low: float = 0.0
        self.close: float = 0.0
        self.volume: int = 0
        self.time: datetime = datetime.min

    @property
    def price(self) -> float:
        return self.close


class Portfolio:
    def __init__(self, initial_cash: float = 100000.0) -> None:
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.securities: dict[Symbol, Security] = {}
        self.total_fees: float = 0.0
        self.realized_pnl: float = 0.0

    def add_security(self, security: Security) -> None:
        self.securities[security.symbol] = security

    def total_portfolio_value(self) -> float:
        val = self.cash
        for sym, sec in self.securities.items():
            if sec.holdings.invested:
                val += sec.holdings.quantity * sec.price
        return val

    def total_unrealized_profit(self) -> float:
        pnl = 0.0
        for sym, sec in self.securities.items():
            if sec.holdings.invested:
                pnl += sec.holdings.unrealized_pnl(sec.price)
        return pnl

    def invested_capital(self) -> float:
        inv = 0.0
        for sym, sec in self.securities.items():
            if sec.holdings.invested:
                inv += sec.holdings.quantity * sec.holdings.average_price
        return inv

    def __getitem__(self, key: Symbol | str) -> SecurityHolding:
        if isinstance(key, Symbol):
            return self.securities[key].holdings
        for sym, sec in self.securities.items():
            if sym.value.upper() == str(key).upper():
                return sec.holdings
        raise KeyError(f"Symbol {key} not in portfolio")


class QCAlgorithm:
    """QuantConnect LEAN Python Algorithm Base Class."""

    def __init__(self) -> None:
        self._start_date: datetime = datetime(2020, 1, 1)
        self._end_date: datetime = datetime.now()
        self._initial_cash: float = 100000.0
        self.portfolio: Portfolio = Portfolio(self._initial_cash)
        self.securities: dict[Symbol, Security] = {}
        self.time: datetime = datetime.min
        self.benchmark_symbol: Symbol | None = None
        self._order_counter: int = 0
        self._order_tickets: list[OrderTicket] = []
        self._pending_orders: list[Order] = []
        self._closed_trades: list[dict[str, Any]] = []
        self._trade_id_counter: int = 0
        self._open_positions_trade_info: dict[Symbol, dict[str, Any]] = {}
        self.commission_rate: float = 0.0005
        self.slippage_rate: float = 0.0005
        self.debug_mode: bool = False
        self.logs: list[str] = []

    def set_start_date(self, year: int, month: int, day: int) -> None:
        self._start_date = datetime(year, month, day)

    def set_end_date(self, year: int, month: int, day: int) -> None:
        self._end_date = datetime(year, month, day, 23, 59, 59)

    def set_cash(self, cash: float) -> None:
        self._initial_cash = float(cash)
        self.portfolio = Portfolio(self._initial_cash)

    def add_equity(
        self, ticker: str, resolution: Resolution = Resolution.DAILY, market: Market = Market.INDIA
    ) -> Security:
        sym = Symbol(value=ticker.strip().upper(), security_type=SecurityType.EQUITY, market=market)
        sec = Security(sym)
        self.securities[sym] = sec
        self.portfolio.add_security(sec)
        return sec

    def set_benchmark(self, ticker: str) -> None:
        self.benchmark_symbol = Symbol(ticker.strip().upper(), SecurityType.INDEX, Market.INDIA)
        if self.benchmark_symbol not in self.securities:
            sec = Security(self.benchmark_symbol)
            self.securities[self.benchmark_symbol] = sec
            self.portfolio.add_security(sec)

    def log(self, message: str) -> None:
        self.logs.append(f"[{self.time.isoformat()}] {message}")

    def debug(self, message: str) -> None:
        if self.debug_mode:
            self.log(f"DEBUG: {message}")

    def market_order(self, symbol: Symbol | str, quantity: int, tag: str = "") -> OrderTicket | None:
        sym = symbol if isinstance(symbol, Symbol) else Symbol(str(symbol).upper())
        if quantity == 0:
            return None
        self._order_counter += 1
        direction = OrderDirection.BUY if quantity > 0 else OrderDirection.SELL
        order = Order(
            order_id=self._order_counter,
            symbol=sym,
            time=self.time,
            type=OrderType.MARKET,
            direction=direction,
            quantity=abs(quantity),
            price=self.securities[sym].close if sym in self.securities else 0.0,
            status=OrderStatus.SUBMITTED,
            tag=tag,
        )
        ticket = OrderTicket(order=order)
        self._order_tickets.append(ticket)
        self._pending_orders.append(order)
        return ticket

    def set_holdings(self, symbol: Symbol | str, percentage: float, tag: str = "") -> OrderTicket | None:
        sym = symbol if isinstance(symbol, Symbol) else Symbol(str(symbol).upper())
        if sym not in self.securities:
            return None
        price = self.securities[sym].close
        if price <= 0:
            return None
        total_equity = self.portfolio.total_portfolio_value()
        target_val = total_equity * percentage
        target_qty = int(target_val // price)
        curr_qty = self.portfolio[sym].quantity
        diff_qty = target_qty - curr_qty
        if diff_qty != 0:
            return self.market_order(sym, diff_qty, tag=tag or f"SetHoldings {percentage*100:.1f}%")
        return None

    def liquidate(self, symbol: Symbol | str | None = None, tag: str = "Liquidate") -> list[OrderTicket]:
        tickets: list[OrderTicket] = []
        if symbol is not None:
            sym = symbol if isinstance(symbol, Symbol) else Symbol(str(symbol).upper())
            if sym in self.portfolio.securities and self.portfolio[sym].invested:
                curr_qty = self.portfolio[sym].quantity
                ticket = self.market_order(sym, -curr_qty, tag=tag)
                if ticket:
                    tickets.append(ticket)
            return tickets

        for sym, sec in self.portfolio.securities.items():
            if sec.holdings.invested:
                curr_qty = sec.holdings.quantity
                ticket = self.market_order(sym, -curr_qty, tag=tag)
                if ticket:
                    tickets.append(ticket)
        return tickets

    def initialize(self) -> None:
        """User algorithm lifecycle initialization hook."""
        pass

    def on_data(self, slice: Slice) -> None:
        """User algorithm bar-by-bar execution hook."""
        pass

    def on_order_event(self, order_event: OrderEvent) -> None:
        """User order event fill callback."""
        pass

    def on_end_of_algorithm(self) -> None:
        """Algorithm completion callback."""
        pass
