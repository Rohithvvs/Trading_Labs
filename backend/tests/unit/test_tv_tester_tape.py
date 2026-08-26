"""Isolated TV TEST-tape replay (qty=1, next-open fills, no 52W signal)."""

from __future__ import annotations

import ast
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.services.strategies.breakout52w.execution import (
    KERNEL_EXECUTION,
    TV_TESTER_EXECUTION,
    parse_execution_profile,
    round_to_tick,
)
from app.services.strategies.breakout52w.tv_tester_tape import (
    TEST_EXIT_REASON,
    replay_tv_tester_tape,
)

_TAPE_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "services"
    / "strategies"
    / "breakout52w"
    / "tv_tester_tape.py"
)


def test_tv_tester_tape_does_not_import_52w_signal():
    tree = ast.parse(_TAPE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[-1])
    assert "buy_signal" not in imported
    assert "prior_high_252" not in imported


def test_parse_tv_tester_profile():
    cfg = parse_execution_profile("TV_TESTER")
    assert cfg.profile == "TV_TESTER"
    assert cfg.order_fill_delay == "NEXT_BAR_OPEN"
    assert cfg.order_size_type == "quantity"
    assert cfg.default_order_size == 1.0
    assert cfg.apply_costs is False
    assert parse_execution_profile("KERNEL").order_size_type == "percent_equity"
    assert cfg.tick_size == 0.10
    assert parse_execution_profile("KERNEL").tick_size == 0.0
    assert KERNEL_EXECUTION.tick_size == 0.0


def test_round_to_tick_matches_tv_prints():
    assert round_to_tick(62.25, 0.10) == 62.3
    assert round_to_tick(59.25, 0.10) == 59.3
    assert round_to_tick(16.32653, 0.10) == 16.3
    assert round_to_tick(366.75, 0.10) == 366.8
    assert round_to_tick(342.85, 0.10) == 342.9
    assert round_to_tick(320.0, 0.10) == 320.0
    assert round_to_tick(356.65, 0.0) == 356.65
    # Known regression vs TV list 239.9: half-up sends 239.95 → 240.0
    assert round_to_tick(239.95, 0.10) == 240.0


def _five_sessions() -> tuple[list[date], dict, dict, dict, dict, dict, dict]:
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(5)]
    symbol = "WELCORP-EQ"
    opens = [10.0, 11.0, 12.0, 13.0, 14.0]
    open_m = {symbol: {d: o for d, o in zip(dates, opens)}}
    high_m = {symbol: {d: o + 1 for d, o in zip(dates, opens)}}
    low_m = {symbol: {d: o - 1 for d, o in zip(dates, opens)}}
    close_m = {symbol: {d: o + 0.5 for d, o in zip(dates, opens)}}
    vol_m = {symbol: {d: 1_000.0 for d in dates}}
    index = {d: 1000.0 for d in dates}
    return dates, high_m, low_m, close_m, vol_m, open_m, index


def test_tv_tester_tape_open_to_open_qty1():
    dates, high_m, low_m, close_m, vol_m, open_m, index = _five_sessions()
    replay = replay_tv_tester_tape(
        dates,
        high_m,
        low_m,
        close_m,
        vol_m,
        index,
        {"WELCORP-EQ"},
        initial_capital=1_000_000.0,
        open_m=open_m,
        execution=TV_TESTER_EXECUTION,
    )
    closed = [t for t in replay["trades"] if not t.open]
    assert [(t.entry_price, t.exit_price, t.shares, t.commission, t.net_pnl) for t in closed] == [
        (11.0, 12.0, 1.0, 0.0, 1.0),
        (13.0, 14.0, 1.0, 0.0, 1.0),
    ]
    assert all(t.reason == TEST_EXIT_REASON for t in closed)
    assert all(t.exit_date != t.entry_date for t in closed)
    # No same-session re-entry: second entry is the session after the first exit.
    assert closed[0].exit_date == dates[2]
    assert closed[1].entry_date == dates[3]


def test_tv_tester_tape_no_same_session_reentry_fill():
    dates, high_m, low_m, close_m, vol_m, open_m, index = _five_sessions()
    replay = replay_tv_tester_tape(
        dates, high_m, low_m, close_m, vol_m, index, {"WELCORP-EQ"}, open_m=open_m
    )
    closed = [t for t in replay["trades"] if not t.open]
    for a, b in zip(closed, closed[1:]):
        assert b.entry_date > a.exit_date
    entries = [t.entry_date for t in closed]
    assert len(entries) == len(set(entries))


