"""Once-per-IST-day Turso catch-up for scanner candle history.

The lock and the result live in Turso (`candle_sync_day`), so two Render
instances or two browser tabs share one sync. An in-memory flag is not the
source of truth. Candle reads and writes stay on Turso when
``CANDLE_HISTORY_BACKEND=turso``. Postgres is not opened for those rows.

Only sessions after 2026-10-01 are requested. Weekends, NSE holidays, and
bars that fail the OHLCV gate are not inserted. A forming session is stored
from batched broker quotes. After the cash close, that same quote batch is
stored once as the official daily bar. Per-symbol history is only for older
missing sessions. A 755-name history download is what pinned hosted scans.

A finished day lock is reused only when Turso already holds that session for
this universe. A smaller sync cannot satisfy a later full scan. When the
stored Fyers access token is expired and the headless TOTP login is
configured, the first scan refreshes the token and then fetches.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from ...db.turso_schema import load_sync_schema_sql, load_v1_schema_sql, split_sql_statements

logger = logging.getLogger("app.market_data.scanner_turso_sync")

IST = ZoneInfo("Asia/Kolkata")
SYNC_FLOOR = date(2026, 10, 1)
MIN_COVERED_SYMBOLS = 500
LEASE_SECONDS = 900.0
SCANNER_SYNC_WAIT_S = 900.0
POLL_SECONDS = 0.4
_HISTORY_CONCURRENCY = 6

EquityFetch = Callable[[list[str], date, date], Awaitable[tuple[list[dict[str, Any]], list[str]]]]
IndexFetch = Callable[[date, date], Awaitable[list[dict[str, Any]]]]
QuoteFetch = Callable[[list[str], date], Awaitable[tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]]]


class TursoSyncError(RuntimeError):
    """Candle sync failed. The scanner must not start."""

    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def _safe_failure(exc: BaseException) -> str:
    return (
        f"{type(exc).__name__}: Turso candle sync failed. "
        "Scanner was not started. Postgres was not used."
    )


def _aware(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=IST)
    return now.astimezone(IST)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_moment(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _hours():
    from ..trading_hours_service import TradingHoursService, trading_hours

    return trading_hours if trading_hours is not None else TradingHoursService()


def _is_trading_day(day: date) -> bool:
    return bool(_hours().is_trading_day(datetime(day.year, day.month, day.day)))


def _trading_days(start: date, end: date) -> list[date]:
    if start > end:
        return []
    out: list[date] = []
    cur = start
    while cur <= end:
        if _is_trading_day(cur):
            out.append(cur)
        cur += timedelta(days=1)
    return out


def _gap_after(latest: date | None, completed: date) -> list[date]:
    """Trading sessions after the stored date, never before the sync floor."""
    anchor = latest if latest is not None else SYNC_FLOOR
    if anchor < SYNC_FLOOR:
        anchor = SYNC_FLOOR
    if anchor >= completed:
        return []
    return _trading_days(anchor + timedelta(days=1), completed)


def _session_is_final(session: date, now: datetime) -> bool:
    if session < now.date():
        return True
    if session > now.date():
        return False
    from ..trading_hours_service import CLOSE_TIME

    return now.time() >= CLOSE_TIME


def plan_scanner_candle_sync(
    now: datetime,
    equity_latest: date | None,
    index_latest: date | None,
    *,
    live_bars_on_completed: int = 0,
    completed_symbol_count: int = 0,
    coverage_requirement: int = MIN_COVERED_SYMBOLS,
) -> dict[str, Any]:
    """Decide the missing window. Does not fetch or insert."""
    from ..trading_hours_service import CLOSE_TIME, OPEN_TIME

    now = _aware(now)
    today = now.date()
    from .calendar_utils import expected_last_completed_session

    completed = expected_last_completed_session(now)
    trading_today = _is_trading_day(today)
    market_open = trading_today and OPEN_TIME <= now.time() < CLOSE_TIME
    history = [
        day
        for day in sorted(set(_gap_after(equity_latest, completed)) | set(_gap_after(index_latest, completed)))
        if day > SYNC_FLOOR
    ]
    replace_existing = False
    # Yesterday's live bars are already the history the scan reads. Re-downloading
    # that covered session one symbol at a time held IND-20261006-016 on
    # "Fetching" for five minutes and the page gave up. Same-day after the close
    # still overwrites today's forming print with one quote batch. A thin previous
    # session (under the coverage bar) is still filled.
    previous_covered = (
        completed < today
        and coverage_requirement > 0
        and completed_symbol_count >= coverage_requirement
    )
    if (
        live_bars_on_completed > 0
        and _session_is_final(completed, now)
        and completed > SYNC_FLOOR
        and not previous_covered
    ):
        # A forming print after the sync floor is already stored. The official
        # bar must overwrite it. The floor day itself is not downloaded again.
        if completed not in history:
            history.append(completed)
        history = [day for day in sorted(set(history)) if day > SYNC_FLOOR and _is_trading_day(day)]
        replace_existing = bool(history)
    live_session = today if market_open else None
    if session_closed := (trading_today and now.time() >= CLOSE_TIME):
        required_state = "eod"
        satisfy = completed
    elif live_session is not None:
        required_state = "live"
        satisfy = live_session
    else:
        required_state = "current"
        satisfy = completed
    # After the close, today's bar is one batched quote request. History for
    # every name is what kept IND scans on "Running" for half an hour.
    quote_session = live_session
    if session_closed and completed == today and completed in history:
        history = [day for day in history if day != completed]
        quote_session = completed
    return {
        "today": today,
        "completed_target": completed,
        "history_days": history,
        "live_session": live_session,
        "quote_session": quote_session,
        "replace_existing": replace_existing,
        "required_state": required_state,
        "satisfy_session": satisfy,
        "session_closed": session_closed,
    }


def _reuse_ok(row: dict[str, Any] | None, plan: dict[str, Any]) -> bool:
    if not row or row.get("status") != "completed":
        return False
    target = str(row.get("target_session") or "")
    if target < plan["satisfy_session"].isoformat():
        return False
    need = plan["required_state"]
    have = str(row.get("bar_state") or "")
    if need == "eod":
        return have == "eod"
    if need == "live":
        return have in {"live", "eod"}
    return True


def _universe_is_covered(client: Any, session: date, universe_size: int) -> bool:
    """True when this universe's session is already stored, not merely the newest date."""
    return _session_count(client, session) >= _coverage_requirement(universe_size)


