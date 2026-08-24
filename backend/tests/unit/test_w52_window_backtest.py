from datetime import date, timedelta

import pytest

from app.services.strategies.breakout52w.analytics import (
    assess_window_coverage,
    expected_trading_sessions,
    parse_window,
    resolve_window_bounds,
)
from app.services.strategies.breakout52w.book_engine import replay_book
from app.services.strategies.breakout52w.costs import apply_buy, apply_sell, buy_cost, sell_cost
from app.services.strategies.breakout52w.identity import DEFAULT_CAPITAL
from app.services.strategies.breakout52w.window_backtest import (
    fetch_start_for_window,
    insufficient_dashboard,
)


def _weekdays(n: int, start: date = date(2023, 8, 14)) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_custom_start_and_end_dates():
    asof = date(2026, 8, 19)
    key, start, end = resolve_window_bounds(
        asof, "CUSTOM", start=date(2024, 1, 15), end=date(2025, 6, 30)
    )
    assert (key, start, end) == ("CUSTOM", date(2024, 1, 15), date(2025, 6, 30))
    swapped = resolve_window_bounds(asof, "CUSTOM", start=date(2025, 6, 30), end=date(2024, 1, 15))
    assert swapped[1:] == (date(2024, 1, 15), date(2025, 6, 30))
    expected = expected_trading_sessions("CUSTOM", start=date(2024, 1, 15), end=date(2025, 6, 30))
    assert expected is not None and expected > 2


def test_window_bounds_1y_3y_5y():
    asof = date(2026, 8, 18)
    assert resolve_window_bounds(asof, "1Y") == ("1Y", date(2025, 8, 18), asof)
    assert resolve_window_bounds(asof, "3Y") == ("3Y", date(2023, 8, 18), asof)
    assert resolve_window_bounds(asof, "5Y") == ("5Y", date(2021, 8, 18), asof)
    key, start, end = resolve_window_bounds(asof, "ALL")
    assert key == "ALL" and end == asof and start < date(1980, 1, 1)
    assert expected_trading_sessions("3Y") == 756
    assert expected_trading_sessions("1Y") == 252
    assert expected_trading_sessions("5Y") == 1260
    assert expected_trading_sessions("ALL") is None
    assert fetch_start_for_window(date(2023, 8, 18), "3Y") < date(2023, 8, 18)
    assert fetch_start_for_window(date(1970, 1, 1), "ALL") is None


def test_one_session_is_sufficient_for_1d():
    cov = assess_window_coverage(
        [date(2026, 8, 19)],
        start=date(2026, 8, 19),
        end=date(2026, 8, 19),
        window="1D",
        min_ratio=0.5,
    )
    assert cov["sufficient"] is True
    assert cov["candle_count"] == 1
    assert cov["expected_sessions"] == 1


def test_one_day_of_data_is_insufficient_for_3y():
    cov = assess_window_coverage(
        [date(2026, 8, 18)],
        start=date(2023, 8, 18),
        end=date(2026, 8, 18),
        window="3Y",
        min_ratio=0.5,
    )
    assert cov["sufficient"] is False
    assert cov["candle_count"] == 1
    dash = insufficient_dashboard(
        symbol="BOSCHLTD-EQ",
        window="3Y",
        asof=date(2026, 8, 18),
        coverage=cov,
    )
    assert dash["unavailable_reason"] == "insufficient_history"
    assert dash["total_return"] is None
    assert dash["trade_count"] == 0
    assert dash["equity_curve"] == []
    assert dash["trades"] == []


def test_full_3y_sessions_are_sufficient():
    dates = _weekdays(800, start=date(2023, 8, 18))
    cov = assess_window_coverage(
        dates,
        start=date(2023, 8, 18),
        end=date(2026, 8, 18),
        window="3Y",
        min_ratio=0.5,
    )
    assert cov["candle_count"] > 1
    assert cov["sufficient"] is True
    assert cov["actual_start"] == dates[0].isoformat()
    assert cov["actual_end"] <= "2026-08-18"
    assert date.fromisoformat(cov["actual_end"]) <= date(2026, 8, 18)


