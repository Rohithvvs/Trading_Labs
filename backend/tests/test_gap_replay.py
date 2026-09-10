import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.app.models.paper_trading import (
    PaperTradingAccount,
    PaperPosition,
    PaperTradeHistory,
    ReplaySession,
)
from backend.app.core.gap_replay import (
    SKIP_DB_CONNECTION_CLOSED,
    SKIP_NO_CANDLE_DATA,
    SKIP_NOTHING_TO_REPLAY,
    SKIP_TOKEN_NOT_READY,
    _intraday_points_for_gap,
    run_gap_replay,
    run_startup_gap_replay,
    wait_for_fyers_token,
)
import backend.app.core.server_state as server_state


class Candle:
    def __init__(self, timestamp, open_, high, low, close):
        self.timestamp = timestamp
        self.open = open_
        self.high = high
        self.low = low
        self.close = close


class FakeFyers:
    def __init__(self, candles=None, configured=True):
        self.candles = candles if candles is not None else []
        self.configured = configured
        self.fetch_calls: list[dict] = []

    def _is_fyers_configured(self) -> bool:
        return self.configured

    async def fetch_ohlcv(self, symbol, analysis_mode, interval, lookback_days, allow_mock=False, **kwargs):
        self.fetch_calls.append(
            {
                "symbol": symbol,
                "mode": analysis_mode,
                "interval": interval,
                "lookback_days": lookback_days,
                "allow_mock": allow_mock,
                "max_points": kwargs.get("max_points"),
            }
        )
        return list(self.candles)


class DeferredTokenFyers(FakeFyers):
    def __init__(self, ready_after_checks: int, candles=None):
        super().__init__(candles=candles, configured=False)
        self.ready_after_checks = ready_after_checks
        self.checks = 0

    def _is_fyers_configured(self) -> bool:
        self.checks += 1
        return self.checks > self.ready_after_checks


def write_last_shutdown(tmp_path: Path, last_shutdown: datetime):
    server_state.STATE_FILE = tmp_path / "server_state.json"
    server_state.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with server_state.STATE_FILE.open("w", encoding="utf-8") as fh:
        json.dump({"last_shutdown": last_shutdown.isoformat()}, fh)


async def create_account_and_position(session, symbol="TEST-EQ", target=None, stop_loss=None):
    acc = PaperTradingAccount(name="TestAccount", starting_balance=100000.0, cash_balance=100000.0)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    pos = PaperPosition(
        account_id=acc.id,
        status="OPEN",
        symbol=symbol,
        qty=1,
        avg_entry_price=100.0,
        current_price=100.0,
        target=target,
        stop_loss=stop_loss,
        notes="pytest",
    )
    session.add(pos)
    await session.commit()
    await session.refresh(pos)
    return acc, pos


async def _first(session, model, **filters):
    stmt = select(model)
    for key, value in filters.items():
        stmt = stmt.where(getattr(model, key) == value)
    return (await session.scalars(stmt)).first()


@pytest.mark.asyncio
async def test_target_hit(tmp_path, async_db_session):
    _acc, pos = await create_account_and_position(async_db_session, symbol="TEST-EQ", target=120.0, stop_loss=None)

    now = datetime.now(timezone.utc)
    last_shutdown = now - timedelta(minutes=10)
    write_last_shutdown(tmp_path, last_shutdown)

    c1 = Candle(last_shutdown + timedelta(minutes=2), 101, 103, 100, 102)
    c2 = Candle(last_shutdown + timedelta(minutes=3), 104, 122, 103, 121)

    fake = FakeFyers([c1, c2])
    await run_gap_replay(async_db_session, fake)

    th = await _first(async_db_session, PaperTradeHistory, symbol=pos.symbol)
    assert th is not None, "Trade history should be created on target hit"
    assert th.exit_reason == "TARGET_HIT"
    assert pytest.approx(th.exit_price, rel=1e-5) == 120.0
    assert await _first(async_db_session, PaperPosition, symbol=pos.symbol) is None


