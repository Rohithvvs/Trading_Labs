"""GLAXO golden / isolation tests for the published 038 52W kernel.

These tests lock what the engine actually does. They do not encode TradingView
report totals (241 trades, 48.96% win rate, PF 1.126). Those numbers come from
a different, unpublished Pine script and must not be hardcoded here.
"""
from datetime import date, timedelta

from app.services.strategies.breakout52w.analytics import build_symbol_dashboard
from app.services.strategies.breakout52w.book_engine import replay_book
from app.services.strategies.breakout52w.identity import DEFAULT_CAPITAL, STRATEGY_ID
from app.services.strategies.breakout52w.indicators import prior_high_252
from app.services.strategies.breakout52w.signal import buy_signal
from app.services.strategies.breakout52w.window_backtest import dataset_fingerprint

# Completed GLAXO-EQ 3Y blotter reproduced from stored daily_ohlcv + replay_book.
# Open 2026-08-19 @ 3032.40 is MTM only and is excluded from these metrics.
GLAXO_CLOSED = [
    {
        "symbol": "GLAXO-EQ",
        "entry_date": "2023-09-13",
        "exit_date": "2023-10-23",
        "entry_price": 1544.05,
        "exit_price": 1463.80,
        "pnl_pct": -0.0520,
        "reason": "atr_trail",
        "open": False,
    },
    {
        "symbol": "GLAXO-EQ",
        "entry_date": "2023-11-20",
        "exit_date": "2024-02-14",
        "entry_price": 1647.95,
        "exit_price": 2153.50,
        "pnl_pct": 0.3068,
        "reason": "atr_trail",
        "open": False,
    },
    {
        "symbol": "GLAXO-EQ",
        "entry_date": "2024-05-30",
        "exit_date": "2024-08-30",
        "entry_price": 2594.30,
        "exit_price": 2745.10,
        "pnl_pct": 0.0581,
        "reason": "atr_trail",
        "open": False,
    },
    {
        "symbol": "GLAXO-EQ",
        "entry_date": "2025-05-28",
        "exit_date": "2025-08-01",
        "entry_price": 3348.20,
        "exit_price": 2936.50,
        "pnl_pct": -0.1230,
        "reason": "atr_trail",
        "open": False,
    },
]


def _weekdays(n: int, start: date = date(2023, 8, 21)) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _dashboard(blotter, symbol="GLAXO-EQ"):
    return build_symbol_dashboard(
        {
            "strategy_id": STRATEGY_ID,
            "evaluation_date": "2026-08-19",
            "recommendations": [{"symbol": symbol}],
        },
        symbol,
        "CUSTOM",
        blotter=blotter,
        equity_curve=[
            {"date": "2023-08-21", "equity": DEFAULT_CAPITAL},
            {"date": "2026-08-19", "equity": 101709.0},
        ],
        asof=date(2026, 8, 19),
        initial_capital=DEFAULT_CAPITAL,
        symbol_replay=True,
        window_start=date(2023, 8, 19),
        window_end=date(2026, 8, 19),
    )


def test_glaxo_completed_trade_count_is_four_not_tv_241():
    dash = _dashboard(GLAXO_CLOSED)
    assert dash["trade_count"] == 4
    assert dash["win_rate"] == 50.0
    assert dash["best_trade"]["entry_date"] == "2023-11-20"
    assert dash["worst_trade"]["entry_date"] == "2025-05-28"
    assert abs(dash["best_trade"]["pnl_percent"] - 30.68) < 0.02
    assert abs(dash["worst_trade"]["pnl_percent"] + 12.30) < 0.02
    # TradingView report totals must not leak into Labs metrics.
    assert dash["trade_count"] != 241
    assert dash["win_rate"] != 48.96


def test_open_mtm_is_excluded_from_completed_metrics():
    open_row = {
        "symbol": "GLAXO-EQ",
        "entry_date": "2026-08-19",
        "exit_date": None,
        "entry_price": 3032.40,
        "exit_price": 3032.40,
        "pnl_pct": 0.0,
        "reason": "open_mtm",
        "open": True,
    }
    dash = _dashboard(GLAXO_CLOSED + [open_row])
    assert dash["trade_count"] == 4
    assert dash["best_trade"]["open"] is False
    assert dash["worst_trade"]["open"] is False
    closed = [t for t in dash["trades"] if not t.get("open")]
    opened = [t for t in dash["trades"] if t.get("open")]
    assert len(closed) == 4
    assert len(opened) == 1
    assert opened[0]["reason"] == "open_mtm"
    assert opened[0]["entry_date"] == "2026-08-19"


