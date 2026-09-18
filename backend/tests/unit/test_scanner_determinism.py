from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.agents.orchestrator_agent import OrchestratorAgent
from backend.app.schemas import (
    FullAnalysisResponse,
    RankingsResponse,
    ScreenerConditionResult,
    ScreenerRequest,
    ScreenerResponse,
    ScreenerStageSummary,
)
from backend.app.services.ranking_service import RankingService


def _screen_result(symbol: str, score: float) -> ScreenerConditionResult:
    return ScreenerConditionResult(
        symbol=symbol,
        close=100.0,
        ema_20=99.0,
        sma_30=98.0,
        sma_50=97.0,
        sma_100=96.0,
        sma_200=95.0,
        macd=1.0,
        macd_signal=0.5,
        supertrend=94.0,
        volume=100000,
        previous_volume=90000,
        screener_score=score,
        technical_signal="bullish",
        technical_score=80.0,
        candles_fetched=260,
        conditions={"broad_trend_eligibility": True},
        matched=True,
    )


def _sort_matched(results: list[ScreenerConditionResult]) -> list[str]:
    """Production sort contract used by orchestrator shortlist path."""
    matched = [item for item in results if item.matched]
    matched.sort(key=lambda item: (-item.screener_score, item.symbol))
    return [item.symbol for item in matched]


@pytest.mark.unit
def test_screener_results_are_stable_across_repeated_runs():
    scores = {"TCS-EQ": 82.0, "INFY-EQ": 82.0, "RELIANCE-EQ": 79.0}
    first_input = [_screen_result(s, scores[s]) for s in scores]
    second_input = [_screen_result(s, scores[s]) for s in reversed(list(scores))]

    first = _sort_matched(first_input)
    second = _sort_matched(second_input)

    assert first == ["INFY-EQ", "TCS-EQ", "RELIANCE-EQ"]
    assert second == first


@pytest.mark.unit
def test_screener_ignores_future_completion_order():
    # Completion order must not affect deterministic ranking by (-score, symbol).
    completion_order = [
        _screen_result("RELIANCE-EQ", 79.0),
        _screen_result("TCS-EQ", 82.0),
        _screen_result("INFY-EQ", 82.0),
    ]
    ordered = _sort_matched(completion_order)
    assert ordered == ["INFY-EQ", "TCS-EQ", "RELIANCE-EQ"]


@pytest.mark.asyncio
async def test_shortlist_breaks_equal_screener_scores_by_symbol():
    orchestrator = object.__new__(OrchestratorAgent)
    orchestrator.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
    orchestrator._log_determinism_debug = lambda *args, **kwargs: None

    async def _screen(symbols, lookback_window, stage_name, progress_callback=None):
        return [
            _screen_result("TCS-EQ", 82.0),
            _screen_result("INFY-EQ", 82.0),
        ]

    orchestrator.screener_service = SimpleNamespace(
        screen_symbols_swing=_screen,
        last_fetched_frames={},
    )

    async def _run_full(request, progress_callback=None, prefetched_candles=None, **kwargs):
        # Accept future kwargs from the shortlist path
        return FullAnalysisResponse(
            items=[],
            rankings=RankingsResponse(
                rankings=[],
                buy_rankings=[],
                watch_rankings=[],
                best_intraday_candidate=None,
                best_swing_candidate=None,
                disclaimer="test",
            ),
            disclaimer="test",
            generated_at=datetime(2026, 5, 17, tzinfo=timezone.utc),
        )

    orchestrator.run_full = _run_full
    orchestrator.ranking_agent = SimpleNamespace(
        run=lambda items: RankingsResponse(
            rankings=[],
            buy_rankings=[],
            watch_rankings=[],
            best_intraday_candidate=None,
            best_swing_candidate=None,
            disclaimer="test",
        )
    )
    orchestrator._data_source_label = lambda *args, **kwargs: "test"
    orchestrator._data_warning = lambda: None
    orchestrator._market_context = lambda: {}
    orchestrator._canonical_symbol = lambda s: str(s).replace("-EQ", "").replace("NSE:", "")

    # Minimal request object with timeframe.lookback_window used by stage.
    request = ScreenerRequest(top_n=2)

    from unittest.mock import MagicMock, patch

    mock_settings = MagicMock()
    mock_settings.is_authoritative_candle_store_enabled.return_value = False

    with patch("app.agents.orchestrator_agent.settings", mock_settings):
        response = await orchestrator._run_screener_stage(
            request=request,
            stage_name="test",
            source_universe=["TCS-EQ", "INFY-EQ"],
            duplicate_symbols_skipped=0,
        )

    assert response.shortlisted_symbols == ["INFY-EQ", "TCS-EQ"]


