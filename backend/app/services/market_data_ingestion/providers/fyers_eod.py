"""FYERS EOD equity/index history adapter wrapping FyersService."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ....config.settings import settings
from ....utils import safe_int

logger = logging.getLogger("app.market_data_ingestion.fyers_eod")

# FYERS history rejects multi-year daily ranges in a single request (code=-50).
# Keep each request to at most this many calendar days (inclusive window length).
_MAX_CHUNK_DAYS = 365


def _iter_date_chunks(range_from: date, range_to: date, max_days: int = _MAX_CHUNK_DAYS):
    """Yield inclusive [chunk_start, chunk_end] windows of at most max_days calendar days."""
    if range_from > range_to:
        return
    # Inclusive length: max_days means end = start + (max_days - 1)
    step = max(1, int(max_days) - 1)
    cur = range_from
    while cur <= range_to:
        end = min(cur + timedelta(days=step), range_to)
        yield cur, end
        cur = end + timedelta(days=1)


class FyersEodProvider:
    def __init__(self, fyers_service: Any | None = None) -> None:
        self._fyers = fyers_service
        # Reuse one SDK client for the whole ensure/load run — recreating per symbol
        # flooded logs with "Scanner token loaded successfully" and paid a sync cost
        # on every history call.
        self._client: Any | None = None
        self._client_lock = asyncio.Lock()

    def _svc(self):
        if self._fyers is None:
            from ...fyers_service import FyersService

            self._fyers = FyersService()
        return self._fyers

    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is not None:
                return self._client
            svc = self._svc()
            self._client = await asyncio.to_thread(svc._client)
            logger.info("FYERS_EOD_CLIENT_READY | source=token_cache_or_db")
            return self._client

    async def fetch_daily_range(
        self,
        symbol: str,
        range_from: date,
        range_to: date,
    ) -> list[dict[str, Any]]:
        """Fetch daily OHLCV for [range_from, range_to] inclusive (chunked for FYERS limits)."""
        if range_from > range_to:
            return []

        by_date: dict[date, dict[str, Any]] = {}
        chunks = list(_iter_date_chunks(range_from, range_to))
        for chunk_from, chunk_to in chunks:
            rows = await self._fetch_daily_chunk(symbol, chunk_from, chunk_to)
            for bar in rows:
                by_date[bar["trade_date"]] = bar

        if len(chunks) > 1:
            logger.info(
                "FYERS_EOD_CHUNKED | symbol=%s | chunks=%s | from=%s | to=%s | bars=%s",
                symbol,
                len(chunks),
                range_from.isoformat(),
                range_to.isoformat(),
                len(by_date),
            )
        return [by_date[d] for d in sorted(by_date)]

    async def _fetch_daily_chunk(
        self,
        symbol: str,
        range_from: date,
        range_to: date,
    ) -> list[dict[str, Any]]:
        """Single FYERS history request for one date window."""
        svc = self._svc()
        client = await self._get_client()
        payload = {
            "symbol": svc._normalize_symbol(symbol),
            "resolution": "1D",
            "date_format": "1",
            "range_from": range_from.isoformat(),
            "range_to": range_to.isoformat(),
            "cont_flag": "1",
        }
        t0 = datetime.now(timezone.utc)
        try:
            loop = asyncio.get_running_loop()
            logger.info(
                "FYERS_EOD_REQUEST | symbol=%s | from=%s | to=%s",
                symbol,
                range_from.isoformat(),
                range_to.isoformat(),
            )
            response = await loop.run_in_executor(
                svc._network_pool,
                svc._request_history_with_retries, client, payload, symbol
            )
            ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
            n_candles = len((response or {}).get("candles") or []) if isinstance(response, dict) else 0
            logger.info(
                "FYERS_EOD_RESPONSE | symbol=%s | candles=%s | duration_ms=%s",
                symbol,
                n_candles,
                ms,
            )
        except Exception as exc:
            logger.warning(
                "FYERS_EOD_FAILED | symbol=%s | from=%s | to=%s | error=%s",
                symbol,
                range_from.isoformat(),
                range_to.isoformat(),
                type(exc).__name__,
            )
            raise

        candles = response.get("candles") if isinstance(response, dict) else None
        if not candles:
            return []
        out: list[dict[str, Any]] = []
        for row in candles:
            if not row or len(row) < 6:
                continue
            ts = row[0]
            if isinstance(ts, (int, float)):
                # FYERS may return epoch seconds
                if ts > 10_000_000_000:
                    ts = ts / 1000.0
                trade_d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            else:
                trade_d = date.fromisoformat(str(ts)[:10])
            if trade_d < range_from or trade_d > range_to:
                continue
            out.append(
                {
                    "trade_date": trade_d,
                    "symbol": symbol,
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": safe_int(row[5], symbol=symbol, field="volume") or 0,
                    "source": "FYERS",
                }
            )
        return out

    async def fetch_daily_session(self, symbol: str, session: date) -> dict[str, Any] | None:
        rows = await self.fetch_daily_range(symbol, session, session)
        return rows[0] if rows else None

    async def fetch_index_range(
        self,
        range_from: date,
        range_to: date,
        provider_symbol: str | None = None,
        store_symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        prov = provider_symbol or settings.strategy_index_provider_symbol
        store = store_symbol or settings.strategy_index_store_symbol
        # Provider accepts NSE:NIFTY500-INDEX style; store as NIFTY500
        rows = await self.fetch_daily_range(prov, range_from, range_to)
        for r in rows:
            r["symbol"] = store
            r["source"] = "FYERS"
        return rows
