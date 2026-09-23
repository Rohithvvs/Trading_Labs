"""Turso/libSQL client for v1 daily/index candle history.

Does not connect at import. Does not log URLs with credentials or auth tokens.
Operational Postgres sessions must not be used here.
"""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from .turso_schema import load_v1_schema_sql, split_sql_statements
from .urls import public_db_target

_logger = logging.getLogger("app.db.turso")

DAILY_UPSERT_SQL = """
INSERT INTO daily_ohlcv (
    trade_date, symbol, open, high, low, close, volume,
    delivery_qty, delivery_pct, turnover, adtv_20, source, loaded_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(trade_date, symbol) DO UPDATE SET
    open = excluded.open,
    high = excluded.high,
    low = excluded.low,
    close = excluded.close,
    volume = excluded.volume,
    delivery_qty = COALESCE(excluded.delivery_qty, daily_ohlcv.delivery_qty),
    delivery_pct = COALESCE(excluded.delivery_pct, daily_ohlcv.delivery_pct),
    turnover = COALESCE(excluded.turnover, daily_ohlcv.turnover),
    adtv_20 = COALESCE(excluded.adtv_20, daily_ohlcv.adtv_20),
    source = excluded.source,
    loaded_at = excluded.loaded_at
"""

INDEX_UPSERT_SQL = """
INSERT INTO index_ohlcv (
    trade_date, symbol, open, high, low, close, volume, source, loaded_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(trade_date, symbol) DO UPDATE SET
    open = excluded.open,
    high = excluded.high,
    low = excluded.low,
    close = excluded.close,
    volume = excluded.volume,
    source = excluded.source,
    loaded_at = excluded.loaded_at
"""


