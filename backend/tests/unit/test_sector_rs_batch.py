"""Regression: lab universe sector overlays must not re-fetch NIFTY/sector per symbol.

The scanner timed out at 600s inside ``_resolve_sector_overlays`` when each of
~700 symbols reloaded NIFTY50 + sector indices (and often Fyers/yfinance).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.schemas import FinalRecommendation, OHLCVPoint, RecommendationReasoning
from app.services.sector_rs_service import SectorRelativeStrengthService


def _df(start: datetime, closes: list[float]) -> pd.DataFrame:
    dates = [start - timedelta(days=len(closes) - 1 - i) for i in range(len(closes))]
    return pd.DataFrame(
        {
            "open": [c * 0.99 for c in closes],
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.98 for c in closes],
            "close": closes,
            "volume": [100_000] * len(closes),
        },
        index=dates,
    )


def _points(start: datetime, closes: list[float]) -> list[OHLCVPoint]:
    out: list[OHLCVPoint] = []
    for i, c in enumerate(closes):
        out.append(
            OHLCVPoint(
                timestamp=start - timedelta(days=len(closes) - 1 - i),
                open=c * 0.99,
                high=c * 1.01,
                low=c * 0.98,
                close=c,
                volume=100_000,
            )
        )
    return out


@pytest.mark.anyio
async def test_batch_loads_each_index_once_not_per_symbol():
    """NIFTY50 + unique sector indices loaded once for the whole universe."""
    scan_date = datetime(2026, 7, 10)
    sector_closes = [100.0] * 20 + [104.0, 108.0, 112.0, 116.0, 120.0]
    nifty_closes = [100.0] * 25
    sector_df = _df(scan_date, sector_closes)
    nifty_df = _df(scan_date, nifty_closes)

    load_calls: list[str] = []

    async def fake_load(md, sym, *, is_index, allow_network=True, lookback=260):
        load_calls.append(str(sym))
        if "NIFTY50" in str(sym).upper():
            return nifty_df.copy()
        if "NIFTYIT" in str(sym).upper():
            return sector_df.copy()
        return pd.DataFrame()

    service = SectorRelativeStrengthService()
    # Force static map so bulk DB is not required
    service.mapping = {
        "TCS": "NSE:NIFTYIT-INDEX",
        "INFY": "NSE:NIFTYIT-INDEX",
        "WIPRO": "NSE:NIFTYIT-INDEX",
        "HCLTECH": "NSE:NIFTYIT-INDEX",
        "TECHM": "NSE:NIFTYIT-INDEX",
    }
    symbols = list(service.mapping.keys())

    with patch.object(service, "_load_candles", side_effect=fake_load):
        with patch.object(service, "_bulk_lookup_master_sectors", return_value={}):
            results = await service.evaluate_sector_overlays_batch(
                symbols,
                scan_date=scan_date,
                allow_network=False,
            )

    assert len(results) == len(symbols)
    # Exactly one NIFTY load + one NIFTYIT load (not 5× each)
    nifty_loads = sum(1 for s in load_calls if "NIFTY50" in s.upper())
    it_loads = sum(1 for s in load_calls if "NIFTYIT" in s.upper())
    assert nifty_loads == 1, f"expected 1 NIFTY load, got {nifty_loads}: {load_calls}"
    assert it_loads == 1, f"expected 1 NIFTYIT load, got {it_loads}: {load_calls}"
    for sym in symbols:
        assert results[sym].sector_filter_status == "STRENGTH"
        assert results[sym].sector_rs_20 is not None


@pytest.mark.anyio
async def test_batch_path_b_uses_prefetched_candles_without_network():
    """Unmapped symbols use prefetched equity candles (no Fyers/Yahoo)."""
    scan_date = datetime(2026, 7, 10)
    stock_closes = [100.0] * 20 + [110.0, 112.0, 114.0, 116.0, 118.0]  # outperforming
    nifty_closes = [100.0] * 25
    nifty_df = _df(scan_date, nifty_closes)
    stock_pts = _points(scan_date, stock_closes)

    async def fake_load(md, sym, *, is_index, allow_network=True, lookback=260):
        assert allow_network is False
        if "NIFTY50" in str(sym).upper():
            return nifty_df.copy()
        return pd.DataFrame()

    service = SectorRelativeStrengthService()
    service.mapping = {}  # force path B

    with patch.object(service, "_load_candles", side_effect=fake_load):
        with patch.object(service, "_bulk_lookup_master_sectors", return_value={}):
            results = await service.evaluate_sector_overlays_batch(
                ["FOO-EQ", "BAR-EQ"],
                candles_by_symbol={"FOO-EQ": stock_pts, "BAR-EQ": stock_pts},
                scan_date=scan_date,
                allow_network=False,
            )

    assert results["FOO-EQ"].sector_rs_20 is not None
    assert results["FOO-EQ"].sector_filter_status == "STRENGTH"
    assert results["BAR-EQ"].sector_rs_20 is not None

@pytest.mark.anyio
async def test_single_symbol_path_still_works():
    """Production Top-N still uses evaluate_sector_overlay."""
    scan_date = datetime(2026, 7, 10)
    sector_closes = [100.0] * 20 + [98.0, 96.0, 94.0, 92.0, 90.0]
    nifty_closes = [100.0] * 20 + [102.0, 104.0, 106.0, 108.0, 110.0]
    sector_df = _df(scan_date, sector_closes)
    nifty_df = _df(scan_date, nifty_closes)

    async def fake_load(md, sym, *, is_index, allow_network=True, lookback=260):
        if "NIFTYIT" in str(sym).upper():
            return sector_df.copy()
        if "NIFTY50" in str(sym).upper():
            return nifty_df.copy()
        return pd.DataFrame()

    service = SectorRelativeStrengthService()
    service.mapping = {"TCS": "NSE:NIFTYIT-INDEX"}
    rec = FinalRecommendation(
        action="BUY",
        confidence=0.85,
        score=85.0,
        reasoning=RecommendationReasoning(
            bullets=[], risk_factors=[], invalidation_signals=[]
        ),
        trade_plans=[],
        summary="x",
    )
    with patch.object(service, "_load_candles", side_effect=fake_load):
        result = await service.evaluate_sector_overlay("TCS", scan_date, rec)

    assert result.sector_filter_status == "WEAK"
    assert result.downgrade_triggered is True
