import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from backend.app.models.paper_trading import PaperPosition, PaperTradeHistory, PaperOrder
from backend.app.services.paper_trading_service import PaperTradingService

@pytest.fixture
def paper_service():
    service = PaperTradingService(MagicMock())
    service.db = MagicMock()
    service.logger = MagicMock()
    return service

def test_try_fill_order_manual_exit(paper_service):
    account = MagicMock()
    account.id = 1
    account.cash_balance = Decimal("100000.00")
    account.starting_balance = Decimal("100000.00")
    account.realized_pnl = Decimal("0.00")
    account.unrealized_pnl = Decimal("0.00")
    
    order = PaperOrder(
        id=10,
        account_id=1,
        symbol="RELIANCE",
        side="SELL",
        order_type="MARKET",
        qty=Decimal("10"),
        order_price=None,
        status="PENDING"
    )
    
    position = PaperPosition(
        id=5,
        account_id=1,
        symbol="RELIANCE",
        qty=Decimal("10"),
        avg_entry_price=Decimal("2500.00"),
        status="OPEN",
        created_at=datetime.utcnow()
    )
    
    # Mock finding the position
    paper_service.db.scalar.return_value = position
    
    current_price = 2600.00
    filled_order, updated_position, trade_info, message = paper_service._try_fill_order(account, order, current_price)
    
    # Check that a PaperTradeHistory record was added
    add_calls = paper_service.db.add.call_args_list
    trade_history = None
    for call in add_calls:
        if isinstance(call[0][0], PaperTradeHistory):
            trade_history = call[0][0]
            
    assert trade_history is not None
    assert trade_history.exit_reason == "MANUAL"
    assert trade_history.exit_source == "MANUAL"

def test_auto_exit_sets_source(paper_service):
    from backend.app.schemas.paper_trading import PaperAccountSummary

    account = MagicMock()
    account.id = 1
    account.name = "Paper"
    account.base_currency = "INR"
    account.cash_balance = Decimal("100000.00")
    account.starting_balance = Decimal("100000.00")
    account.realized_pnl = Decimal("0.00")
    account.unrealized_pnl = Decimal("0.00")
    account.max_risk_per_trade = Decimal("0")
    
    position = PaperPosition(
        id=5,
        account_id=1,
        symbol="RELIANCE",
        qty=Decimal("10"),
        avg_entry_price=Decimal("2500.00"),
        status="OPEN",
        created_at=datetime.utcnow()
    )
    
    summary = PaperAccountSummary(
        account_id=1,
        account_name="Paper",
        starting_balance=100000.0,
        balance=76000.0,
        equity=76000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        total_invested=0.0,
        reserved_cash=0.0,
        available_cash=76000.0,
        open_positions_count=0,
        open_orders_count=0,
        max_risk_per_trade=0.0,
        updated_at=datetime.now(timezone.utc),
    )
    # Mock account load + lean post-exit summary (auto_exit must NOT call get_dashboard)
    paper_service.get_account_by_id = MagicMock(return_value=account)
    paper_service._account_capital_for_confirm = MagicMock(return_value=summary)
    paper_service._serialize_order = MagicMock(return_value=None)
    paper_service._serialize_trade = MagicMock(return_value=None)
    # Return position on first query, then None for ExecutionEvent dedupe check
    paper_service.db.scalar.side_effect = [position, None]
    paper_service.db.bind = None
    paper_service._record_execution_event = MagicMock()
    paper_service.add_notification = MagicMock()
    paper_service.get_dashboard = MagicMock()
    
    paper_service.auto_exit(position.id, 2400.00, reason="STOPLOSS_HIT", source="LIVE")
    paper_service.get_dashboard.assert_not_called()
    
    add_calls = paper_service.db.add.call_args_list
    trade_history = None
    for call in add_calls:
        if isinstance(call[0][0], PaperTradeHistory):
            trade_history = call[0][0]
            
    assert trade_history is not None
    assert trade_history.exit_reason == "STOPLOSS_HIT"
    assert trade_history.exit_source == "LIVE"