def _lease_held_by_other(row: dict[str, Any] | None, owner: str, now: datetime) -> bool:
    if not row or row.get("status") != "running":
        return False
    if str(row.get("owner") or "") == owner:
        return False
    exp = _parse_moment(row.get("lease_expires_at"))
    return exp is not None and exp > now


def apply_candle_schema(client: Any) -> None:
    """Create the lock table once. Candle tables already use IF NOT EXISTS."""
    try:
        existing = client.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'candle_sync_day'"
        )
    except Exception:
        existing = []
    if existing:
        return
    for sql in (load_v1_schema_sql(), load_sync_schema_sql()):
        for stmt in split_sql_statements(sql):
            client.execute(stmt)


def _owner_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def _read_sync_row(client: Any, sync_date: date) -> dict[str, Any] | None:
    rows = client.execute(
        "SELECT * FROM candle_sync_day WHERE sync_date = ?",
        [sync_date.isoformat()],
    )
    return rows[0] if rows else None


def _we_own_running(row: dict[str, Any] | None, owner: str) -> bool:
    return bool(
        row
        and row.get("status") == "running"
        and str(row.get("owner") or "") == owner
    )


def _claim_sync(
    client: Any,
    sync_date: date,
    owner: str,
    plan: dict[str, Any],
    now: datetime,
    *,
    covered: bool,
) -> tuple[str, dict[str, Any] | None]:
    """Return acquired, completed, or busy.

    The primary key is the lock. Ownership is read back after the write so a
    RETURNING column-name mismatch cannot grant a second sync. A completed row
    that does not cover this universe can be taken over.
    """
    lease = _iso(now + timedelta(seconds=LEASE_SECONDS))
    started = _iso(now)
    client.execute(
        """
        INSERT INTO candle_sync_day (
            sync_date, status, backend, owner, lease_expires_at, started_at
        ) VALUES (?, 'running', 'turso', ?, ?, ?)
        ON CONFLICT(sync_date) DO NOTHING
        """,
        [sync_date.isoformat(), owner, lease, started],
    )
    row = _read_sync_row(client, sync_date)
    if _we_own_running(row, owner):
        return "acquired", row
    if covered and _reuse_ok(row, plan):
        return "completed", row
    if _lease_held_by_other(row, owner, now):
        return "busy", row
    satisfy = plan["satisfy_session"].isoformat()
    required = plan["required_state"]
    covered_flag = 1 if covered else 0
    client.execute(
        """
        UPDATE candle_sync_day
        SET status = 'running',
            backend = 'turso',
            owner = ?,
            lease_expires_at = ?,
            started_at = ?,
            error = NULL
        WHERE sync_date = ?
          AND NOT (
            status = 'running'
            AND COALESCE(owner, '') != ?
            AND COALESCE(lease_expires_at, '') >= ?
          )
          AND NOT (
            status = 'completed'
            AND COALESCE(target_session, '') >= ?
            AND (
                ? = 'current'
                OR (? = 'live' AND COALESCE(bar_state, '') IN ('live', 'eod'))
                OR (? = 'eod' AND COALESCE(bar_state, '') = 'eod')
            )
            AND ? = 1
          )
        """,
        [
            owner,
            lease,
            started,
            sync_date.isoformat(),
            owner,
            _iso(now),
            satisfy,
            required,
            required,
            required,
            covered_flag,
        ],
    )
    row = _read_sync_row(client, sync_date)
    if _we_own_running(row, owner):
        return "acquired", row
    if covered and _reuse_ok(row, plan):
        return "completed", row
    return "busy", row


