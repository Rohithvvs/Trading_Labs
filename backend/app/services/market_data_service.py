import pandas as pd
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import time
import random
import asyncio
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, func
from sqlalchemy.exc import OperationalError
from ..db.session import (
    engine,
    AsyncSessionLocal,
    is_asyncpg_concurrency_error,
    is_db_connection_error,
    session_scope,
)
from ..models.market_data import HistoricalCandle
from ..utils import get_logger, safe_int

logger = get_logger("app.market_data")

_IST = ZoneInfo("Asia/Kolkata")
# Rewrite the boundary bar when the missing window is short. A mid-session
# scan stores a forming daily candle; the next day's first scan must replace
# that print with the completed bar instead of starting strictly after it.
_REWRITE_BOUNDARY_DAYS = 10

# Bound concurrent writers so we never thrash the asyncpg pool (pool_size=20).
# Each upsert opens one session; keep well below pool to leave headroom for
# market-engine, locks, and request sessions.
_UPSERT_MAX_CONCURRENCY = 4

class MarketDataService:
    async def get_latest_candle_time(self, symbol: str, timeframe: str) -> datetime | None:
        async with AsyncSessionLocal() as db:
            stmt = select(HistoricalCandle.timestamp).where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.resolution == timeframe
            ).order_by(HistoricalCandle.timestamp.desc()).limit(1)
            result = (await db.execute(stmt)).scalar_one_or_none()
            return result

    async def get_candle_count(self, symbol: str, timeframe: str) -> int:
        async with AsyncSessionLocal() as db:
            stmt = select(func.count(HistoricalCandle.timestamp)).where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.resolution == timeframe
            )
            result = (await db.execute(stmt)).scalar()
            return result or 0

    async def validate_candle_continuity(self, symbol: str, timeframe: str, expected_count: int):
        from .cache_state import CacheState, CacheHealthContext
        count = await self.get_candle_count(symbol, timeframe)
        latest = await self.get_latest_candle_time(symbol, timeframe)
        
        if count == 0 or not latest:
            return CacheHealthContext(
                symbol=symbol, timeframe=timeframe, cached_rows=0, required_rows=expected_count,
                continuity_gap_count=0, cache_state=CacheState.EMPTY, is_valid_for_indicators=False
            )
            
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        latest_no_tz = latest.replace(tzinfo=None) if latest.tzinfo else latest
        staleness_minutes = (now - latest_no_tz).total_seconds() / 60.0
        
        is_fresh = False
        if timeframe == '1m' and staleness_minutes <= 5: is_fresh = True
        elif timeframe == '5m' and staleness_minutes <= 15: is_fresh = True
        elif timeframe == '15m' and staleness_minutes <= 30: is_fresh = True
        elif timeframe == '1D' and staleness_minutes <= 2880: is_fresh = True
            
        is_complete = count >= expected_count
        # Expensive gap/duplicate scans only when history is complete enough to be usable.
        # Incomplete caches are already invalid for indicators — skip full-table reads.
        gap_count = 0
        if is_complete:
            async with AsyncSessionLocal() as db:
                dup_stmt = select(HistoricalCandle.timestamp).where(
                    HistoricalCandle.symbol == symbol, HistoricalCandle.resolution == timeframe
                ).group_by(HistoricalCandle.timestamp).having(func.count(HistoricalCandle.timestamp) > 1)
                duplicates = (await db.execute(dup_stmt)).fetchall()

                if duplicates:
                    logger.error("corrupted_cache_duplicates", extra={"symbol": symbol, "resolution": timeframe})
                    return CacheHealthContext(
                        symbol=symbol, timeframe=timeframe, cached_rows=count, required_rows=expected_count,
                        continuity_gap_count=len(duplicates), cache_state=CacheState.CORRUPTED, is_valid_for_indicators=False
                    )

            # Sample-based gap check: only inspect index spacing, still one load, but only for complete caches.
            df = await self.load_full_history(symbol, timeframe)
            if df is not None and not df.empty:
                df = df.sort_index()
                diffs = df.index.to_series().diff()
                if timeframe == '1D':
                    gaps = diffs[diffs > pd.Timedelta(days=5)]
                    gap_count = len(gaps)
                    if gap_count > 0:
                        logger.error("corrupted_candle_ranges", extra={"symbol": symbol, "timeframe": timeframe, "gap_count": gap_count})

        if gap_count > 0:
            state = CacheState.CORRUPTED
            is_complete = False
        elif is_fresh and is_complete:
            state = CacheState.FRESH_COMPLETE
        elif is_fresh and not is_complete:
            state = CacheState.FRESH_INCOMPLETE
        elif not is_fresh and is_complete:
            state = CacheState.STALE_COMPLETE
        else:
            state = CacheState.STALE_INCOMPLETE
            
        if not is_complete and state != CacheState.CORRUPTED:
            logger.warning("insufficient_indicator_history", extra={
                "symbol": symbol, "timeframe": timeframe, "cached_rows": count, "required_rows": expected_count, "cache_state": state.value
            })
            
        return CacheHealthContext(
            symbol=symbol, timeframe=timeframe, cached_rows=count, required_rows=expected_count,
            continuity_gap_count=gap_count, cache_state=state, is_valid_for_indicators=is_complete
        )

    def check_stale_candles(self, symbol: str, timeframe: str, latest_timestamp: datetime | None):
        if not latest_timestamp:
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if latest_timestamp.tzinfo is not None:
            latest_timestamp = latest_timestamp.replace(tzinfo=None)
            
        staleness_minutes = (now - latest_timestamp).total_seconds() / 60.0

        is_stale = False
        if timeframe == '1m' and staleness_minutes > 5:
            is_stale = True
        elif timeframe == '5m' and staleness_minutes > 15:
            is_stale = True
        elif timeframe == '15m' and staleness_minutes > 30:
            is_stale = True
        elif timeframe == '1D' and staleness_minutes > 2880:  # 2 days
            is_stale = True

        if is_stale:
            logger.warning(
                "stale_candle_detected",
                extra={
                    "symbol": symbol,
                    "resolution": timeframe,
                    "latest_timestamp": latest_timestamp.isoformat(),
                    "staleness_minutes": staleness_minutes,
                }
            )

    async def upsert_candles(self, symbol: str, timeframe: str, candles_df: pd.DataFrame):
        """
        Upserts candles into the database efficiently in chunks.

        When Authoritative Candle Store is enabled, routes writes through ACS
        so historical_candles has a single write owner (audit H7 / FR-001).
        """
        if candles_df.empty:
            return

        # 1. Prepare Records
        records = []
        for timestamp, row in candles_df.iterrows():
            if hasattr(timestamp, "to_pydatetime"):
                timestamp = timestamp.to_pydatetime()
            if getattr(timestamp, "tzinfo", None) is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
                
            records.append({
                "symbol": symbol,
                "resolution": timeframe,
                "timestamp": timestamp,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": safe_int(row["volume"], symbol=symbol, field="volume")
            })

        try:
            from ..config.settings import settings as _settings

            if _settings.is_authoritative_candle_store_enabled():
                from .authoritative_candle_store import authoritative_candle_store

                await authoritative_candle_store.ingest_candles(
                    symbol=symbol,
                    resolution=timeframe,
                    candles=records,
                    source="MARKET_DATA_SERVICE",
                )
                return
        except Exception as acs_exc:
            logger.warning(
                "acs_upsert_route_failed | symbol=%s | timeframe=%s | error=%s | falling_back_direct",
                symbol,
                timeframe,
                acs_exc,
            )

        # 3. PostgreSQL Batching: Chunk the batches to 900
        MAX_CHUNK_SIZE = 900
        for i in range(0, len(records), MAX_CHUNK_SIZE):
            chunk = records[i:i + MAX_CHUNK_SIZE]
            await self._upsert_chunk(symbol, timeframe, chunk)

    async def _upsert_chunk(self, symbol: str, timeframe: str, chunk_records: list[dict]):
        batch_size = len(chunk_records)
        new_timestamps = {r["timestamp"] for r in chunk_records}
        
        # 2. Retry Safety: Exponential Backoff & Jitter
        max_retries = 5
        base_delay = 0.5

        for attempt in range(1, max_retries + 1):
            start_time = time.monotonic()
            inserted_count = 0
            updated_count = 0
            duplicate_count = 0
            try:
                # One session owns the write transaction end-to-end.
                # Never nest a second AsyncSession inside this context — that
                # pattern contributed to asyncpg "another operation in progress".
                async with session_scope(
                    worker_id=symbol, agent_name="market_data.upsert_chunk"
                ) as db:
                    async with db.begin():
                        existing_stmt = select(HistoricalCandle.timestamp).where(
                            HistoricalCandle.symbol == symbol,
                            HistoricalCandle.resolution == timeframe,
                            HistoricalCandle.timestamp.in_(new_timestamps)
                        )
                        existing_ts = set((await db.scalars(existing_stmt)).all())
                        duplicate_count = len(existing_ts)
                        updated_count = duplicate_count
                        inserted_count = batch_size - duplicate_count

                        stmt = pg_insert(HistoricalCandle).values(chunk_records)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["symbol", "resolution", "timestamp"],
                            set_={
                                "open": stmt.excluded.open,
                                "high": stmt.excluded.high,
                                "low": stmt.excluded.low,
                                "close": stmt.excluded.close,
                                "volume": stmt.excluded.volume,
                                "updated_at": func.now(),
                            },
                        )
                        await db.execute(stmt)

                # Post-commit verification uses a *separate* session after the
                # writer is fully closed (no nested connection checkout).
                async with session_scope(
                    worker_id=symbol, agent_name="market_data.upsert_verify"
                ) as verify_db:
                    verify_stmt = select(HistoricalCandle.timestamp).where(
                        HistoricalCandle.symbol == symbol,
                        HistoricalCandle.resolution == timeframe
                    ).order_by(HistoricalCandle.timestamp.desc()).limit(1)
                    verified_ts = (await verify_db.execute(verify_stmt)).scalar_one_or_none()
                if not verified_ts:
                    logger.error(
                        "silent_rollback_detected",
                        extra={"symbol": symbol, "resolution": timeframe},
                    )

                elapsed_ms = (time.monotonic() - start_time) * 1000
                logger.info(
                    "pg_chunked_batch_executed",
                    extra={
                        "symbol": symbol,
                        "resolution": timeframe,
                        "inserted_count": inserted_count,
                        "updated_count": updated_count,
                        "duplicate_count": duplicate_count,
                        "batch_size": batch_size,
                        "elapsed_ms": elapsed_ms,
                        "retry_attempt": attempt,
                    }
                )
                return
            except OperationalError as e:
                elapsed_ms = (time.monotonic() - start_time) * 1000
                is_locked = "database is locked" in str(e) or "database table is locked" in str(e)
                retriable = is_locked or is_db_connection_error(e)
                
                if attempt < max_retries and retriable:
                    sleep_time = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    logger.warning(
                        "database_lock_retry",
                        extra={
                            "symbol": symbol,
                            "resolution": timeframe,
                            "attempt": attempt,
                            "max_retries": max_retries,
                            "lock_wait_ms": elapsed_ms,
                            "sleep_time_s": sleep_time,
                            "error": str(e)[:200],
                        }
                    )
                    await asyncio.sleep(sleep_time)
                else:
                    logger.exception(
                        "candle_upsert_failed",
                        extra={
                            "symbol": symbol,
                            "resolution": timeframe,
                            "attempt": attempt,
                            "elapsed_ms": elapsed_ms,
                            "batch_size": batch_size,
                            "error": str(e)
                        }
                    )
                    logger.warning("database_rollback", extra={"symbol": symbol, "resolution": timeframe})
                    raise e
            except Exception as e:
                elapsed_ms = (time.monotonic() - start_time) * 1000
                # Concurrent connection use / pool desync: retry with a fresh session
                if attempt < max_retries and (
                    is_asyncpg_concurrency_error(e) or is_db_connection_error(e)
                ):
                    sleep_time = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    logger.warning(
                        "candle_upsert_concurrency_retry",
                        extra={
                            "symbol": symbol,
                            "resolution": timeframe,
                            "attempt": attempt,
                            "sleep_time_s": sleep_time,
                            "error": str(e)[:200],
                        },
                    )
                    await asyncio.sleep(sleep_time)
                    continue
                logger.error(
                    "candle_upsert_failed",
                    extra={
                        "symbol": symbol,
                        "resolution": timeframe,
                        "attempt": attempt,
                        "elapsed_ms": elapsed_ms,
                        "error": str(e)
                    }
                )
                logger.warning("database_rollback", extra={"symbol": symbol, "resolution": timeframe})
                raise e

    async def load_full_history(self, symbol: str, timeframe: str) -> pd.DataFrame:
        query = select(
            HistoricalCandle.timestamp.label("date"),
            HistoricalCandle.open,
            HistoricalCandle.high,
            HistoricalCandle.low,
            HistoricalCandle.close,
            HistoricalCandle.volume
        ).where(
            HistoricalCandle.symbol == symbol,
            HistoricalCandle.resolution == timeframe
        ).order_by(HistoricalCandle.timestamp.asc())
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(query)
            df = pd.DataFrame(result.all(), columns=result.keys())
        if not df.empty:
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            # Cast Decimal columns to native Python types for Pandas arithmetic compatibility
            for col in ("open", "high", "low", "close"):
                if col in df.columns:
                    df[col] = df[col].astype(float)
            if "volume" in df.columns:
                df["volume"] = df["volume"].apply(lambda v: safe_int(v, symbol=symbol, field="volume"))
        return df

    async def load_recent_history(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 250,
    ) -> pd.DataFrame:
        """Load at most ``limit`` most-recent candles (bounded; scanner-critical path).

        Returns chronological order (oldest→newest) for indicator compatibility.
        Prefer this over ``load_full_history`` when only a lookback window is needed.
        """
        if limit is None or int(limit) <= 0:
            return await self.load_full_history(symbol, timeframe)

        lim = int(limit)
        query = (
            select(
                HistoricalCandle.timestamp.label("date"),
                HistoricalCandle.open,
                HistoricalCandle.high,
                HistoricalCandle.low,
                HistoricalCandle.close,
                HistoricalCandle.volume,
            )
            .where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.resolution == timeframe,
            )
            .order_by(HistoricalCandle.timestamp.desc())
            .limit(lim)
        )

        async with AsyncSessionLocal() as db:
            result = await db.execute(query)
            rows = result.all()
            keys = result.keys()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=keys)
        df.set_index("date", inplace=True)
        # Query was DESC for LIMIT; restore chronological order for EMA/indicators.
        df.sort_index(inplace=True)
        for col in ("open", "high", "low", "close"):
            if col in df.columns:
                df[col] = df[col].astype(float)
        if "volume" in df.columns:
            df["volume"] = df["volume"].apply(lambda v: safe_int(v, symbol=symbol, field="volume"))
        return df

    @staticmethod
    def symbol_lookup_variants(symbol: str) -> list[str]:
        """All plausible stored forms for a universe symbol (handles NSE: / -EQ drift)."""
        from ..utils.symbol import ohlcv_symbol_variants

        return ohlcv_symbol_variants(symbol)

    async def get_candle_meta_batch(
        self,
        symbols: list[str],
        timeframe: str,
    ) -> dict[str, tuple[int, datetime | None, str | None, datetime | None]]:
        """
        Return {universe_symbol: (row_count, latest_timestamp, stored_db_symbol, updated_at)} for a universe.

        Resolves symbol-format drift (RELIANCE vs RELIANCE-EQ vs NSE:RELIANCE-EQ) so a warm
        cache is not treated as a miss and forced through FYERS.  The 3rd element is the
        actual stored symbol name, which callers can use directly without a second meta query.
        """
        if not symbols:
            return {}

        meta: dict[str, tuple[int, datetime | None, str | None, datetime | None]] = {
            symbol: (0, None, None, None) for symbol in symbols
        }
        # Map every DB variant -> original universe symbol(s)
        variant_to_universe: dict[str, list[str]] = {}
        all_variants: list[str] = []
        for symbol in symbols:
            for v in self.symbol_lookup_variants(symbol):
                variant_to_universe.setdefault(v, []).append(symbol)
                all_variants.append(v)
        # unique variants for the query
        unique_variants = list(dict.fromkeys(all_variants))

        chunk_size = 300
        db_meta: dict[str, tuple[int, datetime | None, datetime | None]] = {}
        db_symbol_names: dict[str, str] = {}
        for i in range(0, len(unique_variants), chunk_size):
            chunk = unique_variants[i : i + chunk_size]
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(
                        HistoricalCandle.symbol,
                        func.count(HistoricalCandle.timestamp),
                        func.max(HistoricalCandle.timestamp),
                        func.max(HistoricalCandle.updated_at),
                    )
                    .where(
                        HistoricalCandle.symbol.in_(chunk),
                        HistoricalCandle.resolution == timeframe,
                    )
                    .group_by(HistoricalCandle.symbol)
                )
                rows = (await db.execute(stmt)).all()
            for symbol, count, latest, updated_at in rows:
                db_meta[symbol] = (int(count or 0), latest, updated_at)
                db_symbol_names[symbol] = symbol

        # Prefer the variant with the richest history for each universe symbol
        for db_symbol, (count, latest, updated_at) in db_meta.items():
            for universe_symbol in variant_to_universe.get(db_symbol, []):
                prev_count = meta[universe_symbol][0]
                if count > prev_count:
                    meta[universe_symbol] = (count, latest, db_symbol, updated_at)
        return meta

    async def resolve_stored_symbol_map(
        self,
        symbols: list[str],
        timeframe: str,
        meta_result: dict[str, tuple] | None = None,
    ) -> dict[str, str]:
        """
        Map universe symbol -> best matching stored HistoricalCandle.symbol (if any).
        When meta_result from get_candle_meta_batch is provided, the stored symbol
        name is extracted from it directly — no additional query needed.
        """
        if not symbols:
            return {}
        if meta_result is not None:
            return {
                sym: row[2]
                for sym, row in meta_result.items()
                if len(row) > 2 and row[2] is not None
            }
        variant_to_universe: dict[str, list[str]] = {}
        unique_variants: list[str] = []
        for symbol in symbols:
            for v in self.symbol_lookup_variants(symbol):
                variant_to_universe.setdefault(v, []).append(symbol)
                if v not in variant_to_universe or True:
                    unique_variants.append(v)
        unique_variants = list(dict.fromkeys(unique_variants))

        best: dict[str, tuple[str, int]] = {}  # universe -> (db_symbol, count)
        chunk_size = 300
        for i in range(0, len(unique_variants), chunk_size):
            chunk = unique_variants[i : i + chunk_size]
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(
                        HistoricalCandle.symbol,
                        func.count(HistoricalCandle.timestamp),
                    )
                    .where(
                        HistoricalCandle.symbol.in_(chunk),
                        HistoricalCandle.resolution == timeframe,
                    )
                    .group_by(HistoricalCandle.symbol)
                )
                rows = (await db.execute(stmt)).all()
            for db_symbol, count in rows:
                for universe_symbol in variant_to_universe.get(db_symbol, []):
                    prev = best.get(universe_symbol)
                    if prev is None or int(count or 0) > prev[1]:
                        best[universe_symbol] = (db_symbol, int(count or 0))
        return {u: db_sym for u, (db_sym, _) in best.items()}

    async def load_histories_batch(
        self,
        symbols: list[str],
        timeframe: str,
        stored_symbol_map: dict[str, str] | None = None,
        max_bars: int | None = None,
    ) -> dict[str, pd.DataFrame]:
        """
        Load daily histories for many symbols with chunked IN queries.

        Performance (scanner path):
        - ``max_bars`` limits each symbol to its most recent N bars (SMA200 needs ~240).
          Full multi-year histories were the dominant scan cost (~120s for 755 symbols).
        - Chunks load concurrently (bounded) instead of strictly sequential.

        If stored_symbol_map is provided, loads by DB symbol and returns frames keyed
        by the original universe symbol.
        """
        if not symbols:
            return {}

        # Swing indicators need ~240 bars; keep a small buffer for ffill / gaps.
        bar_limit = int(max_bars) if max_bars and max_bars > 0 else None
        if bar_limit is not None:
            bar_limit = max(60, min(bar_limit, 2000))

        stored_symbol_map = stored_symbol_map or {s: s for s in symbols}
        # universe -> db symbol (only those that map)
        universe_to_db = {u: stored_symbol_map.get(u, u) for u in symbols}
        db_to_universe: dict[str, list[str]] = {}
        for u, db_s in universe_to_db.items():
            db_to_universe.setdefault(db_s, []).append(u)

        db_symbols = list(db_to_universe.keys())
        frames: dict[str, pd.DataFrame] = {symbol: pd.DataFrame() for symbol in symbols}
        # Larger chunks + parallel load: fewer round-trips over Neon latency.
        # Sequential 80-symbol chunks over Neon were ~12s each × 10 ≈ 120s.
        chunk_size = 150 if bar_limit else 100
        chunks = [db_symbols[i : i + chunk_size] for i in range(0, len(db_symbols), chunk_size)]
        load_sem = asyncio.Semaphore(6)

        async def _load_chunk(chunk: list[str]) -> dict[str, list[dict]]:
            async with load_sem:
                if bar_limit is not None:
                    # Keep only the latest N bars per symbol (SMA200 needs ~240).
                    rn = func.row_number().over(
                        partition_by=HistoricalCandle.symbol,
                        order_by=HistoricalCandle.timestamp.desc(),
                    ).label("rn")
                    ranked = (
                        select(
                            HistoricalCandle.symbol.label("symbol"),
                            HistoricalCandle.timestamp.label("date"),
                            HistoricalCandle.open.label("open"),
                            HistoricalCandle.high.label("high"),
                            HistoricalCandle.low.label("low"),
                            HistoricalCandle.close.label("close"),
                            HistoricalCandle.volume.label("volume"),
                            rn,
                        )
                        .where(
                            HistoricalCandle.symbol.in_(chunk),
                            HistoricalCandle.resolution == timeframe,
                        )
                        .subquery()
                    )
                    query = (
                        select(
                            ranked.c.symbol,
                            ranked.c.date,
                            ranked.c.open,
                            ranked.c.high,
                            ranked.c.low,
                            ranked.c.close,
                            ranked.c.volume,
                        )
                        .where(ranked.c.rn <= bar_limit)
                        .order_by(ranked.c.symbol.asc(), ranked.c.date.asc())
                    )
                else:
                    query = (
                        select(
                            HistoricalCandle.symbol,
                            HistoricalCandle.timestamp.label("date"),
                            HistoricalCandle.open,
                            HistoricalCandle.high,
                            HistoricalCandle.low,
                            HistoricalCandle.close,
                            HistoricalCandle.volume,
                        )
                        .where(
                            HistoricalCandle.symbol.in_(chunk),
                            HistoricalCandle.resolution == timeframe,
                        )
                        .order_by(HistoricalCandle.symbol.asc(), HistoricalCandle.timestamp.asc())
                    )
                async with AsyncSessionLocal() as db:
                    result = await db.execute(query)
                    rows = result.all()

                by_db: dict[str, list[dict]] = {symbol: [] for symbol in chunk}
                for row in rows:
                    by_db[row.symbol].append(
                        {
                            "date": row.date,
                            "open": row.open,
                            "high": row.high,
                            "low": row.low,
                            "close": row.close,
                            "volume": row.volume,
                        }
                    )
                return by_db

        chunk_results = await asyncio.gather(*(_load_chunk(c) for c in chunks))
        for by_db in chunk_results:
            for db_symbol, symbol_rows in by_db.items():
                if not symbol_rows:
                    continue
                df = pd.DataFrame(symbol_rows)
                df.set_index("date", inplace=True)
                df.sort_index(inplace=True)
                for col in ("open", "high", "low", "close"):
                    df[col] = df[col].astype(float)
                if "volume" in df.columns:
                    df["volume"] = df["volume"].apply(
                        lambda v, s=db_symbol: safe_int(v, symbol=s, field="volume")
                    )
                for universe_symbol in db_to_universe.get(db_symbol, [db_symbol]):
                    frames[universe_symbol] = df
        return frames

    async def upsert_candles_multi(
        self,
        updates: list[tuple[str, str, pd.DataFrame]],
    ) -> int:
        """
        Upsert candle frames for many symbols. Returns number of symbols written.

        Each symbol uses its own AsyncSession (via upsert_candles/_upsert_chunk).
        Concurrency is capped below the pool size so market-engine / request
        sessions still have free connections — prevents asyncpg
        "another operation is in progress" under scan load.
        """
        if not updates:
            return 0
        upsert_sem = asyncio.Semaphore(_UPSERT_MAX_CONCURRENCY)

        async def _upsert_one(
            idx: int, symbol: str, timeframe: str, df: pd.DataFrame
        ) -> int:
            if df is None or df.empty:
                return 0
            async with upsert_sem:
                logger.debug(
                    "QUERY_START | op=upsert_candles | worker_id=%s | symbol=%s | timeframe=%s",
                    idx,
                    symbol,
                    timeframe,
                )
                t0 = time.monotonic()
                try:
                    await self.upsert_candles(symbol, timeframe, df)
                finally:
                    logger.debug(
                        "QUERY_END | op=upsert_candles | worker_id=%s | symbol=%s | elapsed_ms=%.0f",
                        idx,
                        symbol,
                        (time.monotonic() - t0) * 1000,
                    )
            return 1

        results = await asyncio.gather(
            *(_upsert_one(i, sym, tf, d) for i, (sym, tf, d) in enumerate(updates)),
            return_exceptions=True,
        )
        written = 0
        errors: list[BaseException] = []
        for r in results:
            if isinstance(r, BaseException):
                errors.append(r)
            else:
                written += int(r or 0)
        if errors:
            # Re-raise first concurrency/connection error so scan can fail cleanly
            # after partial progress; remaining symbols already logged in upsert.
            logger.error(
                "upsert_candles_multi partial failure | written=%s | failed=%s | first_error=%s",
                written,
                len(errors),
                str(errors[0])[:200],
            )
            raise errors[0]
        return written

    @staticmethod
    def is_daily_cache_fresh_enough(
        count: int,
        latest: datetime | None,
        required_history: int,
        max_staleness_minutes: float = 2880.0,
    ) -> bool:
        """True when DB history is complete enough for swing indicators and not stale (>2d for 1D)."""
        if count < required_history or latest is None:
            return False
        latest_no_tz = latest.replace(tzinfo=None) if getattr(latest, "tzinfo", None) else latest
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        staleness_minutes = (now - latest_no_tz).total_seconds() / 60.0
        return staleness_minutes <= max_staleness_minutes


