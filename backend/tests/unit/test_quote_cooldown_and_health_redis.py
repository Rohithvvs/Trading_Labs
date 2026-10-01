"""Quote 429 cooldown and Redis health probe must not stall the API."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from app.routes import health as health_mod
from app.services.fyers_service import FyersService
from tests.unit.test_health_live_and_parallel import _FastDbCM


@pytest.fixture(autouse=True)
def _reset_redis_negative_cache():
    health_mod._redis_negative_until = 0.0
    health_mod._redis_negative_status = "error"
    yield
    health_mod._redis_negative_until = 0.0
    health_mod._redis_negative_status = "error"


@pytest.mark.asyncio
async def test_fetch_ltp_serves_recent_print_during_quote_cooldown():
    service = FyersService.__new__(FyersService)
    key = service._cache_symbol("INFY")
    FyersService._quote_cooldown_until = time.monotonic() + 30
    FyersService._ltp_mem[key] = (1520.5, time.monotonic() - 5)

    async def _boom(*_a, **_k):
        raise AssertionError("broker must not be called during cooldown")

    service._fetch_fyers_ltp = _boom  # type: ignore[method-assign]
    try:
        price = await service.fetch_ltp("INFY", allow_yfinance=False, pg_ttl_sec=0.75)
    finally:
        FyersService._quote_cooldown_until = 0.0
        FyersService._ltp_mem.pop(key, None)

    assert price == 1520.5


@pytest.mark.asyncio
async def test_health_redis_timeout_does_not_retry_or_stick_the_next_probe(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    class TimingOutRedis:
        def __init__(self):
            self.pings = 0

        async def ping(self):
            self.pings += 1
            raise TimeoutError("redis down")

    client = TimingOutRedis()

    with patch("app.db.session.engine") as eng:
        eng.connect = lambda: _FastDbCM()
        with patch("app.core.redis.get_redis", return_value=client) as get_redis:
            with patch("app.core.redis.close_redis_client", new=AsyncMock()):
                with patch(
                    "app.services.market_engine_service.market_engine.status",
                    new=AsyncMock(return_value={"websocket_connected": True, "running": True}),
                ):
                    first = await health_mod.health_check()
                    get_redis.reset_mock()
                    second = await health_mod.health_check()

    assert first.redis == "error"
    assert client.pings == 1
    assert second.redis == "error"
    get_redis.assert_not_called()


@pytest.mark.asyncio
async def test_note_quote_rate_limit_blocks_followup_calls():
    FyersService._quote_cooldown_until = 0.0
    assert FyersService.quote_rate_limited() is False
    FyersService.note_quote_rate_limit()
    try:
        assert FyersService.quote_rate_limited() is True
    finally:
        FyersService._quote_cooldown_until = 0.0
