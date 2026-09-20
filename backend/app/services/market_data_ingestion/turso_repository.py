"""Turso-backed v1 daily/index OHLCV repository.

Does not import or reuse the Nova/Postgres session. Callers must pass a Turso
client, or rely on connect_turso() only when CANDLE_HISTORY_BACKEND=turso.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any

from ...db.turso import (
    DAILY_UPSERT_SQL,
    INDEX_UPSERT_SQL,
    TursoClient,
    connect_turso,
)
from ...config.settings import settings

_thread_client: TursoClient | None = None


def _iso_date(value: Any) -> str:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)[:10]


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _loaded_at_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def daily_row_params(row: dict[str, Any], *, loaded_at: str | None = None) -> tuple[Any, ...]:
    return (
        _iso_date(row["trade_date"]),
        str(row["symbol"]),
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        int(row.get("volume") or 0),
        row.get("delivery_qty"),
        None if row.get("delivery_pct") is None else float(row["delivery_pct"]),
        None if row.get("turnover") is None else float(row["turnover"]),
        None if row.get("adtv_20") is None else float(row["adtv_20"]),
        row.get("source"),
        loaded_at or row.get("loaded_at") or _loaded_at_now(),
    )


def index_row_params(row: dict[str, Any], *, loaded_at: str | None = None) -> tuple[Any, ...]:
    volume = row.get("volume")
    return (
        _iso_date(row["trade_date"]),
        str(row["symbol"]),
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        None if volume is None else int(volume),
        row.get("source"),
        loaded_at or row.get("loaded_at") or _loaded_at_now(),
    )


def upsert_daily_rows(client: TursoClient, rows: list[dict[str, Any]]) -> int:
    from .source_policy import filter_strategy_store_sources
    from .validators.ohlcv_gate import filter_valid_ohlcv_rows

    sourced, _src = filter_strategy_store_sources(
        rows, table_name="daily_ohlcv", log_context="turso_upsert_daily"
    )
    accepted, _rejected = filter_valid_ohlcv_rows(sourced, log_context="turso_upsert_daily")
    if not accepted:
        return 0
    loaded_at = _loaded_at_now()
    return client.executemany(
        DAILY_UPSERT_SQL, [daily_row_params(r, loaded_at=loaded_at) for r in accepted]
    )


def upsert_index_rows(client: TursoClient, rows: list[dict[str, Any]]) -> int:
    from .source_policy import filter_strategy_store_sources
    from .validators.ohlcv_gate import filter_valid_ohlcv_rows

    sourced, _src = filter_strategy_store_sources(
        rows, table_name="index_ohlcv", log_context="turso_upsert_index"
    )
    accepted, _rejected = filter_valid_ohlcv_rows(sourced, log_context="turso_upsert_index")
    if not accepted:
        return 0
    loaded_at = _loaded_at_now()
    return client.executemany(
        INDEX_UPSERT_SQL, [index_row_params(r, loaded_at=loaded_at) for r in accepted]
    )


def _equity_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": _parse_date(row["trade_date"]),
        "symbol": row["symbol"],
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": int(row.get("volume") or 0),
        "delivery_qty": row.get("delivery_qty"),
        "delivery_pct": None if row.get("delivery_pct") is None else float(row["delivery_pct"]),
        "turnover": None if row.get("turnover") is None else float(row["turnover"]),
        "adtv_20": None if row.get("adtv_20") is None else float(row["adtv_20"]),
    }


def select_equity_history(
    client: TursoClient,
    symbol: str,
    *,
    from_date: date | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT trade_date, symbol, open, high, low, close, volume, "
        "delivery_qty, delivery_pct, turnover, adtv_20 "
        "FROM daily_ohlcv WHERE symbol = ?"
    )
    params: list[Any] = [symbol]
    if from_date is not None:
        sql += " AND trade_date >= ?"
        params.append(_iso_date(from_date))
    sql += " ORDER BY trade_date ASC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    return [_equity_dict(r) for r in client.execute(sql, params)]


def select_index_history(
    client: TursoClient,
    symbol: str = "NIFTY500",
    *,
    from_date: date | None = None,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT trade_date, symbol, open, high, low, close, volume "
        "FROM index_ohlcv WHERE symbol = ?"
    )
    params: list[Any] = [symbol]
    if from_date is not None:
        sql += " AND trade_date >= ?"
        params.append(_iso_date(from_date))
    sql += " ORDER BY trade_date ASC"
    rows = client.execute(sql, params)
    return [
        {
            "trade_date": _parse_date(r["trade_date"]),
            "symbol": r["symbol"],
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": None if r.get("volume") is None else int(r["volume"]),
        }
        for r in rows
    ]


def _client() -> TursoClient:
    global _thread_client
    if _thread_client is None:
        _thread_client = connect_turso(settings)
    return _thread_client


async def fetch_equity_history(
    symbol: str,
    *,
    from_date: date | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        select_equity_history, _client(), symbol, from_date=from_date, limit=limit
    )


async def fetch_index_history(
    symbol: str = "NIFTY500",
    *,
    from_date: date | None = None,
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        select_index_history, _client(), symbol, from_date=from_date
    )


def select_daily_ohlcv_for_symbols(
    client: TursoClient,
    symbols: list[str],
    *,
    lookback: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict[str, Any]]:
    if not symbols:
        return []
    placeholders = ",".join("?" for _ in symbols)
    sql = (
        "SELECT trade_date, symbol, open, high, low, close, volume, "
        "delivery_qty, delivery_pct, turnover, adtv_20 "
        f"FROM daily_ohlcv WHERE symbol IN ({placeholders})"
    )
    params: list[Any] = list(symbols)
    if from_date is not None:
        sql += " AND trade_date >= ?"
        params.append(_iso_date(from_date))
    if to_date is not None:
        sql += " AND trade_date <= ?"
        params.append(_iso_date(to_date))
    sql += " ORDER BY symbol ASC, trade_date ASC"
    rows = [_equity_dict(r) for r in client.execute(sql, params)]
    if lookback is not None and from_date is None:
        by_sym: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_sym.setdefault(row["symbol"], []).append(row)
        trimmed: list[dict[str, Any]] = []
        for sym in symbols:
            trimmed.extend(by_sym.get(sym, [])[-int(lookback) :])
        return trimmed
    return rows


async def fetch_daily_ohlcv_for_symbols(
    symbols: list[str],
    *,
    lookback: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        select_daily_ohlcv_for_symbols,
        _client(),
        symbols,
        lookback=lookback,
        from_date=from_date,
        to_date=to_date,
    )


def select_max_equity_trade_date(
    client: TursoClient, symbols: list[str] | None = None
) -> date | None:
    sql = "SELECT MAX(trade_date) AS m FROM daily_ohlcv"
    params: list[Any] = []
    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        sql += f" WHERE symbol IN ({placeholders})"
        params = list(symbols)
    rows = client.execute(sql, params)
    if rows and rows[0].get("m"):
        return _parse_date(rows[0]["m"])
    return None


async def fetch_max_equity_trade_date(
    symbols: list[str] | None = None,
) -> date | None:
    return await asyncio.to_thread(select_max_equity_trade_date, _client(), symbols)


def select_equity_date_span(
    client: TursoClient, symbol: str
) -> tuple[date | None, date | None, int]:
    rows = client.execute(
        "SELECT MIN(trade_date) AS min_d, MAX(trade_date) AS max_d, COUNT(*) AS cnt "
        "FROM daily_ohlcv WHERE symbol = ?",
        [symbol],
    )
    if rows and rows[0]:
        r = rows[0]
        min_d = _parse_date(r["min_d"]) if r.get("min_d") else None
        max_d = _parse_date(r["max_d"]) if r.get("max_d") else None
        cnt = int(r.get("cnt") or 0)
        return min_d, max_d, cnt
    return None, None, 0


async def fetch_equity_date_span(
    symbol: str,
) -> tuple[date | None, date | None, int]:
    return await asyncio.to_thread(select_equity_date_span, _client(), symbol)


def select_max_index_trade_date(
    client: TursoClient, symbol: str = "NIFTY500"
) -> date | None:
    rows = client.execute(
        "SELECT MAX(trade_date) AS m FROM index_ohlcv WHERE symbol = ?", [symbol]
    )
    if rows and rows[0].get("m"):
        return _parse_date(rows[0]["m"])
    return None


async def fetch_max_index_trade_date(
    symbol: str = "NIFTY500",
) -> date | None:
    return await asyncio.to_thread(select_max_index_trade_date, _client(), symbol)


def select_min_index_trade_date(
    client: TursoClient, symbol: str = "NIFTY500"
) -> date | None:
    rows = client.execute(
        "SELECT MIN(trade_date) AS m FROM index_ohlcv WHERE symbol = ?", [symbol]
    )
    if rows and rows[0].get("m"):
        return _parse_date(rows[0]["m"])
    return None


async def fetch_min_index_trade_date(
    symbol: str = "NIFTY500",
) -> date | None:
    return await asyncio.to_thread(select_min_index_trade_date, _client(), symbol)


def select_index_row_count(
    client: TursoClient, symbol: str = "NIFTY500"
) -> int:
    rows = client.execute(
        "SELECT COUNT(*) AS c FROM index_ohlcv WHERE symbol = ?", [symbol]
    )
    return int(rows[0]["c"]) if rows and rows[0].get("c") is not None else 0


async def fetch_index_row_count(
    symbol: str = "NIFTY500",
) -> int:
    return await asyncio.to_thread(select_index_row_count, _client(), symbol)


def select_symbols_present_on(
    client: TursoClient, trade_date: date, symbols: list[str] | None = None
) -> set[str]:
    sql = "SELECT symbol FROM daily_ohlcv WHERE trade_date = ?"
    params: list[Any] = [_iso_date(trade_date)]
    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        sql += f" AND symbol IN ({placeholders})"
        params.extend(symbols)
    rows = client.execute(sql, params)
    return {str(r["symbol"]) for r in rows if r.get("symbol")}


async def fetch_symbols_present_on(
    trade_date: date, symbols: list[str] | None = None
) -> set[str]:
    return await asyncio.to_thread(
        select_symbols_present_on, _client(), trade_date, symbols
    )


def select_index_present(
    client: TursoClient, trade_date: date, symbol: str = "NIFTY500"
) -> bool:
    rows = client.execute(
        "SELECT 1 FROM index_ohlcv WHERE trade_date = ? AND symbol = ? LIMIT 1",
        [_iso_date(trade_date), symbol],
    )
    return len(rows) > 0


async def fetch_index_present(
    trade_date: date, symbol: str = "NIFTY500"
) -> bool:
    return await asyncio.to_thread(
        select_index_present, _client(), trade_date, symbol
    )


def select_distinct_session_count(client: TursoClient) -> int:
    rows = client.execute("SELECT COUNT(DISTINCT trade_date) AS c FROM daily_ohlcv")
    return int(rows[0]["c"]) if rows and rows[0].get("c") is not None else 0


async def fetch_distinct_session_count() -> int:
    return await asyncio.to_thread(select_distinct_session_count, _client())


def select_recent_equity_before(
    client: TursoClient,
    symbol: str,
    before_date: date,
    limit: int = 19,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT trade_date, symbol, open, high, low, close, volume, "
        "delivery_qty, delivery_pct, turnover, adtv_20 "
        "FROM daily_ohlcv WHERE symbol = ? AND trade_date < ? "
        "ORDER BY trade_date DESC LIMIT ?"
    )
    rows = [
        _equity_dict(r)
        for r in client.execute(sql, [symbol, _iso_date(before_date), int(limit)])
    ]
    rows.reverse()
    return rows


async def fetch_recent_equity_before(
    symbol: str,
    before_date: date,
    limit: int = 19,
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        select_recent_equity_before, _client(), symbol, before_date, limit
    )


def select_symbol_has_sufficient_history(
    client: TursoClient, symbol: str, min_rows: int = 500
) -> bool:
    rows = client.execute(
        "SELECT COUNT(*) AS c FROM daily_ohlcv WHERE symbol = ?", [symbol]
    )
    return int(rows[0]["c"] or 0) >= min_rows if rows else False


async def fetch_symbol_has_sufficient_history(
    symbol: str, min_rows: int = 500
) -> bool:
    return await asyncio.to_thread(
        select_symbol_has_sufficient_history, _client(), symbol, min_rows
    )

