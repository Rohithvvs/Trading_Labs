"""Bulk upsert and query helpers for strategy-grade market data."""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import bindparam, func, select, text
from sqlalchemy.dialects.postgresql import ARRAY, VARCHAR, insert as pg_insert

from ...db.session import AsyncSessionLocal
from ...models.strategy_market_data import DailyOhlcv, IndexOhlcv

_ohlcv_log = logging.getLogger("app.market_data.ohlcv")


def _use_turso_history() -> bool:
    """Route daily/index history to Turso only when explicitly selected.

    Any evaluation error falls back to Postgres so default runtime is unchanged.
    """
    try:
        from .history_backend import uses_turso

        return bool(uses_turso())
    except Exception:
        return False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _dec(v: Any) -> Decimal:
    return Decimal(str(v))


async def max_equity_trade_date(symbols: list[str] | None = None) -> date | None:
    if _use_turso_history():
        from . import turso_repository as turso

        return await turso.fetch_max_equity_trade_date(symbols)
    async with AsyncSessionLocal() as db:
        stmt = select(func.max(DailyOhlcv.trade_date))
        if symbols:
            stmt = stmt.where(DailyOhlcv.symbol.in_(symbols))
        return (await db.execute(stmt)).scalar_one_or_none()


async def equity_date_span(symbol: str) -> tuple[date | None, date | None, int]:
    """Return (min_trade_date, max_trade_date, row_count) for one equity symbol."""
    if _use_turso_history():
        from . import turso_repository as turso

        return await turso.fetch_equity_date_span(symbol)
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(
                    func.min(DailyOhlcv.trade_date),
                    func.max(DailyOhlcv.trade_date),
                    func.count(),
                ).where(DailyOhlcv.symbol == symbol)
            )
        ).one()
        return row[0], row[1], int(row[2] or 0)


async def max_index_trade_date(symbol: str = "NIFTY500") -> date | None:
    if _use_turso_history():
        from . import turso_repository as turso

        return await turso.fetch_max_index_trade_date(symbol)
    async with AsyncSessionLocal() as db:
        stmt = select(func.max(IndexOhlcv.trade_date)).where(IndexOhlcv.symbol == symbol)
        return (await db.execute(stmt)).scalar_one_or_none()


async def min_index_trade_date(symbol: str = "NIFTY500") -> date | None:
    if _use_turso_history():
        from . import turso_repository as turso

        return await turso.fetch_min_index_trade_date(symbol)
    async with AsyncSessionLocal() as db:
        stmt = select(func.min(IndexOhlcv.trade_date)).where(IndexOhlcv.symbol == symbol)
        return (await db.execute(stmt)).scalar_one_or_none()


async def index_row_count(symbol: str = "NIFTY500") -> int:
    if _use_turso_history():
        from . import turso_repository as turso

        return await turso.fetch_index_row_count(symbol)
    async with AsyncSessionLocal() as db:
        stmt = select(func.count()).select_from(IndexOhlcv).where(IndexOhlcv.symbol == symbol)
        return int((await db.execute(stmt)).scalar() or 0)


async def symbols_present_on(trade_date: date, symbols: list[str] | None = None) -> set[str]:
    if _use_turso_history():
        from . import turso_repository as turso

        return await turso.fetch_symbols_present_on(trade_date, symbols)
    async with AsyncSessionLocal() as db:
        stmt = select(DailyOhlcv.symbol).where(DailyOhlcv.trade_date == trade_date)
        if symbols:
            stmt = stmt.where(DailyOhlcv.symbol.in_(symbols))
        rows = (await db.execute(stmt)).scalars().all()
        return set(rows)


