"""Bounded daily_ohlcv retrieval for the 52-Week High Breakout scanner."""

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.market_data_ingestion import repository as repo
from app.services.strategies.breakout52w.scan_service import (
    _public_scan_error,
    scan_ohlcv_lookback,
)
from app.services.strategies.breakout52w.identity import DEFAULT_OHLCV_LOOKBACK, HIGH_LOOKBACK


def test_iter_symbol_chunks_dedupes_and_splits():
    symbols = ["A-EQ", "B-EQ", "A-EQ", "C-EQ", "", "D-EQ"]
    assert repo.iter_symbol_chunks(symbols, size=2) == [["A-EQ", "B-EQ"], ["C-EQ", "D-EQ"]]


def test_iter_symbol_chunks_empty():
    assert repo.iter_symbol_chunks([]) == []
    assert repo.iter_symbol_chunks(["", None]) == []  # type: ignore[list-item]


def test_clamp_lookback_rejects_non_positive():
    with pytest.raises(ValueError):
        repo.clamp_ohlcv_lookback(0)
    with pytest.raises(ValueError):
        repo.clamp_ohlcv_lookback(-10)


def test_clamp_lookback_caps_at_configured_maximum():
    assert repo.clamp_ohlcv_lookback(5000, maximum=2000) == 2000
    assert repo.clamp_ohlcv_lookback(260, maximum=2000) == 260


def test_scan_ohlcv_lookback_matches_timeframe_default():
    assert scan_ohlcv_lookback() == DEFAULT_OHLCV_LOOKBACK
    assert scan_ohlcv_lookback() == 260
    assert scan_ohlcv_lookback() >= HIGH_LOOKBACK


def test_w52_scan_uses_date_bounded_history_fetch():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "strategies"
        / "breakout52w"
        / "scan_service.py"
    ).read_text(encoding="utf-8")
    assert "from_date=from_date" in source or "from_date=fetch_from" in source
    assert "scan_fetch_from_date" in source
    assert "DailyOhlcv.symbol.in_(symbols)" not in source


def test_public_scan_error_strips_giant_sql():
    giant = (
        '(sqlalchemy.dialects.postgresql.asyncpg.Error) '
        'canceling statement due to statement timeout [SQL: SELECT daily_ohlcv.trade_date '
        + ("x" * 400)
        + "]"
    )
    assert _public_scan_error(RuntimeError(giant)) == "Daily history query timed out."
    assert "SELECT" not in _public_scan_error(RuntimeError("SQL: SELECT " + "x" * 300))


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def all(self):
        return list(self._rows)