def test_held_and_sold_today_suppress_rebuy():
    kwargs = dict(
        market_ok_flag=True,
        close=3100.0,
        prior_high=3000.0,
        volume=2.0,
        vol_sma=1.0,
    )
    assert buy_signal(**kwargs) is True
    assert buy_signal(**kwargs, held=True) is False
    assert buy_signal(**kwargs, sold_today=True) is False


def test_prior_252_excludes_today():
    highs = [float(i) for i in range(260)]
    assert prior_high_252(highs, 252) == 251.0
    assert prior_high_252(highs, 251) is None


def test_252_kernel_does_not_emit_one_trade_per_few_sessions():
    """Even a continuous 52w-high uptrend is one hold, not ~241 round-trips."""
    dates = _weekdays(320)
    symbol = "GLAXO-EQ"
    close, high, low, vol, index = {}, {}, {}, {}, {}
    px = 100.0
    bench = 1000.0
    for i, d in enumerate(dates):
        px = 100.0 + i * 0.5
        bench = 1000.0 + i * 0.4
        close[d] = px
        high[d] = px
        low[d] = px - 0.2
        vol[d] = 50_000 if i % 4 == 0 else 10_000
        index[d] = bench
    replay = replay_book(
        dates,
        {symbol: high},
        {symbol: low},
        {symbol: close},
        {symbol: vol},
        index,
        {symbol},
        initial_capital=DEFAULT_CAPITAL,
    )
    n = len(replay["trades"])
    assert n < 20
    assert n != 241


def test_symbol_fingerprints_and_blotters_are_independent():
    dates = _weekdays(8, start=date(2023, 8, 21))
    names = ("GLAXO-EQ", "ACE-EQ", "CHENNPETRO-EQ", "BOSCHLTD-EQ")
    first = (1404.6, 667.4, 400.0, 20455.7)
    last = (3032.4, 1184.8, 900.0, 48730.0)
    hashes = []
    for sym, a, b in zip(names, first, last):
        series = {dates[0]: a, dates[-1]: b}
        fp = dataset_fingerprint(sym, series, [dates[0], dates[-1]])
        hashes.append(fp["data_hash"])
        assert fp["symbol"] == sym
    assert len(set(hashes)) == 4


def test_two_symbols_replay_do_not_share_fills():
    dates = _weekdays(280)
    glaxo, ace = "GLAXO-EQ", "ACE-EQ"
    g_c, a_c, g_h, a_h, g_l, a_l, g_v, a_v, index = {}, {}, {}, {}, {}, {}, {}, {}, {}
    for i, d in enumerate(dates):
        g = 100.0 + i * 0.8
        a = 50.0 + (0.1 if i % 20 else 0.0)
        g_c[d] = g_h[d] = g
        g_l[d] = g - 0.3
        g_v[d] = 40_000 if i % 3 == 0 else 8_000
        a_c[d] = a_h[d] = a
        a_l[d] = a - 0.2
        a_v[d] = 1_000
        index[d] = 1000.0 + i * 0.5
    g_rep = replay_book(dates, {glaxo: g_h}, {glaxo: g_l}, {glaxo: g_c}, {glaxo: g_v}, index, {glaxo})
    a_rep = replay_book(dates, {ace: a_h}, {ace: a_l}, {ace: a_c}, {ace: a_v}, index, {ace})
    g_dates = {(t.entry_date, t.exit_date, round(t.entry_price, 2)) for t in g_rep["trades"]}
    a_dates = {(t.entry_date, t.exit_date, round(t.entry_price, 2)) for t in a_rep["trades"]}
    assert g_rep["trades"]
    assert g_dates != a_dates or not a_rep["trades"]
    assert all(t.symbol == glaxo for t in g_rep["trades"])
    assert all(t.symbol == ace for t in a_rep["trades"])