def _finish_sync(client: Any, sync_date: date, owner: str, fields: dict[str, Any]) -> None:
    client.execute(
        """
        UPDATE candle_sync_day
        SET status = ?,
            backend = 'turso',
            finished_at = ?,
            target_session = ?,
            bar_state = ?,
            latest_equity_date = ?,
            latest_index_date = ?,
            symbols_processed = ?,
            symbols_updated = ?,
            symbols_failed = ?,
            rows_upserted = ?,
            duration_ms = ?,
            error = ?,
            lease_expires_at = ?
        WHERE sync_date = ? AND owner = ?
        """,
        [
            fields["status"],
            fields["finished_at"],
            fields.get("target_session"),
            fields.get("bar_state"),
            fields.get("latest_equity_date"),
            fields.get("latest_index_date"),
            fields.get("symbols_processed"),
            fields.get("symbols_updated"),
            fields.get("symbols_failed"),
            fields.get("rows_upserted"),
            fields.get("duration_ms"),
            fields.get("error"),
            fields.get("lease_expires_at"),
            sync_date.isoformat(),
            owner,
        ],
    )


def _renew_lease(client: Any, sync_date: date, owner: str, now: datetime) -> None:
    client.execute(
        """
        UPDATE candle_sync_day
        SET lease_expires_at = ?
        WHERE sync_date = ? AND owner = ? AND status = 'running'
        """,
        [_iso(now + timedelta(seconds=LEASE_SECONDS)), sync_date.isoformat(), owner],
    )


def _diagnostics(
    *,
    sync_date: date,
    status: str,
    equity: date | None,
    index: date | None,
    processed: int,
    updated: int,
    failed: int,
    duration_ms: int,
    reused: bool,
    rows_upserted: int = 0,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "backend": "turso",
        "sync_date": sync_date.isoformat(),
        "latest_equity_date": equity.isoformat() if equity else None,
        "latest_index_date": index.isoformat() if index else None,
        "latest_nifty500_date": index.isoformat() if index else None,
        "symbols_processed": processed,
        "symbols_updated": updated,
        "symbols_failed": failed,
        "sync_duration_ms": duration_ms,
        "sync_status": status,
        "reused": reused,
        "rows_upserted": rows_upserted,
        "error": error,
    }


def _from_row(row: dict[str, Any], *, reused: bool) -> dict[str, Any]:
    return _diagnostics(
        sync_date=date.fromisoformat(str(row["sync_date"])),
        status="reused" if reused else str(row.get("status") or "completed"),
        equity=date.fromisoformat(row["latest_equity_date"]) if row.get("latest_equity_date") else None,
        index=date.fromisoformat(row["latest_index_date"]) if row.get("latest_index_date") else None,
        processed=int(row.get("symbols_processed") or 0),
        updated=int(row.get("symbols_updated") or 0),
        failed=int(row.get("symbols_failed") or 0),
        duration_ms=int(row.get("duration_ms") or 0),
        reused=reused,
        rows_upserted=int(row.get("rows_upserted") or 0),
        error=row.get("error"),
    )