class TursoClient(Protocol):
    def execute(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        ...

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> int:
        ...

    def close(self) -> None:
        ...


class InMemoryTursoClient:
    """sqlite3 stand-in for unit tests. Never talks to Turso Cloud."""

    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self.closed = False

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        cur = self._conn.execute(sql, tuple(params or ()))
        if cur.description is None:
            self._conn.commit()
            return []
        rows = cur.fetchall()
        self._conn.commit()
        return [dict(r) for r in rows]

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> int:
        cur = self._conn.executemany(sql, list(seq_of_params))
        self._conn.commit()
        return int(cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0)

    def close(self) -> None:
        if not self.closed:
            self._conn.close()
            self.closed = True


class _LibsqlClientAdapter:
    """Thin adapter over libsql-client / libsql. Instantiated only on connect()."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        result = self._inner.execute(sql, list(params or []))
        rows = getattr(result, "rows", None) or getattr(result, "result", None) or []
        columns = list(getattr(result, "columns", None) or [])
        out: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                out.append(row)
            elif columns:
                out.append(dict(zip(columns, row)))
            else:
                out.append({"c0": row})
        return out

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> int:
        params_list = [list(p) for p in seq_of_params]
        if not params_list:
            return 0
        batch = getattr(self._inner, "batch", None)
        if callable(batch):
            try:
                batch([(sql, p) for p in params_list])
                return len(params_list)
            except Exception as exc:
                msg = str(exc).lower()
                if "blocked" in msg or "writes are blocked" in msg:
                    _logger.error("TURSO_WRITES_BLOCKED | %s", exc)
                    raise
                pass
        count = 0
        for p in params_list:
            try:
                self._inner.execute(sql, p)
                count += 1
            except Exception as exc:
                msg = str(exc).lower()
                if "blocked" in msg or "writes are blocked" in msg:
                    _logger.error("TURSO_WRITES_BLOCKED | %s", exc)
                    raise
                raise
        return count

    def close(self) -> None:
        closer = getattr(self._inner, "close", None)
        if callable(closer):
            closer()


def assert_startup_candle_history_config(settings: Any) -> None:
    """Fail closed for turso mode; postgres default does not require Turso creds."""
    backend = settings.candle_history_backend_name()
    if backend != "turso":
        return
    if not settings.turso_configured():
        raise RuntimeError(
            "CANDLE_HISTORY_BACKEND=turso requires TURSO_DATABASE_URL and "
            "TURSO_AUTH_TOKEN. Secret values are never logged."
        )


def log_candle_history_backend(settings: Any) -> None:
    backend = settings.candle_history_backend_name()
    _logger.info(
        "CANDLE_HISTORY_BACKEND | backend=%s | operational_target=%s | "
        "turso_target=%s | turso_token_set=%s",
        backend,
        public_db_target(settings.database_url),
        public_db_target(settings.turso_database_url) if settings.turso_database_url else "(unset)",
        bool((settings.turso_auth_token or "").strip()),
    )


def connect_turso(settings: Any) -> TursoClient:
    """Open a Turso client. Callers must close it. Never logs the token."""
    url = (settings.turso_database_url or "").strip()
    token = (settings.turso_auth_token or "").strip()
    if not url or not token:
        raise RuntimeError(
            "Turso client requested but TURSO_DATABASE_URL or TURSO_AUTH_TOKEN is missing."
        )
    inner = _create_libsql_inner(url, token)
    _logger.info("TURSO_CLIENT_OPEN | target=%s", public_db_target(url))
    return _LibsqlClientAdapter(inner)


def _turso_http_url(url: str) -> str:
    """Prefer HTTPS Hrana HTTP over libsql/wss (Turso cloud often rejects wss 400)."""
    raw = url.strip()
    if raw.startswith("libsql://"):
        return "https://" + raw[len("libsql://") :]
    return raw


_libsql_patched = False


def _patch_libsql_http_client() -> None:
    """Fix upstream bug in libsql_client.http where error responses without 'result' raise KeyError."""
    global _libsql_patched
    if _libsql_patched:
        return
    try:
        import libsql_client.http as libsql_http
        from libsql_client.client import LibsqlError

        orig_send = libsql_http.HttpClient._send

        async def _patched_send(self: Any, method: str, path: str, request_body: Any) -> Any:
            data = await orig_send(self, method, path, request_body)
            if isinstance(data, dict) and "result" not in data:
                if "error" in data:
                    err = data["error"]
                    msg = err.get("message") if isinstance(err, dict) else str(err)
                    code = err.get("code", "ERROR") if isinstance(err, dict) else "ERROR"
                    raise LibsqlError(msg, code)
                if "message" in data:
                    raise LibsqlError(data["message"], data.get("code") or "ERROR")
            return data

        libsql_http.HttpClient._send = _patched_send
        _libsql_patched = True
    except Exception:
        pass


def _create_libsql_inner(url: str, token: str) -> Any:
    http_url = _turso_http_url(url)
    _patch_libsql_http_client()
    try:
        import libsql_client  # type: ignore[import-not-found]

        create = getattr(libsql_client, "create_client_sync", None) or getattr(
            libsql_client, "create_client", None
        )
        if create is None:
            raise RuntimeError("libsql_client has no create_client")
        return create(url=http_url, auth_token=token)
    except ImportError:
        pass
    try:
        import libsql  # type: ignore[import-not-found]

        return libsql.connect(url, auth_token=token)
    except ImportError as exc:
        raise RuntimeError(
            "Turso client libraries are not installed. Add libsql-client to requirements "
            "before connecting. No connection was attempted."
        ) from exc


def apply_v1_schema(client: TursoClient, *, execute: bool) -> dict[str, Any]:
    sql = load_v1_schema_sql()
    statements = split_sql_statements(sql)
    if not execute:
        return {
            "status": "DRY_RUN",
            "statements": len(statements),
            "tables": ["daily_ohlcv", "index_ohlcv"],
            "wrote": False,
        }
    for stmt in statements:
        client.execute(stmt)
    return {
        "status": "APPLIED",
        "statements": len(statements),
        "tables": ["daily_ohlcv", "index_ohlcv"],
        "wrote": True,
    }


def inspect_v1_schema(client: TursoClient) -> dict[str, Any]:
    """Read-only sqlite_master listing. No DML."""
    rows = client.execute(
        "SELECT type, name, tbl_name FROM sqlite_master "
        "WHERE type IN ('table', 'index') AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type, name"
    )
    tables = sorted({r.get("name") for r in rows if r.get("type") == "table"})
    indexes = sorted({r.get("name") for r in rows if r.get("type") == "index"})
    required_tables = ["daily_ohlcv", "index_ohlcv"]
    required_indexes = [
        "idx_daily_ohlcv_symbol_trade_date",
        "idx_daily_ohlcv_trade_date",
        "idx_index_ohlcv_symbol_trade_date",
    ]
    missing_tables = [t for t in required_tables if t not in tables]
    missing_indexes = [i for i in required_indexes if i not in indexes]
    unexpected = [t for t in tables if t in {"historical_candles"}]
    return {
        "wrote": False,
        "tables": tables,
        "indexes": indexes,
        "required_tables_ok": not missing_tables,
        "required_indexes_ok": not missing_indexes,
        "missing_tables": missing_tables,
        "missing_indexes": missing_indexes,
        "unexpected_acs_tables": unexpected,
        "ok": not missing_tables and not missing_indexes and not unexpected,
    }