@pytest.mark.asyncio
async def test_stoploss_hit(tmp_path, async_db_session):
    acc, pos = await create_account_and_position(async_db_session, symbol="TEST-EQ", target=None, stop_loss=90.0)

    now = datetime.now(timezone.utc)
    last_shutdown = now - timedelta(minutes=10)
    write_last_shutdown(tmp_path, last_shutdown)

    c1 = Candle(last_shutdown + timedelta(minutes=2), 101, 101, 95, 100)
    c2 = Candle(last_shutdown + timedelta(minutes=3), 99, 100, 89, 90)

    fake = FakeFyers([c1, c2])
    await run_gap_replay(async_db_session, fake)

    th = await _first(async_db_session, PaperTradeHistory, symbol=pos.symbol)
    assert th is not None, "Trade history should be created on stoploss hit"
    assert th.exit_reason == "STOPLOSS_HIT"
    assert pytest.approx(th.exit_price, rel=1e-5) == 90.0
    assert await _first(async_db_session, PaperPosition, symbol=pos.symbol) is None


@pytest.mark.asyncio
async def test_both_hit_target_first(tmp_path, async_db_session):
    acc, pos = await create_account_and_position(async_db_session, symbol="TEST-EQ", target=120.0, stop_loss=90.0)

    now = datetime.now(timezone.utc)
    last_shutdown = now - timedelta(minutes=10)
    write_last_shutdown(tmp_path, last_shutdown)

    c_target = Candle(last_shutdown + timedelta(minutes=2), 119, 120, 119, 120)
    c_stop = Candle(last_shutdown + timedelta(minutes=3), 91, 95, 89, 90)

    fake = FakeFyers([c_target, c_stop])
    await run_gap_replay(async_db_session, fake)

    th = await _first(async_db_session, PaperTradeHistory, symbol=pos.symbol)
    assert th is not None, "Trade history should be created when both hits occur"
    assert th.exit_reason == "TARGET_HIT", "Target should win when hit earlier than stoploss"
    assert pytest.approx(th.exit_price, rel=1e-5) == 120.0
    assert await _first(async_db_session, PaperPosition, symbol=pos.symbol) is None


@pytest.mark.asyncio
async def test_defers_when_fyers_token_not_ready(tmp_path, async_db_session):
    await create_account_and_position(async_db_session, symbol="ANANTRAJ")
    write_last_shutdown(tmp_path, datetime.now(timezone.utc) - timedelta(minutes=30))

    fake = FakeFyers(candles=[], configured=False)
    summary = await run_gap_replay(async_db_session, fake)

    assert summary["skipped_reason"] == SKIP_TOKEN_NOT_READY
    assert fake.fetch_calls == []
    replay = (await async_db_session.scalars(select(ReplaySession))).first()
    assert replay is None, "Must not create a COMPLETED/RUNNING session before token is ready"
    assert await _first(async_db_session, PaperPosition, symbol="ANANTRAJ") is not None


@pytest.mark.asyncio
async def test_empty_candles_do_not_complete_replay(tmp_path, async_db_session):
    await create_account_and_position(async_db_session, symbol="ANANTRAJ")
    write_last_shutdown(tmp_path, datetime.now(timezone.utc) - timedelta(minutes=30))

    fake = FakeFyers(candles=[], configured=True)
    summary = await run_gap_replay(async_db_session, fake)

    assert summary["skipped_reason"] == SKIP_NO_CANDLE_DATA
    replay = (await async_db_session.scalars(select(ReplaySession))).first()
    assert replay is not None
    assert replay.status == "FAILED"
    assert await _first(async_db_session, PaperPosition, symbol="ANANTRAJ") is not None


@pytest.mark.asyncio
async def test_requests_enough_one_minute_bars_for_the_gap(tmp_path, async_db_session):
    await create_account_and_position(async_db_session, symbol="INFY-EQ", target=120.0)
    last_shutdown = datetime.now(timezone.utc) - timedelta(hours=5)
    write_last_shutdown(tmp_path, last_shutdown)
    candles = [Candle(last_shutdown + timedelta(minutes=3), 101, 103, 100, 102)]
    fake = FakeFyers(candles)

    await run_gap_replay(async_db_session, fake)

    assert fake.fetch_calls, "expected a 1m history fetch"
    lookback_days = fake.fetch_calls[0]["lookback_days"]
    assert fake.fetch_calls[0]["max_points"] == _intraday_points_for_gap(lookback_days)
    assert fake.fetch_calls[0]["max_points"] >= 400
    assert fake.fetch_calls[0]["interval"] == "1m"


@pytest.mark.asyncio
async def test_nothing_to_replay_skips_without_session(tmp_path, async_db_session):
    write_last_shutdown(tmp_path, datetime.now(timezone.utc) - timedelta(minutes=30))
    summary = await run_gap_replay(async_db_session, FakeFyers())
    assert summary["skipped_reason"] == SKIP_NOTHING_TO_REPLAY
    assert (await async_db_session.scalars(select(ReplaySession))).first() is None


