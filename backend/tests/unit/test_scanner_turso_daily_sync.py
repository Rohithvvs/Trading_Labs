"""Once-per-day Turso candle sync for Run Scanner.

The clock is frozen. No test opens Turso Cloud, FYERS, or Postgres.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.config.settings import settings
from app.db.turso import InMemoryTursoClient
from app.services.market_data_ingestion import turso_repository
from app.services.market_data_ingestion.scanner_turso_sync import (
    TursoSyncError,
    apply_candle_schema,
    ensure_scanner_turso_sync,
    plan_scanner_candle_sync,
    prepare_sync_rows,
)
from app.services.market_data_ingestion.turso_repository import upsert_daily_rows, upsert_index_rows

IST = ZoneInfo("Asia/Kolkata")
INDEX = settings.strategy_index_store_symbol
FLOOR = date(2026, 10, 1)
OCT5 = date(2026, 10, 5)


def _ist(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)


def _bar(day: date, symbol: str, *, high: float = 110.0, low: float = 90.0, source: str = "FYERS") -> dict:
    return {
        "trade_date": day,
        "symbol": symbol,
        "open": 100.0,
        "high": high,
        "low": low,
        "close": 105.0,
        "volume": 1000,
        "source": source,
    }


@pytest.fixture
def memory_turso(monkeypatch):
    client = InMemoryTursoClient()
    apply_candle_schema(client)
    monkeypatch.setattr(turso_repository, "_client", lambda: client)
    monkeypatch.setattr(
        "app.services.market_data_ingestion.history_backend.uses_turso",
        lambda: True,
    )

    def _boom(*_args, **_kwargs):
        raise AssertionError("postgres session opened")

    monkeypatch.setattr(
        "app.services.market_data_ingestion.repository.AsyncSessionLocal",
        _boom,
    )
    monkeypatch.setattr("app.services.market_data_service.AsyncSessionLocal", _boom)
    upsert_daily_rows(
        client,
        [_bar(FLOOR, "INFY-EQ"), _bar(FLOOR, "TCS-EQ")],
    )
    upsert_index_rows(client, [_bar(FLOOR, INDEX)])
    return client


def _counts(client: InMemoryTursoClient, day: date, symbol: str | None = None) -> int:
    if symbol is None:
        rows = client.execute(
            "SELECT COUNT(*) AS n FROM daily_ohlcv WHERE trade_date = ?",
            [day.isoformat()],
        )
    else:
        rows = client.execute(
            "SELECT COUNT(*) AS n FROM daily_ohlcv WHERE trade_date = ? AND symbol = ?",
            [day.isoformat(), symbol],
        )
    return int(rows[0]["n"])


def test_plan_fetches_only_the_missing_session_after_the_floor():
    after_close = plan_scanner_candle_sync(_ist(OCT5, 16), FLOOR, FLOOR)
    assert after_close["history_days"] == [OCT5]
    assert after_close["live_session"] is None
    assert after_close["required_state"] == "eod"
    assert date(2026, 10, 2) not in after_close["history_days"]
    assert date(2026, 10, 3) not in after_close["history_days"]
    assert date(2026, 10, 4) not in after_close["history_days"]

    during = plan_scanner_candle_sync(_ist(OCT5, 10), FLOOR, FLOOR, live_bars_on_completed=700)
    assert during["history_days"] == []
    assert during["live_session"] == OCT5
    assert during["required_state"] == "live"
    assert during["completed_target"] == FLOOR
    assert during["replace_existing"] is False

    holiday = plan_scanner_candle_sync(_ist(date(2026, 10, 2), 16), FLOOR, FLOOR)
    weekend = plan_scanner_candle_sync(_ist(date(2026, 10, 4), 16), FLOOR, FLOOR)
    assert holiday["history_days"] == []
    assert holiday["live_session"] is None
    assert holiday["completed_target"] == FLOOR
    assert weekend["history_days"] == []
    assert weekend["completed_target"] == FLOOR

    before_open = plan_scanner_candle_sync(_ist(date(2026, 10, 6), 8), OCT5, OCT5)
    assert before_open["history_days"] == []
    assert before_open["required_state"] == "current"
    assert before_open["satisfy_session"] == OCT5

    replace = plan_scanner_candle_sync(_ist(OCT5, 16), OCT5, OCT5, live_bars_on_completed=10)
    assert replace["history_days"] == [OCT5]
    assert replace["replace_existing"] is True


def test_prepare_sync_rows_drops_invalid_weekend_and_holiday_bars():
    rows = [
        _bar(OCT5, "INFY-EQ", high=80.0, low=90.0),
        _bar(date(2026, 10, 3), "INFY-EQ"),
        _bar(date(2026, 10, 2), "INFY-EQ"),
        _bar(OCT5, "INFY-EQ", source="historical_candles"),
        _bar(OCT5, "INFY-EQ"),
        _bar(OCT5, "INFY-EQ", high=111.0),
    ]
    accepted, calendar_rejected, invalid = prepare_sync_rows(rows, allowed_sessions={OCT5})
    assert len(accepted) == 1
    assert accepted[0]["symbol"] == "INFY-EQ"
    assert accepted[0]["high"] == 111.0
    assert len(calendar_rejected) == 2
    assert invalid


@pytest.mark.asyncio
async def test_first_scan_syncs_and_later_scans_reuse_the_same_day(memory_turso):
    calls = {"history": 0}

    async def fetch_history(symbols, start, end):
        calls["history"] += 1
        assert start == OCT5 and end == OCT5
        rows = []
        for symbol in symbols:
            rows.append(_bar(date(2026, 10, 3), symbol))
            rows.append(_bar(date(2026, 10, 2), symbol))
            rows.append(_bar(OCT5, symbol, high=80.0, low=90.0))
            rows.append(_bar(OCT5, symbol))
            rows.append(_bar(OCT5, symbol))
        return rows, []

    async def fetch_index(start, end):
        assert start == OCT5 and end == OCT5
        return [
            _bar(date(2026, 10, 3), INDEX),
            _bar(date(2026, 10, 2), INDEX),
            _bar(OCT5, INDEX),
        ]

    async def fetch_quotes(symbols, session):
        raise AssertionError("quotes are not the post-close sync")

    now = _ist(OCT5, 16)
    first = await ensure_scanner_turso_sync(
        ["INFY", "TCS"],
        strategy="momentum",
        now=now,
        fetch_history=fetch_history,
        fetch_index=fetch_index,
        fetch_quotes=fetch_quotes,
        poll_s=0.02,
    )
    assert first["backend"] == "turso"
    assert first["sync_status"] == "completed"
    assert first["reused"] is False
    assert first["latest_equity_date"] == OCT5.isoformat()
    assert first["latest_index_date"] == OCT5.isoformat()
    assert first["symbols_processed"] == 2
    assert first["symbols_updated"] == 2
    assert calls["history"] == 1
    assert _counts(memory_turso, OCT5, "INFY-EQ") == 1
    assert _counts(memory_turso, date(2026, 10, 2)) == 0
    assert _counts(memory_turso, date(2026, 10, 3)) == 0
    stored = memory_turso.execute(
        "SELECT source FROM daily_ohlcv WHERE trade_date = ? AND symbol = ?",
        [OCT5.isoformat(), "INFY-EQ"],
    )
    assert stored[0]["source"] == "FYERS"

    second = await ensure_scanner_turso_sync(
        ["INFY", "TCS"],
        strategy="momentum",
        now=now,
        fetch_history=fetch_history,
        fetch_index=fetch_index,
        fetch_quotes=fetch_quotes,
        poll_s=0.02,
    )
    assert second["sync_status"] == "reused"
    assert second["reused"] is True
    assert calls["history"] == 1

    for strategy in ("12-1", "vcp"):
        report = await ensure_scanner_turso_sync(
            ["INFY", "TCS"],
            strategy=strategy,
            now=now,
            fetch_history=fetch_history,
            fetch_index=fetch_index,
            fetch_quotes=fetch_quotes,
            poll_s=0.02,
        )
        assert report["sync_status"] == "reused"
    assert calls["history"] == 1
    row = memory_turso.execute("SELECT status, backend, bar_state FROM candle_sync_day")
    assert row == [{"status": "completed", "backend": "turso", "bar_state": "eod"}]


@pytest.mark.asyncio
async def test_concurrent_scanner_clicks_run_one_sync(memory_turso):
    calls = {"history": 0}

    async def fetch_history(symbols, start, end):
        calls["history"] += 1
        await asyncio.sleep(0.05)
        return [_bar(OCT5, symbol) for symbol in symbols], []

    async def fetch_index(start, end):
        return [_bar(OCT5, INDEX)]

    async def fetch_quotes(symbols, session):
        raise AssertionError("quotes are not the post-close sync")

    now = _ist(OCT5, 16)
    reports = await asyncio.gather(
        ensure_scanner_turso_sync(
            ["INFY", "TCS"],
            strategy="momentum",
            now=now,
            fetch_history=fetch_history,
            fetch_index=fetch_index,
            fetch_quotes=fetch_quotes,
            poll_s=0.02,
        ),
        ensure_scanner_turso_sync(
            ["INFY", "TCS"],
            strategy="vcp",
            now=now,
            fetch_history=fetch_history,
            fetch_index=fetch_index,
            fetch_quotes=fetch_quotes,
            poll_s=0.02,
        ),
    )
    assert calls["history"] == 1
    assert {item["sync_status"] for item in reports} == {"completed", "reused"}
    assert _counts(memory_turso, OCT5) == 2


@pytest.mark.asyncio
async def test_morning_quote_is_reused_then_replaced_after_the_close(memory_turso):
    calls = {"quotes": 0, "history": 0}

    async def fetch_quotes(symbols, session):
        calls["quotes"] += 1
        assert session == OCT5
        return [_bar(session, symbol, source="FYERS_LIVE_1D") for symbol in symbols], [], []

    async def fetch_history(symbols, start, end):
        calls["history"] += 1
        return [_bar(OCT5, symbol, source="FYERS") for symbol in symbols], []

    async def fetch_index(start, end):
        return [_bar(OCT5, INDEX, source="FYERS")]

    morning = _ist(OCT5, 10)
    first = await ensure_scanner_turso_sync(
        ["INFY", "TCS"],
        strategy="momentum",
        now=morning,
        fetch_history=fetch_history,
        fetch_index=fetch_index,
        fetch_quotes=fetch_quotes,
        poll_s=0.02,
    )
    assert first["sync_status"] == "completed"
    assert calls["quotes"] == 1
    assert calls["history"] == 0
    live = memory_turso.execute(
        "SELECT source FROM daily_ohlcv WHERE trade_date = ?",
        [OCT5.isoformat()],
    )
    assert {row["source"] for row in live} == {"FYERS_LIVE_1D"}

    second = await ensure_scanner_turso_sync(
        ["TCS", "INFY"],
        strategy="12-1",
        now=morning,
        fetch_history=fetch_history,
        fetch_index=fetch_index,
        fetch_quotes=fetch_quotes,
        poll_s=0.02,
    )
    assert second["sync_status"] == "reused"
    assert calls["quotes"] == 1

    afternoon = await ensure_scanner_turso_sync(
        ["INFY", "TCS"],
        strategy="vcp",
        now=_ist(OCT5, 16),
        fetch_history=fetch_history,
        fetch_index=fetch_index,
        fetch_quotes=fetch_quotes,
        poll_s=0.02,
    )
    assert afternoon["sync_status"] == "completed"
    assert afternoon["reused"] is False
    assert calls["history"] == 1
    assert calls["quotes"] == 1
    official = memory_turso.execute(
        "SELECT source FROM daily_ohlcv WHERE trade_date = ?",
        [OCT5.isoformat()],
    )
    assert {row["source"] for row in official} == {"FYERS"}


@pytest.mark.asyncio
async def test_turso_failure_does_not_start_a_scanner_or_open_postgres(memory_turso):
    started = {"scan": False}
    calls = {"history": 0}

    async def fetch_history(symbols, start, end):
        calls["history"] += 1
        await asyncio.sleep(0.05)
        raise RuntimeError("fyers down")

    async def fetch_index(start, end):
        return [_bar(OCT5, INDEX)]

    async def fetch_quotes(symbols, session):
        raise AssertionError("quotes are not the post-close sync")

    async def one(strategy: str):
        try:
            await ensure_scanner_turso_sync(
                ["INFY", "TCS"],
                strategy=strategy,
                now=_ist(OCT5, 16),
                fetch_history=fetch_history,
                fetch_index=fetch_index,
                fetch_quotes=fetch_quotes,
                poll_s=0.02,
            )
        except TursoSyncError:
            return "failed"
        started["scan"] = True
        return "started"

    outcomes = await asyncio.gather(one("momentum"), one("vcp"))
    assert outcomes == ["failed", "failed"]
    assert started["scan"] is False
    assert calls["history"] == 1
    status = memory_turso.execute("SELECT status, backend FROM candle_sync_day")
    assert status == [{"status": "failed", "backend": "turso"}]
    assert _counts(memory_turso, OCT5) == 0


@pytest.mark.asyncio
async def test_daily_reads_come_from_turso_without_postgres(memory_turso):
    from app.services.market_data_service import MarketDataService, candle_session_date

    service = MarketDataService()
    meta = await service.get_candle_meta_batch(["INFY"], "1D")
    assert meta["INFY"][0] == 1
    assert meta["INFY"][2] == "INFY-EQ"
    assert candle_session_date(meta["INFY"][1]) == FLOOR

    frames = await service.load_histories_batch(
        ["INFY"],
        "1D",
        stored_symbol_map={"INFY": meta["INFY"][2]},
        max_bars=60,
    )
    assert list(frames["INFY"]["close"]) == [105.0]
    assert await service.get_candle_count("INFY", "1D") == 1


@pytest.mark.asyncio
async def test_execute_scan_does_not_start_when_turso_sync_fails():
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.schemas import AnalysisMode, ScreenerRequest
    from app.services.market_data_ingestion.scanner_turso_sync import TursoSyncError
    from app.services.scan_execution_service import ScanExecutionService

    started = {"yes": False}

    async def _run(*_args, **_kwargs):
        started["yes"] = True

    lock = MagicMock()
    lock.acquire = AsyncMock(return_value=True)
    lock.release = AsyncMock()
    lock.start_heartbeat = MagicMock()
    lock.worker_id = "t"
    queue: asyncio.Queue = asyncio.Queue()

    with (
        patch("app.services.scan_execution_service.DistributedLockService", return_value=lock),
        patch(
            "app.services.market_data_ingestion.history_backend.uses_turso",
            return_value=True,
        ),
        patch(
            "app.services.strategy_tester.scan_service.load_universe",
            new=AsyncMock(return_value=[{"store_symbol": "INFY-EQ", "symbol": "INFY"}]),
        ),
        patch(
            "app.services.market_data_ingestion.scanner_turso_sync.sync_before_scan",
            new=AsyncMock(side_effect=TursoSyncError("Turso candle sync failed. Scanner was not started.")),
        ),
        patch.object(ScanExecutionService, "_run_scan_task", new=_run),
    ):
        with pytest.raises(TursoSyncError):
            await ScanExecutionService.execute_scan(
                ScreenerRequest(mode=AnalysisMode.swing),
                progress_queue=queue,
                trigger_source="test",
            )

    assert started["yes"] is False
    lock.release.assert_awaited()
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    assert any(event.get("code") == "TURSO_SYNC_FAILED" for event in events)