def test_tv_tester_tape_rounds_open_to_tick():
    dates = [date(2008, 8, 5) + timedelta(days=i) for i in range(4)]
    symbol = "WELCORP-EQ"
    opens = [353.0, 372.0, 356.65, 345.0]
    open_m = {symbol: {d: o for d, o in zip(dates, opens)}}
    high_m = {symbol: {d: o + 1 for d, o in zip(dates, opens)}}
    low_m = {symbol: {d: o - 1 for d, o in zip(dates, opens)}}
    close_m = {symbol: {d: o for d, o in zip(dates, opens)}}
    vol_m = {symbol: {d: 1_000.0 for d in dates}}
    index = {d: 1000.0 for d in dates}
    replay = replay_tv_tester_tape(
        dates, high_m, low_m, close_m, vol_m, index, {symbol}, open_m=open_m
    )
    closed = [t for t in replay["trades"] if not t.open]
    assert closed
    # Signal on dates[0], enter dates[1] open 372.0, exit dates[2] open 356.65 → 356.7
    first = closed[0]
    assert first.entry_price == 372.0
    assert first.exit_price == 356.7
    assert first.net_pnl == pytest.approx(-15.3, abs=1e-9)


def test_tv_tester_tape_skips_labs_only_session():
    # Thu signal, Fri fill entry, skip Sat analogue (Tue in the set), next session exits.
    dates = [
        date(2024, 1, 4),  # Thu — signal
        date(2024, 1, 5),  # Fri — entry open
        date(2024, 1, 6),  # Sat — Labs-only, must not fill
        date(2024, 1, 8),  # Mon — exit open
    ]
    symbol = "WELCORP-EQ"
    opens = [10.0, 11.0, 99.0, 12.0]
    open_m = {symbol: {d: o for d, o in zip(dates, opens)}}
    high_m = {symbol: {d: o + 1 for d, o in zip(dates, opens)}}
    low_m = {symbol: {d: o - 1 for d, o in zip(dates, opens)}}
    close_m = {symbol: {d: o for d, o in zip(dates, opens)}}
    vol_m = {symbol: {d: 1_000.0 for d in dates}}
    index = {d: 1000.0 for d in dates}
    sessions = {dates[0], dates[1], dates[3]}
    replay = replay_tv_tester_tape(
        dates,
        high_m,
        low_m,
        close_m,
        vol_m,
        index,
        {symbol},
        open_m=open_m,
        session_dates=sessions,
    )
    closed = [t for t in replay["trades"] if not t.open]
    assert len(closed) == 1
    assert closed[0].entry_date == dates[1]
    assert closed[0].entry_price == 11.0
    assert closed[0].exit_date == dates[3]
    assert closed[0].exit_price == 12.0
    assert replay["skipped_sessions"] == 1
    assert all(t.entry_date != dates[2] and t.exit_date != dates[2] for t in closed)


def test_expand_session_calendar_adds_bar_before_first_entry():
    from app.services.strategies.breakout52w.tv_ohlc_csv import expand_tv_session_calendar

    ohlc = [
        date(2002, 8, 21),
        date(2002, 8, 22),
        date(2002, 8, 23),
        date(2002, 9, 3),
    ]
    trades = {date(2002, 8, 22), date(2002, 9, 3)}
    out = expand_tv_session_calendar(trades, ohlc, first_entry=date(2002, 8, 22))
    assert date(2002, 8, 21) in out
    assert date(2002, 8, 23) not in out
    assert date(2002, 8, 22) in out and date(2002, 9, 3) in out


def test_tv_tester_tape_trade1_eight_bar_hold_via_session_set():
    """Signal 08-21, fill 08-22, skip intra-hold bars, exit 09-03."""
    dates = [
        date(2002, 8, 21),
        date(2002, 8, 22),
        date(2002, 8, 23),
        date(2002, 8, 26),
        date(2002, 9, 2),
        date(2002, 9, 3),
        date(2002, 9, 4),
    ]
    symbol = "WELCORP-EQ"
    px = 16.32653
    open_m = {symbol: {d: px for d in dates}}
    high_m = {symbol: {d: px for d in dates}}
    low_m = {symbol: {d: px for d in dates}}
    close_m = {symbol: {d: px for d in dates}}
    vol_m = {symbol: {d: 1.0 for d in dates}}
    index = {d: 1000.0 for d in dates}
    sessions = {date(2002, 8, 21), date(2002, 8, 22), date(2002, 9, 3), date(2002, 9, 4)}
    replay = replay_tv_tester_tape(
        dates,
        high_m,
        low_m,
        close_m,
        vol_m,
        index,
        {symbol},
        open_m=open_m,
        session_dates=sessions,
        execution=TV_TESTER_EXECUTION,
    )
    closed = [t for t in replay["trades"] if not t.open]
    assert closed
    first = closed[0]
    assert first.entry_date == date(2002, 8, 22)
    assert first.exit_date == date(2002, 9, 3)
    assert first.entry_price == 16.3
    assert first.exit_price == 16.3
    assert first.net_pnl == pytest.approx(0.0, abs=1e-9)
    assert date(2002, 8, 23) not in {first.entry_date, first.exit_date}


