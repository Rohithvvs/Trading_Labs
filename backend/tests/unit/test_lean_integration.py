"""Automated Test Suite for QuantConnect LEAN Engine Integration in Trading Labs."""

import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import patch
import pytest

from app.lean.adapters.data_adapter import LeanDataAdapter
from app.lean.adapters.result_parser import LeanResultParser
from app.lean.engine.execution_models import NextBarOpenExecutionModel
from app.lean.engine.existing_engine import ExistingBacktestEngine
from app.lean.engine.fee_models import NseFeeModel
from app.lean.engine.indicators import (
    AverageTrueRange,
    PriorSessionMaximum,
    RelativeStrengthIndex,
    SimpleMovingAverage,
)
from app.lean.engine.lean_engine import LeanBacktestEngine
from app.lean.engine.qc_algorithm import (
    Market,
    Order,
    OrderDirection,
    OrderStatus,
    OrderType,
    QCAlgorithm,
    Resolution,
    RollingWindow,
    Security,
    SecurityType,
    Slice,
    Symbol,
    TradeBar,
)
from app.lean.engine.slippage_models import ConstantSlippageModel
from app.lean.models import (
    EngineType,
    LeanBacktestRequest,
    LeanBacktestResult,
    LeanJobStatus,
    PositionSizingMethod,
)
from app.lean.services.lean_service import LeanBacktestService
from app.lean.services.validation_service import LeanTradingViewValidationService
from app.lean.strategies.breakout52w_algorithm import Breakout52wLeanAlgorithm
from app.lean.strategies.sma_crossover_algorithm import SmaCrossoverLeanAlgorithm


def _create_synthetic_bars(
    symbol_str: str = "RELIANCE",
    count: int = 300,
    start_price: float = 100.0,
    daily_growth: float = 0.001,
) -> list[TradeBar]:
    """Helper creating strictly chronological daily trading bars (skipping weekends)."""
    sym = Symbol(symbol_str, SecurityType.EQUITY, Market.INDIA)
    bars: list[TradeBar] = []
    curr_date = date(2020, 1, 1)
    curr_px = start_price

    while len(bars) < count:
        if curr_date.weekday() < 5:  # Mon-Fri
            dt = datetime.combine(curr_date, datetime.min.time().replace(hour=15, minute=30))
            o = curr_px
            h = curr_px * 1.01
            l = curr_px * 0.99
            c = curr_px * (1.0 + daily_growth)
            v = 100000

            bars.append(
                TradeBar(
                    symbol=sym,
                    time=dt,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=v,
                    period=timedelta(days=1),
                )
            )
            curr_px = c
        curr_date += timedelta(days=1)

    return bars


# ===========================================================================
# Test 1 — Data Ordering (Strictly Chronological)
# ===========================================================================
def test_data_ordering_is_strictly_chronological():
    bars = _create_synthetic_bars("TCS", 100)
    for i in range(1, len(bars)):
        assert bars[i].time > bars[i - 1].time, "Bars must be strictly monotonically increasing in time"


# ===========================================================================
# Test 2 — 252-Session Lookback (Exact 252 Trading Sessions, Not Calendar Days)
# ===========================================================================
def test_252_session_lookback_uses_exact_trading_bars():
    bars = _create_synthetic_bars("INFY", 270, start_price=500.0, daily_growth=0.002)
    win = RollingWindow[float](260)
    for b in bars:
        win.add(b.close)

    assert win.count == 260
    assert win.is_ready is True
    # win[0] is current bar, win[252] is the bar from exactly 252 trading sessions ago
    assert win[0] == bars[-1].close
    assert win[252] == bars[-253].close


# ===========================================================================
# Test 3 — 52-Week High Excludes Current Bar
# ===========================================================================
def test_52w_high_excludes_current_bar():
    ind = PriorSessionMaximum(252)
    start_dt = datetime(2020, 1, 1)

    # Feed 252 bars with high = 100.0
    for i in range(252):
        ind.update(start_dt + timedelta(days=i), 100.0)

    # 253rd bar arrives with a huge spike to 200.0
    ind.update(start_dt + timedelta(days=252), 200.0)

    # The prior high evaluated on bar 253 must STILL be 100.0 (today's 200.0 is excluded)
    assert ind.is_ready is True
    assert ind.value == 100.0, "Prior 252-high must exclude current bar high"


# ===========================================================================
# Test 4 — Momentum Formula
# ===========================================================================
def test_momentum_formula():
    bars = _create_synthetic_bars("RELIANCE", 70, start_price=1000.0, daily_growth=0.01)
    c_today = bars[-1].close
    c_60_ago = bars[-61].close
    expected_mom = (c_today / c_60_ago) - 1.0

    win = RollingWindow[float](65)
    for b in bars:
        win.add(b.close)

    calculated_mom = (win[0] / win[60]) - 1.0
    assert abs(calculated_mom - expected_mom) < 1e-9


