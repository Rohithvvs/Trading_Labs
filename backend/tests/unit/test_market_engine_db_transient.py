"""Market engine must retry transient DB connect timeouts without hard DOWN alerts."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.market_engine_service import (
    MarketEngineService,
    _is_transient_db_error,
    _DB_TRANSIENT_ALERT_AFTER,
)


def test_timeout_is_transient():
    assert _is_transient_db_error(TimeoutError()) is True
    assert _is_transient_db_error(asyncio.TimeoutError()) is True
    assert _is_transient_db_error(ConnectionError("refused")) is True
    assert _is_transient_db_error(RuntimeError("connection is closed")) is True
    assert _is_transient_db_error(
        RuntimeError("SSL connection has been closed unexpectedly")
    ) is True
    assert _is_transient_db_error(ValueError("business logic")) is False
    assert _is_transient_db_error(asyncio.CancelledError()) is False


def test_auto_exit_isolated_retries_ssl_then_succeeds():
    """Transient SSL drops mid-exit must retry with a fresh sync session."""
    svc = MarketEngineService()
    calls = {"n": 0}

    def _flaky(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("SSL connection has been closed unexpectedly")
        return "ok"

    with (
        patch(
            "app.services.market_engine_service.SessionLocal"
        ) as mock_session_cm,
        patch(
            "app.services.market_engine_service.PaperTradingService"
        ) as mock_pts,
        patch("time.sleep"),
    ):
        mock_session_cm.return_value.__enter__.return_value = MagicMock()
        mock_session_cm.return_value.__exit__.return_value = False
        mock_pts.return_value.auto_exit.side_effect = _flaky

        result = svc._auto_exit_isolated(5122, 100.0, "STOPLOSS_HIT", "RECONCILIATION")

    assert result == "ok"
    assert calls["n"] == 2
    assert mock_session_cm.call_count == 2


def test_auto_exit_isolated_does_not_retry_value_error():
    svc = MarketEngineService()
    with (
        patch(
            "app.services.market_engine_service.SessionLocal"
        ) as mock_session_cm,
        patch(
            "app.services.market_engine_service.PaperTradingService"
        ) as mock_pts,
    ):
        mock_session_cm.return_value.__enter__.return_value = MagicMock()
        mock_session_cm.return_value.__exit__.return_value = False
        mock_pts.return_value.auto_exit.side_effect = ValueError("Position not found.")

        with pytest.raises(ValueError, match="Position not found"):
            svc._auto_exit_isolated(5122, 100.0, "STOPLOSS_HIT", "RECONCILIATION")

    assert mock_session_cm.call_count == 1


@pytest.mark.anyio
async def test_run_loop_retries_connect_timeout_without_immediate_down_alert():
    svc = MarketEngineService()
    svc._running = True

    # First two iterations: connect timeout; third: stop the loop.
    calls = {"n": 0}

    class _BoomCM:
        async def __aenter__(self):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise TimeoutError()
            # Stop after recovery path would run — raise CancelledError-like stop
            svc._running = False
            raise TimeoutError()  # still transient; loop exits via _running

        async def __aexit__(self, *args):
            return False

    with (
        patch(
            "app.services.market_engine_service.AsyncSessionLocal",
            side_effect=lambda: _BoomCM(),
        ),
        patch(
            "app.services.market_engine_service.dispose_async_pool",
            new_callable=AsyncMock,
        ) as dispose_mock,
        patch.object(svc.logger, "error") as log_error,
        patch.object(svc.logger, "warning") as log_warning,
        patch("app.services.market_engine_service.asyncio.sleep", new_callable=AsyncMock),
    ):
        await svc._run_loop()

    # Transient warnings logged; no PRODUCTION_ALERT on only 3 consecutive (threshold 5)
    assert any(
        "MARKET_ENGINE_DB_TRANSIENT" in str(c)
        for c in (call.args[0] if call.args else "" for call in log_warning.call_args_list)
    )
    down_alerts = [
        c
        for c in log_error.call_args_list
        if c.args and "MARKET_ENGINE_DOWN" in str(c.args[0])
    ]
    assert down_alerts == []
    assert calls["n"] == 3
    assert svc._consecutive_db_failures == 3
    # Dispose every 3 failures
    assert dispose_mock.await_count >= 1


@pytest.mark.anyio
async def test_run_loop_alerts_after_sustained_failures():
    svc = MarketEngineService()
    svc._running = True
    svc._consecutive_db_failures = _DB_TRANSIENT_ALERT_AFTER - 1

    class _BoomCM:
        async def __aenter__(self):
            svc._running = False  # one more failure then stop
            raise TimeoutError("connect timed out")

        async def __aexit__(self, *args):
            return False

    with (
        patch(
            "app.services.market_engine_service.AsyncSessionLocal",
            side_effect=lambda: _BoomCM(),
        ),
        patch(
            "app.services.market_engine_service.dispose_async_pool",
            new_callable=AsyncMock,
        ),
        patch.object(svc.logger, "error") as log_error,
        patch("app.services.market_engine_service.asyncio.sleep", new_callable=AsyncMock),
    ):
        await svc._run_loop()

    assert any(
        c.args and "MARKET_ENGINE_DOWN" in str(c.args[0])
        for c in log_error.call_args_list
    )
    assert svc._consecutive_db_failures >= _DB_TRANSIENT_ALERT_AFTER


def test_pending_rollback_is_transient():
    from sqlalchemy.exc import PendingRollbackError

    assert _is_transient_db_error(
        PendingRollbackError(
            "Can't reconnect until invalid transaction is rolled back.",
            None,
            None,
        )
    ) is True
    assert (
        _is_transient_db_error(
            RuntimeError(
                "Can't reconnect until invalid transaction is rolled back."
            )
        )
        is True
    )


@pytest.mark.anyio
async def test_reconcile_exit_uses_isolated_session_only():
    """Reconciliation must exit via a fresh sync session — never db.run_sync.

    Regression: sharing the async txn with auto_exit caused PendingRollbackError
    spam when the connection was already invalid (ANANDRATHI position 5233).
    """
    from datetime import datetime, timedelta, timezone
    from unittest.mock import MagicMock

    from app.models.paper_trading import PaperPosition

    svc = MarketEngineService()
    t0 = datetime(2026, 8, 11, 3, 0, tzinfo=timezone.utc)
    pos = PaperPosition(
        id=5233,
        symbol="ANANDRATHI",
        status="OPEN",
        target=200.0,
        stop_loss=100.0,
        created_at=t0,
        last_evaluated_at=t0,
        last_reconciled_at=t0,
    )

    class MockCandle:
        def __init__(self, ts, h, l):
            self.timestamp = ts
            self.high = h
            self.low = l

    # Two stop-breaching candles — must attempt exit only once.
    candles = [
        MockCandle(t0 + timedelta(minutes=i), 150.0, 90.0) for i in range(2)
    ]

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    mock_db.bind.dialect.name = "postgresql"
    mock_db.run_sync = AsyncMock()
    mock_db.commit = AsyncMock()

    isolated = MagicMock(return_value=None)

    with (
        patch(
            "app.services.market_engine_service.AsyncSessionLocal"
        ) as mock_session_cm,
        patch.object(svc.fyers, "fetch_ohlcv", new_callable=AsyncMock) as fetch,
        patch.object(svc, "_auto_exit_isolated", isolated),
    ):
        mock_session_cm.return_value.__aenter__.return_value = mock_db
        mock_session_cm.return_value.__aexit__.return_value = False
        fetch.return_value = candles

        await svc._reconcile_ohlcv_sequence(5233)

    isolated.assert_called_once_with(
        5233, 90.0, "STOPLOSS_HIT", "RECONCILIATION"
    )
    # Must never auto_exit through the shared async session
    mock_db.run_sync.assert_not_called()


@pytest.mark.anyio
async def test_reconcile_exit_stops_candle_loop_when_isolated_exit_fails():
    from datetime import datetime, timedelta, timezone
    from unittest.mock import MagicMock

    from app.models.paper_trading import PaperPosition

    svc = MarketEngineService()
    t0 = datetime(2026, 8, 11, 3, 0, tzinfo=timezone.utc)
    pos = PaperPosition(
        id=5233,
        symbol="ANANDRATHI",
        status="OPEN",
        target=200.0,
        stop_loss=100.0,
        created_at=t0,
        last_evaluated_at=t0,
        last_reconciled_at=t0,
    )

    class MockCandle:
        def __init__(self, ts, h, l):
            self.timestamp = ts
            self.high = h
            self.low = l

    candles = [
        MockCandle(t0 + timedelta(minutes=i), 150.0, 90.0) for i in range(5)
    ]

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    mock_db.bind.dialect.name = "postgresql"
    mock_db.run_sync = AsyncMock()
    mock_db.commit = AsyncMock()

    isolated = MagicMock(side_effect=RuntimeError("db down"))

    with (
        patch(
            "app.services.market_engine_service.AsyncSessionLocal"
        ) as mock_session_cm,
        patch.object(svc.fyers, "fetch_ohlcv", new_callable=AsyncMock) as fetch,
        patch.object(svc, "_auto_exit_isolated", isolated),
    ):
        mock_session_cm.return_value.__aenter__.return_value = mock_db
        mock_session_cm.return_value.__aexit__.return_value = False
        fetch.return_value = candles

        await svc._reconcile_ohlcv_sequence(5233)

    # One attempt + break — not 5 retries across candles
    isolated.assert_called_once()
    mock_db.run_sync.assert_not_called()