def test_resolve_tv_ohlc_csv_kernel_never_uses_file(tmp_path: Path):
    from app.services.strategies.breakout52w.tv_ohlc_csv import resolve_tv_tester_ohlc_csv

    csv_path = tmp_path / "ohlc.csv"
    csv_path.write_text(
        "date,open,high,low,close,volume\n2024-01-01,10,11,9,10.5,1000\n",
        encoding="utf-8",
    )
    assert resolve_tv_tester_ohlc_csv("KERNEL", path=csv_path) is None
    assert resolve_tv_tester_ohlc_csv("TV_COMPAT", path=csv_path) is None
    assert resolve_tv_tester_ohlc_csv("TV_TESTER", path=csv_path) == csv_path
    missing = tmp_path / "nope.csv"
    assert resolve_tv_tester_ohlc_csv("TV_TESTER", path=missing) is None


def test_tv_tester_tape_from_synthetic_ohlc_csv(tmp_path: Path):
    from app.services.strategies.breakout52w.tv_ohlc_csv import (
        maps_from_ohlc_rows,
        parse_tv_ohlc_csv,
    )

    csv_path = tmp_path / "ohlc.csv"
    lines = ["date,open,high,low,close,volume"]
    opens = [10.0, 11.0, 12.0, 13.0, 14.0]
    for i, o in enumerate(opens):
        d = date(2024, 1, 1) + timedelta(days=i)
        lines.append(f"{d.isoformat()},{o},{o+1},{o-1},{o+0.5},1000")
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows = parse_tv_ohlc_csv(csv_path)
    assert len(rows) == 5
    assert rows[0]["open"] == 10.0
    dates, high_m, low_m, close_m, vol_m, index, open_m = maps_from_ohlc_rows(
        "WELCORP-EQ", rows
    )
    replay = replay_tv_tester_tape(
        dates,
        high_m,
        low_m,
        close_m,
        vol_m,
        index,
        {"WELCORP-EQ"},
        open_m=open_m,
        execution=TV_TESTER_EXECUTION,
    )
    closed = [t for t in replay["trades"] if not t.open]
    assert [(t.entry_price, t.exit_price, t.shares, t.net_pnl) for t in closed] == [
        (11.0, 12.0, 1.0, 1.0),
        (13.0, 14.0, 1.0, 1.0),
    ]


def test_load_symbol_window_bars_uses_csv_not_db(tmp_path: Path):
    import asyncio

    from app.services.strategies.breakout52w.window_backtest import load_symbol_window_bars

    csv_path = tmp_path / "ohlc.csv"
    csv_path.write_text(
        "date,open,high,low,close,volume\n"
        "2002-08-22,16.3,16.3,16.3,16.3,1\n"
        "2002-08-23,16.4,16.4,16.4,16.4,1\n",
        encoding="utf-8",
    )

    async def _load():
        return await load_symbol_window_bars(
            "WELCORP-EQ",
            start=date(2000, 6, 23),
            end=date(2002, 8, 23),
            window="ALL",
            ohlc_csv=csv_path,
        )

    dates, high_m, low_m, close_m, vol_m, index, open_m = asyncio.run(_load())
    assert dates == [date(2002, 8, 22), date(2002, 8, 23)]
    assert open_m["WELCORP-EQ"][date(2002, 8, 22)] == 16.3
    assert index == {}


def test_resolve_tv_ohlc_csv_default_is_welcorp_only():
    from app.services.strategies.breakout52w.tv_ohlc_csv import (
        default_tv_ohlc_csv_path,
        is_tv_reference_symbol,
        resolve_tv_tester_ohlc_csv,
    )

    assert is_tv_reference_symbol("WELCORP-EQ")
    assert is_tv_reference_symbol("NSE:WELCORP")
    assert not is_tv_reference_symbol("RELIANCE-EQ")
    assert resolve_tv_tester_ohlc_csv("TV_TESTER", symbol="RELIANCE-EQ") is None
    golden = default_tv_ohlc_csv_path()
    if golden.is_file():
        assert resolve_tv_tester_ohlc_csv("TV_TESTER", symbol="WELCORP-EQ") == golden
        assert resolve_tv_tester_ohlc_csv("KERNEL", symbol="WELCORP-EQ") is None