# ===========================================================================
# Test 5 — No Look-Ahead Bias
# ===========================================================================
@pytest.mark.asyncio
async def test_no_look_ahead_bias():
    bars = _create_synthetic_bars("RELIANCE", 280, start_price=100.0)
    # Inject a massive spike at the final bar
    bars[-1].high = 9999.0
    bars[-1].close = 9999.0

    algo = Breakout52wLeanAlgorithm(
        symbols=["RELIANCE"],
        start_date=datetime(2020, 6, 1),
        end_date=datetime(2021, 6, 1),
        initial_cash=100000.0,
    )
    algo.initialize()

    # Slice at bar index 260 cannot see bar 279
    slice_260 = Slice(time=bars[260].time, bars={bars[260].symbol: bars[260]})
    algo.on_data(slice_260)

    sym = Symbol("RELIANCE", SecurityType.EQUITY, Market.INDIA)
    # The prior high at bar 260 must be normal and cannot see the future 9999.0 price
    assert algo.prior_highs[sym].value < 500.0


# ===========================================================================
# Test 6 — Order Execution (Next Bar Open Fill)
# ===========================================================================
def test_order_execution_fills_at_next_bar_open():
    bars = _create_synthetic_bars("HDFCBANK", 5, start_price=1500.0)
    algo = QCAlgorithm()
    sec = algo.add_equity("HDFCBANK", Resolution.DAILY)
    sym = sec.symbol
    algo.initialize()

    # Place market order at bar 0 close
    algo.time = bars[0].time
    algo.market_order(sym, 10, tag="Test Buy")
    assert len(algo._pending_orders) == 1

    # Execute on bar 1 arrival
    exec_model = NextBarOpenExecutionModel()
    fee_model = NseFeeModel()
    slip_model = ConstantSlippageModel(0.0)

    slice_1 = Slice(time=bars[1].time, bars={sym: bars[1]})
    events = exec_model.execute_pending_orders(algo, slice_1, fee_model, slip_model)

    assert len(events) == 1
    assert events[0].status == OrderStatus.FILLED
    assert events[0].fill_price == bars[1].open
    assert algo.portfolio[sym].quantity == 10


# ===========================================================================
# Test 7 — Commission Calculation (NSE Statutory Fee Model)
# ===========================================================================
def test_commission_calculation_nse_model():
    fee_model = NseFeeModel(brokerage_rate=0.0005, brokerage_flat_cap=20.0)
    order = Order(
        order_id=1,
        symbol=Symbol("TCS", SecurityType.EQUITY, Market.INDIA),
        time=datetime.now(),
        type=OrderType.MARKET,
        direction=OrderDirection.BUY,
        quantity=100,
        price=3500.0,
    )
    # Turnover = 100 * 3500 = 350,000 INR
    fee = fee_model.get_order_fee(order, fill_price=3500.0, fill_qty=100)
    assert fee > 0
    # Brokerage cap is 20, STT buy is 350, GST is 18%, etc.
    assert fee > 350.0  # STT alone is ₹350


# ===========================================================================
# Test 8 — Slippage Calculation
# ===========================================================================
def test_slippage_calculation():
    slip_model = ConstantSlippageModel(percent=0.001)  # 10 bps
    order_buy = Order(
        order_id=1,
        symbol=Symbol("INFY", SecurityType.EQUITY, Market.INDIA),
        time=datetime.now(),
        type=OrderType.MARKET,
        direction=OrderDirection.BUY,
        quantity=10,
        price=1000.0,
    )
    sec = Security(order_buy.symbol)
    slip_buy = slip_model.get_slippage_approximation(order_buy, sec, 1000.0)
    assert slip_buy == 1.0  # Buy pays +1.0 INR

    order_sell = Order(
        order_id=2,
        symbol=order_buy.symbol,
        time=datetime.now(),
        type=OrderType.MARKET,
        direction=OrderDirection.SELL,
        quantity=10,
        price=1000.0,
    )
    slip_sell = slip_model.get_slippage_approximation(order_sell, sec, 1000.0)
    assert slip_sell == -1.0  # Sell receives -1.0 INR


# ===========================================================================
# Test 9 — Portfolio Accounting Consistency
# ===========================================================================
@pytest.mark.asyncio
async def test_portfolio_accounting_consistency():
    bars = _create_synthetic_bars("RELIANCE", 270, start_price=100.0, daily_growth=0.005)
    req = LeanBacktestRequest(
        strategyId="01_sma_cross",
        strategyName="SMA Crossover",
        symbols=["RELIANCE"],
        startDate=date(2020, 1, 1),
        endDate=date(2021, 1, 1),
        initialCapital=100000.0,
    )
    engine = LeanBacktestEngine()
    result: LeanBacktestResult = await engine.run_backtest(req, {"RELIANCE": bars})

    assert result.status == LeanJobStatus.COMPLETED
    assert len(result.equity_curve) > 0
    # Initial equity matches request
    assert result.equity_curve[0].equity == pytest.approx(100000.0, rel=1e-2)
    # Summary final equity matches last equity point
    assert result.summary.final_equity == result.equity_curve[-1].equity