def test_replay_over_multi_year_calendar_emits_daily_equity_and_keeps_costs():
    dates = _weekdays(320, start=date(2024, 1, 2))
    symbol = "ACE-EQ"
    close = {}
    high = {}
    low = {}
    vol = {}
    index = {}
    px = 100.0
    bench = 1000.0
    for i, d in enumerate(dates):
        # Stay in an uptrend so the 52W breakout can fire after warmup.
        px = 100.0 + i * 0.4
        bench = 1000.0 + i * 0.5
        close[d] = px
        high[d] = px
        low[d] = px - 1
        vol[d] = 50_000 if i % 5 == 0 else 10_000
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
    curve = replay["equity_curve"]
    trades = replay["trades"]
    assert len(curve) == len(dates)
    assert len(curve) > 1
    months = {str(p["date"])[:7] for p in curve}
    assert len(months) >= 12
    assert trades  # at least eod liquidation or trail after warmup
    entry_dates = {t.entry_date for t in trades}
    assert len(entry_dates) >= 1
    # Execution costs still move cash away from a frictionless fill.
    turnover = 10_000.0
    assert apply_buy(100_000.0, turnover) < 100_000.0 - turnover
    assert apply_sell(90_000.0, turnover) < 90_000.0 + turnover
    assert buy_cost(turnover) > 0
    assert sell_cost(turnover) > buy_cost(turnover)


@pytest.mark.asyncio
async def test_load_symbol_window_bars_keys_canonical_from_eq_store(monkeypatch):
    from app.services.strategies.breakout52w import window_backtest as wb

    async def fake_equity(symbol, from_date=None):
        assert symbol == "GLAXO"
        return [
            {
                "trade_date": date(2024, 1, 2),
                "symbol": "GLAXO-EQ",
                "open": 1.0,
                "high": 2.0,
                "low": 0.9,
                "close": 1.5,
                "volume": 1000,
            }
        ]

    async def fake_index(symbol, from_date=None):
        return [{"trade_date": date(2024, 1, 2), "symbol": symbol, "close": 20000.0}]

    monkeypatch.setattr(
        "app.services.market_data_ingestion.repository.fetch_equity_history",
        fake_equity,
    )
    monkeypatch.setattr(
        "app.services.market_data_ingestion.repository.fetch_index_history",
        fake_index,
    )
    dates, high_m, _low, close_m, _vol, index, _open = await wb.load_symbol_window_bars(
        "GLAXO",
        start=date(2023, 8, 20),
        end=date(2026, 8, 20),
        window="3Y",
    )
    assert dates == [date(2024, 1, 2)]
    assert close_m["GLAXO"][date(2024, 1, 2)] == 1.5
    assert high_m["GLAXO"][date(2024, 1, 2)] == 2.0
    assert index[date(2024, 1, 2)] == 20000.0
    assert "GLAXO-EQ" not in close_m


def test_parse_window_default_is_3y():
    assert parse_window(None) == "3Y"
    assert parse_window("3y") == "3Y"


def test_dataset_fingerprints_differ_by_symbol():
    from app.services.strategies.breakout52w.window_backtest import dataset_fingerprint

    dates = [date(2023, 8, 18), date(2026, 8, 18)]
    bosch = dataset_fingerprint("BOSCHLTD-EQ", {dates[0]: 20455.7, dates[1]: 48730.0}, dates)
    ace = dataset_fingerprint("ACE-EQ", {dates[0]: 667.4, dates[1]: 1184.8}, dates)
    assert bosch["symbol"] == "BOSCHLTD-EQ"
    assert ace["symbol"] == "ACE-EQ"
    assert bosch["data_hash"] != ace["data_hash"]
    assert bosch["first_close"] != ace["first_close"]
    assert bosch["last_close"] != ace["last_close"]


def test_open_mtm_is_not_a_completed_win():
    from app.services.strategies.breakout52w.analytics import build_symbol_dashboard
    from app.services.strategies.breakout52w.identity import STRATEGY_ID

    dash = build_symbol_dashboard(
        {"strategy_id": STRATEGY_ID, "evaluation_date": "2026-08-18", "recommendations": [{"symbol": "ACE-EQ"}]},
        "ACE-EQ",
        "3Y",
        blotter=[
            {
                "symbol": "ACE-EQ",
                "entry_date": "2026-08-18",
                "exit_date": None,
                "entry_price": 1184.8,
                "exit_price": 1184.8,
                "pnl_pct": 0.0,
                "reason": "open_mtm",
                "open": True,
            }
        ],
        equity_curve=[{"date": "2023-08-18", "equity": 100000}, {"date": "2026-08-18", "equity": 100000}],
        asof=date(2026, 8, 18),
        symbol_replay=True,
    )
    assert dash["replay_kind"] == "symbol_window"
    assert dash["trade_count"] == 0
    assert dash["win_rate"] is None
    assert dash["best_trade"] is None
    assert dash["trades"][0]["open"] is True
