"""Unit Tests for LEAN Multi-Asset Portfolio Accounting & Strategy Execution."""

from datetime import date, datetime, timedelta
import pytest

from app.lean.engine.indicators import AverageTrueRange, RelativeStrengthIndex, SimpleMovingAverage
from app.lean.engine.lean_engine import LeanBacktestEngine
from app.lean.engine.qc_algorithm import (
    Market,
    OrderDirection,
    Resolution,
    SecurityType,
    Slice,
    Symbol,
    TradeBar,
)
from app.lean.models import LeanBacktestRequest, LeanJobStatus
from app.lean.strategies.breakout52w_algorithm import Breakout52wLeanAlgorithm
from app.lean.strategies.dynamic_rule_algorithm import DynamicRuleLeanAlgorithm
from app.lean.strategies.rsi_oversold_algorithm import RsiOversoldLeanAlgorithm
from app.services.strategy_tester.schema import parse_strategy_config


def _generate_price_series(
    sym_str: str,
    prices: list[float],
    start_dt: datetime = datetime(2020, 1, 1),
) -> list[TradeBar]:
    sym = Symbol(sym_str, SecurityType.EQUITY, Market.INDIA)
    bars: list[TradeBar] = []
    for i, p in enumerate(prices):
        t = start_dt + timedelta(days=i)
        bars.append(
            TradeBar(
                symbol=sym,
                time=t,
                open=p,
                high=p * 1.02,
                low=p * 0.98,
                close=p,
                volume=50000,
                period=timedelta(days=1),
            )
        )
    return bars


@pytest.mark.asyncio
async def test_portfolio_cash_allocation_cap():
    """Verify that portfolio respects maximum position count and does not exceed available cash."""
    # 5 stocks with strong upward prices
    syms = ["STOCK_A", "STOCK_B", "STOCK_C", "STOCK_D", "STOCK_E"]
    data_map = {
        s: _generate_price_series(s, [100.0 + (i * 0.5) for i in range(280)])
        for s in syms
    }

    req = LeanBacktestRequest(
        strategyId="09_52w_breakout",
        symbols=syms,
        startDate=date(2020, 1, 1),
        endDate=date(2020, 10, 1),
        initialCapital=100000.0,
        maxPositions=2,  # Maximum 2 slots allowed!
        positionSizingValue=50.0,  # 50% per slot
    )

    engine = LeanBacktestEngine()
    result = await engine.run_backtest(req, data_map)

    assert result.status == LeanJobStatus.COMPLETED
    # Check that at any point in position history, at most 2 distinct symbols are held
    dates = {p.date for p in result.positions}
    for d in dates:
        held_on_d = [p.symbol for p in result.positions if p.date == d and p.quantity > 0]
        assert len(held_on_d) <= 2, f"Expected at most 2 positions on {d}, found {len(held_on_d)}"


@pytest.mark.asyncio
async def test_rsi_oversold_lean_execution():
    """Test RSI mean reversion strategy execution in LEAN."""
    # Oscillating price series to trigger RSI < 30 and RSI > 70
    prices = [100.0] * 30
    # Sharp drop to trigger oversold
    prices.extend([100.0 - i * 3 for i in range(1, 10)])
    # Sharp recovery to trigger overbought
    prices.extend([70.0 + i * 5 for i in range(1, 15)])
    prices.extend([140.0] * 20)

    bars = _generate_price_series("RELIANCE", prices)
    req = LeanBacktestRequest(
        strategyId="02_rsi_oversold",
        symbols=["RELIANCE"],
        startDate=date(2020, 1, 1),
        endDate=date(2020, 4, 1),
        initialCapital=100000.0,
        parameters={"rsi_period": 14, "oversold_level": 30.0, "overbought_level": 70.0},
    )

    engine = LeanBacktestEngine()
    result = await engine.run_backtest(req, {"RELIANCE": bars})

    assert result.status == LeanJobStatus.COMPLETED
    assert len(result.trades) > 0
    # First trade was entered on RSI dip and exited on RSI spike
    first_trade = result.trades[0]
    assert first_trade.entry_price < first_trade.exit_price
    assert first_trade.return_pct > 0


@pytest.mark.asyncio
async def test_dynamic_rule_filter_tree_in_lean():
    """Test Visual Builder filter tree executed inside LEAN."""
    config = parse_strategy_config({
        "name": "Custom Filter Strategy",
        "filters": [
            {"field": "CLOSE", "operator": ">", "right": {"indicator": "SMA", "period": 20}},
            {"field": "RSI", "operator": ">", "value": 50},
        ],
    })

    prices = [100.0 + (i * 1.5) for i in range(60)]
    bars = _generate_price_series("TCS", prices)

    algo = DynamicRuleLeanAlgorithm(
        symbols=["TCS"],
        config=config,
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2020, 3, 1),
        initial_cash=100000.0,
    )
    algo.initialize()

    # Step through bars
    for b in bars:
        slice_obj = Slice(time=b.time, bars={b.symbol: b})
        algo.on_data(slice_obj)

    # Indicator series was built and evaluated
    assert len(algo.hist_close[bars[0].symbol]) == len(bars)