def candle_session_date(ts: datetime | date | None) -> date | None:
    """NSE session date for a stored daily candle. Naive timestamps are UTC."""
    if ts is None:
        return None
    try:
        if pd.isna(ts):
            return None
    except TypeError:
        pass
    if isinstance(ts, datetime):
        pass
    elif isinstance(ts, date):
        return ts
    elif hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    else:
        return None
    if not isinstance(ts, datetime):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(_IST).date()


def required_scanner_session(now: datetime | None = None) -> date:
    """Latest daily session Run Scanner must hold before it can skip Fyers.

    After the NSE cash open, that session is today so the scan sees the
    forming (or just-closed) bar. Before the open, and on non-trading days,
    it is the last completed session.
    """
    from .trading_hours_service import OPEN_TIME, TradingHoursService, trading_hours
    from .market_data_ingestion.calendar_utils import expected_last_completed_session

    th = trading_hours if trading_hours is not None else TradingHoursService()
    ist = th._to_ist(now)
    if th.is_trading_day(ist) and ist.time() >= OPEN_TIME:
        return ist.date()
    return expected_last_completed_session(ist)


def _ist_calendar_day(ts: datetime | None) -> date | None:
    if ts is None:
        return None
    return candle_session_date(ts)


def cache_covers_required_session(
    count: int,
    latest: datetime | None,
    required_history: int,
    now: datetime | None = None,
    *,
    required_session: date | None = None,
) -> bool:
    """True when stored daily history already reaches the session the scan needs."""
    if count < required_history or latest is None:
        return False
    session = candle_session_date(latest)
    if session is None:
        return False
    target = required_session or required_scanner_session(now)
    return session >= target


