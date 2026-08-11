"""Scan-scoped market regime context (SR-004).

Computes MarketPermissionService result **once** per scan / trading date,
with bounded DB loads and hard timeouts so the scanner never spends the full
global wall-clock budget waiting on INDIAVIX/NIFTY full-history queries.
"""

from __future__ import annotations

import asyncio
import time
from contextvars import ContextVar
from datetime import date, datetime, timezone
from typing import Any

from ..schemas import MarketRegimeResult
from ..utils import get_logger

logger = get_logger("app.scan_market_context")

# Hard budget for a single market-context build (DB + Fyers fallback).
# Must stay well below SCAN_EXECUTION_TIMEOUT so the scan can continue.
_MARKET_CONTEXT_TIMEOUT_SEC = 20.0

# Successful results reusable within the same IST trading day.
_CACHE_TTL_SEC = 300.0

_scan_market_regime: ContextVar[MarketRegimeResult | None] = ContextVar(
    "scan_market_regime", default=None
)

# Process-level date cache + singleflight (shared across workers in one process).
_cache_lock = asyncio.Lock()
_regime_by_date: dict[str, tuple[MarketRegimeResult, float]] = {}
_inflight: dict[str, asyncio.Future] = {}


def _trading_date_key(scan_date: datetime | date | None) -> str:
    if scan_date is None:
        return datetime.now(timezone.utc).date().isoformat()
    if isinstance(scan_date, datetime):
        # Prefer IST calendar date when tz-aware; naive treated as local trading date.
        try:
            import pytz

            if scan_date.tzinfo is not None:
                return scan_date.astimezone(pytz.timezone("Asia/Kolkata")).date().isoformat()
        except Exception:
            pass
        return scan_date.date().isoformat()
    if isinstance(scan_date, date):
        return scan_date.isoformat()
    return str(scan_date)


def _unavailable_regime(reason: str) -> MarketRegimeResult:
    """Safe unavailable state — does not invent bullish/bearish; blocks new entries."""
    return MarketRegimeResult(
        market_state="DEFENSIVE",
        trend_state="UNKNOWN",
        breadth_state="UNKNOWN",
        volatility_state="UNKNOWN",
        data_quality_flags={
            "nifty_data_present": False,
            "nifty_data_fresh": False,
            "vix_data_present": False,
            "vix_data_fresh": False,
            "breadth_data_sufficient": False,
            "market_regime_unavailable": True,
        },
        reasons=[f"market regime unavailable: {reason}"],
        new_entry_allowed=False,
        risk_multiplier=0.0,
        manual_review_flag=True,
    )


def get_scan_market_regime() -> MarketRegimeResult | None:
    return _scan_market_regime.get()


def set_scan_market_regime(regime: MarketRegimeResult | None) -> Any:
    return _scan_market_regime.set(regime)


def reset_scan_market_regime(token: Any) -> None:
    try:
        _scan_market_regime.reset(token)
    except Exception:
        pass


def clear_market_regime_cache() -> None:
    """Test helper — drop process cache and inflight map."""
    _regime_by_date.clear()
    _inflight.clear()


def _cache_get(date_key: str) -> MarketRegimeResult | None:
    entry = _regime_by_date.get(date_key)
    if not entry:
        return None
    regime, expires_at = entry
    if time.monotonic() > expires_at:
        _regime_by_date.pop(date_key, None)
        return None
    # Never reuse an explicit unavailable placeholder as a "valid" hit for long.
    flags = getattr(regime, "data_quality_flags", None) or {}
    if flags.get("market_regime_unavailable"):
        return None
    return regime


def _cache_put(date_key: str, regime: MarketRegimeResult) -> None:
    flags = getattr(regime, "data_quality_flags", None) or {}
    if flags.get("market_regime_unavailable"):
        # Short negative cache only — allow quick retry next call window.
        _regime_by_date[date_key] = (regime, time.monotonic() + 15.0)
        return
    _regime_by_date[date_key] = (regime, time.monotonic() + _CACHE_TTL_SEC)


