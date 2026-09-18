"""Canonical closed-trade ledger vs any other trade-count dataset."""

from datetime import date

from app.services.strategies.breakout52w.analytics import build_symbol_dashboard
from app.services.strategies.breakout52w.book_engine import Trade
from app.services.strategies.breakout52w.ledger import aggregate_closed_trades
from app.services.strategies.breakout52w.period import filter_period_trades


def _t(entry: str, exit: str | None, pnl: float, *, open_: bool = False) -> dict:
    return {
        "symbol": "IIFL-EQ",
        "entry_date": entry,
        "exit_date": exit,
        "entry_price": 100.0,
        "exit_price": None if open_ else 100.0 * (1 + pnl),
        "shares": 1.0,
        "pnl_pct": 0.0 if open_ else pnl,
        "reason": "open_mtm" if open_ else "atr_trail",
        "open": open_,
        "net_pnl": 0.0 if open_ else pnl * 100.0,
    }


IIFL_BLOTTER = [
    _t("2021-02-09", "2021-03-25", 0.2725),
    _t("2022-04-27", "2022-05-09", -0.1959),
    _t("2022-10-27", "2022-12-23", 0.1045),
    _t("2023-07-10", "2023-08-14", 0.0382),
    _t("2023-10-16", "2023-10-26", -0.1110),
    _t("2025-10-30", "2026-01-22", -0.0054),
    _t("2026-08-21", None, 0.0, open_=True),
]


def _dash(blotter, *, window="8Y", start=None, end=None):
    return build_symbol_dashboard(
        {
            "strategy_id": "09_52w_breakout",
            "evaluation_date": "2026-08-21",
            "recommendations": [{"symbol": "IIFL-EQ", "signal": "BUY"}],
        },
        "IIFL-EQ",
        window,
        blotter=blotter,
        asof=date(2026, 8, 21),
        initial_capital=100000,
        symbol_replay=True,
        window_start=start,
        window_end=end,
    )


def test_canonical_count_excludes_open_mark():
    dash = _dash(IIFL_BLOTTER, start=date(2018, 8, 21), end=date(2026, 8, 21))
    dist = dash["trade_distribution"]
    closed = [t for t in dash["trades"] if not t.get("open")]
    opened = [t for t in dash["trades"] if t.get("open")]
    assert len(closed) == 6
    assert len(opened) == 1
    assert dash["trade_count"] == 6
    assert dist["total_trades"] == 6
    assert dist["open_trades"] == 1
    assert dist["source"] == "closed_trade_ledger"


def test_classification_three_winners_three_losers():
    dash = _dash(IIFL_BLOTTER, start=date(2018, 8, 21), end=date(2026, 8, 21))
    dist = dash["trade_distribution"]
    assert dist["winners"] == 3
    assert dist["losers"] == 3
    assert dist["breakevens"] == 0
    assert dist["winners"] + dist["losers"] + dist["breakevens"] == dist["total_trades"]


def test_open_trade_does_not_increase_closed_counts():
    closed_only = IIFL_BLOTTER[:-1]
    with_open = IIFL_BLOTTER
    a = _dash(closed_only, start=date(2018, 8, 21), end=date(2026, 8, 21))
    b = _dash(with_open, start=date(2018, 8, 21), end=date(2026, 8, 21))
    for key in ("total_trades", "winners", "losers", "breakevens"):
        assert a["trade_distribution"][key] == b["trade_distribution"][key]
    assert b["trade_distribution"]["open_trades"] == 1
    assert a["trade_distribution"]["open_trades"] == 0


def test_date_range_rebuilds_ledger_instead_of_reusing_all_history():
    five_y = _dash(IIFL_BLOTTER, window="CUSTOM", start=date(2021, 8, 21), end=date(2026, 8, 21))
    eight_y = _dash(IIFL_BLOTTER, window="CUSTOM", start=date(2018, 8, 21), end=date(2026, 8, 21))
    assert five_y["trade_distribution"]["total_trades"] == 5
    assert eight_y["trade_distribution"]["total_trades"] == 6
    assert five_y["trade_count"] != eight_y["trade_count"]


def test_distribution_matches_ledger_and_closed_log():
    dash = _dash(IIFL_BLOTTER, start=date(2018, 8, 21), end=date(2026, 8, 21))
    closed = [t for t in dash["trades"] if not t.get("open")]
    dist = dash["trade_distribution"]
    ledger = dash["ledger"]
    assert len(closed) == ledger["total_trades"] == dist["total_trades"] == dash["trade_count"]
    assert ledger["winning_trades"] == dist["winners"] == 3
    assert ledger["losing_trades"] == dist["losers"] == 3
    assert ledger["breakeven_trades"] == dist["breakevens"] == 0


def test_filter_period_trades_does_not_leak_other_symbol():
    other = dict(IIFL_BLOTTER[0])
    other["symbol"] = "GLAXO-EQ"
    dash = _dash(IIFL_BLOTTER + [other], start=date(2018, 8, 21), end=date(2026, 8, 21))
    assert all(t["symbol"] == "IIFL-EQ" for t in dash["trades"])
    assert dash["trade_distribution"]["total_trades"] == 6


def test_aggregate_closed_trades_ignores_open_marks_directly():
    trades = [
        Trade("IIFL-EQ", date(2021, 2, 9), date(2021, 3, 25), 100, 127.25, 1, 0.2725, "atr_trail", False, net_pnl=27.25),
        Trade("IIFL-EQ", date(2026, 8, 21), None, 678.5, None, 1, None, "open_mtm", True),
    ]
    metrics = aggregate_closed_trades(trades)
    assert metrics["total_trades"] == 1
    assert metrics["winning_trades"] == 1


def test_period_filter_counts_by_entry_date():
    objs = [
        Trade("IIFL-EQ", date(2021, 2, 9), date(2021, 3, 25), 100, 127, 1, 0.27, "atr_trail"),
        Trade("IIFL-EQ", date(2022, 4, 27), date(2022, 5, 9), 100, 80, 1, -0.2, "atr_trail"),
    ]
    a = filter_period_trades(objs, date(2021, 8, 21), date(2026, 8, 21))
    b = filter_period_trades(objs, date(2018, 8, 21), date(2026, 8, 21))
    assert len(a) == 1
    assert len(b) == 2
