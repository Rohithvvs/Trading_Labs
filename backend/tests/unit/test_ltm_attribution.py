from datetime import date

import pytest

from app.services.strategies.ltm.attribution import build_boards, per_name_backtests
from app.services.strategies.ltm.book_engine import Trade


def _t(sym, entry, exit_, pnl, open_=False):
    return Trade(
        symbol=sym,
        entry_date=entry,
        exit_date=exit_,
        entry_price=100,
        exit_price=100 * (1 + pnl),
        shares=1,
        pnl_pct=pnl,
        reason="REBALANCE" if not open_ else "open_mtm",
        open=open_,
    )


def test_never_selected_excluded_from_boards():
    asof = date(2026, 8, 14)
    trades = [_t("WIN", date(2026, 1, 1), date(2026, 6, 1), 0.20)]
    reports = per_name_backtests(trades, asof=asof, history_valid={"WIN", "NEVER"})
    assert "NEVER" not in reports
    top, least = build_boards(reports, {"WIN": "REJECT", "NEVER": "REJECT"})
    assert [r["symbol"] for r in top] == ["WIN"]
    assert "NEVER" not in [r["symbol"] for r in least]


def test_open_mtm_counts():
    asof = date(2026, 8, 14)
    trades = [_t("HOLD", date(2025, 10, 1), None, 0.10, open_=True)]
    reports = per_name_backtests(trades, asof=asof, history_valid={"HOLD"})
    assert reports["HOLD"]["trade_count"] == 1
    assert reports["HOLD"]["net_return"] == pytest.approx(0.10)
    top, _least = build_boards(reports, {"HOLD": "WATCH"})
    assert top[0]["symbol"] == "HOLD"
    assert top[0]["signal"] == "WATCH"


def test_top5_only_positive():
    asof = date(2026, 8, 14)
    trades = [
        _t("P1", date(2026, 1, 1), date(2026, 2, 1), 0.05),
        _t("L1", date(2026, 1, 1), date(2026, 2, 1), -0.20),
    ]
    reports = per_name_backtests(trades, asof=asof)
    top, least = build_boards(reports, {"P1": "BUY", "L1": "REJECT"})
    assert [r["symbol"] for r in top] == ["P1"]
    assert least[0]["symbol"] == "L1"


def test_3y_window_resolves_to_requested_dates():
    from app.services.strategies.ltm.attribution import window_start

    asof = date(2026, 8, 14)
    assert window_start(asof, years=3) == date(2023, 8, 14)


def test_apply_windowed_attribution_uses_3y_and_excludes_missing_from_average():
    from app.services.strategies.ltm.attribution import apply_windowed_attribution
    from app.services.strategies.ltm.identity import STRATEGY_ID

    asof = date(2026, 8, 14)
    payload = {
        "strategy_id": STRATEGY_ID,
        "evaluation_date": asof.isoformat(),
        "recommendations": [
            {"symbol": "WIN", "signal": "BUY", "backtest_1y": {"failed": False, "net_return": 0.1}, "first_failure": None},
            {
                "symbol": "SKIP",
                "signal": "REJECT",
                "backtest_1y": {"failed": False, "net_return": None, "never_selected_in_window": True},
                "first_failure": "failed_momentum_gate",
            },
            {"symbol": "MISS", "signal": "REJECT", "backtest_1y": None, "first_failure": "insufficient_history"},
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
                "reason": "REBALANCE",
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
                "reason": "REBALANCE",
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
    assert avg["strategy_id"] == STRATEGY_ID
    assert avg["universe_size"] == 3
    assert avg["valid_backtests"] == 1
    assert avg["unavailable"] == 2
    assert abs(avg["average_return"] - 0.32) < 1e-9
    assert out["data_coverage"]["complete_3y"] is False


def test_universe_average_does_not_treat_missing_as_zero():
    from app.services.strategies.ltm.attribution import universe_average

    asof = date(2026, 8, 14)
    recs = [{"backtest_1y": {"net_return": 0.2}}, {"backtest_1y": {"net_return": None}}, {"backtest_1y": None}]
    summary = universe_average(recs, asof=asof, years=3)
    assert summary["universe_size"] == 3
    assert summary["valid_backtests"] == 1
    assert summary["unavailable"] == 2
    assert abs(summary["average_return"] - 0.2) < 1e-9
