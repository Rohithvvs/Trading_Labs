import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import get_sync_db
from app.models.paper_trading import PaperTradingAccount, PaperOrder
from app.services.paper_trading_service import PaperTradingService
from app.utils.money import q_pnl


@pytest.fixture()
def api(test_engine):
    with TestClient(app) as client:
        yield client


def _register(api: TestClient, name: str = "Trader User") -> tuple[dict, str]:
    email = f"trader_{uuid.uuid4().hex[:10]}@example.com"
    res = api.post(
        "/auth/register",
        json={"email": email, "password": "SecurePassword123!", "full_name": name},
    )
    assert res.status_code in (200, 201), res.text
    token = res.json()["access_token"]
    user_id = res.json()["id"]
    return {"Authorization": f"Bearer {token}"}, user_id


def test_charge_profile_route(api):
    headers, _ = _register(api)
    res = api.get("/paper-trading/charges/profile", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["broker_id"] == "DEFAULT"
    assert data["exchange"] == "NSE"
    assert data["segment"] == "EQUITY_DELIVERY"
    assert data["stt_buy_rate_pct"] == 0.10
    assert data["gst_rate_pct"] == 18.0
    assert data["is_active"] is True


def test_charge_preview_routes(api):
    headers, _ = _register(api)
    # GET preview
    res_get = api.get(
        "/paper-trading/charges/preview?symbol=TCS&side=BUY&qty=10&price=3500",
        headers=headers,
    )
    assert res_get.status_code == 200, res_get.text
    body_get = res_get.json()
    assert body_get["turnover"] == 35000.0
    assert body_get["charges"]["stt"] == 35.0  # 0.10%
    assert body_get["charges"]["total_charges"] > 0
    assert body_get["estimated_order_cost"] > 35000.0
    assert body_get["assumptions"]["break_even_price"] > 3500.0

    # POST preview
    res_post = api.post(
        "/paper-trading/charges/preview",
        headers=headers,
        json={
            "symbol": "TCS",
            "side": "SELL",
            "qty": 10,
            "price": 3600.0,
            "exchange": "NSE",
        },
    )
    assert res_post.status_code == 200, res_post.text
    body_post = res_post.json()
    assert body_post["turnover"] == 36000.0
    assert body_post["charges"]["stt"] == 36.0
    assert body_post["estimated_net_proceeds"] < 36000.0


def test_end_to_end_charges_execution_and_audit(api, test_engine):
    headers, user_id = _register(api)

    # Use a sync DB session to execute orders and test service logic
    db = next(get_sync_db())
    try:
        service = PaperTradingService(db, user_id=user_id)
        account = service._get_or_create_account()
        starting_cash = Decimal(str(account.cash_balance))

        # 1. Place and fill BUY order: 100 shares @ Rs 500
        buy_order = PaperOrder(
            account_id=account.id,
            symbol="INFY",
            side="BUY",
            order_type="MARKET",
            qty=100,
            order_price=Decimal("500.00"),
            status="PENDING",
            idempotency_key=str(uuid.uuid4()),
        )
        db.add(buy_order)
        db.flush()

        order, position, trade, msg = service._try_fill_order(
            account=account,
            order=buy_order,
            current_price=500.0,
            require_market_open=False,
        )
        assert order.status == "FILLED"
        assert position is not None
        assert position.qty == 100
        assert Decimal(str(position.total_buy_charges)) == Decimal("59.38")
        assert Decimal(str(position.break_even_price)) > Decimal("500.00")

        # Cash balance deducted by turnover (50,000) + buy charges (59.38)
        expected_cash_after_buy = starting_cash - Decimal("50059.38")
        assert Decimal(str(account.cash_balance)) == expected_cash_after_buy
        db.commit()

        # 2. Check Order Charges endpoint
        res_order_charges = api.get(f"/paper-trading/orders/{buy_order.id}/charges", headers=headers)
        assert res_order_charges.status_code == 200, res_order_charges.text
        order_charges_data = res_order_charges.json()
        assert len(order_charges_data) == 1
        assert order_charges_data[0]["side"] == "BUY"
        assert order_charges_data[0]["charges"]["total_charges"] == 59.38

        # 3. Check Position P&L endpoint
        res_pos_pnl = api.get(f"/paper-trading/positions/{position.id}/pnl", headers=headers)
        assert res_pos_pnl.status_code == 200, res_pos_pnl.text
        pos_pnl_data = res_pos_pnl.json()
        assert pos_pnl_data["total_buy_charges"] == 59.38
        assert pos_pnl_data["break_even_price"] > 500.0

        # 4. Place and fill SELL order: 100 shares @ Rs 550
        sell_order = PaperOrder(
            account_id=account.id,
            symbol="INFY",
            side="SELL",
            order_type="MARKET",
            qty=100,
            order_price=Decimal("550.00"),
            status="PENDING",
            idempotency_key=str(uuid.uuid4()),
        )
        db.add(sell_order)
        db.flush()

        s_order, updated_pos, s_trade, s_msg = service._try_fill_order(
            account=account,
            order=sell_order,
            current_price=550.0,
            require_market_open=False,
        )
        assert s_order.status == "FILLED"
        assert updated_pos is None  # Position fully closed
        assert s_trade is not None
        # Gross P&L = (550 - 500) * 100 = Rs 5,000.00
        assert Decimal(str(s_trade.gross_pnl)) == Decimal("5000.00")
        # Sell charges = 57.07, Total trade charges = 59.38 + 57.07 = 116.45
        assert Decimal(str(s_trade.total_charges)) == Decimal("116.45")
        # Net P&L = 5000 - 116.45 = 4883.55
        assert Decimal(str(s_trade.net_pnl)) == Decimal("4883.55")
        assert Decimal(str(s_trade.pnl)) == Decimal("4883.55")

        # Net cash balance = expected_cash_after_buy + (55,000 - 57.07)
        # = starting_cash - 50,059.38 + 54,942.93 = starting_cash + 4,883.55 (exact Net P&L added to capital!)
        assert Decimal(str(account.cash_balance)) == starting_cash + Decimal("4883.55")
        db.commit()

        # 5. Check Trade Charges endpoint
        res_trade_charges = api.get(f"/paper-trading/trades/{s_trade.id}/charges", headers=headers)
        assert res_trade_charges.status_code == 200, res_trade_charges.text
        trade_charges_data = res_trade_charges.json()
        assert len(trade_charges_data) == 1
        assert trade_charges_data[0]["side"] == "SELL"
        assert trade_charges_data[0]["charges"]["total_charges"] == 57.07

        # 6. Check Dashboard Summary has gross and net items
        res_dash = api.get("/paper-trading/dashboard", headers=headers)
        assert res_dash.status_code == 200
        dash_acc = res_dash.json()["account"]
        assert dash_acc["gross_realized_pnl"] == 5000.0
        assert dash_acc["total_charges_paid"] == 116.45
        assert dash_acc["net_realized_pnl"] == 4883.55
        assert dash_acc["realized_pnl"] == 4883.55

    finally:
        db.close()