async def index_present(trade_date: date, symbol: str = "NIFTY500") -> bool:
    if _use_turso_history():
        from . import turso_repository as turso

        return await turso.fetch_index_present(trade_date, symbol)
    async with AsyncSessionLocal() as db:
        stmt = (
            select(IndexOhlcv.symbol)
            .where(IndexOhlcv.trade_date == trade_date, IndexOhlcv.symbol == symbol)
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none() is not None


async def symbols_with_delivery_on(
    trade_date: date, symbols: list[str] | None = None
) -> set[str]:
    """Symbols that have non-null delivery_pct (or delivery_qty) on trade_date."""
    async with AsyncSessionLocal() as db:
        stmt = select(DailyOhlcv.symbol).where(
            DailyOhlcv.trade_date == trade_date,
            (DailyOhlcv.delivery_pct.is_not(None)) | (DailyOhlcv.delivery_qty.is_not(None)),
        )
        if symbols:
            stmt = stmt.where(DailyOhlcv.symbol.in_(symbols))
        return set((await db.execute(stmt)).scalars().all())


async def symbols_with_adtv_on(
    trade_date: date, symbols: list[str] | None = None
) -> set[str]:
    """Symbols that have non-null adtv_20 on trade_date."""
    async with AsyncSessionLocal() as db:
        stmt = select(DailyOhlcv.symbol).where(
            DailyOhlcv.trade_date == trade_date,
            DailyOhlcv.adtv_20.is_not(None),
        )
        if symbols:
            stmt = stmt.where(DailyOhlcv.symbol.in_(symbols))
        return set((await db.execute(stmt)).scalars().all())


async def session_coverage_snapshot(
    trade_date: date,
    symbols: list[str],
    *,
    index_symbol: str = "NIFTY500",
    include_symbol_sets: bool = False,
) -> dict[str, Any]:
    """Fast session coverage for ensure.

    Default path uses aggregate COUNTs (cheap). Set ``include_symbol_sets=True``
    when callers need the actual present/missing symbol lists.
    """
    if not symbols:
        return {
            "present": set(),
            "with_delivery": set(),
            "with_adtv": set(),
            "present_count": 0,
            "delivery_count": 0,
            "adtv_count": 0,
            "universe_count": 0,
            "index_present": False,
            "max_equity_date": None,
        }

    async with AsyncSessionLocal() as db:
        # Avoid huge IN (...) lists on the fast path — count the session day globally.
        # Strategy table is NIFTY500-scoped; slight over-count from pilot aliases is fine.
        counts = (
            await db.execute(
                select(
                    func.count().label("present_n"),
                    func.count()
                    .filter(
                        (DailyOhlcv.delivery_pct.is_not(None))
                        | (DailyOhlcv.delivery_qty.is_not(None))
                    )
                    .label("deliv_n"),
                    func.count().filter(DailyOhlcv.adtv_20.is_not(None)).label("adtv_n"),
                ).where(DailyOhlcv.trade_date == trade_date)
            )
        ).one()
        present_n = min(int(counts[0] or 0), len(symbols))
        deliv_n = min(int(counts[1] or 0), len(symbols))
        adtv_n = min(int(counts[2] or 0), len(symbols))

        idx = (
            await db.execute(
                select(IndexOhlcv.symbol)
                .where(
                    IndexOhlcv.trade_date == trade_date,
                    IndexOhlcv.symbol == index_symbol,
                )
                .limit(1)
            )
        ).scalar_one_or_none()

        max_eq = (await db.execute(select(func.max(DailyOhlcv.trade_date)))).scalar_one_or_none()

        present: set[str] = set()
        with_delivery: set[str] = set()
        with_adtv: set[str] = set()
        if include_symbol_sets:
            rows = (
                await db.execute(
                    select(
                        DailyOhlcv.symbol,
                        DailyOhlcv.delivery_pct,
                        DailyOhlcv.delivery_qty,
                        DailyOhlcv.adtv_20,
                    ).where(
                        DailyOhlcv.trade_date == trade_date,
                        DailyOhlcv.symbol.in_(symbols),
                    )
                )
            ).all()
            for sym, d_pct, d_qty, adtv in rows:
                present.add(sym)
                if d_pct is not None or d_qty is not None:
                    with_delivery.add(sym)
                if adtv is not None:
                    with_adtv.add(sym)
            present_n = len(present)
            deliv_n = len(with_delivery)
            adtv_n = len(with_adtv)

        return {
            "present": present,
            "with_delivery": with_delivery,
            "with_adtv": with_adtv,
            "present_count": present_n,
            "delivery_count": deliv_n,
            "adtv_count": adtv_n,
            "universe_count": len(symbols),
            "index_present": idx is not None,
            "max_equity_date": max_eq,
        }


async def update_adtv_for_session(
    session: date,
    symbol_adtv: dict[str, float | None],
) -> int:
    """Bulk-set adtv_20 for symbols on a session. Returns rows updated."""
    if not symbol_adtv:
        return 0
    from sqlalchemy import text

    payload = [(sym, val) for sym, val in symbol_adtv.items() if val is not None]
    if not payload:
        return 0
    total = 0
    chunk_size = 400
    async with AsyncSessionLocal() as db:
        for i in range(0, len(payload), chunk_size):
            chunk = payload[i : i + chunk_size]
            values_sql = []
            params: dict[str, Any] = {"sess": session}
            for j, (sym, val) in enumerate(chunk):
                values_sql.append(f"(CAST(:sym{j} AS text), CAST(:adtv{j} AS numeric))")
                params[f"sym{j}"] = sym
                params[f"adtv{j}"] = float(val)
            sql = f"""
                UPDATE daily_ohlcv AS d
                SET adtv_20 = v.adtv
                FROM (VALUES {", ".join(values_sql)}) AS v(sym, adtv)
                WHERE d.trade_date = :sess AND d.symbol = v.sym
            """
            result = await db.execute(text(sql), params)
            total += int(result.rowcount or 0)
        await db.commit()
    return total


async def upsert_daily_bars(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Idempotent upsert. Returns (accepted_count, rejected_count).

    Source allowlist (FYERS only) is applied before the OHLC gate. Invalid OHLC
    is dropped (not clamped). Delivery fields: only overwrite when the incoming
    row has a non-null value (COALESCE) so OHLCV-only rewrites do not wipe prior
    delivery backfill.
    """
    from .source_policy import filter_strategy_store_sources
    from .validators.ohlcv_gate import filter_valid_ohlcv_rows

    sourced, source_rejected = filter_strategy_store_sources(
        rows, table_name="daily_ohlcv", log_context="upsert_daily_bars"
    )
    accepted, ohlc_rejected = filter_valid_ohlcv_rows(sourced, log_context="upsert_daily_bars")
    rejected_n = len(source_rejected) + len(ohlc_rejected)
    if _use_turso_history():
        from . import turso_repository as turso

        n = turso.upsert_daily_rows(turso._client(), accepted)
        return n, rejected_n
    if not accepted:
        return 0, rejected_n
    loaded_at = _utc_now()
    payload = []
    for r in accepted:
        payload.append(
            {
                "trade_date": r["trade_date"],
                "symbol": r["symbol"],
                "open": _dec(r["open"]),
                "high": _dec(r["high"]),
                "low": _dec(r["low"]),
                "close": _dec(r["close"]),
                "volume": int(r.get("volume") or 0),
                "delivery_qty": r.get("delivery_qty"),
                "delivery_pct": _dec(r["delivery_pct"]) if r.get("delivery_pct") is not None else None,
                "turnover": _dec(r["turnover"]) if r.get("turnover") is not None else None,
                "adtv_20": _dec(r["adtv_20"]) if r.get("adtv_20") is not None else None,
                "source": r.get("source"),
                "loaded_at": loaded_at,
            }
        )
    async with AsyncSessionLocal() as db:
        stmt = pg_insert(DailyOhlcv).values(payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=["trade_date", "symbol"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "delivery_qty": func.coalesce(stmt.excluded.delivery_qty, DailyOhlcv.delivery_qty),
                "delivery_pct": func.coalesce(stmt.excluded.delivery_pct, DailyOhlcv.delivery_pct),
                "turnover": func.coalesce(stmt.excluded.turnover, DailyOhlcv.turnover),
                "adtv_20": func.coalesce(stmt.excluded.adtv_20, DailyOhlcv.adtv_20),
                "source": stmt.excluded.source,
                "loaded_at": stmt.excluded.loaded_at,
            },
        )
        await db.execute(stmt)
        await db.commit()
    return len(payload), rejected_n


async def delete_cloned_daily_bars(session: date, previous: date) -> int:
    """Delete rows on `session` whose OHLCV is an exact copy of `previous`."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                """
                DELETE FROM daily_ohlcv AS d
                USING daily_ohlcv AS p
                WHERE d.trade_date = :session
                  AND p.trade_date = :previous
                  AND d.symbol = p.symbol
                  AND d.open = p.open
                  AND d.high = p.high
                  AND d.low = p.low
                  AND d.close = p.close
                  AND d.volume = p.volume
                """
            ),
            {"session": session, "previous": previous},
        )
        await db.commit()
        return int(result.rowcount or 0)


async def update_delivery_fields(rows: list[dict[str, Any]]) -> int:
    """Update delivery_qty / delivery_pct for existing (trade_date, symbol) rows.

    Only applies non-null delivery values. Returns number of rows attempted.
    """
    if not rows:
        return 0
    from sqlalchemy import update

    updated = 0
    async with AsyncSessionLocal() as db:
        for r in rows:
            d_qty = r.get("delivery_qty")
            d_pct = r.get("delivery_pct")
            if d_qty is None and d_pct is None:
                continue
            values: dict[str, Any] = {}
            if d_qty is not None:
                values["delivery_qty"] = int(d_qty)
            if d_pct is not None:
                values["delivery_pct"] = _dec(d_pct)
            if not values:
                continue
            stmt = (
                update(DailyOhlcv)
                .where(
                    DailyOhlcv.trade_date == r["trade_date"],
                    DailyOhlcv.symbol == r["symbol"],
                )
                .values(**values)
            )
            result = await db.execute(stmt)
            updated += int(result.rowcount or 0)
        await db.commit()
    return updated


async def update_delivery_for_session(
    session: date,
    delivery_map: dict[str, dict[str, Any]],
    *,
    symbols: list[str] | None = None,
) -> int:
    """Apply a session delivery map onto daily_ohlcv rows for that trade_date.

    Uses a single bulk UPDATE … FROM (VALUES …) for performance.
    """
    if not delivery_map:
        return 0
    from sqlalchemy import text

    from .derived import compute_delivery_pct
    from .providers.nse_delivery import NseDeliveryProvider

    async with AsyncSessionLocal() as db:
        stmt = select(DailyOhlcv.symbol).where(DailyOhlcv.trade_date == session)
        if symbols:
            stmt = stmt.where(DailyOhlcv.symbol.in_(symbols))
        present = list((await db.execute(stmt)).scalars().all())
        if not present:
            return 0

        nse = NseDeliveryProvider()
        payload: list[dict[str, Any]] = []
        for sym in present:
            drec = nse.lookup(delivery_map, symbol=sym)
            if not drec:
                continue
            d_qty = drec.get("delivery_qty")
            d_pct = drec.get("delivery_pct")
            if d_pct is None and d_qty is not None:
                pct = compute_delivery_pct(d_qty, drec.get("traded_qty"))
                d_pct = float(pct) if pct is not None else None
            if d_qty is None and d_pct is None:
                continue
            payload.append(
                {
                    "sym": sym,
                    "d_qty": int(d_qty) if d_qty is not None else None,
                    "d_pct": float(d_pct) if d_pct is not None else None,
                }
            )
        if not payload:
            return 0

        # Chunk VALUES to keep statement size reasonable
        total = 0
        chunk_size = 400
        for i in range(0, len(payload), chunk_size):
            chunk = payload[i : i + chunk_size]
            values_sql = []
            params: dict[str, Any] = {"sess": session}
            for j, row in enumerate(chunk):
                values_sql.append(
                    f"(CAST(:sym{j} AS text), CAST(:qty{j} AS bigint), CAST(:pct{j} AS numeric))"
                )
                params[f"sym{j}"] = row["sym"]
                params[f"qty{j}"] = row["d_qty"]
                params[f"pct{j}"] = row["d_pct"]
            sql = f"""
                UPDATE daily_ohlcv AS d
                SET
                    delivery_qty = COALESCE(v.d_qty, d.delivery_qty),
                    delivery_pct = COALESCE(v.d_pct, d.delivery_pct)
                FROM (VALUES {", ".join(values_sql)}) AS v(sym, d_qty, d_pct)
                WHERE d.trade_date = :sess AND d.symbol = v.sym
            """
            result = await db.execute(text(sql), params)
            total += int(result.rowcount or 0)
        await db.commit()
        return total



async def backfill_adtv_20_sql() -> int:
    """Populate adtv_20 for all rows using a 20-session rolling average of close*volume."""
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        # PostgreSQL window; for other dialects this may need a Python path.
        await db.execute(
            text(
                """
                UPDATE daily_ohlcv AS d
                SET adtv_20 = s.adtv
                FROM (
                    SELECT trade_date, symbol,
                           AVG(close::numeric * volume::numeric) OVER (
                               PARTITION BY symbol
                               ORDER BY trade_date
                               ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                           ) AS adtv
                    FROM daily_ohlcv
                ) AS s
                WHERE d.trade_date = s.trade_date AND d.symbol = s.symbol
                """
            )
        )
        await db.commit()
        cnt = (
            await db.execute(text("SELECT COUNT(*) FROM daily_ohlcv WHERE adtv_20 IS NOT NULL"))
        ).scalar()
        return int(cnt or 0)


async def backfill_adtv_20_for_session(
    session: date,
    symbols: list[str] | None = None,
) -> int:
    """Set adtv_20 for one trade_date using a SQL window — O(1) round-trips.

    Replaces the previous N×``fetch_equity_history`` Python loop that blocked
    scanners for minutes with zero progress events.
    """
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        # Window over recent history per symbol, then write only the target session.
        # Limit history lookback via trade_date filter to keep the plan cheap.
        params: dict[str, Any] = {"sess": session}
        symbol_filter = ""
        if symbols:
            # Bound IN-list size; caller should already pass a reasonable set.
            syms = list(symbols)[:2000]
            placeholders = []
            for i, s in enumerate(syms):
                key = f"s{i}"
                placeholders.append(f":{key}")
                params[key] = s
            symbol_filter = f"AND symbol IN ({', '.join(placeholders)})"

        sql = f"""
            UPDATE daily_ohlcv AS d
            SET adtv_20 = w.adtv
            FROM (
                SELECT trade_date, symbol,
                       AVG(close::numeric * volume::numeric) OVER (
                           PARTITION BY symbol
                           ORDER BY trade_date
                           ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                       ) AS adtv
                FROM daily_ohlcv
                WHERE trade_date <= :sess
                  AND trade_date >= (:sess::date - INTERVAL '90 days')
                  {symbol_filter}
            ) AS w
            WHERE d.trade_date = :sess
              AND d.symbol = w.symbol
              AND d.trade_date = w.trade_date
              AND d.adtv_20 IS NULL
        """
        result = await db.execute(text(sql), params)
        await db.commit()
        return int(result.rowcount or 0)


async def fetch_recent_equity_before(
    symbol: str,
    before_date: date,
    limit: int = 19,
) -> list[dict[str, Any]]:
    """Last ``limit`` bars strictly before ``before_date`` (ascending)."""
    if _use_turso_history():
        from . import turso_repository as turso

        return await turso.fetch_recent_equity_before(symbol, before_date, limit)
    async with AsyncSessionLocal() as db:
        stmt = (
            select(DailyOhlcv)
            .where(DailyOhlcv.symbol == symbol, DailyOhlcv.trade_date < before_date)
            .order_by(DailyOhlcv.trade_date.desc())
            .limit(limit)
        )
        rows = list((await db.scalars(stmt)).all())
        rows.reverse()
        return [
            {
                "trade_date": r.trade_date,
                "symbol": r.symbol,
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": int(r.volume),
                "turnover": float(r.turnover) if r.turnover is not None else None,
                "adtv_20": float(r.adtv_20) if r.adtv_20 is not None else None,
            }
            for r in rows
        ]


async def upsert_index_bars(rows: list[dict[str, Any]]) -> int:
    from .source_policy import filter_strategy_store_sources
    from .validators.ohlcv_gate import filter_valid_ohlcv_rows

    sourced, _source_rejected = filter_strategy_store_sources(
        rows, table_name="index_ohlcv", log_context="upsert_index_bars"
    )
    accepted, _ohlc_rejected = filter_valid_ohlcv_rows(sourced, log_context="upsert_index_bars")
    if _use_turso_history():
        from . import turso_repository as turso

        return turso.upsert_index_rows(turso._client(), accepted)
    if not accepted:
        return 0
    loaded_at = _utc_now()
    payload = []
    for r in accepted:
        payload.append(
            {
                "trade_date": r["trade_date"],
                "symbol": r["symbol"],
                "open": _dec(r["open"]),
                "high": _dec(r["high"]),
                "low": _dec(r["low"]),
                "close": _dec(r["close"]),
                "volume": int(r["volume"]) if r.get("volume") is not None else None,
                "source": r.get("source"),
                "loaded_at": loaded_at,
            }
        )
    chunk = 500
    async with AsyncSessionLocal() as db:
        for i in range(0, len(payload), chunk):
            part = payload[i : i + chunk]
            stmt = pg_insert(IndexOhlcv).values(part)
            stmt = stmt.on_conflict_do_update(
                index_elements=["trade_date", "symbol"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                    "source": stmt.excluded.source,
                    "loaded_at": stmt.excluded.loaded_at,
                },
            )
            await db.execute(stmt)
        await db.commit()
    return len(payload)


def _equity_row_dict(r: DailyOhlcv) -> dict[str, Any]:
    return {
        "trade_date": r.trade_date,
        "symbol": r.symbol,
        "open": float(r.open),
        "high": float(r.high),
        "low": float(r.low),
        "close": float(r.close),
        "volume": int(r.volume),
        "delivery_qty": r.delivery_qty,
        "delivery_pct": float(r.delivery_pct) if r.delivery_pct is not None else None,
        "turnover": float(r.turnover) if r.turnover is not None else None,
        "adtv_20": float(r.adtv_20) if getattr(r, "adtv_20", None) is not None else None,
    }


async def fetch_equity_history(
    symbol: str,
    *,
    from_date: date | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if _use_turso_history():
        from . import turso_repository as turso

        return await turso.fetch_equity_history(symbol, from_date=from_date, limit=limit)
    from ...utils.symbol import ohlcv_symbol_variants, preferred_ohlcv_store_symbol

    variants = ohlcv_symbol_variants(symbol) or [symbol]
    async with AsyncSessionLocal() as db:
        stmt = select(DailyOhlcv).where(DailyOhlcv.symbol.in_(variants))
        if from_date:
            stmt = stmt.where(DailyOhlcv.trade_date >= from_date)
        stmt = stmt.order_by(DailyOhlcv.trade_date.asc())
        rows = list((await db.scalars(stmt)).all())
        store = preferred_ohlcv_store_symbol([r.symbol for r in rows])
        if store:
            rows = [r for r in rows if r.symbol == store]
        if limit:
            rows = rows[: int(limit)]
        if store and store != symbol:
            _ohlcv_log.info(
                "EQUITY_HISTORY_RESOLVED requested=%s store_symbol=%s rows=%s from_date=%s",
                symbol,
                store,
                len(rows),
                from_date.isoformat() if from_date else None,
            )
        return [_equity_row_dict(r) for r in rows]


async def fetch_index_history(
    symbol: str = "NIFTY500",
    *,
    from_date: date | None = None,
) -> list[dict[str, Any]]:
    if _use_turso_history():
        from . import turso_repository as turso

        return await turso.fetch_index_history(symbol, from_date=from_date)
    async with AsyncSessionLocal() as db:
        stmt = select(IndexOhlcv).where(IndexOhlcv.symbol == symbol)
        if from_date:
            stmt = stmt.where(IndexOhlcv.trade_date >= from_date)
        stmt = stmt.order_by(IndexOhlcv.trade_date.asc())
        rows = (await db.scalars(stmt)).all()
        return [
            {
                "trade_date": r.trade_date,
                "symbol": r.symbol,
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": int(r.volume) if r.volume is not None else None,
            }
            for r in rows
        ]


async def symbol_has_sufficient_history(symbol: str, min_rows: int = 500) -> bool:
    if _use_turso_history():
        from . import turso_repository as turso

        return await turso.fetch_symbol_has_sufficient_history(symbol, min_rows)
    async with AsyncSessionLocal() as db:
        cnt = (
            await db.execute(
                select(func.count()).select_from(DailyOhlcv).where(DailyOhlcv.symbol == symbol)
            )
        ).scalar() or 0
        return int(cnt) >= min_rows


# Universe scans used to SELECT 700+ symbols in one IN (...) ORDER BY trade_date.
# That plan sorts ~2M rows and is killed by the pool's 30s statement_timeout.
SCAN_OHLCV_SYMBOL_CHUNK = 50
SCAN_OHLCV_STATEMENT_TIMEOUT = "90s"
OHLCV_LOOKBACK_MAX_DEFAULT = 2000  # TimeframeConfig.lookback_window le=2000
_OHLCV_SQL_COLUMNS = frozenset(
    {
        "trade_date",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "delivery_qty",
        "delivery_pct",
        "turnover",
        "adtv_20",
        "source",
        "loaded_at",
    }
)


def iter_symbol_chunks(
    symbols: Iterable[str], size: int = SCAN_OHLCV_SYMBOL_CHUNK
) -> list[list[str]]:
    """Stable unique chunks for IN-list queries. Empty / duplicate names are dropped."""
    unique = list(dict.fromkeys(s for s in symbols if s))
    if not unique:
        return []
    if size <= 0:
        return [unique]
    return [unique[i : i + size] for i in range(0, len(unique), size)]


def clamp_ohlcv_lookback(
    lookback: int,
    *,
    maximum: int | None = None,
    minimum: int = 1,
) -> int:
    """Reject non-positive lookback; cap at the configured maximum."""
    try:
        n = int(lookback)
    except (TypeError, ValueError) as exc:
        raise ValueError("lookback must be a positive integer") from exc
    if n < minimum:
        raise ValueError(f"lookback must be >= {minimum}")
    max_n = int(maximum) if maximum is not None else _configured_lookback_max()
    if max_n < minimum:
        max_n = minimum
    return min(n, max_n)


def _configured_lookback_max() -> int:
    try:
        from ...config.settings import settings

        return int(getattr(settings, "ohlcv_lookback_max_sessions", OHLCV_LOOKBACK_MAX_DEFAULT))
    except Exception:
        return OHLCV_LOOKBACK_MAX_DEFAULT


def _ohlcv_column_names(columns: tuple[Any, ...] | None) -> list[str]:
    if not columns:
        return ["trade_date", "symbol", "high", "low", "close", "volume"]
    names: list[str] = []
    for col in columns:
        name = getattr(col, "key", None) or getattr(col, "name", None)
        if not name or name not in _OHLCV_SQL_COLUMNS:
            raise ValueError(f"unsupported daily_ohlcv column: {col!r}")
        names.append(str(name))
    return names


def _default_ohlcv_columns() -> tuple[Any, ...]:
    return (
        DailyOhlcv.trade_date,
        DailyOhlcv.symbol,
        DailyOhlcv.high,
        DailyOhlcv.low,
        DailyOhlcv.close,
        DailyOhlcv.volume,
    )


async def extend_scan_statement_timeout(db: Any, timeout: str = SCAN_OHLCV_STATEMENT_TIMEOUT) -> None:
    bind = getattr(db, "bind", None)
    dialect = getattr(bind, "dialect", None)
    if getattr(dialect, "name", None) != "postgresql":
        return
    await db.execute(text(f"SET LOCAL statement_timeout = '{timeout}'"))


def _dialect_name(db: Any) -> str:
    bind = getattr(db, "bind", None)
    return str(getattr(getattr(bind, "dialect", None), "name", "") or "")


def latest_n_ohlcv_sql(column_names: list[str]) -> str:
    """Indexed latest-N per symbol. Caller must whitelist column_names."""
    cols = ", ".join(column_names)
    return (
        "SELECT "
        + ", ".join(f"d.{c}" for c in column_names)
        + " FROM unnest(CAST(:symbols AS varchar[])) AS s(symbol) "
        "CROSS JOIN LATERAL ("
        f" SELECT {cols} FROM daily_ohlcv"
        " WHERE daily_ohlcv.symbol = s.symbol"
        " ORDER BY daily_ohlcv.trade_date DESC"
        " LIMIT :lookback"
        ") AS d"
        " ORDER BY d.symbol ASC, d.trade_date ASC"
    )


async def fetch_daily_ohlcv_for_symbols(
    symbols: Iterable[str],
    *,
    columns: tuple[Any, ...] | None = None,
    lookback: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[Any]:
    """Load daily bars for a universe.

    ``lookback=None`` keeps the unbounded (chunked) path for other strategies.
    A positive ``lookback`` fetches only the latest N sessions per symbol via
    an indexed LATERAL query — no full-table sort.
    ``from_date`` / ``to_date`` constrain the store by trade_date (used by
    historical 52W boards). Date bounds take precedence over lookback.
    """
    unique = list(dict.fromkeys(s for s in symbols if s))
    if _use_turso_history():
        from collections import namedtuple
        from . import turso_repository as turso

        dict_rows = await turso.fetch_daily_ohlcv_for_symbols(
            unique, lookback=lookback, from_date=from_date, to_date=to_date
        )
        col_names = _ohlcv_column_names(columns)
        RowCls = namedtuple("DailyOhlcvRow", col_names)
        return [RowCls(*(r.get(c) for c in col_names)) for r in dict_rows]
    col_names = _ohlcv_column_names(columns)
    cols = columns or _default_ohlcv_columns()
    bound = None if from_date is not None else (clamp_ohlcv_lookback(lookback) if lookback is not None else None)
    _ohlcv_log.info(
        "OHLCV_FETCH_STARTED symbol_count=%s lookback=%s from_date=%s to_date=%s",
        len(unique),
        bound,
        from_date.isoformat() if from_date else None,
        to_date.isoformat() if to_date else None,
    )
    started = time.perf_counter()
    if not unique:
        _ohlcv_log.info(
            "OHLCV_FETCH_COMPLETED symbol_count=0 rows_returned=0 duration_ms=0"
        )
        return []

    async with AsyncSessionLocal() as db:
        if from_date is not None:
            await extend_scan_statement_timeout(db, "180s")
            rows = await _fetch_date_range_chunked(
                db, unique, cols, from_date=from_date, to_date=to_date
            )
        elif bound is not None:
            rows = await _fetch_latest_n(db, unique, col_names, cols, bound)
        else:
            rows = await _fetch_unbounded_chunked(db, unique, cols)

    duration_ms = int((time.perf_counter() - started) * 1000)
    _ohlcv_log.info(
        "OHLCV_FETCH_COMPLETED symbol_count=%s lookback=%s from_date=%s to_date=%s rows_returned=%s duration_ms=%s",
        len(unique),
        bound,
        from_date.isoformat() if from_date else None,
        to_date.isoformat() if to_date else None,
        len(rows),
        duration_ms,
    )
    return rows


async def _fetch_latest_n(
    db: Any,
    symbols: list[str],
    col_names: list[str],
    cols: tuple[Any, ...],
    lookback: int,
) -> list[Any]:
    if _dialect_name(db) == "sqlite":
        return await _fetch_latest_n_portable(db, symbols, cols, lookback)
    sql = text(latest_n_ohlcv_sql(col_names)).bindparams(
        bindparam("symbols", type_=ARRAY(VARCHAR(32))),
        bindparam("lookback"),
    )
    return list((await db.execute(sql, {"symbols": symbols, "lookback": lookback})).all())


async def _fetch_latest_n_portable(
    db: Any,
    symbols: list[str],
    cols: tuple[Any, ...],
    lookback: int,
) -> list[Any]:
    """SQLite / tests: per-symbol DESC LIMIT, then chronological order."""
    rows: list[Any] = []
    for symbol in symbols:
        stmt = (
            select(*cols)
            .where(DailyOhlcv.symbol == symbol)
            .order_by(DailyOhlcv.trade_date.desc())
            .limit(lookback)
        )
        part = list((await db.execute(stmt)).all())
        part.reverse()
        rows.extend(part)
    return rows


async def _fetch_unbounded_chunked(db: Any, symbols: list[str], cols: tuple[Any, ...]) -> list[Any]:
    rows: list[Any] = []
    for chunk in iter_symbol_chunks(symbols):
        stmt = select(*cols).where(DailyOhlcv.symbol.in_(chunk))
        rows.extend((await db.execute(stmt)).all())
    return rows


async def _fetch_date_range_chunked(
    db: Any,
    symbols: list[str],
    cols: tuple[Any, ...],
    *,
    from_date: date,
    to_date: date | None = None,
) -> list[Any]:
    """Indexed per-chunk history: symbol IN (...) AND trade_date >= from_date."""
    rows: list[Any] = []
    for chunk in iter_symbol_chunks(symbols):
        stmt = select(*cols).where(
            DailyOhlcv.symbol.in_(chunk),
            DailyOhlcv.trade_date >= from_date,
        )
        if to_date is not None:
            stmt = stmt.where(DailyOhlcv.trade_date <= to_date)
        stmt = stmt.order_by(DailyOhlcv.symbol.asc(), DailyOhlcv.trade_date.asc())
        rows.extend((await db.execute(stmt)).all())
    return rows
