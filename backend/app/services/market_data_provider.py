"""Canonical Market History Provider abstraction.

Provides a unified interface for loading historical daily OHLCV candles,
index benchmarks, and data quality validation.

Scanner -> MarketHistoryProvider -> Canonical Backend (Turso / Postgres)
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from typing import Any, Protocol, runtime_checkable

from ..config.settings import settings
from ..utils.symbol import canonical_symbol, ohlcv_symbol_variants
from .strategy_tester.indicators import BarSeries

_logger = logging.getLogger("app.market_data.provider")


@runtime_checkable
class MarketHistoryProvider(Protocol):
    """Protocol for historical market-data providers."""

    name: str

    async def get_daily_bars(
        self,
        symbols: list[str],
        *,
        from_date: date,
        to_date: date,
        session_dates: set[date] | None = None,
        chunk_size: int = 250,
    ) -> dict[str, BarSeries]:
        """Fetch daily OHLCV series for a universe of symbols."""
        ...

    async def get_index_bars(
        self,
        symbol: str = "NIFTY500",
        *,
        from_date: date,
        to_date: date,
    ) -> BarSeries | None:
        """Fetch benchmark index bars."""
        ...

    async def check_health(self) -> dict[str, Any]:
        """Verify provider configuration, reachability, and sample query without exposing secrets."""
        ...


class TursoMarketHistoryProvider:
    """Canonical Turso/libSQL historical market-data provider."""

    name = "turso"

    def __init__(self, *, client: Any | None = None) -> None:
        self._custom_client = client

    def _get_client(self) -> Any:
        if self._custom_client is not None:
            return self._custom_client
        from .market_data_ingestion.turso_repository import _client
        return _client()

    async def get_daily_bars(
        self,
        symbols: list[str],
        *,
        from_date: date,
        to_date: date,
        session_dates: set[date] | None = None,
        chunk_size: int = 250,
    ) -> dict[str, BarSeries]:
        if not symbols:
            return {}

        from .market_data_ingestion import turso_repository as turso
        from ..strategy_tester.scan_service import _series_from_rows

        query_symbols: list[str] = []
        seen_query: set[str] = set()
        for s in symbols:
            for variant in ohlcv_symbol_variants(s):
                if variant not in seen_query:
                    seen_query.add(variant)
                    query_symbols.append(variant)

        cols_to_fetch = [
            "trade_date",
            "symbol",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        chunks = [query_symbols[i : i + chunk_size] for i in range(0, len(query_symbols), chunk_size)]
        sem = asyncio.Semaphore(4)
        client = self._get_client()

        async def fetch_chunk(ch: list[str]) -> list[dict[str, Any]]:
            async with sem:
                return await asyncio.to_thread(
                    turso.select_daily_ohlcv_for_symbols,
                    client,
                    ch,
                    from_date=from_date,
                    to_date=to_date,
                    columns=cols_to_fetch,
                )

        chunk_results = await asyncio.gather(*(fetch_chunk(ch) for ch in chunks), return_exceptions=False)

        buckets: dict[str, list[tuple]] = defaultdict(list)
        for rows in chunk_results:
            for r in rows:
                sym = r.get("symbol")
                if not sym:
                    continue
                trade_date = r.get("trade_date")
                open_px = r.get("open")
                high = r.get("high")
                low = r.get("low")
                close = r.get("close")
                volume = r.get("volume", 0)
                canon = canonical_symbol(sym) or sym
                buckets[canon].append((trade_date, open_px, high, low, close, volume))

        out: dict[str, BarSeries] = {}
        for symbol, items in buckets.items():
            items.sort(key=lambda row: row[0])
            out[symbol] = _series_from_rows(items, session_dates=session_dates)
        return out

    async def get_index_bars(
        self,
        symbol: str = "NIFTY500",
        *,
        from_date: date,
        to_date: date,
    ) -> BarSeries | None:
        from .market_data_ingestion import turso_repository as turso
        from ..strategy_tester.scan_service import _series_from_rows

        client = self._get_client()
        rows = await asyncio.to_thread(
            turso.select_index_history,
            client,
            symbol=symbol,
            from_date=from_date,
        )
        filtered = [r for r in rows if r.get("trade_date") and r["trade_date"] <= to_date]
        if not filtered:
            return None
        tuples = [
            (r["trade_date"], r.get("open"), r.get("high"), r.get("low"), r.get("close"), r.get("volume"))
            for r in filtered
        ]
        return _series_from_rows(tuples, apply_holiday_calendar=False)

    async def check_health(self) -> dict[str, Any]:
        """Safely probe Turso historical candle database."""
        configured = settings.turso_configured()
        if not configured:
            return {
                "backend": "turso",
                "configured": False,
                "reachable": False,
                "sample_query": False,
                "error": "TURSO_DATABASE_URL or TURSO_AUTH_TOKEN is not configured.",
            }

        try:
            client = self._get_client()

            def _probe():
                rows = client.execute("SELECT max(trade_date) AS max_date FROM daily_ohlcv")
                return rows[0] if rows else {}

            sample = await asyncio.wait_for(asyncio.to_thread(_probe), timeout=5.0)
            return {
                "backend": "turso",
                "configured": True,
                "reachable": True,
                "sample_query": True,
                "max_trade_date": sample.get("max_date"),
            }
        except Exception as exc:
            _logger.warning("TURSO_HEALTH_PROBE_FAILED | err=%s", exc)
            return {
                "backend": "turso",
                "configured": True,
                "reachable": False,
                "sample_query": False,
                "error": str(exc)[:200],
            }


class PostgresMarketHistoryProvider:
    """Postgres/Neon historical market-data provider."""

    name = "postgres"

    async def get_daily_bars(
        self,
        symbols: list[str],
        *,
        from_date: date,
        to_date: date,
        session_dates: set[date] | None = None,
        chunk_size: int = 250,
    ) -> dict[str, BarSeries]:
        from .strategy_tester.scan_service import load_bar_series
        return await load_bar_series(
            symbols,
            from_date=from_date,
            to_date=to_date,
            session_dates=session_dates,
            chunk_size=chunk_size,
        )

    async def get_index_bars(
        self,
        symbol: str = "NIFTY500",
        *,
        from_date: date,
        to_date: date,
    ) -> BarSeries | None:
        from .strategy_tester.scan_service import load_benchmark_series
        return await load_benchmark_series(from_date=from_date, to_date=to_date)

    async def check_health(self) -> dict[str, Any]:
        try:
            from sqlalchemy import text
            from ..db.session import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                res = await db.execute(
                    text("SELECT max(trade_date) AS max_date, count(DISTINCT symbol) AS sym_count FROM daily_ohlcv WHERE trade_date >= '2026-09-01'")
                )
                row = res.fetchone()
                return {
                    "backend": "postgres",
                    "configured": True,
                    "reachable": True,
                    "sample_query": True,
                    "max_trade_date": row[0].isoformat() if row and row[0] else None,
                    "recent_symbols_count": row[1] if row else 0,
                }
        except Exception as exc:
            return {
                "backend": "postgres",
                "configured": True,
                "reachable": False,
                "sample_query": False,
                "error": str(exc)[:200],
            }


def get_market_history_provider() -> MarketHistoryProvider:
    """Return the configured canonical MarketHistoryProvider."""
    backend = settings.candle_history_backend_name()
    if backend == "turso":
        if not settings.turso_configured():
            raise RuntimeError(
                "CANDLE_HISTORY_BACKEND=turso requires TURSO_DATABASE_URL and "
                "TURSO_AUTH_TOKEN. Secret values are never logged."
            )
        return TursoMarketHistoryProvider()
    return PostgresMarketHistoryProvider()
