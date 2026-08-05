"""Portfolio unavailable fail-closed for BUY."""

from app.services.re002.portfolio_context import portfolio_blocks_buy, resolve_portfolio_snapshot


def test_unavailable_blocks_buy():
    snap = resolve_portfolio_snapshot(user_portfolio=None, risk_settings=None)
    blocked, reason = portfolio_blocks_buy(snap)
    assert blocked
    assert reason == "portfolio_context_unavailable"


def test_available_ok():
    snap = resolve_portfolio_snapshot(
        user_portfolio={"open_positions_count": 0, "max_positions": 5, "available_cash": 10000},
    )
    blocked, reason = portfolio_blocks_buy(snap)
    assert not blocked
    assert reason is None
