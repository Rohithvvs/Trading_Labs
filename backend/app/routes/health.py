import asyncio
import logging
import os
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..config import settings
from ..schemas import HealthResponse
from ..utils import advisory_payload, sanitize_for_json


router = APIRouter(tags=["health"])
logger = logging.getLogger("app.routes.health")

# Keep health probes bounded so the UI never marks the whole stack OFFLINE
# solely because Neon is cold-starting or Redis is absent locally.
# Neon cold connect is often 5–10s; stay under the frontend probe budget (15s).
_DB_PROBE_TIMEOUT_SEC = 8.0
_REDIS_PROBE_TIMEOUT_SEC = 1.0
# A down Redis must not add a 1–2s wait to every /health poll. The UI live
# probe budget is 3s; stacking a retry on TimeoutError blew past it.
_REDIS_NEGATIVE_CACHE_SEC = 30.0
_redis_negative_until = 0.0
_redis_negative_status = "error"


@router.get("/market-data/freshness")
async def market_data_freshness():
    """Operator-facing strategy market-data freshness + recent load summary."""
    try:
        from ..services.market_data_ingestion.freshness import status_snapshot

        snap = await asyncio.wait_for(status_snapshot(), timeout=5.0)
        return sanitize_for_json(snap)
    except Exception as exc:
        logger.warning("market_data_freshness failed: %s", exc)
        return {
            "market_data_freshness": {
                "ok": False,
                "code": "MARKET_DATA_STALE",
                "reason": "db_unavailable",
                "message": str(exc)[:200],
            }
        }