def symbol_needs_daily_fyers_fetch(
    count: int,
    latest: datetime | None,
    required_history: int,
    *,
    updated_at: datetime | None = None,
    now: datetime | None = None,
    required_session: date | None = None,
) -> bool:
    """True when this Run Scanner click must pull daily bars from Fyers.

    The first scan of an IST calendar day refreshes every name and stores the
    result. Later scans that day reuse the database once the required session
    is present and this symbol was written today.
    """
    from .trading_hours_service import TradingHoursService, trading_hours

    if not cache_covers_required_session(
        count,
        latest,
        required_history,
        now,
        required_session=required_session,
    ):
        return True
    th = trading_hours if trading_hours is not None else TradingHoursService()
    today = th._to_ist(now).date()
    written_on = _ist_calendar_day(updated_at)
    return written_on is None or written_on < today


def incremental_history_window(
    last_session: date | None,
    *,
    today: date,
    target: date,
    refresh_latest: bool,
) -> tuple[date, date, str] | None:
    """Inclusive Fyers history window, or None when the cache can be reused.

    A short gap includes the last stored session so a forming bar saved earlier
    is replaced by the completed print. Long gaps stay incremental.
    """
    if last_session is None:
        start = today - timedelta(days=364)
        return start, today, "full_backfill"
    if last_session >= target and not refresh_latest:
        return None
    gap_days = (max(target, today) - last_session).days
    if refresh_latest or gap_days <= _REWRITE_BOUNDARY_DAYS:
        return last_session, today, "daily_refresh" if refresh_latest else "incremental"
    return last_session + timedelta(days=1), today, "incremental"


