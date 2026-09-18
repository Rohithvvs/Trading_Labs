from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from backend.app.models.paper_trading import ExecutionEvent, MarketEngineSession, PaperNotification, PaperOrder, PaperPosition
from backend.app.services.market_engine_service import MarketEngineService, market_engine
import backend.app.services.paper_trading_service as paper_service
from tests.utils.fakes import FakeFyersService, FakeMarketDataFeed


@pytest.fixture(autouse=True)
def fake_services(monkeypatch):
    monkeypatch.setattr(paper_service, "FyersService", FakeFyersService)
    monkeypatch.setattr(market_engine, "_feed", FakeMarketDataFeed(market_engine._on_tick, market_engine._on_feed_error, market_engine._on_connection_change))
    monkeypatch.setattr(market_engine, "is_market_hours", lambda now=None: True)


@pytest.mark.integration
def test_start_stop_status_and_heartbeat_routes(client, db_session):
    from backend.tests.conftest import auth_headers

    headers = auth_headers()
    started = client.post("/paper-trading/engine/start", headers=headers)
    assert started.status_code == 200
    assert started.json()["status"] in {"STARTING", "RUNNING", "STOPPED"}

    status = client.get("/paper-trading/engine/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["market_hours_active"] is True
    assert status.json()["websocket_connected"] is False

    before_orders = db_session.query(PaperOrder).count()
    heartbeat = client.get("/health/heartbeat")
    assert heartbeat.status_code == 200
    assert heartbeat.json()["status"] == "ok"
    assert db_session.query(PaperOrder).count() == before_orders
    assert db_session.query(MarketEngineSession).one().last_heartbeat_at is not None

    stopped = client.post("/paper-trading/engine/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "STOPPED"


@pytest.mark.integration
def test_limit_order_api_persists_lifecycle_and_execution_audit(client, db_session, monkeypatch):
    from backend.tests.conftest import register_auth_headers

    headers = register_auth_headers(client)
    response = client.post(
        "/paper-trading/orders",
        json={
            "symbol": "INFY-EQ",
            "side": "BUY",
            "type": "LIMIT",
            "qty": 1,
            "limit_price": 95,
            "stop_loss": 90,
            "target": 105,
            "idempotency_key": f"test-limit-{uuid.uuid4().hex}",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["order"]["status"] == "PENDING"
    assert body["order"]["lifecycle_state"] == "PENDING_ENTRY"

    db_session.expire_all()
    order = db_session.scalar(select(PaperOrder).where(PaperOrder.symbol.in_(["INFY-EQ", "INFY"])))
    assert order is not None
    engine = MarketEngineService()
    monkeypatch.setattr(engine, "is_market_hours", lambda now=None: True)

    from backend.app.db.session import AsyncSessionLocal

    async def _fill():
        async with AsyncSessionLocal() as db:
            await engine._process_symbol(db, "INFY", 95.0)
            await engine._process_symbol(db, "INFY", 105.0)
            await db.commit()

    asyncio.run(_fill())
    db_session.expire_all()
    db_session.refresh(order)
    assert order.requested_entry_price == 95.0
    assert order.lifecycle_state in {"PENDING_ENTRY", "ENTRY_FILLED", "OPEN_POSITION"}
    assert db_session.query(PaperOrder).filter(PaperOrder.symbol.in_(["INFY-EQ", "INFY"])).count() == 1


@pytest.mark.integration
def test_restart_recovery_and_market_closed_reconcile_do_not_crash(db_session, monkeypatch):
    service_engine = MarketEngineService()
    order = PaperOrder(
        account_id=1,
        symbol="TCS-EQ",
        side="BUY",
        order_type="LIMIT",
        product_type="CNC",
        qty=1,
        order_price=100.0,
        requested_entry_price=100.0,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY",
    )
    db_session.add(order)
    db_session.commit()

    assert db_session.query(PaperOrder).filter_by(symbol="TCS-EQ").count() == 1
    monkeypatch.setattr(service_engine, "is_market_hours", lambda now=None: False)
    asyncio.run(service_engine._reconcile_session_isolated())
    db_session.expire_all()
    session = db_session.query(MarketEngineSession).one_or_none()
    assert session is not None
    assert session.status in {"RUNNING", "WAITING_MARKET_OPEN", "STOPPED", "STARTING", "ERROR_RETRYING"}
