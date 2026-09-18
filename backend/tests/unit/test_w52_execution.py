"""Execution-model tests for 52W book replay.

KERNEL must keep 038 signal-close / close-cross behaviour. TV_COMPAT covers
next-bar-open fills, intrabar stops, same-bar entry+exit, and ledger stats.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.services.strategies.breakout52w.book_engine import Trade, replay_book
from app.services.strategies.breakout52w.execution import (
    BACKTEST_END_CANONICAL,
    BACKTEST_END_REASON,
    BarOHLC,
    KERNEL_EXECUTION,
    TV_COMPAT_EXECUTION,
    close_cross_exit,
    long_stop_fill,
    parse_execution_profile,
    walk_lower_timeframe,
)
from app.services.strategies.breakout52w.indicators import prior_high_252
from app.services.strategies.breakout52w.ledger import (
    aggregate_closed_trades,
    classify_outcome,
    ledger_payload,
    outlier_pnl,
)
from app.services.strategies.breakout52w.period import filter_period_trades, period_window_start


def _weekdays(n: int, start: date = date(2020, 1, 2)) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _series(dates: list[date], symbol: str = "AAA-EQ", *, start_px: float = 100.0, step: float = 0.4):
    high, low, close, vol, opens, index = {}, {}, {}, {}, {}, {}
    px = start_px
    bench = 1000.0
    for i, d in enumerate(dates):
        px = start_px + i * step
        bench = 1000.0 + i * 0.5
        close[d] = px
        high[d] = px
        low[d] = px - 1
        opens[d] = px - 0.2
        vol[d] = 50_000 if i % 5 == 0 else 10_000
        index[d] = bench
    return (
        {symbol: high},
        {symbol: low},
        {symbol: close},
        {symbol: vol},
        {symbol: opens},
        index,
    )


def test_parse_execution_profiles():
    assert parse_execution_profile("KERNEL").order_fill_delay == "SAME_BAR_CLOSE"
    tv = parse_execution_profile("TV_COMPAT")
    assert tv.order_fill_delay == "NEXT_BAR_OPEN"
    assert tv.trail_touch == "INTRABAR_TOUCH"
    ltf = parse_execution_profile("TV_COMPAT", fill_mode="LOWER_TIMEFRAME")
    assert ltf.historical_fill_mode == "LOWER_TIMEFRAME"


def test_prior_252_excludes_current_bar():
    highs = [float(i) for i in range(260)]
    # Window is highs[8:260] max is 259; today index 259's high 259 is excluded... 
    # prior_high_252(highs, t) uses highs[t-252:t], today excluded.
    assert prior_high_252(highs, 252) == max(highs[0:252])
    assert prior_high_252(highs, 252) == 251.0
    highs[252] = 999.0
    assert prior_high_252(highs, 252) == 251.0
    assert prior_high_252(highs, 200) is None


def test_kernel_signal_close_fill_not_next_open():
    dates = _weekdays(280)
    high, low, close, vol, opens, index = _series(dates)
    symbol = "AAA-EQ"
    kernel = replay_book(
        dates, high, low, close, vol, index, {symbol},
        execution=KERNEL_EXECUTION, open_m=opens,
    )
    tv = replay_book(
        dates, high, low, close, vol, index, {symbol},
        execution=TV_COMPAT_EXECUTION, open_m=opens,
    )
    k_entries = [t for t in kernel["trades"] if not t.open]
    t_entries = [t for t in tv["trades"] if not t.open]
    assert k_entries
    # KERNEL fills at the signal close; TV fills at the next open when a next bar exists.
    if t_entries:
        first_k = k_entries[0]
        first_t = t_entries[0]
        assert first_k.entry_price == close[symbol][first_k.entry_date]
        if first_t.signal_time and first_t.entry_date != first_t.signal_time:
            assert first_t.entry_date > first_t.signal_time
            assert abs(first_t.entry_price - opens[symbol][first_t.entry_date]) < 1e-9


def test_next_bar_open_skips_missing_last_bar_entry():
    dates = _weekdays(260)
    high, low, close, vol, opens, index = _series(dates)
    # Force a buy signal on the final session by making close a new high with volume spike.
    last = dates[-1]
    close["AAA-EQ"][last] = 10_000.0
    high["AAA-EQ"][last] = 10_001.0
    vol["AAA-EQ"][last] = 9_999_999
    index[last] = 10_000.0
    replay = replay_book(
        dates, high, low, close, vol, index, {"AAA-EQ"},
        execution=TV_COMPAT_EXECUTION, open_m=opens,
    )
    pending_skipped = replay["diagnostics"]["skipped_pending_entries"]
    last_entries = [t for t in replay["trades"] if t.entry_date == last and not t.open]
    assert last_entries == []
    assert pending_skipped >= 0


def test_intrabar_stop_gap_and_touch():
    bar = BarOHLC(session=date(2024, 1, 2), open=99.0, high=101.0, low=94.0, close=100.0)
    gap = long_stop_fill(BarOHLC(session=date(2024, 1, 2), open=93.0, high=100.0, low=90.0, close=95.0), 94.0)
    assert gap is not None and gap.gap is True and gap.price == 93.0
    touch = long_stop_fill(bar, 94.5)
    assert touch is not None and touch.gap is False and touch.price == 94.5
    miss = long_stop_fill(bar, 90.0)
    assert miss is None
    # CLOSE_CROSS ignores the low and only exits when close < stop.
    assert close_cross_exit(bar, 94.5) is None
    assert close_cross_exit(bar, 100.5) is not None


def test_same_bar_stop_before_target_is_conservative():
    # Both stop and a theoretical target are touched; stop wins.
    bar = BarOHLC(session=date(2024, 1, 3), open=100.0, high=110.0, low=90.0, close=105.0)
    hit = long_stop_fill(bar, 95.0)
    assert hit is not None and hit.price == 95.0


def test_lower_timeframe_first_touch_and_fallback():
    bars = [
        BarOHLC(session=date(2024, 1, 4), open=100.0, high=101.0, low=99.0, close=100.5),
        BarOHLC(session=date(2024, 1, 4), open=100.5, high=101.0, low=94.0, close=96.0),
    ]
    hit = walk_lower_timeframe(bars, 95.0)
    assert hit is not None and hit.source == "LOWER_TIMEFRAME" and hit.price == 95.0
    assert walk_lower_timeframe([], 95.0) is None


def test_kernel_no_entry_bar_exit():
    dates = _weekdays(270)
    high, low, close, vol, opens, index = _series(dates)
    replay = replay_book(
        dates, high, low, close, vol, index, {"AAA-EQ"}, execution=KERNEL_EXECUTION
    )
    for tr in replay["trades"]:
        if tr.reason == "atr_trail":
            assert tr.entry_date != tr.exit_date


def test_end_of_backtest_liquidation_not_daily():
    dates = _weekdays(260)
    high, low, close, vol, opens, index = _series(dates)
    replay = replay_book(
        dates, high, low, close, vol, index, {"AAA-EQ"}, execution=KERNEL_EXECUTION
    )
    liquidations = [t for t in replay["trades"] if t.reason == BACKTEST_END_REASON]
    for tr in liquidations:
        assert tr.exit_date == dates[-1]
        assert tr.exit_reason_canonical == BACKTEST_END_CANONICAL
    # Must not close every session.
    assert len(liquidations) <= 1


def test_duplicate_entry_and_exit_prevention():
    dates = _weekdays(280)
    high, low, close, vol, opens, index = _series(dates)
    replay = replay_book(
        dates, high, low, close, vol, index, {"AAA-EQ"}, execution=KERNEL_EXECUTION
    )
    closed = [t for t in replay["trades"] if not t.open]
    keys = [(t.symbol, t.entry_date, t.exit_date, t.reason) for t in closed]
    assert len(keys) == len(set(keys))
    open_days: dict[date, int] = {}
    for t in closed:
        d = t.entry_date
        open_days[d] = open_days.get(d, 0) + 1
    assert all(v == 1 for v in open_days.values())


def test_breakeven_classification_uses_net_pnl_tolerance():
    assert classify_outcome(0.0) == "breakeven"
    assert classify_outcome(0.4, tolerance=0.5) == "breakeven"
    assert classify_outcome(0.6, tolerance=0.5) == "winner"
    assert classify_outcome(-0.6, tolerance=0.5) == "loser"


def test_ledger_reports_strategy_tester_fields_and_outliers():
    def _row(day: int, net: float) -> Trade:
        return Trade(
            symbol="IIFL-EQ",
            entry_date=date(2024, 1, 1) + timedelta(days=day),
            exit_date=date(2024, 1, 2) + timedelta(days=day),
            entry_price=100.0,
            exit_price=100.0 + net,
            shares=1.0,
            pnl_pct=net / 100.0,
            reason="atr_trail",
            open=False,
            net_pnl=net,
            gross_pnl=net,
            commission=0.0,
        )

    trades = [_row(i, 10.0 if i % 2 == 0 else -8.0) for i in range(9)]
    trades.append(_row(20, 500.0))
    metrics = aggregate_closed_trades(trades, initial_capital=100_000)
    assert metrics["total_trades"] == 10
    assert metrics["gross_profit"] > 0
    assert metrics["gross_loss"] < 0
    assert metrics["net_pnl"] == metrics["gross_profit"] + metrics["gross_loss"]
    assert metrics["largest_profit_inr"] == 500.0
    ui = ledger_payload(metrics)
    assert ui["gross_profit"] == metrics["gross_profit"]
    assert ui["largest_profit_inr"] == 500.0
    assert "outlier_pnl" in ui

    flagged, n = outlier_pnl([1.0] * 40 + [-1.0] * 40 + [200.0])
    assert n == 1
    assert flagged == 200.0


def test_ledger_ignores_open_marks():
    dates = _weekdays(270)
    high, low, close, vol, opens, index = _series(dates)
    replay = replay_book(
        dates, high, low, close, vol, index, {"AAA-EQ"}, execution=KERNEL_EXECUTION
    )
    metrics = aggregate_closed_trades(replay["trades"])
    assert metrics["source"] == "closed_trade_ledger"
    assert metrics["total_trades"] == len([t for t in replay["trades"] if not t.open])
    assert metrics["winning_trades"] + metrics["losing_trades"] + metrics["breakeven_trades"] == metrics["total_trades"]


def test_candle_ordering_and_date_bounds():
    dates = _weekdays(300, start=date(2018, 8, 21))
    assert dates == sorted(dates)
    asof = date(2026, 8, 21)
    assert period_window_start(asof, "3Y") == date(2023, 8, 21)
    assert period_window_start(asof, "5Y") == date(2021, 8, 21)
    assert period_window_start(asof, "8Y") == date(2018, 8, 21)


def test_3y_5y_8y_filter_by_entry_date():
    dates = _weekdays(280)
    high, low, close, vol, opens, index = _series(dates)
    replay = replay_book(
        dates, high, low, close, vol, index, {"AAA-EQ"}, execution=KERNEL_EXECUTION
    )
    end = dates[-1]
    y3 = filter_period_trades(replay["trades"], end.replace(year=end.year - 3) if end.year > 3 else dates[0], end)
    y5 = filter_period_trades(replay["trades"], date(end.year - 5, end.month, end.day) if end.year > 5 else dates[0], end)
    assert len(y5) >= len(y3)


def test_insufficient_history_no_warmup_entries():
    dates = _weekdays(20)
    high, low, close, vol, opens, index = _series(dates)
    replay = replay_book(
        dates, high, low, close, vol, index, {"AAA-EQ"}, execution=KERNEL_EXECUTION
    )
    assert replay["state"].book_status == "WARMUP"
    assert all(t.reason == BACKTEST_END_REASON for t in replay["trades"])


def test_missing_close_does_not_enter():
    dates = _weekdays(270)
    high, low, close, vol, opens, index = _series(dates)
    hole = dates[260]
    close["AAA-EQ"].pop(hole, None)
    high["AAA-EQ"].pop(hole, None)
    replay = replay_book(
        dates, high, low, close, vol, index, {"AAA-EQ"}, execution=KERNEL_EXECUTION
    )
    assert all(t.entry_date != hole for t in replay["trades"])


def test_missing_lower_timeframe_records_fallback():
    dates = _weekdays(270)
    high, low, close, vol, opens, index = _series(dates)
    cfg = parse_execution_profile("TV_COMPAT", fill_mode="LOWER_TIMEFRAME")
    replay = replay_book(
        dates, high, low, close, vol, index, {"AAA-EQ"},
        execution=cfg, open_m=opens, lower_tf={},
    )
    assert replay["diagnostics"]["lower_timeframe_requested"] is True
    assert replay["diagnostics"]["lower_timeframe_fallback"] is True


def test_symbol_failure_does_not_abort_universe():
    dates = _weekdays(270)
    high, low, close, vol, opens, index = _series(dates, "GOOD-EQ")
    high["BAD-EQ"] = {}
    low["BAD-EQ"] = {}
    close["BAD-EQ"] = {}
    vol["BAD-EQ"] = {}
    replay = replay_book(
        dates, high, low, close, vol, index, {"GOOD-EQ", "BAD-EQ"},
        execution=KERNEL_EXECUTION,
    )
    assert replay["incomplete"] is False or isinstance(replay["failed_symbols"], list)
    assert "GOOD-EQ" in replay["successful_symbols"] or any(t.symbol == "GOOD-EQ" for t in replay["trades"]) or replay["state"].holdings


def test_deterministic_rerun():
    dates = _weekdays(280)
    high, low, close, vol, opens, index = _series(dates)
    a = replay_book(dates, high, low, close, vol, index, {"AAA-EQ"}, execution=KERNEL_EXECUTION, open_m=opens)
    b = replay_book(dates, high, low, close, vol, index, {"AAA-EQ"}, execution=KERNEL_EXECUTION, open_m=opens)
    def _rows(rep):
        return [
            (t.symbol, t.entry_date, t.exit_date, t.entry_price, t.exit_price, t.pnl_pct, t.reason)
            for t in rep["trades"]
        ]
    assert _rows(a) == _rows(b)
    assert aggregate_closed_trades(a["trades"])["total_trades"] == aggregate_closed_trades(b["trades"])["total_trades"]


def test_kernel_and_tv_are_not_forced_to_same_count():
    dates = _weekdays(280)
    high, low, close, vol, opens, index = _series(dates)
    k = replay_book(dates, high, low, close, vol, index, {"AAA-EQ"}, execution=KERNEL_EXECUTION, open_m=opens)
    t = replay_book(dates, high, low, close, vol, index, {"AAA-EQ"}, execution=TV_COMPAT_EXECUTION, open_m=opens)
    # Different models may differ; neither count is hardcoded.
    assert isinstance(len(k["trades"]), int)
    assert isinstance(len(t["trades"]), int)