@router.get("/health/live")
async def health_live() -> dict[str, object]:
    """Process liveness only — no DB, Redis, FYERS, or scanner dependencies.

    Used to distinguish:
      - process dead / network down  → this endpoint never answers
      - process alive but deps slow / event-loop previously blocked → this answers, /health may lag
    """
    return {
        "status": "ok",
        "live": True,
        "environment": settings.app_env,
        "ts": time.time(),
    }


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness + dependency probe. Always returns quickly (bounded timeouts).

    Probes run concurrently so a slow Redis cannot stack on a slow DB past the
    frontend budget. Individual probes never call external broker HTTP APIs.
    """
    started = time.perf_counter()

    async def _probe_db() -> str:
        try:
            from ..db.session import engine

            async def _db_ping() -> None:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))

            await asyncio.wait_for(_db_ping(), timeout=_DB_PROBE_TIMEOUT_SEC)
            return "ok"
        except Exception as exc:
            logger.warning(
                "[health] database probe failed (%s): %s",
                type(exc).__name__,
                str(exc)[:200],
            )
            return "error"

    async def _probe_redis() -> str:
        global _redis_negative_until, _redis_negative_status
        if not (os.getenv("REDIS_URL") or "").strip():
            return "not_configured"
        if time.monotonic() < _redis_negative_until:
            return _redis_negative_status

        def _remember(status: str) -> str:
            global _redis_negative_until, _redis_negative_status
            _redis_negative_status = status
            _redis_negative_until = time.monotonic() + _REDIS_NEGATIVE_CACHE_SEC
            return status

        try:
            from ..core.redis import close_redis_client, get_redis

            async def _ping() -> str:
                r = get_redis()
                if r is None:
                    return "not_configured"
                await asyncio.wait_for(r.ping(), timeout=_REDIS_PROBE_TIMEOUT_SEC)
                return "ok"

            try:
                status = await _ping()
            except Exception as first_exc:
                logger.warning(
                    "[health] redis probe failed (%s): %s — recreating client",
                    type(first_exc).__name__,
                    str(first_exc)[:160],
                )
                await close_redis_client()
                # Timeout means the server is unreachable. A second ping only
                # doubles the wait. Connection errors can be a stale client.
                if isinstance(first_exc, (asyncio.TimeoutError, TimeoutError)):
                    explicit = (os.getenv("REDIS_URL") or "").strip()
                    return _remember("error" if explicit else "not_configured")
                status = await _ping()
            if status == "ok":
                _redis_negative_until = 0.0
                return status
            return _remember(status)
        except Exception as exc:
            explicit = (os.getenv("REDIS_URL") or "").strip()
            status = "error" if explicit else "not_configured"
            logger.warning(
                "[health] redis probe failed (%s): %s → %s",
                type(exc).__name__,
                str(exc)[:160],
                status,
            )
            return _remember(status)

    async def _probe_engine() -> tuple[str, str]:
        fyers_status = "ok"
        websocket_status = "ok"
        try:
            from ..services.market_engine_service import market_engine

            eng = await asyncio.wait_for(market_engine.status(), timeout=0.75)
            if isinstance(eng, dict):
                eng_status = str(eng.get("status") or "").upper()
                # After-hours cooldown (15:30 IST) leaves the Fyers socket down on
                # purpose — do not paint the badge as "Connecting" overnight.
                if eng_status in {"STOPPED", "STOPPING"}:
                    websocket_status = "idle"
                elif eng.get("websocket_connected") is False:
                    websocket_status = "disconnected"
                if eng.get("running") is False and eng.get("status") in ("stopped", "error"):
                    fyers_status = "idle"
        except Exception:
            pass
        return fyers_status, websocket_status

    # Parallel probes — worst case ≈ max(db, redis, engine), not sum.
    db_status, redis_status, engine_pair = await asyncio.gather(
        _probe_db(),
        _probe_redis(),
        _probe_engine(),
    )
    fyers_status, websocket_status = engine_pair

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "[health] ok | db=%s redis=%s fyers=%s ws=%s | %sms",
        db_status,
        redis_status,
        fyers_status,
        websocket_status,
        elapsed_ms,
    )

    return HealthResponse(
        status="ok",
        environment=settings.app_env,
        disclaimer=advisory_payload(),
        database=db_status,
        redis=redis_status,
        fyers=fyers_status,
        websocket=websocket_status,
    )


@router.get("/health/heartbeat")
async def heartbeat() -> dict[str, object]:
    from ..services.market_engine_service import market_engine

    await market_engine.heartbeat()
    return sanitize_for_json({"status": "ok", "engine": await market_engine.status()})


def _redact_health_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    token = (settings.turso_auth_token or "").strip()
    if token and token in text:
        text = text.replace(token, "[redacted]")
    return text[:200]


@router.get("/health/market-data")
async def health_market_data():
    """Verify the selected candle backend. Turso failures do not report Postgres as healthy."""
    from ..services.market_data_ingestion.candle_diagnostics import candle_backend_identity
    from ..services.market_data_provider import get_market_history_provider

    identity = candle_backend_identity()
    try:
        provider = get_market_history_provider()
        payload = await provider.check_health()
    except Exception as exc:
        logger.warning("HEALTH_MARKET_DATA_FAILED | err_type=%s", type(exc).__name__)
        payload = {
            "backend": identity["candle_backend"],
            "configured": settings.turso_configured() if identity["candle_backend"] == "turso" else True,
            "reachable": False,
            "sample_query": False,
            "error": _redact_health_error(exc),
        }
    if isinstance(payload, dict):
        payload.setdefault("candle_backend", identity["candle_backend"])
        payload.setdefault("database_type", identity["database_type"])
        payload.setdefault("database_target", identity["database_target"])
        payload["silent_postgres_fallback"] = False
    failed = isinstance(payload, dict) and payload.get("reachable") is False
    if failed and identity["candle_backend"] == "turso":
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/market-data/coverage")
async def market_data_coverage(trade_date: str | None = None):
    """Symbols stored for one session on the active candle backend."""
    from datetime import date as date_cls

    from ..services.market_data_ingestion.candle_diagnostics import coverage_snapshot

    target = None
    if trade_date:
        try:
            target = date_cls.fromisoformat(trade_date)
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "trade_date must be YYYY-MM-DD"})
    try:
        payload = await coverage_snapshot(target)
    except Exception as exc:
        logger.warning("MARKET_DATA_COVERAGE_FAILED | err_type=%s", type(exc).__name__)
        identity_error = {
            "reachable": False,
            "error": _redact_health_error(exc),
            "silent_postgres_fallback": False,
        }
        status = 503 if settings.uses_turso_candle_history() else 200
        return JSONResponse(status_code=status, content=identity_error)
    return payload


@router.get("/market-data/parity")
async def market_data_parity(
    symbols: str = "MOTILALOFS,CARTRADE,CHENNPETRO,RELIANCE,TCS",
    trade_date: str | None = None,
) -> dict[str, object]:
    """Diagnostic endpoint to compare market data and technical indicator parity across backends."""
    from datetime import date, timedelta
    from ..services.market_data_provider import get_market_history_provider
    from ..services.indicator_scanner.ta_functions import rsi, sma
    from ..utils.datetime_utils import ist_now

    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return {"error": "No symbols specified"}

    target_date: date
    if trade_date:
        try:
            target_date = date.fromisoformat(trade_date)
        except ValueError:
            target_date = ist_now().date()
    else:
        target_date = ist_now().date()

    from_date = target_date - timedelta(days=500)
    provider = get_market_history_provider()
    series_by_symbol = await provider.get_daily_bars(
        symbol_list, from_date=from_date, to_date=target_date
    )

    out: dict[str, object] = {}
    for sym in symbol_list:
        canon = sym if sym.endswith("-EQ") else f"{sym}-EQ"
        series = series_by_symbol.get(sym) or series_by_symbol.get(canon)
        if series is None or not series.dates:
            out[sym] = {"status": "NO_DATA", "bar_count": 0}
            continue

        idx = series.index_on_or_before(target_date)
        if idx is None:
            out[sym] = {"status": "NO_DATA_BEFORE_DATE", "bar_count": len(series)}
            continue

        n = idx + 1
        closes = series.close[:n]
        highs = series.high[:n]
        lows = series.low[:n]
        volumes = series.volume[:n]
        dates = series.dates[:n]

        rsi_vals = rsi(closes, 14)
        sma_20 = sma(closes, 20)
        sma_50 = sma(closes, 50)
        sma_200 = sma(closes, 200)
        vol_sma_20 = sma(volumes, 20)

        tr_list = []
        for i in range(n):
            if i == 0 or closes[i - 1] is None:
                tr_list.append((highs[i] or 0.0) - (lows[i] or 0.0))
            else:
                tr_list.append(
                    max(
                        (highs[i] or 0.0) - (lows[i] or 0.0),
                        abs((highs[i] or 0.0) - (closes[i - 1] or 0.0)),
                        abs((lows[i] or 0.0) - (closes[i - 1] or 0.0)),
                    )
                )
        atr_14 = sma(tr_list, 14)

        cur_close = closes[-1]
        cur_rsi = rsi_vals[-1]
        cur_sma_50 = sma_50[-1]
        cur_sma_200 = sma_200[-1]
        cur_vol = volumes[-1]
        cur_vol_20 = vol_sma_20[-1]

        out[sym] = {
            "status": "OK",
            "date": dates[-1].isoformat(),
            "bar_count": n,
            "open": series.open[idx],
            "high": series.high[idx],
            "low": series.low[idx],
            "close": cur_close,
            "volume": cur_vol,
            "indicators": {
                "sma_20": round(float(sma_20[-1]), 2) if sma_20[-1] is not None else None,
                "sma_50": round(float(cur_sma_50), 2) if cur_sma_50 is not None else None,
                "sma_200": round(float(cur_sma_200), 2) if cur_sma_200 is not None else None,
                "rsi_14": round(float(cur_rsi), 2) if cur_rsi is not None else None,
                "atr_14": round(float(atr_14[-1]), 2) if atr_14[-1] is not None else None,
                "vol_sma_20": round(float(cur_vol_20), 2) if cur_vol_20 is not None else None,
            },
            "strategy_conditions_sample": {
                "close_gt_sma_50": bool(cur_close is not None and cur_sma_50 is not None and cur_close > cur_sma_50),
                "sma_50_gt_sma_200": bool(cur_sma_50 is not None and cur_sma_200 is not None and cur_sma_50 > cur_sma_200),
                "rsi_gt_55": bool(cur_rsi is not None and cur_rsi > 55),
                "vol_gt_avg_20": bool(cur_vol is not None and cur_vol_20 is not None and cur_vol > cur_vol_20),
            },
        }

    return {
        "backend": provider.name,
        "as_of": target_date.isoformat(),
        "symbols_count": len(out),
        "data": out,
    }



