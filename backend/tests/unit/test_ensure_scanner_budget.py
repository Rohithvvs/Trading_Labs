"""Scanner ensure path must not hang at 4% forever.

Root cause of:
  UI stuck at "Ensuring market data..." 4%
  → stream stalled 90s
  → logs end at "Scanner token loaded successfully"

was unbounded ensure work (full-universe FYERS + sequential ADTV) with no budget.
"""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.market_data_ingestion import ensure as ens


@pytest.fixture(autouse=True)
def _clear_universe_cache():
    ens._UNIVERSE_CACHE = None
    yield
    ens._UNIVERSE_CACHE = None


@pytest.mark.asyncio
async def test_scanner_ensure_times_out_instead_of_hanging():
    """When FYERS never returns, scanner budget yields TIMEOUT quickly."""
    session = date(2026, 8, 7)
    symbols = [f"SYM{i}-EQ" for i in range(20)]

    lease = MagicMock()
    lease.acquired = True
    lease.release = AsyncMock()

    async def hang_forever(*_a, **_k):
        await asyncio.sleep(3600)
        return None

    progress_events: list[dict] = []

    def on_progress(msg: dict) -> None:
        progress_events.append(dict(msg))

    def _empty_snap(universe, *, index_present=False, max_eq=None, include_sets=False):
        n = len(universe)
        snap = {
            "present": set(),
            "with_delivery": set(),
            "with_adtv": set(),
            "present_count": 0,
            "delivery_count": 0,
            "adtv_count": 0,
            "universe_count": n,
            "index_present": index_present,
            "max_equity_date": max_eq,
            "equity_coverage": 0.0,
            "delivery_coverage": 0.0,
            "adtv_coverage": 0.0,
            "missing_ohlcv": list(universe) if include_sets else [f"__m{i}" for i in range(n)],
            "missing_delivery": list(universe) if include_sets else [],
            "missing_adtv": list(universe) if include_sets else [],
        }
        return snap

    async def fake_snapshot(_expected, _universe, index_symbol="NIFTY500", include_symbol_sets=False):
        return _empty_snap(_universe, index_present=False, max_eq=None, include_sets=include_symbol_sets)

    with (
        patch.object(ens, "expected_last_completed_session", return_value=session),
        patch.object(ens, "_get_universe", new=AsyncMock(return_value=symbols)),
        patch.object(ens, "_snapshot", new=fake_snapshot),
        patch(
            "app.services.universe_service.UniverseService.touch_lifecycle",
            new=AsyncMock(),
        ),
        patch.object(ens, "acquire_market_data_load_lock", new=AsyncMock(return_value=lease)),
        patch.object(ens.repository, "index_present", new=AsyncMock(return_value=False)),
        patch.object(ens.repository, "symbols_present_on", new=AsyncMock(return_value=set())),
        patch.object(ens.repository, "symbols_with_delivery_on", new=AsyncMock(return_value=set())),
        patch.object(ens.repository, "symbols_with_adtv_on", new=AsyncMock(return_value=set())),
        patch.object(ens.repository, "upsert_daily_bars", new=AsyncMock(return_value=(0, 0))),
        patch.object(ens.repository, "upsert_index_bars", new=AsyncMock(return_value=0)),
        patch.object(ens.repository, "update_delivery_for_session", new=AsyncMock(return_value=0)),
        patch.object(ens.repository, "backfill_adtv_20_for_session", new=AsyncMock(return_value=0)),
        patch(
            "app.services.market_data_ingestion.providers.nse_delivery.NseDeliveryProvider.fetch_session_delivery",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.market_data_ingestion.providers.fyers_eod.FyersEodProvider.fetch_daily_session",
            new=hang_forever,
        ),
        patch(
            "app.services.market_data_ingestion.providers.fyers_eod.FyersEodProvider.fetch_index_range",
            new=AsyncMock(return_value=[]),
        ),
    ):
        t0 = asyncio.get_running_loop().time()
        result = await ens.ensure_latest_market_data(
            trigger_source="SCANNER",
            progress_callback=on_progress,
            max_duration_s=2.0,
        )
        elapsed = asyncio.get_running_loop().time() - t0

    assert result["status"] in {"TIMEOUT", "PARTIAL", "FAILED", "SUCCESS"}
    assert elapsed < 12.0, f"ensure hung too long: {elapsed:.1f}s"
    assert len(progress_events) >= 1


@pytest.mark.asyncio
async def test_scanner_ensure_caps_ohlcv_symbols():
    """Scanner path must not schedule full-universe live FYERS chase."""
    session = date(2026, 8, 7)
    symbols = [f"SYM{i}-EQ" for i in range(200)]

    lease = MagicMock()
    lease.acquired = True
    lease.release = AsyncMock()

    fetch_calls: list[str] = []

    async def track_fetch(sym, *_a, **_k):
        fetch_calls.append(sym)
        return {
            "trade_date": session,
            "symbol": sym,
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 100,
            "source": "FYERS",
        }

    async def fake_snapshot(_expected, _universe, index_symbol="NIFTY500", include_symbol_sets=False):
        n = len(_universe)
        return {
            "present": set(),
            "with_delivery": set(),
            "with_adtv": set(),
            "present_count": 0,
            "delivery_count": 0,
            "adtv_count": 0,
            "universe_count": n,
            "index_present": True,
            "max_equity_date": session,
            "equity_coverage": 0.0,
            "delivery_coverage": 0.0,
            "adtv_coverage": 0.0,
            "missing_ohlcv": list(_universe) if include_symbol_sets else [f"__m{i}" for i in range(n)],
            "missing_delivery": [],
            "missing_adtv": [],
        }

    with (
        patch.object(ens, "expected_last_completed_session", return_value=session),
        patch.object(ens, "_get_universe", new=AsyncMock(return_value=symbols)),
        patch.object(ens, "_snapshot", new=fake_snapshot),
        patch(
            "app.services.universe_service.UniverseService.touch_lifecycle",
            new=AsyncMock(),
        ),
        patch.object(ens, "acquire_market_data_load_lock", new=AsyncMock(return_value=lease)),
        patch.object(ens.repository, "index_present", new=AsyncMock(return_value=True)),
        patch.object(ens.repository, "symbols_present_on", new=AsyncMock(return_value=set())),
        patch.object(ens.repository, "symbols_with_delivery_on", new=AsyncMock(return_value=set())),
        patch.object(ens.repository, "symbols_with_adtv_on", new=AsyncMock(return_value=set())),
        patch.object(ens.repository, "upsert_daily_bars", new=AsyncMock(return_value=(10, 0))),
        patch.object(ens.repository, "update_delivery_for_session", new=AsyncMock(return_value=0)),
        patch.object(ens.repository, "backfill_adtv_20_for_session", new=AsyncMock(return_value=0)),
        patch.object(ens.repository, "fetch_recent_equity_before", new=AsyncMock(return_value=[])),
        patch(
            "app.services.market_data_ingestion.providers.nse_delivery.NseDeliveryProvider.fetch_session_delivery",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.market_data_ingestion.providers.fyers_eod.FyersEodProvider.fetch_daily_session",
            new=track_fetch,
        ),
        patch(
            "app.services.market_data_ingestion.providers.fyers_eod.FyersEodProvider.fetch_index_range",
            new=AsyncMock(return_value=[]),
        ),
    ):
        result = await ens.ensure_latest_market_data(
            trigger_source="SCANNER",
            max_duration_s=30.0,
        )

    assert len(fetch_calls) <= ens._SCANNER_MAX_OHLCV_FETCH
    assert result["status"] in {"SUCCESS", "PARTIAL", "TIMEOUT", "FAILED"}