def _parse_day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def prepare_sync_rows(
    rows: list[dict[str, Any]],
    *,
    allowed_sessions: set[date],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop non-sessions and invalid OHLC. Last row wins for one key.

    Returns (accepted, calendar_rejected, invalid_rejected).
    """
    from .source_policy import filter_strategy_store_sources
    from .validators.ohlcv_gate import filter_valid_ohlcv_rows

    calendar_rejected: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for row in rows:
        day = _parse_day(row.get("trade_date"))
        if day is None or day not in allowed_sessions or not _is_trading_day(day):
            calendar_rejected.append(row)
            continue
        candidates.append({**row, "trade_date": day})
    sourced, source_rejected = filter_strategy_store_sources(
        candidates, table_name="daily_ohlcv", log_context="scanner_turso_sync"
    )
    accepted, invalid = filter_valid_ohlcv_rows(sourced, log_context="scanner_turso_sync")
    deduped: dict[tuple[date, str], dict[str, Any]] = {}
    for row in accepted:
        deduped[(_parse_day(row["trade_date"]), str(row["symbol"]))] = row
    ordered = [deduped[key] for key in sorted(deduped)]
    return ordered, calendar_rejected, list(source_rejected) + list(invalid)


def _coverage_requirement(symbol_count: int) -> int:
    if symbol_count <= 0:
        return MIN_COVERED_SYMBOLS
    return min(MIN_COVERED_SYMBOLS, symbol_count)


def _client():
    from . import turso_repository as turso

    return turso._client()


def _live_bar_count(client: Any, session: date) -> int:
    rows = client.execute(
        """
        SELECT COUNT(*) AS n FROM daily_ohlcv
        WHERE trade_date = ? AND source = 'FYERS_LIVE_1D'
        """,
        [session.isoformat()],
    )
    if not rows:
        return 0
    return int(rows[0].get("n") or 0)


def _session_count(client: Any, session: date) -> int:
    rows = client.execute(
        "SELECT COUNT(*) AS n FROM daily_ohlcv WHERE trade_date = ?",
        [session.isoformat()],
    )
    if not rows:
        return 0
    return int(rows[0].get("n") or 0)


def _read_latest_dates(client: Any) -> tuple[date | None, date | None]:
    """Read max dates on the caller thread. The in-memory client is not shared across threads."""
    from ...config.settings import settings
    from .turso_repository import select_max_equity_trade_date, select_max_index_trade_date

    equity = select_max_equity_trade_date(client)
    index = select_max_index_trade_date(client, settings.strategy_index_store_symbol)
    return equity, index


def _count_landed(client: Any, table: str, rows: list[dict[str, Any]]) -> int:
    found = 0
    for row in rows:
        day = _parse_day(row.get("trade_date"))
        symbol = row.get("symbol")
        if day is None or not symbol:
            continue
        got = client.execute(
            f"SELECT 1 AS ok FROM {table} WHERE trade_date = ? AND symbol = ?",
            [day.isoformat(), str(symbol)],
        )
        if got:
            found += 1
    return found


async def _persist_rows(client: Any, rows: list[dict[str, Any]], *, table: str) -> int:
    """Upsert, then confirm by read. A zero executemany count is not success."""
    if not rows:
        return 0
    if table == "daily_ohlcv":
        from .repository import upsert_daily_bars

        saved, _rejected = await upsert_daily_bars(rows)
    else:
        from .repository import upsert_index_bars

        saved = await upsert_index_bars(rows)
    if saved > 0:
        return len(rows)
    return _count_landed(client, table, rows)


def _broker_session_problem() -> str | None:
    """Why a FYERS refresh cannot run. None means a broker call can be attempted."""
    from ...services.fyers_service import FyersService
    from ...services.token_service import (
        _decode_jwt_expiry,
        _ensure_utc,
        get_current_access_token_sync,
        utc_now,
    )

    if not FyersService().is_fyers_sdk_available():
        return "sdk"
    token, _source = get_current_access_token_sync()
    if not token or not str(token).strip():
        return "missing"
    expiry = _decode_jwt_expiry(token)
    if expiry is not None and _ensure_utc(expiry) <= utc_now():
        return "expired"
    return None


def _headless_refresh_configured() -> bool:
    """True when this process can mint a Fyers access token without a browser login."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    from ...config.settings import settings

    def _val(*names: str, setting: str = "") -> str:
        for name in names:
            raw = os.environ.get(name)
            if raw and str(raw).strip():
                return str(raw).strip()
        if setting:
            return str(getattr(settings, setting, "") or "").strip()
        return ""

    return bool(
        _val("FYERS_TOTP_SECRET", setting="fyers_totp_secret")
        and _val("FYERS_PIN", setting="fyers_pin")
        and _val("FYERS_CLIENT_ID", setting="fyers_client_id")
        and _val("FYERS_APP_ID", setting="fyers_app_id")
        and _val("FYERS_APP_SECRET", "FYERS_SECRET_ID", setting="fyers_secret_id")
    )


async def _refresh_broker_token() -> bool:
    """Mint a new access token and return True only when a broker call can proceed."""
    from ...db.session import AsyncSessionLocal
    from ..token_service import generate_and_persist_fyers_token

    try:
        async with AsyncSessionLocal() as db:
            await generate_and_persist_fyers_token(db)
    except Exception as exc:
        logger.warning("TURSO_SYNC_TOKEN_REFRESH_FAILED | err_type=%s", type(exc).__name__)
        return False
    return _broker_session_problem() is None


async def _resolve_broker_problem() -> str | None:
    """Return why FYERS cannot be called. Refresh an expired login once when configured."""
    problem = _broker_session_problem()
    if problem is None or problem == "sdk":
        return problem
    if not _headless_refresh_configured():
        return problem
    logger.info("TURSO_SYNC_TOKEN_REFRESH | reason=%s", problem)
    refreshed = await _refresh_broker_token()
    if not refreshed:
        return _broker_session_problem() or problem
    return _broker_session_problem()


def _stored_session_covers(
    client: Any,
    session: date,
    index_latest: date | None,
    universe_size: int,
) -> bool:
    """True when Turso already has the last completed session for this universe."""
    if index_latest is None or index_latest < session:
        return False
    return _session_count(client, session) >= _coverage_requirement(universe_size)


def _stored_session_warning(problem: str) -> str:
    if problem == "sdk":
        return (
            "Fyers is unavailable, so today's candles were not refreshed. "
            "The scan is using the last stored session."
        )
    return (
        "Fyers login expired, so today's candles were not refreshed. "
        "The scan is using the last stored session."
    )


def _auth_blocks_scan_message(problem: str) -> str:
    if problem == "sdk":
        return (
            "Fyers is unavailable. Stored candles do not cover the last session, "
            "so the scanner was not started. Postgres was not used."
        )
    return (
        "Fyers login expired. Reconnect Fyers, then click Scan. "
        "Stored candles do not cover the last session, so the scanner was not started. "
        "Postgres was not used."
    )


def _require_broker_session() -> None:
    """Stop before a universe-sized FYERS loop when the session is already expired."""
    from ...services.fyers_service import FyersAuthExpiredError

    if _broker_session_problem():
        raise FyersAuthExpiredError(
            "Fyers access token has expired. Scanner was not started. Postgres was not used."
        )


async def _default_fetch_history(
    symbols: list[str], start: date, end: date
) -> tuple[list[dict[str, Any]], list[str]]:
    from .providers.fyers_eod import FyersEodProvider

    _require_broker_session()
    provider = FyersEodProvider()
    sem = asyncio.Semaphore(_HISTORY_CONCURRENCY)
    failed: list[str] = []
    rows: list[dict[str, Any]] = []

    async def one(symbol: str) -> None:
        async with sem:
            try:
                got = await provider.fetch_daily_range(symbol, start, end)
            except Exception as exc:
                # An expired broker session will fail every symbol. Stop here.
                if "Auth" in type(exc).__name__:
                    raise
                logger.warning(
                    "TURSO_SYNC_HISTORY_SYMBOL_FAILED | symbol=%s | err_type=%s",
                    symbol,
                    type(exc).__name__,
                )
                failed.append(symbol)
                return
            rows.extend(got)

    await asyncio.gather(*(one(symbol) for symbol in symbols))
    return rows, failed


async def _default_fetch_index(start: date, end: date) -> list[dict[str, Any]]:
    from .providers.fyers_eod import FyersEodProvider

    _require_broker_session()
    return await FyersEodProvider().fetch_index_range(start, end)


async def _default_fetch_quotes(
    symbols: list[str], session: date
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    from ...config.settings import settings
    from ...utils.symbol import strategy_daily_symbol
    from ..strategies.breakout52w.session_overlay import fetch_live_session_bars

    _require_broker_session()
    equity, _index_close = await fetch_live_session_bars(symbols)
    rows: list[dict[str, Any]] = []
    for symbol, bar in equity.items():
        rows.append(
            {
                "trade_date": session,
                "symbol": strategy_daily_symbol(symbol),
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "volume": int(bar.get("volume") or 0),
                "source": "FYERS_LIVE_1D",
            }
        )
    got = {row["symbol"] for row in rows}
    failed = [strategy_daily_symbol(symbol) for symbol in symbols if strategy_daily_symbol(symbol) not in got]
    index_rows: list[dict[str, Any]] = []
    try:
        fetched = await _default_fetch_index(session, session)
    except Exception as exc:
        logger.warning("TURSO_SYNC_INDEX_QUOTE_FAILED | err_type=%s", type(exc).__name__)
        fetched = []
    for row in fetched:
        if _parse_day(row.get("trade_date")) != session:
            continue
        index_rows.append({**row, "symbol": settings.strategy_index_store_symbol, "source": "FYERS_LIVE_1D"})
    return rows, index_rows, failed


def _store_symbols(symbols: list[str]) -> list[str]:
    from ...utils.symbol import strategy_daily_symbol

    out: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        stored = strategy_daily_symbol(symbol)
        if stored and stored not in seen:
            seen.add(stored)
            out.append(stored)
    return out


async def ensure_scanner_turso_sync(
    symbols: list[str],
    *,
    strategy: str = "scanner",
    now: datetime | None = None,
    fetch_history: EquityFetch | None = None,
    fetch_index: IndexFetch | None = None,
    fetch_quotes: QuoteFetch | None = None,
    wait_s: float = SCANNER_SYNC_WAIT_S,
    poll_s: float = POLL_SECONDS,
) -> dict[str, Any]:
    """Run today's Turso catch-up, or reuse the finished one.

    Raises TursoSyncError when the catch-up does not finish. Callers must not
    start a scanner after that.
    """
    from .history_backend import uses_turso

    if not uses_turso():
        raise TursoSyncError(
            "CANDLE_HISTORY_BACKEND is not turso. Refusing to sync candle history from Postgres."
        )
    universe = _store_symbols(symbols)
    if not universe:
        raise TursoSyncError("Turso candle sync has no symbols. Scanner was not started.")

    moment = _aware(now or datetime.now(IST))
    sync_day = moment.date()
    owner = _owner_id()
    started = time.perf_counter()
    client = _client()
    apply_candle_schema(client)
    equity_latest, index_latest = _read_latest_dates(client)
    from .calendar_utils import expected_last_completed_session

    completed = expected_last_completed_session(moment)
    live_on_completed = _live_bar_count(client, completed)
    completed_count = _session_count(client, completed)
    plan = plan_scanner_candle_sync(
        moment,
        equity_latest,
        index_latest,
        live_bars_on_completed=live_on_completed,
        completed_symbol_count=completed_count,
        coverage_requirement=_coverage_requirement(len(universe)),
    )

    # Default fetchers talk to FYERS. Refresh an expired login once, then
    # fall back to the last covered session. Do not open Postgres for candles.
    if fetch_history is None and fetch_index is None and fetch_quotes is None:
        problem = await _resolve_broker_problem()
        if problem:
            if _stored_session_covers(client, plan["completed_target"], index_latest, len(universe)):
                report = _diagnostics(
                    sync_date=sync_day,
                    status="stored",
                    equity=equity_latest,
                    index=index_latest,
                    processed=len(universe),
                    updated=0,
                    failed=0,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    reused=True,
                )
                report["auth"] = problem
                report["warning"] = _stored_session_warning(problem)
                _log_report(strategy, report)
                return report
            raise TursoSyncError(_auth_blocks_scan_message(problem))

    deadline = time.monotonic() + max(1.0, float(wait_s))
    while True:
        covered = _universe_is_covered(client, plan["satisfy_session"], len(universe))
        state, row = _claim_sync(client, sync_day, owner, plan, moment, covered=covered)
        if state == "completed" and row is not None and covered:
            report = _from_row(row, reused=True)
            _log_report(strategy, report)
            return report
        if state == "acquired":
            break
        outcome = await _wait_for_owner(
            client, sync_day, plan, deadline, poll_s, universe_size=len(universe)
        )
        if outcome is not None:
            _log_report(strategy, outcome)
            return outcome
        moment = _aware(now or datetime.now(IST))
        if time.monotonic() >= deadline:
            raise TursoSyncError(
                "Timed out waiting for the Turso candle sync already in progress. "
                "Scanner was not started. Postgres was not used."
            )

    try:
        report = await _run_owner_sync(
            client,
            universe,
            sync_day,
            owner,
            plan,
            moment,
            started,
            fetch_history or _default_fetch_history,
            fetch_index or _default_fetch_index,
            fetch_quotes or _default_fetch_quotes,
        )
    except TursoSyncError:
        raise
    except Exception as exc:
        message = _safe_failure(exc)
        _mark_failed(client, sync_day, owner, plan, started, message)
        raise TursoSyncError(message) from exc
    _log_report(strategy, report)
    return report


async def _wait_for_owner(
    client: Any,
    sync_day: date,
    plan: dict[str, Any],
    deadline: float,
    poll_s: float,
    *,
    universe_size: int,
) -> dict[str, Any] | None:
    while time.monotonic() < deadline:
        await asyncio.sleep(max(0.01, poll_s))
        row = _read_sync_row(client, sync_day)
        if _reuse_ok(row, plan) and row is not None:
            if _universe_is_covered(client, plan["satisfy_session"], universe_size):
                return _from_row(row, reused=True)
            # A smaller sync finished this day. The caller must take the lock.
            return None
        if row and row.get("status") == "failed":
            report = _from_row(row, reused=False)
            report["sync_status"] = "failed"
            raise TursoSyncError(
                str(row.get("error") or "Turso candle sync failed. Scanner was not started."),
                report,
            )
        if row and row.get("status") == "running":
            exp = _parse_moment(row.get("lease_expires_at"))
            if exp is not None and exp > datetime.now(timezone.utc):
                continue
        return None
    return None


def _mark_failed(
    client: Any,
    sync_day: date,
    owner: str,
    plan: dict[str, Any],
    started: float,
    message: str,
) -> None:
    now = datetime.now(timezone.utc)
    try:
        equity, index = None, None
        _finish_sync(
            client,
            sync_day,
            owner,
            {
                "status": "failed",
                "finished_at": _iso(now),
                "target_session": plan["satisfy_session"].isoformat(),
                "bar_state": plan["required_state"],
                "latest_equity_date": equity.isoformat() if equity else None,
                "latest_index_date": index.isoformat() if index else None,
                "symbols_processed": 0,
                "symbols_updated": 0,
                "symbols_failed": 0,
                "rows_upserted": 0,
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "error": message[:500],
                "lease_expires_at": _iso(now),
            },
        )
    except Exception as exc:
        logger.error("TURSO_SYNC_FAIL_RECORD | err_type=%s", type(exc).__name__)


async def _run_owner_sync(
    client: Any,
    universe: list[str],
    sync_day: date,
    owner: str,
    plan: dict[str, Any],
    moment: datetime,
    started: float,
    fetch_history: EquityFetch,
    fetch_index: IndexFetch,
    fetch_quotes: QuoteFetch,
) -> dict[str, Any]:
    processed = len(universe)
    updated: set[str] = set()
    failed: set[str] = set()
    rows_upserted = 0
    history_days: list[date] = list(plan["history_days"])
    quote_session: date | None = plan.get("quote_session") or plan.get("live_session")
    official_close = plan.get("required_state") == "eod"

    if history_days:
        _renew_lease(client, sync_day, owner, moment)
        pending = list(universe)
        if not plan["replace_existing"] and len(history_days) == 1:
            present = {
                str(row["symbol"])
                for row in client.execute(
                    "SELECT symbol FROM daily_ohlcv WHERE trade_date = ?",
                    [history_days[-1].isoformat()],
                )
                if row.get("symbol")
            }
            pending = [symbol for symbol in universe if symbol not in present]
        if pending:
            try:
                fetched, fetch_failed = await fetch_history(pending, history_days[0], history_days[-1])
            except Exception as exc:
                message = _safe_failure(exc)
                _mark_failed(client, sync_day, owner, plan, started, message)
                raise TursoSyncError(message) from exc
            failed.update(fetch_failed)
            accepted, _calendar, invalid = prepare_sync_rows(
                fetched, allowed_sessions=set(history_days)
            )
            failed.update(
                str(row.get("symbol"))
                for row in invalid
                if row.get("symbol") and str(row.get("symbol")) not in {r["symbol"] for r in accepted}
            )
            if accepted:
                stored = await _persist_rows(client, accepted, table="daily_ohlcv")
                if stored <= 0:
                    message = (
                        "Turso rejected the equity candle batch. "
                        "Scanner was not started. Postgres was not used."
                    )
                    _mark_failed(client, sync_day, owner, plan, started, message)
                    raise TursoSyncError(message)
                rows_upserted += stored
                updated.update(str(row["symbol"]) for row in accepted)
        try:
            index_rows = await fetch_index(history_days[0], history_days[-1])
        except Exception as exc:
            message = _safe_failure(exc)
            _mark_failed(client, sync_day, owner, plan, started, message)
            raise TursoSyncError(message) from exc
        index_accepted, _cal, _bad = prepare_sync_rows(
            index_rows, allowed_sessions=set(history_days)
        )
        if index_accepted:
            stored_index = await _persist_rows(client, index_accepted, table="index_ohlcv")
            if stored_index <= 0:
                message = (
                    "Turso rejected the NIFTY 500 candle batch. "
                    "Scanner was not started. Postgres was not used."
                )
                _mark_failed(client, sync_day, owner, plan, started, message)
                raise TursoSyncError(message)
            rows_upserted += stored_index

    if quote_session is not None:
        _renew_lease(client, sync_day, owner, moment)
        try:
            quote_rows, index_rows, quote_failed = await fetch_quotes(universe, quote_session)
        except Exception as exc:
            message = _safe_failure(exc)
            _mark_failed(client, sync_day, owner, plan, started, message)
            raise TursoSyncError(message) from exc
        if official_close:
            quote_rows = [{**row, "source": "FYERS"} for row in quote_rows]
            index_rows = [{**row, "source": "FYERS"} for row in index_rows]
            if not index_rows:
                try:
                    index_rows = [
                        {**row, "source": "FYERS"}
                        for row in await fetch_index(quote_session, quote_session)
                    ]
                except Exception as exc:
                    message = _safe_failure(exc)
                    _mark_failed(client, sync_day, owner, plan, started, message)
                    raise TursoSyncError(message) from exc
        failed.update(quote_failed)
        accepted, _calendar, invalid = prepare_sync_rows(
            quote_rows, allowed_sessions={quote_session}
        )
        if accepted:
            stored = await _persist_rows(client, accepted, table="daily_ohlcv")
            if stored <= 0:
                message = (
                    "Turso rejected the live equity candle batch. "
                    "Scanner was not started. Postgres was not used."
                )
                _mark_failed(client, sync_day, owner, plan, started, message)
                raise TursoSyncError(message)
            rows_upserted += stored
            updated.update(str(row["symbol"]) for row in accepted)
        index_accepted, _c2, _b2 = prepare_sync_rows(
            index_rows, allowed_sessions={quote_session}
        )
        if index_accepted:
            stored_index = await _persist_rows(client, index_accepted, table="index_ohlcv")
            if stored_index <= 0:
                message = (
                    "Turso rejected the live NIFTY 500 candle. "
                    "Scanner was not started. Postgres was not used."
                )
                _mark_failed(client, sync_day, owner, plan, started, message)
                raise TursoSyncError(message)
            rows_upserted += stored_index

    equity_latest, index_latest = _read_latest_dates(client)
    required = _coverage_requirement(processed)
    problems: list[str] = []
    if history_days:
        newest = history_days[-1]
        count = _session_count(client, newest)
        if count < required:
            problems.append(
                f"equity session {newest.isoformat()} has {count} symbols, need {required}"
            )
        if index_latest is None or index_latest < newest:
            problems.append(f"NIFTY 500 candle is missing for {newest.isoformat()}")
    if quote_session is not None:
        count = _session_count(client, quote_session)
        if count < required:
            label = "live session" if not official_close else "equity session"
            problems.append(
                f"{label} {quote_session.isoformat()} has {count} symbols, need {required}"
            )
    if equity_latest is None or equity_latest < plan["completed_target"]:
        problems.append("latest equity candle is behind the completed NSE session")
    if index_latest is None or index_latest < plan["completed_target"]:
        problems.append("latest NIFTY 500 candle is behind the completed NSE session")
    if plan["required_state"] == "eod" and (equity_latest is None or equity_latest < plan["satisfy_session"]):
        problems.append("official equity session was not stored")
    if plan["required_state"] == "live" and (equity_latest is None or equity_latest < plan["satisfy_session"]):
        problems.append("live equity session was not stored")

    duration_ms = int((time.perf_counter() - started) * 1000)
    if problems:
        message = (
            "Turso candle sync is incomplete (" + "; ".join(problems) + "). "
            "Scanner was not started. Postgres was not used."
        )
        _mark_failed(client, sync_day, owner, plan, started, message)
        raise TursoSyncError(
            message,
            _diagnostics(
                sync_date=sync_day,
                status="failed",
                equity=equity_latest,
                index=index_latest,
                processed=processed,
                updated=len(updated),
                failed=len(failed),
                duration_ms=duration_ms,
                reused=False,
                rows_upserted=rows_upserted,
                error=message,
            ),
        )

    untouched = set(universe) - updated
    # Names already stored on a gap day were not pending. They are not failures.
    if history_days and not plan["replace_existing"]:
        failed = {symbol for symbol in failed if symbol not in updated}
    else:
        failed = {symbol for symbol in failed if symbol not in updated}
    del untouched
    report = _diagnostics(
        sync_date=sync_day,
        status="completed",
        equity=equity_latest,
        index=index_latest,
        processed=processed,
        updated=len(updated),
        failed=len(failed),
        duration_ms=duration_ms,
        reused=False,
        rows_upserted=rows_upserted,
    )
    _finish_sync(
        client,
        sync_day,
        owner,
        {
            "status": "completed",
            "finished_at": _iso(datetime.now(timezone.utc)),
            "target_session": plan["satisfy_session"].isoformat(),
            "bar_state": "eod" if plan["required_state"] == "eod" else plan["required_state"],
            "latest_equity_date": report["latest_equity_date"],
            "latest_index_date": report["latest_index_date"],
            "symbols_processed": processed,
            "symbols_updated": len(updated),
            "symbols_failed": len(failed),
            "rows_upserted": rows_upserted,
            "duration_ms": duration_ms,
            "error": None,
            "lease_expires_at": _iso(datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)),
        },
    )
    return report


def _log_report(strategy: str, report: dict[str, Any]) -> None:
    logger.info(
        "TURSO_DAILY_SYNC | strategy=%s | backend=%s | sync_date=%s | status=%s | "
        "equity=%s | nifty500=%s | processed=%s | updated=%s | failed=%s | duration_ms=%s | reused=%s",
        strategy,
        report.get("backend"),
        report.get("sync_date"),
        report.get("sync_status"),
        report.get("latest_equity_date"),
        report.get("latest_index_date"),
        report.get("symbols_processed"),
        report.get("symbols_updated"),
        report.get("symbols_failed"),
        report.get("sync_duration_ms"),
        report.get("reused"),
    )


async def sync_before_scan(
    symbols: list[str],
    *,
    strategy: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Sync or reuse today's Turso catch-up. Raises when the scanner must stop."""
    try:
        return await asyncio.wait_for(
            ensure_scanner_turso_sync(symbols, strategy=strategy, now=now),
            timeout=SCANNER_SYNC_WAIT_S,
        )
    except asyncio.TimeoutError as exc:
        raise TursoSyncError(
            "Turso daily candle sync timed out. Scanner was not started. Postgres was not used."
        ) from exc


def _cli() -> int:
    """Catch Turso up to the latest session. Prints diagnostics, never the token."""
    import json

    from ...config.settings import settings
    from ...db.urls import public_db_target

    backend = settings.candle_history_backend_name()
    host = public_db_target(settings.turso_database_url)
    token_set = bool((settings.turso_auth_token or "").strip())
    print(f"backend={backend}")
    print(f"turso_host={host}")
    print(f"turso_token_set={str(token_set).lower()}")
    if backend != "turso" or not token_set:
        print("sync_status=failed")
        print("error=CANDLE_HISTORY_BACKEND=turso and TURSO_AUTH_TOKEN are required")
        return 1

    async def _run() -> dict[str, Any]:
        client = _client()
        apply_candle_schema(client)
        rows = client.execute("SELECT MAX(trade_date) AS m FROM daily_ohlcv")
        latest = rows[0]["m"] if rows else None
        names: list[str] = []
        if latest:
            found = client.execute(
                "SELECT symbol FROM daily_ohlcv WHERE trade_date = ?",
                [str(latest)[:10]],
            )
            names = [str(row["symbol"]) for row in found if row.get("symbol")]
        return await ensure_scanner_turso_sync(names, strategy="initial_sync")

    try:
        report = asyncio.run(_run())
    except TursoSyncError as exc:
        print("sync_status=failed")
        print(f"error={exc}")
        if exc.diagnostics:
            print(json.dumps({k: v for k, v in exc.diagnostics.items() if k != "error"}, default=str))
        return 1
    print(json.dumps(report, default=str))
    return 0 if report.get("sync_status") in {"completed", "reused"} else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
