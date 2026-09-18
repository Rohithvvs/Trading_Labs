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