def test_parse_tv_trades_session_calendar_adds_predecessor(tmp_path: Path):
    from app.services.strategies.breakout52w.tv_ohlc_csv import (
        load_tv_tester_session_dates,
        parse_tv_trades_dates,
    )

    trades = tmp_path / "trades.csv"
    trades.write_text(
        "Trade number,Type,Date and time,Signal,Price INR\n"
        "1,Exit long,2002-09-03,Close entry(s) order TEST,16.3\n"
        "1,Entry long,2002-08-22,TEST,16.3\n",
        encoding="utf-8",
    )
    dates, first = parse_tv_trades_dates(trades)
    assert first == date(2002, 8, 22)
    assert dates == {date(2002, 8, 22), date(2002, 9, 3)}
    ohlc = [date(2002, 8, 21), date(2002, 8, 22), date(2002, 8, 23), date(2002, 9, 3)]
    sessions = load_tv_tester_session_dates(
        symbol="WELCORP-EQ",
        trades_csv=trades,
        ohlc_dates=ohlc,
    )
    assert sessions is not None
    assert date(2002, 8, 21) in sessions
    assert date(2002, 8, 23) not in sessions
    assert load_tv_tester_session_dates(symbol="RELIANCE-EQ", trades_csv=trades) is None


def test_run_symbol_window_overrides_kernel_capital_for_tv_tester(tmp_path: Path):
    import asyncio

    from app.services.strategies.breakout52w.execution import TV_TESTER_CAPITAL
    from app.services.strategies.breakout52w.identity import DEFAULT_CAPITAL
    from app.services.strategies.breakout52w.window_backtest import (
        clear_window_backtest_cache,
        run_symbol_window_backtest,
    )

    csv_path = tmp_path / "ohlc.csv"
    lines = ["date,open,high,low,close,volume"]
    opens = [10.0, 11.0, 12.0, 13.0, 14.0]
    for i, o in enumerate(opens):
        d = date(2024, 1, 1) + timedelta(days=i)
        lines.append(f"{d.isoformat()},{o},{o + 1},{o - 1},{o + 0.5},1000")
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    clear_window_backtest_cache()

    async def _run():
        return await run_symbol_window_backtest(
            "SYNTH-EQ",
            "ALL",
            asof=date(2024, 1, 5),
            start=date(2024, 1, 1),
            end=date(2024, 1, 5),
            initial_capital=DEFAULT_CAPITAL,
            execution_profile="TV_TESTER",
            ohlc_csv=csv_path,
        )

    dash = asyncio.run(_run())
    assert dash["execution"]["profile"] == "TV_TESTER"
    assert dash["initial_capital"] == TV_TESTER_CAPITAL
    assert dash["ohlc_source"] == "tv_ohlc_csv"
    assert dash["tester_tape"] is True
    closed = [t for t in dash["trades"] if not t.get("open")]
    assert len(closed) == 2
    assert all(t.get("entry_signal") == "TEST" for t in closed)


@pytest.mark.skipif(
    not (
        Path(__file__).resolve().parents[2].parent
        / "hermes-research"
        / "tradingview_reference"
        / "Strategy_001"
        / "ohlc.csv"
    ).is_file()
    or not (
        Path(__file__).resolve().parents[2].parent
        / "hermes-research"
        / "tradingview_reference"
        / "Strategy_001"
        / "trades.csv"
    ).is_file(),
    reason="Strategy_001 golden files missing",
)
def test_welcorp_tv_tester_matches_golden_trade_counts():
    import asyncio

    from app.services.strategies.breakout52w.tv_ohlc_csv import default_tv_ohlc_csv_path
    from app.services.strategies.breakout52w.window_backtest import (
        clear_window_backtest_cache,
        run_symbol_window_backtest,
    )

    assert default_tv_ohlc_csv_path().is_file()
    clear_window_backtest_cache()

    async def _run(start: date, end: date = date(2026, 8, 24)):
        return await run_symbol_window_backtest(
            "WELCORP-EQ",
            "CUSTOM",
            asof=end,
            start=start,
            end=end,
            initial_capital=1_000_000,
            execution_profile="TV_TESTER",
        )

    full = asyncio.run(_run(date(2000, 6, 23)))
    ledger = full.get("ledger") or {}
    assert int(ledger.get("total_trades") or full.get("trade_count") or 0) == 2954
    assert full["execution"]["profile"] == "TV_TESTER"
    slice_2013 = asyncio.run(_run(date(2013, 9, 11)))
    slice_ledger = slice_2013.get("ledger") or {}
    assert int(slice_ledger.get("total_trades") or slice_2013.get("trade_count") or 0) == 1600
    # HALF_UP vs TV tenth prints move ~2 legs across win/breakeven (losers stay 778).
    assert int(slice_ledger.get("losing_trades") or 0) == 778
    assert abs(int(slice_ledger.get("winning_trades") or 0) - 788) <= 2
    assert abs(int(slice_ledger.get("breakeven_trades") or 0) - 34) <= 2