@pytest.mark.asyncio
async def test_wait_for_fyers_token_polls_until_ready():
    fyers = DeferredTokenFyers(ready_after_checks=2)
    ready = await wait_for_fyers_token(fyers, timeout_sec=1.0, poll_sec=0.01)
    assert ready is True
    assert fyers.checks > 2


@pytest.mark.asyncio
async def test_wait_for_fyers_token_times_out():
    fyers = FakeFyers(configured=False)
    ready = await wait_for_fyers_token(fyers, timeout_sec=0.05, poll_sec=0.01)
    assert ready is False


@pytest.mark.asyncio
async def test_startup_replay_retries_after_token_becomes_ready(tmp_path, async_db_session):
    acc, pos = await create_account_and_position(
        async_db_session, symbol="TEST-EQ", target=120.0, stop_loss=None
    )
    last_shutdown = datetime.now(timezone.utc) - timedelta(minutes=10)
    write_last_shutdown(tmp_path, last_shutdown)
    c_target = Candle(last_shutdown + timedelta(minutes=2), 119, 122, 119, 120)
    fyers = DeferredTokenFyers(ready_after_checks=2, candles=[c_target])

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return async_db_session

        async def __aexit__(self, *args):
            return False

    summary = await run_startup_gap_replay(
        _Factory(),
        fyers,
        token_timeout_sec=1.0,
        token_poll_sec=0.01,
        candle_retries=2,
        candle_retry_delay_sec=0.0,
    )
    assert summary.get("skipped_reason") is None
    th = await _first(async_db_session, PaperTradeHistory, symbol=pos.symbol)
    assert th is not None
    assert th.exit_reason == "TARGET_HIT"


def test_intraday_points_cover_full_sessions():
    assert _intraday_points_for_gap(1) == 400
    assert _intraday_points_for_gap(2) == 800


class _ClosedOnExitFactory:
    def __init__(self, session, enter_delay: float = 0.0):
        self.session = session
        self.enter_delay = enter_delay

    def __call__(self):
        return self

    async def __aenter__(self):
        if self.enter_delay:
            await asyncio.sleep(self.enter_delay)
        return self.session

    async def __aexit__(self, *args):
        raise RuntimeError(
            "cannot call Transaction.rollback(): the underlying connection is closed"
        )


@pytest.mark.asyncio
async def test_startup_replay_swallows_closed_connection_on_session_close(
    tmp_path, async_db_session
):
    fyers = FakeFyers(configured=True)
    summary = await run_startup_gap_replay(
        _ClosedOnExitFactory(async_db_session),
        fyers,
        token_timeout_sec=0.0,
        token_poll_sec=0.01,
        candle_retries=1,
        candle_retry_delay_sec=0.0,
    )
    assert summary["skipped_reason"] == SKIP_DB_CONNECTION_CLOSED
    assert any("connection is closed" in w.lower() for w in summary["warnings"])


@pytest.mark.asyncio
async def test_startup_replay_reraises_cancelled_after_closed_connection(
    tmp_path, async_db_session, monkeypatch
):
    fyers = FakeFyers(configured=True)

    async def _slow_replay(*args, **kwargs):
        await asyncio.sleep(60)
        return {
            "gap_start": None,
            "gap_end": None,
            "orders_filled": [],
            "positions_exited": [],
            "warnings": [],
            "skipped_reason": None,
        }

    monkeypatch.setattr("backend.app.core.gap_replay.run_gap_replay", _slow_replay)

    async def _run():
        await run_startup_gap_replay(
            _ClosedOnExitFactory(async_db_session),
            fyers,
            token_timeout_sec=0.0,
            token_poll_sec=0.01,
            candle_retries=1,
            candle_retry_delay_sec=0.0,
        )

    task = asyncio.create_task(_run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_startup_replay_still_raises_non_connection_errors(async_db_session):
    fyers = FakeFyers(configured=True)

    class _BoomFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return async_db_session

        async def __aexit__(self, *args):
            raise ValueError("not a db error")

    with pytest.raises(ValueError, match="not a db error"):
        await run_startup_gap_replay(
            _BoomFactory(),
            fyers,
            token_timeout_sec=0.0,
            token_poll_sec=0.01,
            candle_retries=1,
            candle_retry_delay_sec=0.0,
        )