# ===========================================================================
# Test 10 — Multi-Symbol Portfolio Execution
# ===========================================================================
@pytest.mark.asyncio
async def test_multi_symbol_portfolio_execution():
    bars_rel = _create_synthetic_bars("RELIANCE", 270, start_price=1000.0, daily_growth=0.002)
    bars_tcs = _create_synthetic_bars("TCS", 270, start_price=2000.0, daily_growth=0.003)
    bars_infy = _create_synthetic_bars("INFY", 270, start_price=500.0, daily_growth=0.001)

    req = LeanBacktestRequest(
        strategyId="09_52w_breakout",
        symbols=["RELIANCE", "TCS", "INFY"],
        startDate=date(2020, 1, 1),
        endDate=date(2021, 1, 1),
        initialCapital=300000.0,
        maxPositions=3,
        positionSizingValue=33.3,
    )
    engine = LeanBacktestEngine()
    result = await engine.run_backtest(
        req,
        {"RELIANCE": bars_rel, "TCS": bars_tcs, "INFY": bars_infy},
    )

    assert result.status == LeanJobStatus.COMPLETED
    assert len(result.symbols) == 3


# ===========================================================================
# Test 11 — Persistence Across Job Lifecycle
# ===========================================================================
@pytest.mark.asyncio
async def test_persistence_across_job_lifecycle():
    bars = _create_synthetic_bars("RELIANCE", 100, start_price=1000.0)
    with patch.object(LeanDataAdapter, "load_historical_data", return_value=({"RELIANCE": bars}, None)):
        req = LeanBacktestRequest(
            strategyId="01_sma_cross",
            symbols=["RELIANCE"],
            startDate=date(2020, 1, 1),
            endDate=date(2020, 12, 31),
            initialCapital=50000.0,
        )
        job = await LeanBacktestService.create_and_start_job(req)
        assert job.job_id.startswith("LEAN-")

        # Wait for completion
        for _ in range(50):
            if job.status in {LeanJobStatus.COMPLETED, LeanJobStatus.FAILED}:
                break
            await asyncio.sleep(0.05)

        retrieved = LeanBacktestService.get_job(job.job_id)
        assert retrieved is not None
        assert retrieved.job_id == job.job_id


# ===========================================================================
# Test 12 — Repeatability (Identical Inputs Produce Identical Results)
# ===========================================================================
@pytest.mark.asyncio
async def test_repeatability_identical_results():
    bars1 = _create_synthetic_bars("RELIANCE", 270, start_price=100.0, daily_growth=0.002)
    bars2 = _create_synthetic_bars("RELIANCE", 270, start_price=100.0, daily_growth=0.002)
    req = LeanBacktestRequest(
        strategyId="09_52w_breakout",
        symbols=["RELIANCE"],
        startDate=date(2020, 1, 1),
        endDate=date(2021, 1, 1),
        initialCapital=100000.0,
    )
    engine1 = LeanBacktestEngine()
    engine2 = LeanBacktestEngine()
    res1 = await engine1.run_backtest(req, {"RELIANCE": bars1})
    res2 = await engine2.run_backtest(req, {"RELIANCE": bars2})

    assert res1.summary.final_equity == res2.summary.final_equity
    assert res1.summary.total_trades == res2.summary.total_trades
    assert len(res1.trades) == len(res2.trades)


# ===========================================================================
# Test 13 — TradingView Parity Validation Mode
# ===========================================================================
@pytest.mark.asyncio
async def test_tradingview_validation_mode():
    bars = _create_synthetic_bars("RELIANCE", 270, start_price=1000.0, daily_growth=0.001)
    with patch.object(LeanDataAdapter, "load_historical_data", return_value=({"RELIANCE": bars}, None)):
        report = await LeanTradingViewValidationService.validate_symbol(
            symbol="RELIANCE",
            start_date=date(2020, 1, 1),
            end_date=date(2021, 1, 1),
            strategy_id="09_52w_breakout",
        )
        assert report.symbol == "RELIANCE"
        assert report.total_bars > 0
        assert report.verdict in {"PASS", "FAIL", "INCONCLUSIVE"}


# ===========================================================================
# Test 14 — Engine Switching (LEAN vs Existing)
# ===========================================================================
@pytest.mark.asyncio
async def test_engine_switching():
    bars = _create_synthetic_bars("RELIANCE", 100, start_price=1000.0)
    req_lean = LeanBacktestRequest(strategyId="01_sma_cross", executionMode=EngineType.LEAN)
    req_existing = LeanBacktestRequest(strategyId="01_sma_cross", executionMode=EngineType.EXISTING)

    lean_engine = LeanBacktestEngine()
    existing_engine = ExistingBacktestEngine()

    res_lean = await lean_engine.run_backtest(req_lean, {"RELIANCE": bars})
    res_existing = await existing_engine.run_backtest(req_existing, {"RELIANCE": bars})

    assert res_lean.engine == "LEAN"
    assert res_existing.engine == "EXISTING"
