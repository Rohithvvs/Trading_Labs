"""Unit tests for Long-Term Buy & Hold Momentum (17_long_term_mom) in QuantConnect LEAN."""

from datetime import date, datetime, timedelta
import pytest

from app.lean.adapters.algorithm_adapter import LeanAlgorithmAdapter
from app.lean.engine.lean_engine import LeanBacktestEngine
from app.lean.engine.qc_algorithm import (
    Market,
    SecurityType,
    Symbol,
    TradeBar,
)
from app.lean.models import LeanBacktestRequest
from app.lean.strategies.ltm_algorithm import LongTermMomentumLeanAlgorithm


def _create_bars(
    symbol_str: str,
    count: int = 600,
    start_price: float = 100.0,
    daily_growth: float = 0.003,
) -> list[TradeBar]:
    sym = Symbol(symbol_str, SecurityType.EQUITY, Market.INDIA)
    bars: list[TradeBar] = []
    curr_date = date(2020, 1, 1)
    curr_px = start_price

    while len(bars) < count:
        if curr_date.weekday() < 5:
            curr_px *= (1.0 + daily_growth)
            dt = datetime.combine(curr_date, datetime.min.time())
            bars.append(
                TradeBar(
                    time=dt,
                    symbol=sym,
                    open=curr_px * 0.995,
                    high=curr_px * 1.01,
                    low=curr_px * 0.99,
                    close=curr_px,
                    volume=500_000.0,
                )
            )
        curr_date += timedelta(days=1)
    return bars


@pytest.mark.asyncio
async def test_ltm_algorithm_adapter_instantiation():
    req = LeanBacktestRequest(
        strategyId="17_long_term_mom",
        strategyName="Long-Term Momentum",
        symbols=["TCS", "INFY"],
        startDate=date(2020, 1, 1),
        endDate=date(2022, 1, 1),
        initialCapital=100000.0,
    )
    algo = LeanAlgorithmAdapter.create_algorithm(req)
    assert isinstance(algo, LongTermMomentumLeanAlgorithm)
    assert algo.momentum_gate == 0.50
    assert algo.rebalance_period == 252


@pytest.mark.asyncio
async def test_ltm_backtest_execution():
    # Stock A grows fast (+100% over 252 bars, daily_growth=0.003) -> eligible
    bars_a = _create_bars("GROWTH_STOCK", count=600, start_price=100.0, daily_growth=0.003)
    # Stock B flat -> not eligible (daily_growth=0.0)
    bars_b = _create_bars("FLAT_STOCK", count=600, start_price=100.0, daily_growth=0.0)

    data_map = {
        "GROWTH_STOCK": bars_a,
        "FLAT_STOCK": bars_b,
    }

    req = LeanBacktestRequest(
        strategyId="17_long_term_mom",
        symbols=["GROWTH_STOCK", "FLAT_STOCK"],
        startDate=date(2020, 1, 1),
        endDate=bars_a[-1].time.date(),
        initialCapital=100000.0,
        maxPositions=10,
    )

    engine = LeanBacktestEngine()
    result = await engine.run_backtest(req, data_map)

    assert result.summary.initial_capital == 100000.0
    assert result.summary.final_equity > 100000.0
    assert result.summary.total_trades >= 1
    # Only GROWTH_STOCK was eligible and bought
    traded_symbols = {t.symbol for t in result.trades}
    assert "GROWTH_STOCK" in traded_symbols
    assert "FLAT_STOCK" not in traded_symbols
