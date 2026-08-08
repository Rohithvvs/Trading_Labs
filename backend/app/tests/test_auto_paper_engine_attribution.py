"""Unit tests: engine-scoped paper positions + auto paper BUY attribution + order flow."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.auth import User
from app.models.paper_trading import (
    MARKET_WAITING_STATUSES,
    PaperOrder,
    PaperPosition,
)
from app.services.paper_trading_service import PaperTradingService
from app.services.recommendation_engine_ids import (
    PRODUCTION,
    RE_001,
    RE_002,
    normalize_recommendation_engine,
)

IST = ZoneInfo("Asia/Kolkata")


def _seed_user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    db.add(
        User(
            id=uid,
            email=f"auto-paper-{uid.hex[:10]}@test.local",
            full_name="Auto Paper Test",
            password_hash="not-a-real-hash",
            is_active=True,
            is_email_verified=True,
            role="trader",
        )
    )
    db.commit()
    return uid


def test_normalize_recommendation_engine_aliases():
    assert normalize_recommendation_engine(None) == PRODUCTION
    assert normalize_recommendation_engine("") == PRODUCTION
    assert normalize_recommendation_engine("production") == PRODUCTION
    assert normalize_recommendation_engine("PROD") == PRODUCTION
    assert normalize_recommendation_engine("RE-001") == RE_001
    assert normalize_recommendation_engine("re001") == RE_001
    assert normalize_recommendation_engine("RE_002") == RE_002
    assert normalize_recommendation_engine("RE-002") == RE_002


def test_lab_auto_allowed_production_always():
    from app.services.auto_paper_trading_service import _lab_auto_allowed

    assert _lab_auto_allowed(PRODUCTION) is True


def test_lab_auto_allowed_respects_paper_linked_gate(monkeypatch):
    from app.config import settings
    from app.services.auto_paper_trading_service import _lab_auto_allowed

    monkeypatch.setattr(settings, "auto_paper_trading_force_lab", False, raising=False)
    # Gate off (default for engine comparison): LAB_SHADOW allowed
    monkeypatch.setattr(settings, "auto_paper_trading_lab_requires_paper_linked", False, raising=False)
    monkeypatch.setattr(settings, "re001_stage", "LAB_SHADOW", raising=False)
    assert _lab_auto_allowed(RE_001) is True

    # Gate on: only PAPER_LINKED
    monkeypatch.setattr(settings, "auto_paper_trading_lab_requires_paper_linked", True, raising=False)
    monkeypatch.setattr(settings, "re001_stage", "LAB_SHADOW", raising=False)
    assert _lab_auto_allowed(RE_001) is False

    monkeypatch.setattr(settings, "re001_stage", "PAPER_LINKED", raising=False)
    assert _lab_auto_allowed(RE_001) is True

    monkeypatch.setattr(settings, "auto_paper_trading_force_lab", True, raising=False)
    monkeypatch.setattr(settings, "re001_stage", "LAB_SHADOW", raising=False)
    assert _lab_auto_allowed(RE_001) is True


def _market_closed_mock():
    mock_th = MagicMock()
    mock_th.is_market_open.return_value = False
    next_open = datetime(2026, 5, 26, 9, 15, tzinfo=IST)
    mock_th.get_next_market_open.return_value = next_open
    mock_th.get_market_status.return_value = {
        "is_open": False,
        "is_trading_day": True,
        "status": "CLOSED",
        "reason": "After market close",
        "current_ist": "2026-05-25T20:45:00+05:30",
        "open_time": "2026-05-25T09:15:00+05:30",
        "close_time": "2026-05-25T15:30:00+05:30",
        "next_open_ist": next_open.isoformat(),
        "session": "CLOSED",
    }
    return mock_th


def _market_open_mock():
    mock_th = MagicMock()
    mock_th.is_market_open.return_value = True
    mock_th.get_market_status.return_value = {
        "is_open": True,
        "is_trading_day": True,
        "status": "OPEN",
        "reason": "Market open",
        "current_ist": "2026-05-26T10:00:00+05:30",
        "open_time": "2026-05-26T09:15:00+05:30",
        "close_time": "2026-05-26T15:30:00+05:30",
        "next_open_ist": None,
        "session": "OPEN",
    }
    mock_th.get_next_market_open.return_value = None
    return mock_th


def _price_snap(symbol: str = "ABC", price: float = 100.0):
    snap = MagicMock()
    snap.symbol = symbol
    snap.current_price = price
    snap.candles = []
    snap.ema_20 = None
    snap.supertrend = None
    snap.source = "TEST_MOCK"
    snap.fetched_at = datetime.now(IST)
    return snap


def test_auto_paper_three_engines_market_closed_orders_only(monkeypatch):
    """Scenario 1: Production + RE-001 + RE-002 BUY while market closed → 3 orders, 0 positions."""
    from app.config import settings
    from app.services.auto_paper_trading_service import place_auto_paper_buy

    monkeypatch.setattr(settings, "auto_paper_trading_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auto_paper_trading_lab_requires_paper_linked", False, raising=False)

    mock_th = _market_closed_mock()
    with SessionLocal() as db:
        user = _seed_user(db)
        with patch("app.services.paper_trading_service.trading_hours", mock_th):
            with patch.object(
                PaperTradingService,
                "_price_for_execution",
                return_value=_price_snap("RELIANCE", 100.0),
            ):
                with patch.object(PaperTradingService, "_validate_symbol", return_value=None):
                    for eng in (PRODUCTION, RE_001, RE_002):
                        results = place_auto_paper_buy(
                            db,
                            symbol="RELIANCE",
                            recommendation_engine=eng,
                            signal="BUY",
                            recommendation_id=f"rec-{eng}-closed",
                            user_id=user,
                        )
                        assert results and not results[0].get("skipped"), results

        service = PaperTradingService(db, user_id=user)
        account = service._get_or_create_account()
        orders = list(
            db.scalars(
                select(PaperOrder).where(
                    PaperOrder.account_id == account.id,
                    PaperOrder.symbol.like("%RELIANCE%"),
                )
            )
        )
        engines = {o.source_engine_id for o in orders}
        assert engines == {PRODUCTION, RE_001, RE_002}
        assert all(o.status in MARKET_WAITING_STATUSES for o in orders)
        assert all(o.side == "BUY" for o in orders)

        positions = list(
            db.scalars(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.status == "OPEN",
                    PaperPosition.symbol.like("%RELIANCE%"),
                )
            )
        )
        assert positions == []


def test_auto_paper_duplicate_open_order_skipped(monkeypatch):
    """Scenario 4: second BUY for same symbol+engine while order open → no duplicate."""
    from app.config import settings
    from app.services.auto_paper_trading_service import place_auto_paper_buy

    monkeypatch.setattr(settings, "auto_paper_trading_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auto_paper_trading_lab_requires_paper_linked", False, raising=False)

    mock_th = _market_closed_mock()
    with SessionLocal() as db:
        user = _seed_user(db)
        with patch("app.services.paper_trading_service.trading_hours", mock_th):
            with patch.object(
                PaperTradingService,
                "_price_for_execution",
                return_value=_price_snap("INFY", 1500.0),
            ):
                with patch.object(PaperTradingService, "_validate_symbol", return_value=None):
                    first = place_auto_paper_buy(
                        db,
                        symbol="INFY",
                        recommendation_engine=PRODUCTION,
                        signal="BUY",
                        recommendation_id="dup-1",
                        user_id=user,
                    )
                    second = place_auto_paper_buy(
                        db,
                        symbol="INFY",
                        recommendation_engine=PRODUCTION,
                        signal="BUY",
                        recommendation_id="dup-2",
                        user_id=user,
                    )
                    # Different engine still allowed
                    re001 = place_auto_paper_buy(
                        db,
                        symbol="INFY",
                        recommendation_engine=RE_001,
                        signal="BUY",
                        recommendation_id="dup-re001",
                        user_id=user,
                    )

        assert first and not first[0].get("skipped"), first
        assert second and second[0].get("skipped") is True
        assert second[0].get("reason") == "open_buy_order_exists"
        assert re001 and not re001[0].get("skipped"), re001

        service = PaperTradingService(db, user_id=user)
        account = service._get_or_create_account()
        prod_orders = list(
            db.scalars(
                select(PaperOrder).where(
                    PaperOrder.account_id == account.id,
                    PaperOrder.source_engine_id == PRODUCTION,
                    PaperOrder.symbol.like("%INFY%"),
                )
            )
        )
        assert len(prod_orders) == 1


def test_waiting_for_market_executes_into_position_with_engine(monkeypatch):
    """Scenario 2 fragment: WAITING_FOR_MARKET → execute → position keeps engine tag."""
    with SessionLocal() as db:
        user = _seed_user(db)
        service = PaperTradingService(db, user_id=user)
        account = service._get_or_create_account()
        order = PaperOrder(
            account_id=account.id,
            symbol="TCS-EQ",
            side="BUY",
            order_type="MARKET",
            qty=Decimal("2"),
            order_price=Decimal("3000"),
            requested_entry_price=Decimal("3000"),
            status="WAITING_FOR_MARKET",
            lifecycle_state="WAITING_FOR_MARKET",
            market_session="CLOSED",
            source_engine_id=RE_002,
            source_signal="BUY",
            scheduled_execution=datetime(2026, 5, 26, 9, 15, tzinfo=IST),
            idempotency_key=f"auto-wait-{uuid.uuid4()}",
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        mock_open = _market_open_mock()
        with patch("app.services.paper_trading_service.trading_hours", mock_open):
            filled, position, _, _msg = service._try_fill_order(
                account, order, 3010.0, require_market_open=True
            )
            db.commit()

        assert filled.status in {"FILLED", "EXECUTED"}
        assert position is not None
        assert position.source_engine_id == RE_002
        assert position.source_signal == "BUY"


def test_failed_order_status_on_zero_price(monkeypatch):
    """Execution with no live price → FAILED (retryable), stays on Orders tab."""
    with SessionLocal() as db:
        user = _seed_user(db)
        service = PaperTradingService(db, user_id=user)
        account = service._get_or_create_account()
        order = PaperOrder(
            account_id=account.id,
            symbol="WIPRO-EQ",
            side="BUY",
            order_type="MARKET",
            qty=Decimal("1"),
            order_price=Decimal("400"),
            status="WAITING_FOR_MARKET",
            lifecycle_state="WAITING_FOR_MARKET",
            source_engine_id=PRODUCTION,
            idempotency_key=f"fail-price-{uuid.uuid4()}",
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        mock_open = _market_open_mock()
        with patch("app.services.paper_trading_service.trading_hours", mock_open):
            filled, pos, _, msg = service._try_fill_order(
                account, order, 0.0, require_market_open=True
            )

        assert filled.status == "FAILED"
        assert pos is None
        assert filled.paused_reason == "LIVE_PRICE_UNAVAILABLE"
        assert "unavailable" in msg.lower() or "failed" in msg.lower()


def test_watch_and_reject_do_not_auto_paper(monkeypatch):
    """Scenario 3: only BUY creates orders."""
    from app.config import settings
    from app.services.auto_paper_trading_service import place_auto_paper_buy

    monkeypatch.setattr(settings, "auto_paper_trading_enabled", True, raising=False)
    with SessionLocal() as db:
        user = _seed_user(db)
        for signal in ("WATCH", "REJECT", "HOLD", "SELL"):
            results = place_auto_paper_buy(
                db,
                symbol="SBIN",
                recommendation_engine=PRODUCTION,
                signal=signal,
                user_id=user,
            )
            assert results and results[0].get("skipped") is True
