"""Bulk upsert and query helpers for strategy-grade market data."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ...db.session import AsyncSessionLocal
from ...models.strategy_market_data import DailyOhlcv, IndexOhlcv


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _dec(v: Any) -> Decimal:
    return Decimal(str(v))


async def max_equity_trade_date(symbols: list[str] | None = None) -> date | None:
    async with AsyncSessionLocal() as db:
        stmt = select(func.max(DailyOhlcv.trade_date))
        if symbols:
            stmt = stmt.where(DailyOhlcv.symbol.in_(symbols))
        return (await db.execute(stmt)).scalar_one_or_none()


async def max_index_trade_date(symbol: str = "NIFTY500") -> date | None:
    async with AsyncSessionLocal() as db:
        stmt = select(func.max(IndexOhlcv.trade_date)).where(IndexOhlcv.symbol == symbol)
        return (await db.execute(stmt)).scalar_one_or_none()


async def symbols_present_on(trade_date: date, symbols: list[str] | None = None) -> set[str]:
    async with AsyncSessionLocal() as db:
        stmt = select(DailyOhlcv.symbol).where(DailyOhlcv.trade_date == trade_date)
        if symbols:
            stmt = stmt.where(DailyOhlcv.symbol.in_(symbols))
        rows = (await db.execute(stmt)).scalars().all()
        return set(rows)


async def index_present(trade_date: date, symbol: str = "NIFTY500") -> bool:
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
    """Idempotent upsert. Returns (inserted_or_updated_count, 0) — PG upsert doesn't split easily.

    Delivery fields: only overwrite when the incoming row has a non-null value
    (COALESCE) so OHLCV-only rewrites do not wipe prior delivery backfill.
    """
    if not rows:
        return 0, 0
    loaded_at = _utc_now()
    payload = []
    for r in rows:
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
    return len(payload), 0


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
    if not rows:
        return 0
    loaded_at = _utc_now()
    payload = []
    for r in rows:
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
    async with AsyncSessionLocal() as db:
        stmt = pg_insert(IndexOhlcv).values(payload)
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


async def fetch_equity_history(
    symbol: str,
    *,
    from_date: date | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        stmt = select(DailyOhlcv).where(DailyOhlcv.symbol == symbol)
        if from_date:
            stmt = stmt.where(DailyOhlcv.trade_date >= from_date)
        stmt = stmt.order_by(DailyOhlcv.trade_date.asc())
        if limit:
            stmt = stmt.limit(limit)
        rows = (await db.scalars(stmt)).all()
        return [
            {
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
            for r in rows
        ]


async def fetch_index_history(
    symbol: str = "NIFTY500",
    *,
    from_date: date | None = None,
) -> list[dict[str, Any]]:
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
    async with AsyncSessionLocal() as db:
        cnt = (
            await db.execute(
                select(func.count()).select_from(DailyOhlcv).where(DailyOhlcv.symbol == symbol)
            )
        ).scalar() or 0
        return int(cnt) >= min_rows
