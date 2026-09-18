"""Health liveness + parallel dependency probes must stay non-blocking.

Regression for scanner_stream_and_health root cause:
event-loop starvation made /health unresponsive → UI painted ALL services "Waking Up".
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_live_has_no_db_dependency():
    """GET /health/live must not touch DB/Redis and return immediately."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        t0 = time.perf_counter()
        resp = await client.get("/health/live")
        elapsed = time.perf_counter() - t0

    assert resp.status_code == 200
    body = resp.json()
    assert body.get("live") is True
    assert body.get("status") == "ok"
    # Pure process answer — should be well under a second even under load.
    assert elapsed < 2.0


@pytest.mark.asyncio
async def test_health_probes_run_in_parallel_not_serial():
    """DB + Redis probes must overlap; worst case ≈ max, not sum."""
    from app.routes import health as health_mod

    async def slow_db() -> str:
        await asyncio.sleep(0.25)
        return "ok"

    async def slow_redis() -> str:
        await asyncio.sleep(0.25)
        return "ok"

    async def fast_engine() -> tuple[str, str]:
        return "ok", "ok"

    # Re-bind the inner helpers by patching the gather path indirectly:
    # call health_check while forcing probe timings via patched wait_for side effects.
    # Simpler: unit-test that asyncio.gather is used by measuring wall time of the
    # public health_check with mocked slow probes via engine/redis modules.

    call_order: list[str] = []

    async def fake_db_connect():
        call_order.append("db_start")
        await asyncio.sleep(0.2)
        call_order.append("db_end")

        class _Conn:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def execute(self, *a, **k):
                return None

        class _Engine:
            def connect(self):
                return _Conn()

        return _Engine()

    class FakeRedis:
        async def ping(self):
            call_order.append("redis_start")
            await asyncio.sleep(0.2)
            call_order.append("redis_end")
            return True

    with patch("app.db.session.engine") as eng:
        # engine.connect is used as async context manager
        class _CM:
            async def __aenter__(self):
                call_order.append("db_start")
                await asyncio.sleep(0.2)
                call_order.append("db_end")
                return self

            async def __aexit__(self, *a):
                return False

            async def execute(self, *a, **k):
                return None

        eng.connect = lambda: _CM()

        with patch("app.core.redis.get_redis", return_value=FakeRedis()):
            with patch(
                "app.services.market_engine_service.market_engine.status",
                new=AsyncMock(return_value={"websocket_connected": True, "running": True}),
            ):
                t0 = time.perf_counter()
                result = await health_mod.health_check()
                wall = time.perf_counter() - t0

    assert result.status == "ok"
    assert result.database == "ok"
    assert result.redis == "ok"
    # Parallel: ~0.2s, not ~0.4s. Allow overhead headroom.
    assert wall < 0.38, f"probes appear serial: wall={wall:.3f}s order={call_order}"
    # Overlap evidence: both starts before either end
    assert call_order.index("db_start") < call_order.index("redis_end")
    assert call_order.index("redis_start") < call_order.index("db_end")


class _FastDbCM:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, *a, **k):
        return None


@pytest.mark.asyncio
async def test_health_redis_recreates_stale_client():
    """A client left half-open after Redis was down must recover on the next probe."""
    from app.routes import health as health_mod

    class DeadRedis:
        async def ping(self):
            raise ConnectionError("stale pool")

    class LiveRedis:
        async def ping(self):
            return True

    clients = iter([DeadRedis(), LiveRedis()])

    with patch("app.db.session.engine") as eng:
        eng.connect = lambda: _FastDbCM()
        with patch("app.core.redis.get_redis", side_effect=lambda: next(clients)):
            with patch("app.core.redis.close_redis_client", new=AsyncMock()) as closed:
                with patch(
                    "app.services.market_engine_service.market_engine.status",
                    new=AsyncMock(return_value={"websocket_connected": True, "running": True}),
                ):
                    result = await health_mod.health_check()

    assert result.redis == "ok"
    closed.assert_awaited()


@pytest.mark.asyncio
async def test_health_websocket_idle_when_engine_stopped():
    """After-hours STOPPED engine must not report websocket as disconnected."""
    from app.routes import health as health_mod

    class LiveRedis:
        async def ping(self):
            return True

    with patch("app.db.session.engine") as eng:
        eng.connect = lambda: _FastDbCM()
        with patch("app.core.redis.get_redis", return_value=LiveRedis()):
            with patch(
                "app.services.market_engine_service.market_engine.status",
                new=AsyncMock(
                    return_value={
                        "status": "STOPPED",
                        "websocket_connected": False,
                        "running": False,
                    }
                ),
            ):
                result = await health_mod.health_check()

    assert result.websocket == "idle"

