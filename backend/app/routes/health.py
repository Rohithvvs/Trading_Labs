import asyncio
import logging
import os
import time

from fastapi import APIRouter
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
        try:
            from ..core.redis import close_redis_client, get_redis

            async def _ping() -> str:
                r = get_redis()
                if r is None:
                    return "not_configured"
                await asyncio.wait_for(r.ping(), timeout=_REDIS_PROBE_TIMEOUT_SEC)
                return "ok"

            try:
                return await _ping()
            except Exception as first_exc:
                logger.warning(
                    "[health] redis probe failed (%s): %s — recreating client",
                    type(first_exc).__name__,
                    str(first_exc)[:160],
                )
                await close_redis_client()
                return await _ping()
        except Exception as exc:
            explicit = (os.getenv("REDIS_URL") or "").strip()
            status = "error" if explicit else "not_configured"
            logger.warning(
                "[health] redis probe failed (%s): %s → %s",
                type(exc).__name__,
                str(exc)[:160],
                status,
            )
            return status

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
    return sanitize_for_json({"status": "ok", "engine": market_engine.status()})


