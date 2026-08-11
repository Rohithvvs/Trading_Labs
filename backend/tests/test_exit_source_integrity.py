import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from backend.app.services.paper_trading_service import PaperTradingService
from backend.app.models.paper_trading import PaperTradeHistory

@pytest.fixture
def paper_service():
    service = PaperTradingService(MagicMock())
    service.db = MagicMock()
    service.logger = MagicMock()
    return service

def test_legacy_null_exit_source_serialization(paper_service):
    """
    TEST CATEGORY 10 — EXIT SOURCE INTEGRITY
    Legacy Rows: NULL
    Verify frontend fallback still works by ensuring serialization handles None correctly.
    """
    trade = PaperTradeHistory(
        id=1,
        account_id=1,
        symbol="TEST",
        qty=Decimal("10"),
        entry_price=Decimal("100.00"),
        exit_price=Decimal("105.00"),
        pnl=Decimal("50.00"),
        pnl_percent=Decimal("5.00"),
        opened_at=datetime.utcnow(),
        closed_at=datetime.utcnow(),
        exit_reason="MANUAL_EXIT",
        exit_source=None,  # Legacy row
    )
    
    serialized = paper_service._serialize_trade(trade)
    
    # Ensures it doesn't crash and correctly passes None up to the API layer
    # where the frontend `?? "MANUAL"` will take over
    assert serialized.exit_source is None
    assert serialized.exit_reason == "MANUAL_EXIT"

def test_reconciliation_exit_source(paper_service):
    """
    TEST CATEGORY 10 — EXIT SOURCE INTEGRITY
    Verify RECONCILIATION exit source is assigned when an order is historically filled.
    Actually, RECONCILIATION exits are simulated by auto_exit passing source="RECONCILIATION".
    """
    from backend.app.schemas.paper_trading import PaperAccountSummary

    # This is handled exactly the same way as LIVE, we just ensure the parameter propagates.
    account_mock = MagicMock()
    account_mock.id = 1
    account_mock.name = "Paper"
    account_mock.base_currency = "INR"
    account_mock.cash_balance = Decimal("100000.00")
    account_mock.starting_balance = Decimal("100000.00")
    account_mock.realized_pnl = Decimal("0.00")
    account_mock.unrealized_pnl = Decimal("0.00")
    account_mock.max_risk_per_trade = Decimal("0")
    summary = PaperAccountSummary(
        account_id=1,
        account_name="Paper",
        starting_balance=100000.0,
        balance=101000.0,
        equity=101000.0,
        realized_pnl=100.0,
        unrealized_pnl=0.0,
        total_invested=0.0,
        reserved_cash=0.0,
        available_cash=101000.0,
        open_positions_count=0,
        open_orders_count=0,
        max_risk_per_trade=0.0,
        updated_at=datetime.now(timezone.utc),
    )
    paper_service.get_account_by_id = MagicMock(return_value=account_mock)
    paper_service._account_capital_for_confirm = MagicMock(return_value=summary)
    paper_service._serialize_order = MagicMock(return_value=None)
    paper_service._serialize_trade = MagicMock(return_value=None)
    paper_service._record_execution_event = MagicMock()
    paper_service.add_notification = MagicMock()
    pos_mock = MagicMock(
        id=5,
        account_id=1,
        qty=Decimal("10"),
        avg_entry_price=Decimal("100"),
        symbol="RELIANCE",
        notes=None,
        source_signal=None,
        source_score=None,
        source_confidence=None,
        source_engine_id=None,
        source_engine_version=None,
        source_recommendation_id=None,
        experiment_id=None,
        created_at=None,
    )
    paper_service.db.scalar.side_effect = [pos_mock, None]
    paper_service.db.bind = None
    
    paper_service.auto_exit(5, 110.00, reason="TARGET_HIT", source="RECONCILIATION")
    
    add_calls = paper_service.db.add.call_args_list
    trade_history = None
    for call in add_calls:
        if isinstance(call[0][0], PaperTradeHistory):
            trade_history = call[0][0]
            
    assert trade_history is not None
    assert trade_history.exit_source == "RECONCILIATION"
