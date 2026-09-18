"""Unit tests for the score-based recommendation service (replaces legacy engine).

Covers: pure classifier thresholds, composite-score classification through
ScoringMatrixService, mandatory precondition failures (mock data, missing trade
plan, untrusted source), and trade-plan generation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas import (
    AnalysisMode,
    BacktestResult,
    FundamentalAnalysisResult,
    OHLCVPoint,
    TechnicalAnalysisResult,
)
from app.services.score_recommendation_service import (
    BUY_SCORE_THRESHOLD,
    WATCH_SCORE_THRESHOLD,
    ScoreRecommendationService,
    classify_signal_from_score,
    is_trade_plan_complete,
)

SERVICE = ScoreRecommendationService()


def _candles(n: int = 30, price: float = 100.0, volume: int = 1000) -> list[OHLCVPoint]:
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    points = []
    for i in range(n):
        pts = []
        for j in range(5):
            pts.append(
                OHLCVPoint(
                    timestamp=base + timedelta(days=i * 5 + j),
                    open=price + j * 0.5,
                    high=price + j * 0.5 + 1.0,
                    low=price + j * 0.5 - 1.0,
                    close=price + j * 0.5 + 0.2,
                    volume=volume,
                )
            )
        points.extend(pts)
    return points


def _tech(signal: str = "bullish", score: float = 90.0) -> TechnicalAnalysisResult:
    return TechnicalAnalysisResult(
        mode=AnalysisMode.swing,
        signal=signal,
        score=score,
        indicators={},
        summary=f"technical {signal}",
    )


def _backtest(verdict: str = "success", total_return: float = 15.0, trade_count: int = 10) -> BacktestResult:
    return BacktestResult(
        mode=AnalysisMode.swing,
        strategy_name="strategy_test",
        total_return=total_return,
        cagr=10.0,
        max_drawdown=-8.0,
        win_rate=60.0,
        profit_factor=1.4,
        trade_count=trade_count,
        verdict=verdict,
        equity_curve=[],
    )


def _valid_data_quality() -> dict:
    return {
        "source": "CANDLE_CACHE_DB",
        "candles": 150,
        "mock_warning": False,
        "minimum_swing_candles_met": True,
    }


# ---------------------------------------------------------------------------
# Pure classifier
# ---------------------------------------------------------------------------


def test_classify_thresholds():
    assert classify_signal_from_score(100.0) == "BUY"
    assert classify_signal_from_score(BUY_SCORE_THRESHOLD) == "BUY"
    assert classify_signal_from_score(BUY_SCORE_THRESHOLD - 0.01) == "WATCH"
    assert classify_signal_from_score(WATCH_SCORE_THRESHOLD) == "WATCH"
    assert classify_signal_from_score(WATCH_SCORE_THRESHOLD - 0.01) == "REJECT"
    assert classify_signal_from_score(0.0) == "REJECT"


def test_classify_non_finite_rejects():
    assert classify_signal_from_score(float("nan")) == "REJECT"
    assert classify_signal_from_score(float("inf")) == "REJECT"


# ---------------------------------------------------------------------------
# Trade-plan completeness
# ---------------------------------------------------------------------------


def test_is_trade_plan_complete_accepts_valid_plan():
    candles = _candles()
    plan = SERVICE._build_trade_plans([_tech()], [_backtest()], {AnalysisMode.swing: candles})[0]
    assert is_trade_plan_complete(plan) is True


def test_is_trade_plan_complete_rejects_empty_plan():
    assert is_trade_plan_complete(None) is False


# ---------------------------------------------------------------------------
# End-to-end build -> BUY / WATCH / REJECT
# ---------------------------------------------------------------------------


def test_build_strong_buy():
    rec = SERVICE.build(
        symbol="BUY_TEST",
        technical_results=[_tech(signal="bullish", score=90.0)],
        sentiment_score=0.8,
        fundamental_result=FundamentalAnalysisResult(fundamental_score=0.8, summary="ok"),
        backtests=[_backtest(total_return=15.0)],
        candles_by_mode={AnalysisMode.swing: _candles()},
        data_quality=_valid_data_quality(),
    )
    assert rec.action == "BUY"
    assert rec.score >= BUY_SCORE_THRESHOLD
    assert 0.35 <= rec.confidence <= 0.95
    assert rec.trade_plans
    assert rec.technical_score is not None
    assert rec.backtest_score is not None
    assert rec.fundamental_score is not None
    # Baseline matrix: tech 0.35 + sent 0.25 + fund 0.25 + vol 0.15 (breadth 0)
    # tech 90 -> 31.5 | news (0.8+1)/2*100=90 -> 22.5 | fund 90 -> 22.5 | vol 50 -> 7.5
    assert rec.score == pytest.approx(84.0, abs=0.01)


def test_build_watch_band():
    rec = SERVICE.build(
        symbol="WATCH_TEST",
        technical_results=[_tech(signal="neutral", score=70.0)],
        sentiment_score=0.0,
        fundamental_result=FundamentalAnalysisResult(fundamental_score=0.0, summary="ok"),
        backtests=[_backtest(total_return=5.0)],
        candles_by_mode={AnalysisMode.swing: _candles()},
        data_quality=_valid_data_quality(),
    )
    assert rec.action == "WATCH"
    assert WATCH_SCORE_THRESHOLD <= rec.score < BUY_SCORE_THRESHOLD
    # tech 70 -> 24.5 | news 50 -> 12.5 | fund 50 -> 12.5 | vol 50 -> 7.5
    assert rec.score == pytest.approx(57.0, abs=0.01)


def test_build_reject_low_score():
    rec = SERVICE.build(
        symbol="REJECT_TEST",
        technical_results=[_tech(signal="bearish", score=30.0)],
        sentiment_score=-0.6,
        fundamental_result=FundamentalAnalysisResult(fundamental_score=-0.5, summary="weak"),
        backtests=[_backtest(total_return=-5.0)],
        candles_by_mode={AnalysisMode.swing: _candles()},
        data_quality=_valid_data_quality(),
    )
    assert rec.action == "REJECT"
    assert rec.score < WATCH_SCORE_THRESHOLD
    # tech 30 -> 10.5 | news 20 -> 5.0 | fund 25 -> 6.25 | vol 50 -> 7.5
    assert rec.score == pytest.approx(29.25, abs=0.01)


# ---------------------------------------------------------------------------
# Mandatory preconditions -> REJECT regardless of score
# ---------------------------------------------------------------------------


def test_build_mock_data_rejects():
    rec = SERVICE.build(
        symbol="MOCK_TEST",
        technical_results=[_tech(score=90.0)],
        sentiment_score=0.8,
        fundamental_result=FundamentalAnalysisResult(fundamental_score=0.8, summary="ok"),
        backtests=[_backtest()],
        candles_by_mode={AnalysisMode.swing: _candles()},
        data_quality={**_valid_data_quality(), "mock_warning": True},
    )
    assert rec.action == "REJECT"
    assert "Analysis Failed" in rec.reasoning.bullets[0]


def test_build_untrusted_source_rejects():
    rec = SERVICE.build(
        symbol="UNTRUSTED_TEST",
        technical_results=[_tech(score=90.0)],
        sentiment_score=0.8,
        fundamental_result=FundamentalAnalysisResult(fundamental_score=0.8, summary="ok"),
        backtests=[_backtest()],
        candles_by_mode={AnalysisMode.swing: _candles()},
        data_quality={**_valid_data_quality(), "source": "NO_DATA"},
    )
    assert rec.action == "REJECT"


def test_build_insufficient_candles_rejects():
    # Too few candles for a trade plan -> precondition failure.
    rec = SERVICE.build(
        symbol="SHORT_TEST",
        technical_results=[_tech(score=90.0)],
        sentiment_score=0.8,
        fundamental_result=FundamentalAnalysisResult(fundamental_score=0.8, summary="ok"),
        backtests=[_backtest()],
        candles_by_mode={AnalysisMode.swing: _candles(n=2)},
        data_quality={**_valid_data_quality(), "minimum_swing_candles_met": False},
    )
    assert rec.action == "REJECT"


def test_build_no_data_quality_rejects_when_no_plan():
    # data_quality=None skips source checks but trade plans still gate.
    # No candles -> no trade plan -> REJECT.
    rec = SERVICE.build(
        symbol="NODQ_TEST",
        technical_results=[_tech(score=90.0)],
        sentiment_score=0.8,
        fundamental_result=FundamentalAnalysisResult(fundamental_score=0.8, summary="ok"),
        backtests=[_backtest()],
        candles_by_mode={AnalysisMode.swing: []},
        data_quality=None,
    )
    assert rec.action == "REJECT"


# ---------------------------------------------------------------------------
# Determinism + reasoning payload
# ---------------------------------------------------------------------------


def test_build_is_deterministic():
    kwargs = dict(
        symbol="DET_TEST",
        technical_results=[_tech(score=90.0)],
        sentiment_score=0.8,
        fundamental_result=FundamentalAnalysisResult(fundamental_score=0.8, summary="ok"),
        backtests=[_backtest()],
        candles_by_mode={AnalysisMode.swing: _candles()},
        data_quality=_valid_data_quality(),
    )
    first = SERVICE.build(**kwargs)
    second = SERVICE.build(**kwargs)
    assert first.action == second.action == "BUY"
    assert first.score == second.score
    assert first.trade_plans[0].entry_low == second.trade_plans[0].entry_low


def test_reasoning_includes_components_and_risk_factors():
    rec = SERVICE.build(
        symbol="REASON_TEST",
        technical_results=[_tech(score=90.0)],
        sentiment_score=0.8,
        fundamental_result=FundamentalAnalysisResult(fundamental_score=0.8, summary="ok"),
        backtests=[_backtest()],
        candles_by_mode={AnalysisMode.swing: _candles()},
        data_quality=_valid_data_quality(),
    )
    assert rec.reasoning.bullets
    assert rec.reasoning.invalidation_signals
    assert any("Composite score" in b for b in rec.reasoning.bullets)
    assert rec.summary.startswith("REASON_TEST")
