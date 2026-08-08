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


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness + dependency probe. Always returns quickly (bounded timeouts)."""
    started = time.perf_counter()

    # --- Database (async engine — must use async connect, not sync `with engine.connect()`) ---
    db_status = "ok"
    try:
        from ..db.session import engine

        async def _db_ping() -> None:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_db_ping(), timeout=_DB_PROBE_TIMEOUT_SEC)
    except Exception as exc:
        db_status = "error"
        logger.warning(
            "[health] database probe failed (%s): %s",
            type(exc).__name__,
            str(exc)[:200],
        )

    # --- Redis (graceful if not configured / local redis not running) ---
    redis_status = "ok"
    try:
        from ..core.redis import get_redis

        r = get_redis()
        if r is None:
            redis_status = "not_configured"
        else:
            await asyncio.wait_for(r.ping(), timeout=_REDIS_PROBE_TIMEOUT_SEC)
    except Exception as exc:
        # No explicit REDIS_URL → treat missing local Redis as optional, not hard error.
        explicit = (os.getenv("REDIS_URL") or "").strip()
        redis_status = "error" if explicit else "not_configured"
        logger.warning(
            "[health] redis probe failed (%s): %s → %s",
            type(exc).__name__,
            str(exc)[:160],
            redis_status,
        )

    # Lightweight derived signals (do not call external broker APIs here).
    fyers_status = "ok"
    websocket_status = "ok"
    try:
        from ..services.market_engine_service import market_engine

        eng = await asyncio.wait_for(market_engine.status(), timeout=0.75)
        if isinstance(eng, dict):
            # Reflect engine/ws connectivity when the market engine is running.
            if eng.get("websocket_connected") is False:
                websocket_status = "disconnected"
            if eng.get("running") is False and eng.get("status") in ("stopped", "error"):
                fyers_status = "idle"
    except Exception:
        pass

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


