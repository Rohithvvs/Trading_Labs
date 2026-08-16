from datetime import date

from app.services.strategies.ltm.analytics import build_symbol_dashboard


def test_window_filters_trades_and_reports_metrics():
    blotter = [
        {
            "symbol": "AAA-EQ",
            "entry_date": "2025-01-10",
            "exit_date": "2025-06-10",
            "entry_price": 100,
            "exit_price": 120,
            "shares": 10,
            "pnl_pct": 0.20,
            "reason": "REBALANCE",
            "open": False,
        },
        {
            "symbol": "AAA-EQ",
            "entry_date": "2022-01-10",
            "exit_date": "2022-06-10",
            "entry_price": 80,
            "exit_price": 70,
            "shares": 10,
            "pnl_pct": -0.125,
            "reason": "REBALANCE",
            "open": False,
        },
    ]
    curve = [
        {"date": "2023-08-15", "equity": 100000},
        {"date": "2024-01-10", "equity": 100000},
        {"date": "2024-06-10", "equity": 120000},
        {"date": "2025-08-15", "equity": 118000},
    ]
    dash = build_symbol_dashboard(
        symbol="AAA-EQ",
        blotter=blotter,
        equity_curve=curve,
        index_curve=[{"date": "2024-01-10", "close": 1000}, {"date": "2025-08-15", "close": 1100}],
        asof=date(2025, 8, 15),
        window="1Y",
        initial_capital=100000,
    )
    assert dash["window"] == "1Y"
    assert dash["trade_count"] == 1
    assert dash["never_selected_in_window"] is False
    assert dash["best_trade"]["pnl_percent"] == 20.0
    assert dash["equity_curve"]
    assert dash["monthly_returns"]
    assert dash["cagr"] is None or isinstance(dash["cagr"], float)


def test_empty_window_is_honest():
    dash = build_symbol_dashboard(
        symbol="ZZZ-EQ",
        blotter=[],
        equity_curve=[{"date": "2025-01-01", "equity": 100000}],
        index_curve=[],
        asof=date(2025, 8, 15),
        window="3Y",
    )
    assert dash["trade_count"] == 0
    assert dash["never_selected_in_window"] is True
    assert dash["best_trade"] is None
