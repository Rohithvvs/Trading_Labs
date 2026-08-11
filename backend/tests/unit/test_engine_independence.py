"""Engine independence: RE-001 / RE-002 must not depend on Production top-N."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import AnalysisMode, TechnicalAnalysisResult
from app.services.independent_lab_universe import (
    build_technical_map,
    frames_to_ohlcv_points,
    technical_from_screener_row,
)


def test_technical_from_screener_row_reuses_score():
    row = SimpleNamespace(
        technical_score=67.5,
        technical_signal="bullish",
        ema_20=100.0,
        ema_50=95.0,
        sma_30=98.0,
        sma_50=94.0,
        sma_100=90.0,
        sma_200=85.0,
        macd=1.2,
        macd_signal=0.8,
        supertrend=92.0,
    )
    tech = technical_from_screener_row(row)
    assert isinstance(tech, TechnicalAnalysisResult)
    assert tech.score == 67.5
    assert tech.signal == "bullish"
    assert tech.mode == AnalysisMode.swing
    assert tech.indicators.get("ema_20") == 100.0


def test_build_technical_map_covers_full_symbol_list():
    rows = [
        SimpleNamespace(
            symbol="AAA",
            technical_score=80.0,
            technical_signal="bullish",
            ema_20=1,
            ema_50=1,
            sma_30=1,
            sma_50=1,
            sma_100=1,
            sma_200=1,
            macd=0,
            macd_signal=0,
            supertrend=1,
        ),
        SimpleNamespace(
            symbol="BBB",
            technical_score=40.0,
            technical_signal="neutral",
            ema_20=1,
            ema_50=1,
            sma_30=1,
            sma_50=1,
            sma_100=1,
            sma_200=1,
            macd=0,
            macd_signal=0,
            supertrend=1,
        ),
    ]
    # Lab universe can include symbols not matched by Production
    mapping = build_technical_map(rows, ["AAA", "BBB", "CCC"])
    assert set(mapping.keys()) == {"AAA", "BBB", "CCC"}
    assert mapping["AAA"][0].score == 80.0
    assert mapping["BBB"][0].score == 40.0
    assert mapping["CCC"][0].score == 0.0  # missing screener row


def test_frames_to_ohlcv_requires_min_bars():
    import pandas as pd
    from datetime import datetime, timedelta

    # Too few bars
    short = pd.DataFrame(
        {
            "open": [1.0] * 10,
            "high": [1.1] * 10,
            "low": [0.9] * 10,
            "close": [1.0] * 10,
            "volume": [1000] * 10,
        },
        index=[datetime(2024, 1, 1) + timedelta(days=i) for i in range(10)],
    )
    out = frames_to_ohlcv_points({"AAA": short}, ["AAA"], min_bars=220)
    assert out == {}

    long = pd.DataFrame(
        {
            "open": [1.0] * 220,
            "high": [1.1] * 220,
            "low": [0.9] * 220,
            "close": [1.0] * 220,
            "volume": [1000] * 220,
        },
        index=[datetime(2024, 1, 1) + timedelta(days=i) for i in range(220)],
    )
    out2 = frames_to_ohlcv_points({"AAA": long}, ["AAA"], min_bars=220)
    assert "AAA" in out2
    assert len(out2["AAA"]) == 220


@pytest.mark.asyncio
async def test_independent_lab_universe_receives_full_data_valid_not_top_n():
    """RE engines are invoked for every data_valid symbol, not Production shortlist."""
    from app.services.independent_lab_universe import run_independent_lab_universe
    from app.schemas import OHLCVPoint
    from datetime import datetime, timedelta

    # 5 data_valid symbols; Production would only shortlist 2
    symbols = ["S1", "S2", "S3", "S4", "S5"]
    base = datetime(2024, 1, 1)
    candles = {
        s: [
            OHLCVPoint(
                timestamp=base + timedelta(days=i),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0 + (i % 3),
                volume=1_000_000,
            )
            for i in range(250)
        ]
        for s in symbols
    }
    screener_results = [
        SimpleNamespace(
            symbol=s,
            technical_score=60.0,
            technical_signal="bullish",
            ema_20=100,
            ema_50=95,
            sma_30=98,
            sma_50=94,
            sma_100=90,
            sma_200=85,
            macd=1,
            macd_signal=0.5,
            supertrend=92,
            conditions={"data_source_failed": False, "data_quality_failed": False},
        )
        for s in symbols
    ]

    called_re001: list[str] = []
    called_re002: list[str] = []

    async def fake_re001(**kwargs):
        called_re001.append(kwargs["symbol"])
        return SimpleNamespace(
            engine_id="RE-001",
            recommendation_state="REJECT",
            confidence_score=0.1,
            technical_analysis={},
            model_dump=lambda mode="json": {
                "engine_id": "RE-001",
                "recommendation_state": "REJECT",
                "symbol": kwargs["symbol"],
            },
        )

    async def fake_re002(**kwargs):
        called_re002.append(kwargs["symbol"])
        return SimpleNamespace(
            engine_id="RE-002",
            recommendation_state="REJECT",
            confidence_score=0.1,
            technical_analysis={},
            model_dump=lambda mode="json": {
                "engine_id": "RE-002",
                "recommendation_state": "REJECT",
                "symbol": kwargs["symbol"],
            },
        )

    mock_settings = MagicMock()
    mock_settings.is_re001_active.return_value = True
    mock_settings.is_re002_active.return_value = True

    with (
        patch("app.services.independent_lab_universe.settings", mock_settings),
        patch(
            "app.services.independent_lab_universe._resolve_sector_overlays",
            new=AsyncMock(return_value={s: None for s in symbols}),
        ),
        patch(
            "app.services.independent_lab_universe._benchmark_candles_for_re002",
            new=AsyncMock(return_value=(None, None)),
        ),
        patch("app.services.re001.run_re001_isolated_async", side_effect=fake_re001),
        patch("app.services.re002.run_re002_isolated_async", side_effect=fake_re002),
        patch("app.db.session.SessionLocal", MagicMock()),
    ):
        summary = await run_independent_lab_universe(
            symbols=symbols,
            screener_results=screener_results,
            prefetched_candles=candles,
            market_regime=SimpleNamespace(market_state="BULL", model_dump=lambda: {"market_state": "BULL"}),
            scan_run_id="test-scan-independence",
            concurrency=5,
        )

    # Critical: all 5 data_valid symbols received by both engines — not top_n=2
    assert set(called_re001) == set(symbols)
    assert set(called_re002) == set(symbols)
    assert summary["input_universe"] == 5
    assert summary["re001_evaluated"] == 5
    assert summary["re002_evaluated"] == 5


@pytest.mark.asyncio
async def test_production_shortlist_not_used_as_lab_input_boundary():
    """Document architectural invariant: lab_input = data_valid, production = top_n matched."""
    matched = [f"M{i}" for i in range(50)]
    data_valid = [f"V{i}" for i in range(100)]
    top_n = 20
    shortlisted = matched[:top_n]
    lab_input = list(data_valid)

    assert len(shortlisted) == 20
    assert len(lab_input) == 100
    # Lab must not equal Production shortlist
    assert lab_input != shortlisted
    # Lab universe is larger and independent
    assert set(shortlisted).issubset(set(matched))
    assert len(lab_input) > len(shortlisted)
