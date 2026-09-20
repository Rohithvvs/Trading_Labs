"""Read-only OHLC anomaly listing for local Postgres V1 tables.

Diagnosis only: never clamps, drops, or rewrites bars. Never opens Turso.
Never uses DATABASE_URL. Unit tests inject fetchall and must not use the
default readonly executor.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from ...db.turso_schema import FORBIDDEN_V1_TABLES, V1_TABLES
from ...db.urls import public_db_target
from .turso_source_preflight import (
    FetchAll,
    PreflightError,
    _require_local_source,
    _symbol_where,
    readonly_postgres_fetchall,
)

ANOMALY_LINE = "ANOMALY REPORT COMPLETE — NO DATA WAS WRITTEN"

_INVALID_PREDICATE = (
    "(high < low OR open < low OR open > high OR close < low OR close > high)"
)
_VALID_PREDICATE = (
    "(high >= low AND open >= low AND open <= high AND close >= low AND close <= high)"
)
_DAILY_SELECT = (
    "trade_date, symbol, open, high, low, close, volume, "
    "delivery_qty, delivery_pct, turnover, adtv_20, source, loaded_at"
)
_INDEX_SELECT = "trade_date, symbol, open, high, low, close, volume, source, loaded_at"

EXTERNAL_VERIFICATION = {
    "status": "deferred",
    "provider": "FyersEodProvider.fetch_daily_session",
    "invoked": False,
    "reason": (
        "A read-only FYERS session fetch exists, but this command does not call it. "
        "Bar-by-bar external verification must be done later manually after approval."
    ),
}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _as_date(value: Any) -> str | None:
    raw = _iso(value)
    if not raw:
        return None
    return raw[:10]


def _year(value: Any) -> str | None:
    day = _as_date(value)
    return day[:4] if day else None


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (numerator / denominator) * 100.0


def classify_violations(open_: float, high: float, low: float, close: float) -> tuple[list[str], dict[str, float]]:
    types: list[str] = []
    diffs: dict[str, float] = {}
    if high < low:
        types.append("high_lt_low")
        diffs["high_minus_low"] = high - low
    if open_ < low or open_ > high:
        types.append("open_outside")
        diffs["open_minus_high"] = open_ - high
        diffs["low_minus_open"] = low - open_
    if close < low or close > high:
        types.append("close_outside")
        diffs["close_minus_high"] = close - high
        diffs["low_minus_close"] = low - close
    return types, diffs


def _select_list(table: str) -> str:
    return _DAILY_SELECT if table == "daily_ohlcv" else _INDEX_SELECT


def _neighbor_sql(table: str, *, previous: bool) -> str:
    order = "DESC" if previous else "ASC"
    cmp_op = "<" if previous else ">"
    return (
        f"SELECT {_select_list(table)} FROM {table} "
        f"WHERE symbol = :symbol AND trade_date {cmp_op} :trade_date "
        f"AND {_VALID_PREDICATE} "
        f"ORDER BY trade_date {order} LIMIT 1"
    )


def _row_payload(table: str, row: Mapping[str, Any]) -> dict[str, Any]:
    open_ = _f(row.get("open"))
    high = _f(row.get("high"))
    low = _f(row.get("low"))
    close = _f(row.get("close"))
    types, diffs = classify_violations(open_ or 0.0, high or 0.0, low or 0.0, close or 0.0)
    if open_ is None or high is None or low is None or close is None:
        types = list(types)
    return {
        "table": table,
        "symbol": row.get("symbol"),
        "trade_date": _as_date(row.get("trade_date")),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": row.get("volume"),
        "delivery_qty": row.get("delivery_qty"),
        "delivery_pct": _f(row.get("delivery_pct")),
        "turnover": _f(row.get("turnover")),
        "adtv_20": _f(row.get("adtv_20")),
        "source": row.get("source"),
        "loaded_at": _iso(row.get("loaded_at")),
        "failure_types": types,
        "multiple_violation_types": len(types) > 1,
        "diffs": diffs,
    }


def _attach_neighbors(
    payload: dict[str, Any],
    prev_row: Mapping[str, Any] | None,
    next_row: Mapping[str, Any] | None,
) -> None:
    prev_close = _f(prev_row.get("close")) if prev_row else None
    next_open = _f(next_row.get("open")) if next_row else None
    payload["previous_valid"] = (
        {
            "trade_date": _as_date(prev_row.get("trade_date")),
            "open": _f(prev_row.get("open")),
            "high": _f(prev_row.get("high")),
            "low": _f(prev_row.get("low")),
            "close": prev_close,
            "volume": prev_row.get("volume"),
        }
        if prev_row
        else None
    )
    payload["next_valid"] = (
        {
            "trade_date": _as_date(next_row.get("trade_date")),
            "open": next_open,
            "high": _f(next_row.get("high")),
            "low": _f(next_row.get("low")),
            "close": _f(next_row.get("close")),
            "volume": next_row.get("volume"),
        }
        if next_row
        else None
    )
    payload["previous_close"] = prev_close
    payload["pct_change_prev_close_to_open"] = _pct(
        None if payload["open"] is None or prev_close is None else payload["open"] - prev_close,
        prev_close,
    )
    payload["pct_change_close_to_next_open"] = _pct(
        None if next_open is None or payload["close"] is None else next_open - payload["close"],
        payload["close"],
    )


def _summaries(anomalies: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    def _group(key_fn) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        for row in anomalies:
            counts[str(key_fn(row) or "")] += 1
        return [{"key": k, "count": n} for k, n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]

    type_counts: Counter[str] = Counter()
    for row in anomalies:
        for t in row.get("failure_types") or []:
            type_counts[t] += 1
    return {
        "by_table": _group(lambda r: r.get("table")),
        "by_symbol": _group(lambda r: r.get("symbol")),
        "by_year": _group(lambda r: (_as_date(r.get("trade_date")) or "")[:4]),
        "by_source": _group(lambda r: r.get("source")),
        "by_loaded_at_date": _group(lambda r: (_iso(r.get("loaded_at")) or "")[:10]),
        "by_violation_type": [{"key": k, "count": n} for k, n in sorted(type_counts.items())],
    }


def run_source_anomalies(
    *,
    local_postgres_url: str | None,
    symbols: list[str] | None = None,
    tables: Sequence[str] | None = None,
    limit: int | None = None,
    fetchall: FetchAll | None = None,
) -> dict[str, Any]:
    url = _require_local_source(local_postgres_url)
    requested = tuple(tables or V1_TABLES)
    forbidden = [t for t in requested if t in FORBIDDEN_V1_TABLES]
    if forbidden:
        raise PreflightError(f"v1 anomaly report forbids {forbidden}")
    unknown = [t for t in requested if t not in V1_TABLES]
    if unknown:
        raise PreflightError(f"Unknown v1 tables: {unknown}. Allowed: {list(V1_TABLES)}")
    if fetchall is None:

        def fetchall(sql: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
            return readonly_postgres_fetchall(url, sql, params)

    anomalies: list[dict[str, Any]] = []
    for table in requested:
        where_sql, where_params = _symbol_where(symbols)
        if where_sql:
            invalid_where = f"{where_sql} AND {_INVALID_PREDICATE}"
        else:
            invalid_where = f" WHERE {_INVALID_PREDICATE}"
        sql = (
            f"SELECT {_select_list(table)} FROM {table}{invalid_where} "
            "ORDER BY symbol ASC, trade_date ASC"
        )
        if limit is not None:
            sql += " LIMIT :limit"
            where_params = dict(where_params)
            where_params["limit"] = int(limit)
        rows = fetchall(sql, where_params)
        for row in rows:
            item = _row_payload(table, row)
            prev_rows = fetchall(
                _neighbor_sql(table, previous=True),
                {"symbol": row.get("symbol"), "trade_date": row.get("trade_date")},
            )
            next_rows = fetchall(
                _neighbor_sql(table, previous=False),
                {"symbol": row.get("symbol"), "trade_date": row.get("trade_date")},
            )
            _attach_neighbors(
                item,
                prev_rows[0] if prev_rows else None,
                next_rows[0] if next_rows else None,
            )
            anomalies.append(item)

    return {
        "ok": True,
        "wrote": False,
        "turso_connected": False,
        "mode": "source-anomalies",
        "source_target": public_db_target(url),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "summaries": _summaries(anomalies),
        "filters": {
            "symbols": symbols or [],
            "tables": list(requested),
            "limit": limit,
        },
        "external_verification": dict(EXTERNAL_VERIFICATION),
        "final_line": ANOMALY_LINE,
        "note": "Diagnosis only. No bars were fixed, clamped, dropped, or excluded.",
    }


def format_anomaly_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Source: {payload.get('source_target')}",
        f"Filters: {payload.get('filters')}",
        f"Anomaly rows: {payload.get('anomaly_count')}",
        "Turso: not connected",
        "Wrote: false",
        f"External verification: {payload.get('external_verification', {}).get('status')}",
    ]
    for group_name, rows in (payload.get("summaries") or {}).items():
        lines.append(f"{group_name}: {rows}")
    for item in payload.get("anomalies") or []:
        lines.append(
            f"{item.get('table')} {item.get('symbol')} {item.get('trade_date')} "
            f"OHLC={item.get('open')}/{item.get('high')}/{item.get('low')}/{item.get('close')} "
            f"types={item.get('failure_types')} diffs={item.get('diffs')} "
            f"prev_close={item.get('previous_close')} "
            f"pct_prev={item.get('pct_change_prev_close_to_open')} "
            f"pct_next={item.get('pct_change_close_to_next_open')}"
        )
    lines.append(payload.get("final_line") or ANOMALY_LINE)
    return "\n".join(lines)
