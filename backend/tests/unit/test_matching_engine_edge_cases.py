import uuid

from backend.app.models.paper_trading import PaperOrder, PaperPosition
from backend.app.services.paper_trading_service import PaperTradingService

_TEST_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")


def test_gap_down_stop_loss_execution(db_session):
    """
    Mock an order with a stop-loss at 100. Feed it a new daily open candle
    that gaps down to 90. Assert that the matching engine executes the fill
    exactly at the gap price (90), not the ideal trigger price (100).
    """
    service = PaperTradingService(db_session, user_id=_TEST_USER_ID)
    
    # Setup initial account and position
    account = service._get_or_create_account()
    
    # Create an open position at 120
    position = PaperPosition(
        account_id=account.id,
        status="OPEN",
        lifecycle_state="OPEN_POSITION",
        symbol="GAP_TEST",
        qty=10,
        avg_entry_price=120.0,
        current_price=120.0,
        stop_loss=100.0,
    )
    db_session.add(position)
    
    # Create the pending STOP order to sell at 100
    stop_order = PaperOrder(
        account_id=account.id,
        symbol="GAP_TEST",
        side="SELL",
        order_type="STOP",
        product_type="CNC",
        qty=10,
        order_price=100.0,  # Limit price fallback
        stop_price=100.0,   # Trigger price
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )
    db_session.add(stop_order)
    db_session.commit()
    
    # Market opens and the price gaps down instantly to 90
    gap_price = 90.0
    
    # Process the fill
    filled_order, updated_position, trade, message = service._try_fill_order(
        account=account,
        order=stop_order,
        current_price=gap_price,
        require_market_open=False,
    )
    
    # Assertions
    assert filled_order.status == "FILLED"
    # The crucial assertion: executed at gap price (90), not stop price (100)
    assert filled_order.filled_price == 90.0
    
    # The position should be fully closed
    assert updated_position is None
    
    # The trade history should reflect the gap down PnL
    assert trade is not None
    assert trade.exit_price == 90.0
    assert trade.pnl == (90.0 - 120.0) * 10  # -300.0


def test_partial_fill_scaling(db_session):
    """
    Mock an execution where only 50% of the target quantity is filled. Assert
    that the database updates the position size correctly without duplicating
    the initial invested capital tracking rows.
    """
    service = PaperTradingService(db_session, user_id=_TEST_USER_ID)
    account = service._get_or_create_account()
    
    # Create an open position for 100 shares
    position = PaperPosition(
        account_id=account.id,
        status="OPEN",
        lifecycle_state="OPEN_POSITION",
        symbol="PARTIAL_TEST",
        qty=100,
        avg_entry_price=50.0,
        current_price=50.0,
    )
    db_session.add(position)
    db_session.commit()
    
    # We want to sell 50 shares (50% partial fill)
    partial_sell_order = PaperOrder(
        account_id=account.id,
        symbol="PARTIAL_TEST",
        side="SELL",
        order_type="MARKET",
        product_type="CNC",
        qty=50,
        order_price=60.0,
        status="PENDING",
    )
    db_session.add(partial_sell_order)
    db_session.commit()
    
    filled_order, updated_position, trade, message = service._try_fill_order(
        account=account,
        order=partial_sell_order,
        current_price=60.0,
        require_market_open=False,
    )
    
    assert filled_order.status == "FILLED"
    assert filled_order.qty == 50
    assert trade.qty == 50
    
    # Assert position was updated correctly
    assert updated_position is not None
    assert updated_position.qty == 50
    # Average entry price should remain untouched for the remaining shares
    assert updated_position.avg_entry_price == 50.0
    
    # Count the number of positions for this symbol
    position_count = db_session.query(PaperPosition).filter_by(symbol="PARTIAL_TEST").count()
    assert position_count == 1, "Should not duplicate capital tracking rows"


def test_adjust_long_position_levels_scaling():
    from decimal import Decimal
    from backend.app.services.paper_trading_service import PaperTradingService

    # Case 1: ABCAPITAL - limit 410.05, stop 401.85, fill 400.55 (stop >= fill)
    stop, target = PaperTradingService._adjust_long_position_levels(
        fill_price=Decimal("400.55"),
        order_price=Decimal("410.05"),
        order_stop_loss=Decimal("401.85"),
        order_target=Decimal("426.45"),
    )
    assert stop is not None and stop < Decimal("400.55")
    assert stop == Decimal("392.54") or stop == Decimal("392.55")
    assert target is not None and target > Decimal("400.55")

    # Case 2: Cross-symbol mismatch (INFY with OFSS price 11896, fill 1021.80)
    stop2, target2 = PaperTradingService._adjust_long_position_levels(
        fill_price=Decimal("1021.80"),
        order_price=Decimal("11896.00"),
        order_stop_loss=Decimal("11658.10"),
        order_target=Decimal("12371.80"),
    )
    assert stop2 is not None and stop2 < Decimal("1021.80")
    assert target2 is not None and target2 > Decimal("1021.80")


def test_fill_order_prevents_inverted_stop_loss(db_session):
    from decimal import Decimal
    service = PaperTradingService(db_session, user_id=_TEST_USER_ID)
    account = service._get_or_create_account()

    buy_order = PaperOrder(
        account_id=account.id,
        symbol="LEVELS_TEST",
        side="BUY",
        order_type="LIMIT",
        product_type="CNC",
        qty=1,
        order_price=410.05,
        stop_loss=401.85,
        target=426.45,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY",
    )
    db_session.add(buy_order)
    db_session.commit()

    # Fills at live market price 400.55 (lower than limit and lower than original stop!)
    filled_order, position, trade, message = service._try_fill_order(
        account=account,
        order=buy_order,
        current_price=400.55,
        require_market_open=False,
    )

    assert filled_order.status == "FILLED"
    assert position is not None
    assert position.avg_entry_price == Decimal("400.55")
    # Stop loss must be strictly LESS than avg_entry_price!
    assert position.stop_loss is not None
    assert Decimal(str(position.stop_loss)) < Decimal("400.55")
    assert Decimal(str(position.target)) > Decimal("400.55")


def test_exact_levels_preserved_when_valid(db_session):
    """
    When order_stop_loss < fill_price and order_target > fill_price,
    the exact user-specified levels must be preserved without ratio distortion.
    """
    from decimal import Decimal
    from backend.app.services.paper_trading_service import PaperTradingService

    stop, target = PaperTradingService._adjust_long_position_levels(
        fill_price=Decimal("99.50"),
        order_price=Decimal("100.00"),
        order_stop_loss=Decimal("95.00"),
        order_target=Decimal("110.00"),
    )
    assert stop == Decimal("95.00")
    assert target == Decimal("110.00")