def _stage_response(*, stage_name: str = "NIFTY500", buy: list[str] | None = None) -> ScreenerResponse:
    buy_symbols = buy or ["INFY-EQ"]
    return ScreenerResponse(
        scanned_symbols=len(buy_symbols),
        screener_name=f"{stage_name} Combined Swing Scanner ({len(buy_symbols)})",
        data_valid_symbols=buy_symbols,
        eligible_symbols=buy_symbols,
        shortlisted_symbols=buy_symbols,
        buy_candidate_symbols=buy_symbols,
        watch_candidate_symbols=[],
        matched_symbols=buy_symbols,
        matches=[],
        analysis=None,
        disclaimer="test",
        scan_stages=[
            ScreenerStageSummary(
                stage_name=stage_name,
                source_universe_size=len(buy_symbols),
                unique_symbols_scanned=len(buy_symbols),
                duplicate_symbols_skipped=0,
                matched_symbols=len(buy_symbols),
                shortlisted_symbols=len(buy_symbols),
                buy_candidate_symbols=buy_symbols,
            )
        ],
    )


def _orchestrator_for_impl() -> OrchestratorAgent:
    orchestrator = object.__new__(OrchestratorAgent)
    orchestrator.logger = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    orchestrator._canonical_symbol = OrchestratorAgent._canonical_symbol.__get__(orchestrator)
    orchestrator._dedupe_symbols = OrchestratorAgent._dedupe_symbols.__get__(orchestrator)
    return orchestrator


@pytest.mark.asyncio
async def test_run_screener_impl_accepts_screener_response_from_stage():
    """Regression: stage returns ScreenerResponse, not a 3-tuple.

    Unpacking a Pydantic model as ``a, b, c = response`` raises
    ``ValueError: too many values to unpack (expected 3)`` and aborts
    automated screening after the first universe stage completes.
    """
    orchestrator = _orchestrator_for_impl()
    stage_response = _stage_response(buy=["ACE-EQ", "BHEL-EQ"])

    async def _stage(**kwargs):
        return stage_response

    async def _universes():
        return [("NIFTY500", ["ACE-EQ", "BHEL-EQ"])]

    orchestrator._run_screener_stage = _stage
    orchestrator._prioritized_universes = _universes

    result = await orchestrator._run_screener_impl(ScreenerRequest(top_n=20))

    assert result.buy_candidate_symbols == ["ACE-EQ", "BHEL-EQ"]
    assert result.stopped_at_stage == "NIFTY500"
    assert result.scan_stages[-1].stopped_here is True


@pytest.mark.asyncio
async def test_run_screener_impl_custom_symbols_returns_stage_response():
    orchestrator = _orchestrator_for_impl()
    stage_response = _stage_response(stage_name="Custom symbols", buy=["INFY-EQ"])

    async def _stage(**kwargs):
        return stage_response

    orchestrator._run_screener_stage = _stage

    result = await orchestrator._run_screener_impl(
        ScreenerRequest(top_n=2, symbols=["INFY-EQ"])
    )

    assert result is stage_response
    assert result.buy_candidate_symbols == ["INFY-EQ"]


@pytest.mark.unit
def test_ranking_service_breaks_score_ties_by_symbol():
    service = RankingService()
    items = [
        SimpleNamespace(
            symbol="TCS-EQ",
            recommendation=SimpleNamespace(score=80.0, action="BUY"),
            technical=[SimpleNamespace(mode=SimpleNamespace(value="swing"))],
        ),
        SimpleNamespace(
            symbol="INFY-EQ",
            recommendation=SimpleNamespace(score=80.0, action="BUY"),
            technical=[SimpleNamespace(mode=SimpleNamespace(value="swing"))],
        ),
    ]

    rankings = service.rank(items)

    assert [item.symbol for item in rankings.rankings] == ["INFY-EQ", "TCS-EQ"]
    assert rankings.best_swing_candidate == "INFY-EQ"