def session_bar_is_final(session: date, now: datetime | None = None) -> bool:
    """False for today's forming cash bar. Completed sessions are safe to store as EOD."""
    from .trading_hours_service import CLOSE_TIME, TradingHoursService, trading_hours

    th = trading_hours if trading_hours is not None else TradingHoursService()
    ist = th._to_ist(now)
    if session < ist.date():
        return True
    if session > ist.date():
        return False
    if not th.is_trading_day(ist):
        return True
    return ist.time() >= CLOSE_TIME


def strategy_rows_from_scan_frames(
    pending: list[tuple[str, str, pd.DataFrame]],
    *,
    now: datetime | None = None,
) -> list[dict]:
    """Map scanner OHLCV frames onto ``daily_ohlcv`` rows.

    Today's forming bar stays in the candle cache the scanner scores. It is
    not written into the EOD store until the cash session has closed.
    """
    from ..utils import safe_int
    from ..utils.symbol import strategy_daily_symbol

    deduped: dict[tuple[date, str], dict] = {}
    for symbol, timeframe, frame in pending:
        if str(timeframe).upper() not in {"1D", "D", "1d"}:
            continue
        if frame is None or getattr(frame, "empty", True):
            continue
        store_symbol = strategy_daily_symbol(symbol)
        if not store_symbol:
            continue
        for ts, row in frame.iterrows():
            session = candle_session_date(ts)
            if session is None or not session_bar_is_final(session, now):
                continue
            deduped[(session, store_symbol)] = {
                "trade_date": session,
                "symbol": store_symbol,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": safe_int(row.get("volume"), symbol=store_symbol, field="volume") or 0,
                "source": "FYERS",
            }
    return [deduped[key] for key in sorted(deduped)]


