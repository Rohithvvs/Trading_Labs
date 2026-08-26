from datetime import date

from app.services.strategies.breakout52w.attribution import build_boards, empty_backtest, per_name_backtests
from app.services.strategies.breakout52w.book_engine import Trade


def test_never_selected_excluded_from_boards():
    asof = date(2026, 8, 14)
    reports = {
        "WIN": {
            "net_return": 0.1,
            "trade_count": 1,
            "win_rate": 1.0,
            "max_drawdown": 0.0,
            "profit_factor": None,
            "never_selected_in_window": False,
            "failed": False,
            "window_start": "2025-08-14",
            "window_end": "2026-08-14",
        },
        "SKIP": empty_backtest(asof),
        "FAIL": empty_backtest(asof, failed=True),
    }
    top5, least5 = build_boards(reports, {"WIN": "REJECT", "SKIP": "REJECT"})
    assert [r["symbol"] for r in top5] == ["WIN"]
    assert all(r["symbol"] != "SKIP" for r in least5)
    assert all(r["symbol"] != "FAIL" for r in least5)


def test_profit_factor_survives_breakeven_trades():
    """Zero PnL must not be treated as a loss with a zero denominator."""
    asof = date(2026, 8, 14)
    trades = [
        Trade("AAA", date(2026, 1, 1), date(2026, 2, 1), 100.0, 110.0, 1.0, 0.10, "atr_trail", False),
        Trade("AAA", date(2026, 3, 1), date(2026, 4, 1), 110.0, 110.0, 1.0, 0.0, "time_stop", False),
        Trade("BBB", date(2026, 1, 1), date(2026, 2, 1), 50.0, 50.0, 1.0, 0.0, "time_stop", False),
        Trade("CCC", date(2026, 1, 1), date(2026, 2, 1), 80.0, 72.0, 1.0, -0.10, "stop", False),
        Trade("DDD", date(2026, 1, 1), date(2026, 2, 1), 100.0, 120.0, 1.0, 0.20, "atr_trail", False),
        Trade("DDD", date(2026, 3, 1), date(2026, 4, 1), 120.0, 108.0, 1.0, -0.10, "stop", False),
    ]
    reports = per_name_backtests(
        trades, asof=asof, years=1, history_valid={"AAA", "BBB", "CCC", "DDD"}
    )
    assert reports["AAA"]["profit_factor"] == float("inf")
    assert reports["BBB"]["profit_factor"] is None
    assert reports["CCC"]["profit_factor"] == 0.0
    assert abs(reports["DDD"]["profit_factor"] - 2.0) < 1e-9


def test_open_mtm_counts():
    asof = date(2026, 8, 14)
    trades = [
        Trade("AAA", date(2026, 6, 1), None, 100.0, 110.0, 1.0, 0.10, "open_mtm", True),
    ]
    reports = per_name_backtests(trades, asof=asof, years=1, history_valid={"AAA"})
    assert reports["AAA"]["trade_count"] == 1
    assert abs(reports["AAA"]["net_return"] - 0.10) < 1e-9


def test_3y_window_resolves_to_requested_dates():
    from app.services.strategies.breakout52w.attribution import window_start
    from app.services.strategies.breakout52w.analytics import resolve_window_bounds

    asof = date(2026, 8, 14)
    assert window_start(asof, years=3) == date(2023, 8, 14)
    key, start, end = resolve_window_bounds(asof, "3Y")
    assert key == "3Y"
    assert start == date(2023, 8, 14)
    assert end == date(2026, 8, 14)


def test_apply_windowed_attribution_uses_3y_and_excludes_missing_from_average():
    from app.services.strategies.breakout52w.attribution import apply_windowed_attribution
    from app.services.strategies.breakout52w.identity import STRATEGY_ID

    asof = date(2026, 8, 14)
    payload = {
        "strategy_id": STRATEGY_ID,
        "evaluation_date": asof.isoformat(),
        "recommendations": [
            {"symbol": "WIN", "signal": "BUY", "backtest_1y": {"failed": False, "net_return": 0.1}, "first_failure": None},
            {"symbol": "SKIP", "signal": "REJECT", "backtest_1y": {"failed": False, "net_return": None, "never_selected_in_window": True}, "first_failure": "close_below_prior_high"},
            {"symbol": "FAIL", "signal": "REJECT", "backtest_1y": {"failed": True, "net_return": None}, "first_failure": "data_source_failure"},
        ],
        "blotter": [
            {
                "symbol": "WIN",
                "entry_date": "2024-01-10",
                "exit_date": "2024-06-10",
                "entry_price": 100,
                "exit_price": 120,
                "shares": 1,
                "pnl_pct": 0.20,
                "reason": "atr_trail",
                "open": False,
            },
            {
                "symbol": "WIN",
                "entry_date": "2025-09-01",
                "exit_date": "2025-12-01",
                "entry_price": 120,
                "exit_price": 132,
                "shares": 1,
                "pnl_pct": 0.10,
                "reason": "atr_trail",
                "open": False,
            },
        ],
        "equity_curve": [
            {"date": "2025-06-18", "equity": 100000},
            {"date": "2026-08-14", "equity": 105000},
        ],
    }
    out = apply_windowed_attribution(payload, years=3)
    assert out["attribution_window"] == "3Y"
    assert out["attribution_window_start"] == "2023-08-14"
    assert out["attribution_window_end"] == "2026-08-14"
    assert out["top5_positive"][0]["symbol"] == "WIN"
    assert out["top5_positive"][0]["window_start"] == "2023-08-14"
    avg = out["universe_average"]
    assert avg["universe_size"] == 3
    assert avg["valid_backtests"] == 1
    assert avg["unavailable"] == 2
    assert abs(avg["average_return"] - 0.32) < 1e-9
    assert out["data_coverage"]["complete_3y"] is False
    assert out["data_coverage"]["ohlcv_start"] == "2025-06-18"


def test_universe_average_does_not_treat_missing_as_zero():
    from app.services.strategies.breakout52w.attribution import universe_average

    asof = date(2026, 8, 14)
    recs = [{"backtest_1y": {"net_return": 0.2}}, {"backtest_1y": {"net_return": None}}, {"backtest_1y": None}]
    summary = universe_average(recs, asof=asof, years=3)
    assert summary["universe_size"] == 3
    assert summary["valid_backtests"] == 1
    assert summary["unavailable"] == 2
    assert abs(summary["average_return"] - 0.2) < 1e-9
