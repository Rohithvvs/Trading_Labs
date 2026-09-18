from datetime import date

from app.services.strategies.breakout52w.analytics import build_symbol_dashboard, parse_window, resolve_window_bounds
from app.services.strategies.breakout52w.identity import STRATEGY_ID


def test_8y_window_resolves_eight_calendar_years():
    key, start, end = resolve_window_bounds(date(2026, 8, 21), "8Y")
    assert (key, start, end) == ("8Y", date(2018, 8, 21), date(2026, 8, 21))


def test_default_window_is_3y():
    assert parse_window(None) == "3Y"
    assert parse_window("bogus") == "3Y"
    key, start, end = resolve_window_bounds(date(2026, 8, 14), "3Y")
    assert (key, start, end) == ("3Y", date(2023, 8, 14), date(2026, 8, 14))


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
            "reason": "atr_trail",
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
            "reason": "atr_trail",
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
        {
            "strategy_id": STRATEGY_ID,
            "evaluation_date": "2025-08-15",
            "recommendations": [{"symbol": "AAA-EQ", "signal": "BUY", "backtest_1y": {"failed": False}}],
        },
        "AAA-EQ",
        "1Y",
        blotter=blotter,
        equity_curve=curve,
        index_curve=[{"date": "2024-01-10", "close": 1000}, {"date": "2025-08-15", "close": 1100}],
        asof=date(2025, 8, 15),
        initial_capital=100000,
    )
    assert dash["strategy_id"] == STRATEGY_ID
    assert dash["window"] == "1Y"
    assert dash["trade_count"] == 1
    assert dash["never_selected_in_window"] is False
    assert dash["best_trade"]["pnl_percent"] == 20.0
    assert dash["total_return"] is not None
    assert dash["cagr"] is None or isinstance(dash["cagr"], float)
    assert dash["equity_curve"]
    assert dash["monthly_returns"]


def test_3y_includes_older_trade_and_populates_cards():
    blotter = [
        {
            "symbol": "AAA-EQ",
            "entry_date": "2024-01-10",
            "exit_date": "2024-06-10",
            "entry_price": 100,
            "exit_price": 110,
            "shares": 1,
            "pnl_pct": 0.10,
            "reason": "atr_trail",
            "open": False,
        }
    ]
    dash = build_symbol_dashboard(
        {"strategy_id": STRATEGY_ID, "evaluation_date": "2026-08-14", "recommendations": [{"symbol": "AAA-EQ", "signal": "BUY"}]},
        "AAA-EQ",
        "3Y",
        blotter=blotter,
        equity_curve=[
            {"date": "2023-08-14", "equity": 100000},
            {"date": "2026-08-14", "equity": 110000},
        ],
        asof=date(2026, 8, 14),
    )
    assert dash["window"] == "3Y"
    assert dash["window_start"] == "2023-08-14"
    assert dash["window_end"] == "2026-08-14"
    assert dash["trade_count"] == 1
    assert dash["total_return"] == 10.0
    assert dash["win_rate"] == 100.0
    assert dash["profit_factor_infinite"] is True


def test_empty_window_is_honest():
    dash = build_symbol_dashboard(
        {"strategy_id": STRATEGY_ID, "evaluation_date": "2026-08-14"},
        "ZZZ-EQ",
        "3Y",
        blotter=[],
        equity_curve=[{"date": "2025-06-18", "equity": 100000}],
        asof=date(2026, 8, 14),
    )
    assert dash["trade_count"] == 0
    assert dash["never_selected_in_window"] is True
    assert dash["unavailable_reason"] == "never_selected_in_window"
    assert dash["best_trade"] is None
    assert dash["total_return"] is None
    assert dash["equity_curve"] == []


def test_buy_names_do_not_share_book_equity():
    """Stock-detail Backtest must be per-name. The 10-slot book curve is shared."""
    blotter = [
        {
            "symbol": "AAA-EQ",
            "entry_date": "2024-01-10",
            "exit_date": "2024-06-10",
            "entry_price": 100,
            "exit_price": 150,
            "shares": 10,
            "pnl_pct": 0.50,
            "reason": "atr_trail",
            "open": False,
        },
        {
            "symbol": "BBB-EQ",
            "entry_date": "2024-02-10",
            "exit_date": "2024-08-10",
            "entry_price": 200,
            "exit_price": 160,
            "shares": 5,
            "pnl_pct": -0.20,
            "reason": "atr_trail",
            "open": False,
        },
    ]
    book_curve = [
        {"date": "2023-08-14", "equity": 100000},
        {"date": "2024-06-10", "equity": 115000},
        {"date": "2024-08-10", "equity": 108000},
        {"date": "2026-08-14", "equity": 125000},
    ]
    payload = {
        "strategy_id": STRATEGY_ID,
        "evaluation_date": "2026-08-14",
        "recommendations": [
            {"symbol": "AAA-EQ", "signal": "BUY"},
            {"symbol": "BBB-EQ", "signal": "BUY"},
        ],
        "book_metrics": {"total_return": 0.25, "initial_capital": 100000},
    }
    aaa = build_symbol_dashboard(
        payload, "AAA-EQ", "3Y", blotter=blotter, equity_curve=book_curve, asof=date(2026, 8, 14)
    )
    bbb = build_symbol_dashboard(
        payload, "BBB-EQ", "3Y", blotter=blotter, equity_curve=book_curve, asof=date(2026, 8, 14)
    )
    assert aaa["symbol"] == "AAA-EQ"
    assert bbb["symbol"] == "BBB-EQ"
    assert aaa["total_return"] == 50.0
    assert bbb["total_return"] == -20.0
    assert aaa["trade_count"] == 1
    assert bbb["trade_count"] == 1
    assert aaa["trades"][0]["entry_price"] == 100
    assert bbb["trades"][0]["entry_price"] == 200
    assert aaa["equity_curve"]
    assert bbb["equity_curve"]
    assert aaa["equity_curve"][-1]["equity"] != bbb["equity_curve"][-1]["equity"]
    assert aaa["equity_curve"][-1]["equity"] != 125000
    assert bbb["equity_curve"][-1]["equity"] != 125000
    assert aaa["total_return"] != bbb["total_return"]