async def get_or_build_market_regime(
    scan_date: datetime | None = None,
    *,
    scan_id: str | None = None,
    force_refresh: bool = False,
) -> MarketRegimeResult:
    """Return market regime for this scan — at most one real evaluation per date.

    Callers (orchestrator production path, independent lab universe, per-symbol
    fallback) all share this entrypoint so INDIAVIX/NIFTY loads happen once.
    """
    if scan_date is None:
        scan_date = datetime.now(timezone.utc)
    date_key = _trading_date_key(scan_date)
    sid = scan_id or "-"
    t0 = time.perf_counter()

    logger.info(
        "SCAN_MARKET_CONTEXT_START | scan_id=%s | scan_date=%s | force_refresh=%s",
        sid,
        date_key,
        force_refresh,
    )

    # 1) ContextVar — same scan task tree
    if not force_refresh:
        ctx = get_scan_market_regime()
        if ctx is not None:
            logger.info(
                "SCAN_MARKET_CONTEXT_CACHE_HIT | scan_id=%s | scan_date=%s | "
                "duration_ms=%.0f | data_source=contextvar | cache_hit=true | fallback_used=false",
                sid,
                date_key,
                (time.perf_counter() - t0) * 1000,
            )
            return ctx

    # 2) Process date cache
    if not force_refresh:
        cached = _cache_get(date_key)
        if cached is not None:
            set_scan_market_regime(cached)
            logger.info(
                "SCAN_MARKET_CONTEXT_CACHE_HIT | scan_id=%s | scan_date=%s | "
                "duration_ms=%.0f | data_source=process_cache | cache_hit=true | fallback_used=false | "
                "market_state=%s",
                sid,
                date_key,
                (time.perf_counter() - t0) * 1000,
                cached.market_state,
            )
            return cached

    logger.info(
        "SCAN_MARKET_CONTEXT_CACHE_MISS | scan_id=%s | scan_date=%s",
        sid,
        date_key,
    )

    # 3) Singleflight — one build per date_key
    async with _cache_lock:
        if not force_refresh:
            cached = _cache_get(date_key)
            if cached is not None:
                set_scan_market_regime(cached)
                return cached
        fut = _inflight.get(date_key)
        if fut is None or fut.done():
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            _inflight[date_key] = fut
            leader = True
        else:
            leader = False

    if not leader:
        try:
            regime = await asyncio.wait_for(asyncio.shield(fut), timeout=_MARKET_CONTEXT_TIMEOUT_SEC + 5.0)
            set_scan_market_regime(regime)
            logger.info(
                "SCAN_MARKET_CONTEXT_CACHE_HIT | scan_id=%s | scan_date=%s | "
                "duration_ms=%.0f | data_source=singleflight | cache_hit=true | fallback_used=false",
                sid,
                date_key,
                (time.perf_counter() - t0) * 1000,
            )
            return regime
        except Exception as wait_exc:
            logger.warning(
                "SCAN_MARKET_PERMISSION_FALLBACK | scan_id=%s | scan_date=%s | "
                "reason=singleflight_wait_failed | error=%s | fallback_used=true",
                sid,
                date_key,
                wait_exc,
            )
            # Fall through only if leader never completed; try cache again.
            cached = _cache_get(date_key)
            if cached is not None:
                set_scan_market_regime(cached)
                return cached
            unavailable = _unavailable_regime(f"singleflight wait failed: {wait_exc}")
            set_scan_market_regime(unavailable)
            return unavailable

    # Leader builds
    regime: MarketRegimeResult
    fallback_used = False
    data_source = "market_permission_service"
    try:
        from .market_permission_service import MarketPermissionService

        try:
            regime = await asyncio.wait_for(
                MarketPermissionService().evaluate_market_permission(scan_date=scan_date),
                timeout=_MARKET_CONTEXT_TIMEOUT_SEC,
            )
            logger.info(
                "SCAN_MARKET_PERMISSION_SUCCESS | scan_id=%s | scan_date=%s | "
                "duration_ms=%.0f | market_state=%s | entry_allowed=%s | cache_hit=false | fallback_used=false",
                sid,
                date_key,
                (time.perf_counter() - t0) * 1000,
                regime.market_state,
                regime.new_entry_allowed,
            )
        except asyncio.TimeoutError:
            data_source = "timeout_fallback"
            fallback_used = True
            cached = _cache_get(date_key)
            if cached is not None:
                regime = cached
                logger.warning(
                    "SCAN_MARKET_PERMISSION_FALLBACK | scan_id=%s | scan_date=%s | "
                    "reason=evaluation_timeout | duration_ms=%.0f | fallback_used=true | "
                    "data_source=process_cache | market_state=%s",
                    sid,
                    date_key,
                    (time.perf_counter() - t0) * 1000,
                    regime.market_state,
                )
            else:
                regime = _unavailable_regime(
                    f"evaluation timed out after {_MARKET_CONTEXT_TIMEOUT_SEC:.0f}s"
                )
                logger.warning(
                    "SCAN_MARKET_PERMISSION_FALLBACK | scan_id=%s | scan_date=%s | "
                    "reason=evaluation_timeout_no_cache | duration_ms=%.0f | fallback_used=true | "
                    "data_source=unavailable",
                    sid,
                    date_key,
                    (time.perf_counter() - t0) * 1000,
                )
        except asyncio.CancelledError:
            logger.warning(
                "SCAN_MARKET_PERMISSION_FALLBACK | scan_id=%s | scan_date=%s | "
                "reason=cancelled | duration_ms=%.0f",
                sid,
                date_key,
                (time.perf_counter() - t0) * 1000,
            )
            raise
        except Exception as exc:
            data_source = "error_fallback"
            fallback_used = True
            cached = _cache_get(date_key)
            if cached is not None:
                regime = cached
                logger.warning(
                    "SCAN_MARKET_PERMISSION_FALLBACK | scan_id=%s | scan_date=%s | "
                    "reason=evaluation_error | error=%s | fallback_used=true | "
                    "data_source=process_cache | market_state=%s",
                    sid,
                    date_key,
                    exc,
                    regime.market_state,
                )
            else:
                regime = _unavailable_regime(str(exc))
                logger.warning(
                    "SCAN_MARKET_PERMISSION_FALLBACK | scan_id=%s | scan_date=%s | "
                    "reason=evaluation_error_no_cache | error=%s | fallback_used=true | "
                    "data_source=unavailable",
                    sid,
                    date_key,
                    exc,
                )

        _cache_put(date_key, regime)
        set_scan_market_regime(regime)
        if not fut.done():
            fut.set_result(regime)
    except asyncio.CancelledError:
        if not fut.done():
            fut.set_exception(asyncio.CancelledError())
        raise
    except Exception as exc:
        if not fut.done():
            fut.set_exception(exc)
        raise
    finally:
        async with _cache_lock:
            if _inflight.get(date_key) is fut:
                _inflight.pop(date_key, None)

    logger.info(
        "SCAN_MARKET_CONTEXT_READY | scan_id=%s | scan_date=%s | duration_ms=%.0f | "
        "data_source=%s | cache_hit=false | fallback_used=%s | market_state=%s | "
        "entry_allowed=%s",
        sid,
        date_key,
        (time.perf_counter() - t0) * 1000,
        data_source,
        fallback_used,
        regime.market_state,
        regime.new_entry_allowed,
    )
    return regime
