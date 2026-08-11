"""Pre-recommendation 3-year backtest integration tests."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import AnalysisMode, BacktestResult
from app.services import recommendation_backtest as rbt


@pytest.fixture(autouse=True)
def _clear_cache():
    rbt.clear_cache()
    yield
    rbt.clear_cache()


def _bt(
    *,
    trade_count: int = 10,
    total_return: float = 20.0,
    verdict: str = "favorable",
    strategy_name: str = "sma_rsi_macd",
) -> BacktestResult:
    return BacktestResult(
        mode=AnalysisMode.swing,
        strategy_name=strategy_name,
        total_return=total_return,
        cagr=5.0,
        max_drawdown=10.0,
        win_rate=55.0,
        profit_factor=1.5,
        trade_count=trade_count,
        verdict=verdict,
        equity_curve=[{"label": "2023-01-01", "equity": 100000.0}, {"label": "2024-01-01", "equity": 120000.0}],
        trades=[{"entry_date": "2023-01-01", "exit_date": "2023-02-01"}] * trade_count,
    )


# TEST 1 — no qualified → no backtest execution
def test_envelope_not_qualified_no_score():
    env = rbt.envelope_not_qualified("ABC", "RE-001", reason="gates_failed")
    assert env.status == "SKIPPED_NOT_QUALIFIED"
    assert env.backtest_score is None
    assert env.score_eligible is False
    assert env.as_backtest_list() == []


def test_no_qualified_cohort_state():
    env = rbt.envelope_no_qualified_cohort("RE-001")
    assert env.status == "NO_TECHNICALLY_QUALIFIED_STOCKS"
    assert "No stocks qualified" in (env.message or "")


# TEST 4 — three-year window
def test_three_year_window():
    start, end = rbt.three_year_window(date(2026, 8, 9))
    assert end == date(2026, 8, 9)
    assert start == date(2026, 8, 9) - timedelta(days=3 * 365)
    assert (end - start).days == 1095


# TEST 5 / 6 — trade count eligibility
def test_insufficient_trades_no_score():
    result = _bt(trade_count=4, total_return=50.0)
    score, eligible = rbt.compute_raw_backtest_score(result)
    assert eligible is False
    assert score is None
    start, end = rbt.three_year_window()
    env = rbt.classify_result(result, symbol="X", engine_id="RE-001", start=start, end=end)
    assert env.status == "BACKTEST_INSUFFICIENT_TRADES"
    assert env.backtest_score is None
    assert env.score_eligible is False


def test_exact_five_trades_eligible():
    result = _bt(trade_count=5, total_return=10.0)
    score, eligible = rbt.compute_raw_backtest_score(result)
    assert eligible is True
    assert score == pytest.approx(40.0)  # 10 * 4
    start, end = rbt.three_year_window()
    env = rbt.classify_result(result, symbol="X", engine_id="RE-001", start=start, end=end)
    assert env.status == "SUCCESS"
    assert env.score_eligible is True
    assert env.backtest_score == pytest.approx(40.0)


# TEST 7 — success injectable
def test_success_envelope_has_result_list():
    result = _bt(trade_count=8, total_return=12.5)
    start, end = rbt.three_year_window()
    env = rbt.classify_result(result, symbol="INFY", engine_id="RE-002", start=start, end=end)
    assert env.status == "SUCCESS"
    assert len(env.as_backtest_list()) == 1
    d = env.to_dict()
    assert d["engine_id"] == "RE-002"
    assert d["trade_count"] == 8
    assert d["backtest_score"] == pytest.approx(50.0)


# TEST 8 — failure explicit
def test_failed_backtest_status():
    result = _bt(trade_count=0, verdict="Failed", strategy_name="error_fallback")
    start, end = rbt.three_year_window()
    env = rbt.classify_result(result, symbol="X", engine_id="RE-001", start=start, end=end)
    assert env.status in {"BACKTEST_FAILED", "BACKTEST_INSUFFICIENT_DATA", "BACKTEST_INSUFFICIENT_TRADES"}
    assert env.score_eligible is False


# TEST 9 — duplicate prevention via reuse
def test_reuse_existing_backtest():
    existing = [_bt(trade_count=12, total_return=15.0)]
    start, end = rbt.three_year_window()
    env = rbt.try_reuse_existing(existing, symbol="TCS", engine_id="RE-001", start=start, end=end)
    assert env is not None
    assert env.reused is True
    assert env.score_eligible is True


@pytest.mark.asyncio
async def test_run_reuses_existing_without_agent_call():
    existing = [_bt(trade_count=10, total_return=8.0)]
    with patch.object(rbt, "try_reuse_existing", wraps=rbt.try_reuse_existing) as spy:
        env = await rbt.run_three_year_backtest(
            symbol="RELIANCE",
            engine_id="RE-001",
            candles=[SimpleNamespace(timestamp=date.today(), open=1, high=1, low=1, close=1, volume=1)],
            existing_backtests=existing,
            allow_reuse=True,
        )
    assert env.reused is True
    assert env.status == "SUCCESS"
    assert spy.called


# TEST 11 — technical fail → skip (via envelope helper used by runners)
def test_technical_no_buy_skips_backtest_envelope():
    env = rbt.envelope_not_qualified("FAIL", "RE-001", reason="keltner_breakout_failed")
    assert env.status == "SKIPPED_NOT_QUALIFIED"
    assert "Not technically qualified" in (env.message or "")


# TEST 12 / 13 — bounded concurrency + partial
@pytest.mark.asyncio
async def test_bounded_concurrency_partial_results():
    calls = {"n": 0}

    async def fake_run(**kwargs):
        calls["n"] += 1
        if kwargs["symbol"] == "FAIL":
            return rbt.RecommendationBacktestEnvelope(
                symbol="FAIL",
                engine_id=kwargs["engine_id"],
                status="BACKTEST_FAILED",
                message="forced",
            )
        if kwargs["symbol"] == "LOW":
            return rbt.classify_result(
                _bt(trade_count=3),
                symbol="LOW",
                engine_id=kwargs["engine_id"],
                start=date.today() - timedelta(days=1095),
                end=date.today(),
            )
        return rbt.classify_result(
            _bt(trade_count=10),
            symbol=kwargs["symbol"],
            engine_id=kwargs["engine_id"],
            start=date.today() - timedelta(days=1095),
            end=date.today(),
        )

    jobs = [
        {"symbol": f"S{i}", "engine_id": "RE-001"} for i in range(7)
    ] + [
        {"symbol": "FAIL", "engine_id": "RE-001"},
        {"symbol": "LOW", "engine_id": "RE-001"},
        {"symbol": "OK", "engine_id": "RE-001"},
    ]
    with patch.object(rbt, "run_three_year_backtest", side_effect=fake_run):
        out = await rbt.run_bounded_backtests(jobs, concurrency=3)
    assert len(out) == 10
    assert calls["n"] == 10
    statuses = {e.symbol: e.status for e in out}
    assert statuses["FAIL"] == "BACKTEST_FAILED"
    assert statuses["LOW"] == "BACKTEST_INSUFFICIENT_TRADES"
    assert statuses["OK"] == "SUCCESS"


# TEST empty jobs
@pytest.mark.asyncio
async def test_zero_jobs_no_backtests():
    out = await rbt.run_bounded_backtests([])
    assert out == []


def test_score_matches_production_formula():
    # recommendation_service: min(max(total_return * 4, -20), 100)
    s, ok = rbt.compute_raw_backtest_score(_bt(trade_count=5, total_return=30.0))
    assert ok and s == 100.0  # 30*4=120 → clamp 100
    s2, ok2 = rbt.compute_raw_backtest_score(_bt(trade_count=5, total_return=-10.0))
    assert ok2 and s2 == pytest.approx(-20.0)  # -40 → clamp -20