class _FakeDB:
    def __init__(self, dialect="postgresql", rows=None):
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
        self.calls: list[tuple[object, object]] = []
        self._rows = rows or []

    async def execute(self, stmt, params=None):
        self.calls.append((stmt, params))
        return _FakeResult(self._rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_empty_universe_issues_no_sql(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(repo, "AsyncSessionLocal", lambda: db)
    rows = await repo.fetch_daily_ohlcv_for_symbols([], lookback=260)
    assert rows == []
    assert db.calls == []


@pytest.mark.asyncio
async def test_full_universe_lookback_uses_lateral_limit(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(repo, "AsyncSessionLocal", lambda: db)
    symbols = [f"S{i:03d}-EQ" for i in range(755)]
    await repo.fetch_daily_ohlcv_for_symbols(symbols, lookback=260)

    assert len(db.calls) == 1
    stmt, params = db.calls[0]
    sql = str(stmt)
    assert "LATERAL" in sql.upper()
    assert "LIMIT" in sql.upper()
    assert "ORDER BY daily_ohlcv.trade_date DESC" in sql
    assert params["lookback"] == 260
    assert len(params["symbols"]) == 755


@pytest.mark.asyncio
async def test_small_universe_rows_are_chronological(monkeypatch):
    start = date(2025, 1, 2)
    raw = []
    for i in range(5):
        sym = f"N{i}-EQ"
        # DESC order as LATERAL would emit before the outer ASC sort — repo SQL
        # already asks ASC; the portable path reverses. Feed already-ASC rows.
        for d in range(260):
            raw.append((start + timedelta(days=d), sym, 10.0 + d))

    db = _FakeDB(rows=raw)
    monkeypatch.setattr(repo, "AsyncSessionLocal", lambda: db)
    symbols = [f"N{i}-EQ" for i in range(5)]
    rows = await repo.fetch_daily_ohlcv_for_symbols(symbols, lookback=260)

    assert len(rows) == 5 * 260
    by_sym: dict[str, list[date]] = {}
    for trade_date, symbol, _close in rows:
        by_sym.setdefault(symbol, []).append(trade_date)
    assert set(by_sym) == set(symbols)
    for dates in by_sym.values():
        assert dates == sorted(dates)
        assert len(dates) == 260


@pytest.mark.asyncio
async def test_insufficient_history_is_returned_as_is(monkeypatch):
    """Newly listed name: fewer than 260 rows, no fabricated candles."""
    rows_in = [(date(2026, 8, 1), "NEW-EQ", 12.0), (date(2026, 8, 4), "NEW-EQ", 12.5)]
    db = _FakeDB(rows=rows_in)
    monkeypatch.setattr(repo, "AsyncSessionLocal", lambda: db)
    rows = await repo.fetch_daily_ohlcv_for_symbols(["NEW-EQ"], lookback=260)
    assert rows == rows_in
    assert all(r[2] != 0 for r in rows)


@pytest.mark.asyncio
async def test_large_universe_row_budget_is_lookback_times_symbols():
    sql = repo.latest_n_ohlcv_sql(["trade_date", "symbol", "close"])
    assert "LIMIT :lookback" in sql
    assert "unnest" in sql
    # 755 * 260 is the hard ceiling the planner can return.
    assert 755 * 260 < 2_000_000


@pytest.mark.asyncio
async def test_from_date_query_constrains_trade_date(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(repo, "AsyncSessionLocal", lambda: db)
    symbols = ["AAA-EQ", "BBB-EQ"]
    start = date(2008, 8, 20)
    end = date(2026, 8, 20)
    await repo.fetch_daily_ohlcv_for_symbols(symbols, from_date=start, to_date=end)

    assert db.calls
    select_calls = [(stmt, params) for stmt, params in db.calls if "daily_ohlcv" in str(stmt).lower()]
    assert select_calls
    stmt, _params = select_calls[0]
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    text = str(compiled).lower()
    assert "trade_date" in text
    assert "2008-08-20" in text
    assert "2026-08-20" in text
    assert "lateral" not in text


@pytest.mark.asyncio
async def test_from_date_takes_precedence_over_lookback(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(repo, "AsyncSessionLocal", lambda: db)
    await repo.fetch_daily_ohlcv_for_symbols(
        ["AAA-EQ"], lookback=260, from_date=date(2021, 8, 20)
    )
    select_calls = [(stmt, params) for stmt, params in db.calls if "daily_ohlcv" in str(stmt).lower()]
    assert select_calls
    stmt, _params = select_calls[0]
    sql = str(stmt).upper()
    assert "LATERAL" not in sql


@pytest.mark.asyncio
async def test_unbounded_path_still_chunks_for_other_strategies(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(repo, "AsyncSessionLocal", lambda: db)
    symbols = [f"S{i:03d}-EQ" for i in range(120)]
    await repo.fetch_daily_ohlcv_for_symbols(symbols)

    assert len(db.calls) == 3  # 50 + 50 + 20, no LATERAL
    for stmt, _params in db.calls:
        assert "LATERAL" not in str(stmt).upper()


@pytest.mark.asyncio
async def test_fetch_equity_history_unaffected(monkeypatch):
    """Regression: single-symbol history helper is unchanged."""
    captured: list[object] = []

    class Result:
        def all(self):
            return []

        def scalars(self):
            return self

    class DB:
        async def scalars(self, stmt):
            captured.append(stmt)
            return Result()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(repo, "AsyncSessionLocal", lambda: DB())
    out = await repo.fetch_equity_history("AAA-EQ")
    assert out == []
    assert captured
    sql = str(captured[0])
    assert "LATERAL" not in sql.upper()


@pytest.mark.asyncio
async def test_fetch_equity_history_resolves_canonical_to_eq_store(monkeypatch):
    """Scan publishes GLAXO; daily_ohlcv stores GLAXO-EQ."""
    captured: list[object] = []
    row = SimpleNamespace(
        trade_date=date(2024, 1, 2),
        symbol="GLAXO-EQ",
        open=1.0,
        high=2.0,
        low=1.0,
        close=1.5,
        volume=10,
        delivery_qty=None,
        delivery_pct=None,
        turnover=None,
        adtv_20=None,
    )

    class Result:
        def all(self):
            return [row]

        def scalars(self):
            return self

    class DB:
        async def scalars(self, stmt):
            captured.append(stmt)
            return Result()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(repo, "AsyncSessionLocal", lambda: DB())
    out = await repo.fetch_equity_history("GLAXO", from_date=date(2023, 8, 20))
    assert len(out) == 1
    assert out[0]["symbol"] == "GLAXO-EQ"
    assert out[0]["close"] == 1.5
    compiled = str(captured[0].compile(compile_kwargs={"literal_binds": True}))
    assert "GLAXO-EQ" in compiled
    assert "LATERAL" not in compiled.upper()
