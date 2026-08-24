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
    assert dash["total_return"] is None
    assert dash["equity_curve"] == []


def test_selected_names_do_not_share_book_equity():
    blotter = [
        {
            "symbol": "AAA-EQ",
            "entry_date": "2024-01-10",
            "exit_date": "2024-06-10",
            "entry_price": 100,
            "exit_price": 130,
            "shares": 10,
            "pnl_pct": 0.30,
            "reason": "REBALANCE",
            "open": False,
        },
        {
            "symbol": "BBB-EQ",
            "entry_date": "2024-01-10",
            "exit_date": "2024-06-10",
            "entry_price": 50,
            "exit_price": 40,
            "shares": 20,
            "pnl_pct": -0.20,
            "reason": "REBALANCE",
            "open": False,
        },
    ]
    book_curve = [
        {"date": "2023-08-15", "equity": 100000},
        {"date": "2025-08-15", "equity": 140000},
    ]
    aaa = build_symbol_dashboard(
        symbol="AAA-EQ",
        blotter=blotter,
        equity_curve=book_curve,
        index_curve=[],
        asof=date(2025, 8, 15),
        window="3Y",
        initial_capital=100000,
    )
    bbb = build_symbol_dashboard(
        symbol="BBB-EQ",
        blotter=blotter,
        equity_curve=book_curve,
        index_curve=[],
        asof=date(2025, 8, 15),
        window="3Y",
        initial_capital=100000,
    )
    assert aaa["total_return"] == 30.0
    assert bbb["total_return"] == -20.0
    assert aaa["equity_curve"][-1]["equity"] != bbb["equity_curve"][-1]["equity"]
    assert aaa["equity_curve"][-1]["equity"] != 140000
