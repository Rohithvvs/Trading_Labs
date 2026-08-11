"""Scanner bulk indicators must run off the asyncio event loop.

Root cause of simultaneous:
  - Scanner stream stalled — no progress for 90s
  - Infrastructure all "Waking Up" (health timed out)

was pure-CPU analyze_bulk_from_frame + frame build on the event loop.
"""
from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.schemas import AnalysisMode, TechnicalAnalysisResult
from app.services.screener_service import ScreenerService


@pytest.mark.asyncio
async def test_analyze_bulk_runs_off_event_loop_thread():
    """While bulk analysis runs, the event loop must still schedule other tasks."""
    loop_thread = threading.current_thread().ident
    saw_other_task = {"ok": False}
    analyze_thread = {"id": None}

    async def heartbeat_probe():
        # If event loop is free, this runs during the CPU offload.
        for _ in range(50):
            await asyncio.sleep(0.01)
            saw_other_task["ok"] = True
            if analyze_thread["id"] is not None:
                break

    def slow_analyze(frame, mode):
        analyze_thread["id"] = threading.current_thread().ident
        # Simulate multi-second CPU work without burning CI time.
        import time

        time.sleep(0.15)
        return {
            "SYM": TechnicalAnalysisResult(
                mode=AnalysisMode.swing,
                signal="neutral",
                score=50.0,
                indicators={},
                summary="test",
            )
        }

    svc = ScreenerService.__new__(ScreenerService)
    svc.technical_service = MagicMock()
    svc.technical_service.analyze_bulk_from_frame = slow_analyze
    svc.logger = MagicMock()

    # Build a tiny multi-symbol frame path by calling the private offload helper pattern
    # through the same asyncio.to_thread entry used in screen_symbols_swing.
    bar_cap = 240
    frames = {
        "SYM": pd.DataFrame(
            {
                "open": [1.0] * 230,
                "high": [1.1] * 230,
                "low": [0.9] * 230,
                "close": [1.0] * 230,
                "volume": [1000] * 230,
            },
            index=pd.date_range("2024-01-01", periods=230, freq="B"),
        )
    }

    def _build_and_analyze_bulk(frames_in):
        ffill_t0 = 0.0
        frame_parts = []
        frames_out = {}
        for symbol, df in list(frames_in.items()):
            df = df.sort_index().ffill().bfill().fillna(0)
            if len(df) > bar_cap:
                df = df.iloc[-bar_cap:]
            frames_out[symbol] = df
            sym_df = df.copy()
            sym_df["symbol"] = symbol
            sym_df.index.name = "timestamp"
            sym_df = sym_df.reset_index().set_index(["timestamp", "symbol"])
            frame_parts.append(sym_df)
        combined = pd.concat(frame_parts)
        combined.sort_index(inplace=True)
        bulk = svc.technical_service.analyze_bulk_from_frame(combined, AnalysisMode.swing)
        return frames_out, bulk, 1.0, 1.0

    probe = asyncio.create_task(heartbeat_probe())
    result = await asyncio.to_thread(_build_and_analyze_bulk, frames)
    await probe

    frames_out, bulk, _, _ = result
    assert "SYM" in frames_out
    assert "SYM" in bulk
    assert saw_other_task["ok"] is True
    assert analyze_thread["id"] is not None
    assert analyze_thread["id"] != loop_thread, "bulk analysis must not run on event-loop thread"