async def persist_fyers_scan_bars(
    pending: list[tuple[str, str, pd.DataFrame]],
    *,
    refresh_index: bool = False,
    now: datetime | None = None,
) -> dict:
    """Store Fyers bars fetched for Run Scanner into ``daily_ohlcv`` and ``index_ohlcv``."""
    rows = strategy_rows_from_scan_frames(pending, now=now)
    saved = {
        "daily_upserted": 0,
        "daily_rejected": 0,
        "index_upserted": 0,
        "index_fetched": 0,
    }
    if rows:
        from .market_data_ingestion.repository import upsert_daily_bars

        chunk = 400
        for i in range(0, len(rows), chunk):
            accepted, rejected = await upsert_daily_bars(rows[i : i + chunk])
            saved["daily_upserted"] += int(accepted or 0)
            saved["daily_rejected"] += int(rejected or 0)
        logger.info(
            "SCANNER_DAILY_OHLCV_STORED | rows=%s | upserted=%s | rejected=%s",
            len(rows),
            saved["daily_upserted"],
            saved["daily_rejected"],
        )

    if refresh_index or rows:
        try:
            from .market_data_ingestion.providers.fyers_eod import FyersEodProvider
            from .market_data_ingestion.repository import upsert_index_bars
            from .trading_hours_service import TradingHoursService, trading_hours

            th = trading_hours if trading_hours is not None else TradingHoursService()
            today = th._to_ist(now).date()
            if rows:
                start = min(r["trade_date"] for r in rows)
                end = max(r["trade_date"] for r in rows)
            else:
                start = end = required_scanner_session(now)
            if end > today:
                end = today
            if start > end:
                start = end
            index_rows = await FyersEodProvider().fetch_index_range(start, end)
            saved["index_fetched"] = len(index_rows)
            final_index = [
                row
                for row in index_rows
                if isinstance(row.get("trade_date"), date)
                and session_bar_is_final(row["trade_date"], now)
            ]
            if final_index:
                saved["index_upserted"] = int(await upsert_index_bars(final_index) or 0)
            logger.info(
                "SCANNER_INDEX_OHLCV_STORED | fetched=%s | upserted=%s | from=%s | to=%s",
                saved["index_fetched"],
                saved["index_upserted"],
                start.isoformat(),
                end.isoformat(),
            )
        except Exception as exc:
            logger.warning("SCANNER_INDEX_OHLCV_FAILED | err=%s", type(exc).__name__)
    return saved
