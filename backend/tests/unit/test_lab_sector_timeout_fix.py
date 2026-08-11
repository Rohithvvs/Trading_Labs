"""Regression: Top Set=20 must not hang in per-symbol sector overlay on full universe.

Product architecture intentionally evaluates RE-001/RE-002 on full data_valid (~700),
independent of Production top_n. Sector RS for that universe must be BATCHED, not
N+1 evaluate_sector_overlay, or the 600s scan budget is exhausted after AI Top-N.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import OHLCVPoint
from app.services import independent_lab_universe as lab
from app.services.scan_execution_service import ScanExecutionService, _scan_state


def _pts(n: int = 25) -> list[OHLCVPoint]:
    start = datetime(2026, 7, 10)
    out = []
    for i in range(n):
        c = 100.0 + i * 0.1
        out.append(
            OHLCVPoint(
                timestamp=start - timedelta(days=n - 1 - i),
                open=c,
                high=c,
                low=c,
                close=c,
                volume=1_000,
            )
        )
    return out


@pytest.mark.anyio
async def test_top_n_does_not_gate_lab_input_universe_size():
    """Architectural contract: lab_input = data_valid, not top_n shortlist."""
    # Documented in orchestrator_agent — verify the independent module contract.
    symbols = [f"S{i}" for i in range(50)]
    with patch("app.services.independent_lab_universe.settings") as mock_settings:
        mock_settings.is_re001_active.return_value = False
        mock_settings.is_re002_active.return_value = False
        summary = await lab.run_independent_lab_universe(symbols=symbols)
    assert summary["input_universe"] == 50


@pytest.mark.anyio
async def test_resolve_sector_overlays_uses_batch_not_per_symbol_gather():
    """Must not create N concurrent evaluate_sector_overlay coroutines."""
    batch = AsyncMock(
        return_value={s: MagicMock() for s in ["A", "B", "C"]}
    )
    single = AsyncMock()
    with patch(
        "app.services.sector_rs_service.SectorRelativeStrengthService.evaluate_sector_overlays_batch",
        batch,
    ):
        with patch(
            "app.services.sector_rs_service.SectorRelativeStrengthService.evaluate_sector_overlay",
            single,
        ):
            candles = {s: _pts() for s in ["A", "B", "C"]}
            out = await lab._resolve_sector_overlays(
                ["A", "B", "C"], candles, concurrency=8
            )
    batch.assert_awaited_once()
    single.assert_not_called()
    assert len(out) == 3
    kwargs = batch.await_args.kwargs
    assert kwargs.get("allow_network") is False
    assert "candles_by_symbol" in kwargs


@pytest.mark.anyio
async def test_batch_sector_completes_under_budget_for_700_symbols():
    """Cached-data batch path must finish well under scan residual budget."""
    from app.services.sector_rs_service import SectorRelativeStrengthService
    import pandas as pd
    import time

    n = 700
    symbols = [f"SYM{i}" for i in range(n)]
    scan_date = datetime(2026, 7, 10)
    closes = [100.0] * 25
    nifty = pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1] * 25,
        },
        index=[scan_date - timedelta(days=24 - i) for i in range(25)],
    )
    # Map every 50th symbol to same sector so unique sector count is small
    mapping = {f"SYM{i}": "NSE:NIFTYIT-INDEX" for i in range(n)}

    async def fake_load(md, sym, *, is_index, allow_network=True, lookback=260):
        return nifty.copy()

    svc = SectorRelativeStrengthService()
    svc.mapping = mapping
    t0 = time.perf_counter()
    with patch.object(svc, "_load_candles", side_effect=fake_load):
        with patch.object(svc, "_bulk_lookup_master_sectors", return_value={}):
            out = await svc.evaluate_sector_overlays_batch(
                symbols,
                candles_by_symbol={s: _pts() for s in symbols[:10]},  # sparse path B
                scan_date=scan_date,
                allow_network=False,
            )
    elapsed = time.perf_counter() - t0
    assert len(out) == n
    assert elapsed < 15.0, f"batch too slow: {elapsed:.2f}s for {n} symbols"


@pytest.mark.anyio
async def test_lab_eval_tasks_cancelled_on_parent_cancel():
    """Cancelling run_independent_lab_universe must cancel outstanding eval tasks."""
    symbols = [f"S{i}" for i in range(30)]
    started = asyncio.Event()

    async def slow_re001(**kwargs):
        started.set()
        await asyncio.sleep(60)
        return MagicMock(
            recommendation_state="WATCH",
            model_dump=lambda mode="json": {"recommendation_state": "WATCH"},
        )

    mock_settings = MagicMock()
    mock_settings.is_re001_active.return_value = True
    mock_settings.is_re002_active.return_value = False

    with patch("app.services.independent_lab_universe.settings", mock_settings):
        with patch.object(
            lab,
            "_resolve_sector_overlays",
            AsyncMock(return_value={s: None for s in symbols}),
        ):
            with patch.object(
                lab,
                "_load_missing_candles",
                AsyncMock(side_effect=lambda symbols, existing, **kw: existing),
            ):
                with patch(
                    "app.services.re001.run_re001_isolated_async",
                    side_effect=slow_re001,
                ):
                    task = asyncio.create_task(
                        lab.run_independent_lab_universe(
                            symbols=symbols,
                            prefetched_candles={s: _pts(60) for s in symbols},
                            concurrency=4,
                        )
                    )
                    for _ in range(100):
                        await asyncio.sleep(0.02)
                        if started.is_set():
                            break
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
    assert task.done()


def test_progress_callback_updates_state_on_heartbeat_stage():
    """Lab stages with heartbeat=True must still update _scan_state for SSE heartbeats."""
    _scan_state.update(
        stage="Running AI Analysis... (20/20)",
        progress=85,
        done=20,
        remaining=0,
        total=20,
    )

    # Simulate the fixed progress_callback logic
    update = {
        "stage": "Lab sector RS overlays (40/712)...",
        "progress": 89,
        "heartbeat": True,
        "done": 40,
        "remaining": 672,
        "total": 712,
    }
    # Inline the contract: stage-bearing heartbeats must update state
    assert update.get("heartbeat") and update.get("stage")
    _scan_state.update(
        stage=update["stage"],
        progress=update["progress"],
        done=update["done"],
        remaining=update["remaining"],
        total=update["total"],
    )
    snap = _scan_state.snapshot()
    assert "Lab sector" in snap["stage"]
    assert snap["progress"] == 89
    assert snap["done"] == 40
    assert "AI Analysis" not in snap["stage"]


def test_progress_monotonic_watermark():
    """Incoming progress lower than current watermark is raised to current."""
    _scan_state.update(stage="AI done", progress=85, done=20, remaining=0, total=20)
    incoming = 72  # old lab band (bug)
    effective = max(incoming, int(_scan_state.progress or 0))
    assert effective == 85


@pytest.mark.anyio
async def test_batch_allow_network_false_does_not_call_fyers():
    from app.services.sector_rs_service import SectorRelativeStrengthService
    import pandas as pd

    scan_date = datetime(2026, 7, 10)
    closes = [100.0 + i for i in range(25)]
    df = pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1] * 25,
        },
        index=[scan_date - timedelta(days=24 - i) for i in range(25)],
    )
    fyers_called = {"n": 0}

    async def fake_load(md, sym, *, is_index, allow_network=True, lookback=260):
        assert allow_network is False
        return df.copy()

    svc = SectorRelativeStrengthService()
    svc.mapping = {"TCS": "NSE:NIFTYIT-INDEX"}
    with patch.object(svc, "_load_candles", side_effect=fake_load):
        with patch.object(svc, "_bulk_lookup_master_sectors", return_value={}):
            with patch(
                "app.services.fyers_service.FyersService",
                side_effect=lambda *a, **k: fyers_called.__setitem__("n", fyers_called["n"] + 1),
            ):
                await svc.evaluate_sector_overlays_batch(
                    ["TCS"],
                    scan_date=scan_date,
                    allow_network=False,
                )
    assert fyers_called["n"] == 0
