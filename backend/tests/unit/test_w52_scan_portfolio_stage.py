"""Tests for the portfolio-backtest stage: deterministic timeout + progress reset.

Guards the fix for the 52W scanner hanging at 755/755 "Running portfolio
backtest...". The portfolio backtest (replay_book) must (a) never leave the
scan RUNNING indefinitely and (b) clear stale per-symbol progress counters
when it starts so the UI does not show "755/755" + the last symbol while the
portfolio simulation runs.
"""

import asyncio
import time
import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.strategies.breakout52w import scan_service
from app.services.strategies.breakout52w.book_engine import BookState
from app.services.strategies.breakout52w.scan_service import run_scan


def _ok_freshness():
    return SimpleNamespace(ok=True, to_dict=lambda: {})


def _minimal_matrices():
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(300)]
    sym = "AAA-EQ"
    high_m = {sym: {dt: 10.0 for dt in dates}}
    low_m = {sym: {dt: 9.0 for dt in dates}}
    close_m = {sym: {dt: 9.5 for dt in dates}}
    vol_m = {sym: {dt: 1e6 for dt in dates}}
    index = {dt: 100.0 for dt in dates}
    return dates, high_m, low_m, close_m, vol_m, index, "test"


def _minimal_replay():
    st = BookState(cash=100_000.0, initial_capital=100_000.0)
    st.session_index = 299
    st.last_session = date(2024, 10, 25)
    return {
        "state": st,
        "trades": [],
        "equity_curve": [{"date": "2024-10-25", "equity": 100_000.0, "cash": 100_000.0, "n_positions": 0}],
    }


def _minimal_ev():
    return {
        "rows": [],
        "market_ok": True,
        "selected": [],
        "orders": [],
        "book_status": "ACTIVE",
        "free_slots": 10,
        "warmup": False,
        "nifty_close": None,
        "nifty_sma50": None,
    }


def _patch_common(run_id):
    locks = SimpleNamespace(
        acquire=AsyncMock(return_value=True),
        release=AsyncMock(),
        start_heartbeat=lambda *a, **kw: None,
    )
    update_run = AsyncMock()
    return {
        "lock": locks,
        "update_run": update_run,
        "run_id": run_id,
    }



def _apply_common_mocks(ctx, replay_fn=None, ev_fn=None, build_payload_fn=None):
    locks = ctx["lock"]
    update_run = ctx["update_run"]
    replay_fn = replay_fn or _minimal_replay
    ev_fn = ev_fn or _minimal_ev
    build_payload_fn = build_payload_fn or (lambda **kw: {"status": "completed", "recommendations_final": True})

    mats = _minimal_matrices()

    def _fake_replay_book(*args, **kwargs):
        return replay_fn()

    return [
        patch.object(scan_service, "DistributedLockService", return_value=locks),
        patch.object(scan_service.persistence, "update_run", update_run),
        patch.object(scan_service.persistence, "save_latest", AsyncMock()),
        patch.object(scan_service.persistence, "save_book_state", AsyncMock()),
        patch.object(scan_service, "UniverseService", SimpleNamespace(
            get_active_nifty500_symbols=AsyncMock(return_value=["AAA-EQ"]),
            get_company_name_map=AsyncMock(return_value={}),
            get_company_name_map_sync=lambda: {},
        )),
        patch.object(scan_service, "evaluate_freshness", AsyncMock(return_value=_ok_freshness())),
        patch.object(scan_service, "_load_matrices", AsyncMock(return_value=mats)),
        patch.object(scan_service, "overlay_current_session", AsyncMock(
            return_value=(mats[0], mats[1], mats[2], mats[3], mats[4], mats[5], "live")
        )),
        patch.object(scan_service, "replay_book", _fake_replay_book),
        patch.object(scan_service, "evaluate_session", lambda **kw: ev_fn()),
        patch.object(scan_service, "build_payload", build_payload_fn),
    ]


def _run_with_mocks(mocks, coro):
    for m in mocks:
        m.start()
    try:
        return asyncio.run(coro)
    finally:
        for m in mocks:
            m.stop()


def test_portfolio_backtest_clears_stale_stock_progress():
    run_id = uuid.uuid4()
    ctx = _patch_common(run_id)
    mocks = _apply_common_mocks(ctx)

    result = _run_with_mocks(mocks, run_scan(scan_id=run_id))

    assert result.get("status") == "completed"
    # Find the update_run call that set stage="backtesting".
    backtest_calls = [
        c for c in ctx["update_run"].await_args_list
        if c.kwargs.get("stage") == "backtesting"
    ]
    assert backtest_calls, "backtesting stage update was never emitted"
    meta = backtest_calls[0].kwargs.get("progress_meta") or {}
    assert meta.get("phase") == "portfolio_backtest"
    assert meta.get("current_symbol") is None
    assert meta.get("processed_count") is None
    assert meta.get("total_count") is None
    # Lock always released.
    ctx["lock"].release.assert_awaited()


def test_portfolio_backtest_timeout_fails_safely_and_releases_lock():
    run_id = uuid.uuid4()
    ctx = _patch_common(run_id)

    def _slow_replay(*args, **kwargs):
        time.sleep(3)
        return _minimal_replay()

    mats = _minimal_matrices()
    mocks = [
        patch.object(scan_service, "DistributedLockService", return_value=ctx["lock"]),
        patch.object(scan_service.persistence, "update_run", ctx["update_run"]),
        patch.object(scan_service.persistence, "save_latest", AsyncMock()),
        patch.object(scan_service.persistence, "save_book_state", AsyncMock()),
        patch.object(scan_service, "UniverseService", SimpleNamespace(
            get_active_nifty500_symbols=AsyncMock(return_value=["AAA-EQ"]),
            get_company_name_map=AsyncMock(return_value={}),
            get_company_name_map_sync=lambda: {},
        )),
        patch.object(scan_service, "evaluate_freshness", AsyncMock(return_value=_ok_freshness())),
        patch.object(scan_service, "_load_matrices", AsyncMock(return_value=mats)),
        patch.object(scan_service, "overlay_current_session", AsyncMock(
            return_value=(mats[0], mats[1], mats[2], mats[3], mats[4], mats[5], "live")
        )),
        patch.object(scan_service, "replay_book", _slow_replay),
        patch.object(scan_service.settings, "w52_portfolio_backtest_timeout_seconds", 1),
    ]

    result = _run_with_mocks(mocks, run_scan(scan_id=run_id))

    assert result.get("status") == "failed"
    assert result.get("error_code") == "W52_SCAN_TIMEOUT"
    # The run row must be marked finished/failed, not left RUNNING.
    fail_calls = [
        c for c in ctx["update_run"].await_args_list
        if c.kwargs.get("status") == "failed"
    ]
    assert any(c.kwargs.get("error_code") == "W52_SCAN_TIMEOUT" for c in fail_calls)
    assert any(c.kwargs.get("finished") is True for c in fail_calls)
    ctx["lock"].release.assert_awaited()
