from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.strategies.breakout52w.book_engine import evaluate_session
from app.services.strategies.breakout52w.session_overlay import (
    apply_session_bars,
    drop_open_session_bar,
    fill_missing_completed_sessions,
    parse_quote_bar,
    should_overlay_session,
)
from app.services.strategies.breakout52w.signal import buy_signal, screener_pass


def test_parse_quote_bar_reads_fyers_fields():
    bar = parse_quote_bar(
        {"lp": 1487.4, "high_price": 1492.0, "low_price": 1450.0, "volume": 3_210_388}
    )
    assert bar["high"] == 1492.0
    assert bar["low"] == 1450.0
    assert bar["close"] == 1487.4
    assert bar["volume"] == 3_210_388.0
    assert bar["open"] == 1487.4


def test_apply_session_appends_today_without_changing_yesterday():
    yesterday = date(2026, 8, 18)
    today = date(2026, 8, 19)
    dates = [yesterday]
    high_m = {"CHENNPETRO-EQ": {yesterday: 1449.0}}
    low_m = {"CHENNPETRO-EQ": {yesterday: 1400.0}}
    close_m = {"CHENNPETRO-EQ": {yesterday: 1404.0}}
    vol_m = {"CHENNPETRO-EQ": {yesterday: 3_584_947.0}}
    index = {yesterday: 23000.0}
    dates, high_m, low_m, close_m, vol_m, index = apply_session_bars(
        dates,
        high_m,
        low_m,
        close_m,
        vol_m,
        index,
        session=today,
        equity_bars={
            "CHENNPETRO-EQ": {"high": 1492.0, "low": 1450.0, "close": 1487.4, "volume": 3_210_388.0}
        },
        index_close=23100.0,
    )
    assert dates == [yesterday, today]
    assert close_m["CHENNPETRO-EQ"][yesterday] == 1404.0
    assert close_m["CHENNPETRO-EQ"][today] == 1487.4
    assert index[today] == 23100.0


def test_chennpetro_fails_yesterday_and_passes_on_live_bar():
    """TV list vs app list: same name, different session close."""
    prior = 1449.0
    assert not buy_signal(
        market_ok_flag=True, close=1404.0, prior_high=prior, volume=3_584_947.0, vol_sma=2_546_799.0
    )
    assert buy_signal(
        market_ok_flag=True, close=1487.4, prior_high=1454.5, volume=3_210_388.0, vol_sma=2_946_242.9
    )


def test_should_overlay_when_stored_bar_is_stale(monkeypatch):
    from app.services.strategies.breakout52w import session_overlay as so

    monkeypatch.setattr(so, "_session_date", lambda now=None: date(2026, 8, 19))
    monkeypatch.setattr(so, "cash_session_complete", lambda now=None: True)
    assert so.should_overlay_session([date(2026, 8, 18)]) == date(2026, 8, 19)
    assert so.should_overlay_session([date(2026, 8, 19)]) == date(2026, 8, 19)
    assert so.should_overlay_session([date(2026, 8, 20)]) is None


def test_open_session_overlays_forming_1d_bar(monkeypatch):
    """Pine Screener 1D uses the forming daily candle. Overlay live quotes during RTH."""
    from app.services.strategies.breakout52w import session_overlay as so

    open_now = datetime(2026, 8, 21, 13, 4, tzinfo=ZoneInfo("Asia/Kolkata"))
    monkeypatch.setattr(so, "_session_date", lambda now=None: date(2026, 8, 21))
    monkeypatch.setattr(so, "cash_session_complete", lambda now=None: False)
    assert should_overlay_session([date(2026, 8, 20)], now=open_now) == date(2026, 8, 21)
    after_close = datetime(2026, 8, 21, 15, 45, tzinfo=ZoneInfo("Asia/Kolkata"))
    monkeypatch.setattr(so, "cash_session_complete", lambda now=None: True)
    assert should_overlay_session([date(2026, 8, 20)], now=after_close) == date(2026, 8, 21)


def test_drop_open_session_bar_is_fallback_when_quotes_fail(monkeypatch):
    from app.services.strategies.breakout52w import session_overlay as so

    open_now = datetime(2026, 8, 21, 13, 4, tzinfo=ZoneInfo("Asia/Kolkata"))
    monkeypatch.setattr(so, "_session_date", lambda now=None: date(2026, 8, 21))
    monkeypatch.setattr(so, "cash_session_complete", lambda now=None: False)
    assert drop_open_session_bar([date(2026, 8, 20), date(2026, 8, 21)], now=open_now) == [
        date(2026, 8, 20)
    ]


@pytest.mark.asyncio
async def test_fill_missing_completed_sessions_applies_gap(monkeypatch):
    stored = date(2026, 8, 19)
    completed = date(2026, 8, 20)
    dates = [stored]
    high_m = {"EPL-EQ": {stored: 255.7}}
    low_m = {"EPL-EQ": {stored: 244.5}}
    close_m = {"EPL-EQ": {stored: 250.8}}
    vol_m = {"EPL-EQ": {stored: 5_477_431.0}}
    index = {stored: 23000.0}

    async def fake_fetch(symbols, range_from, range_to):
        assert range_to == completed
        return (
            {
                completed: {
                    "EPL-EQ": {"high": 273.0, "low": 251.0, "close": 270.1, "volume": 6_480_002.0}
                }
            },
            {completed: 23150.0},
            [],
            [],
        )

    from app.services.strategies.breakout52w import session_overlay as so

    monkeypatch.setattr(so, "fetch_missing_completed_bars", fake_fetch)
    monkeypatch.setattr(
        so,
        "expected_last_completed_session",
        lambda now=None: completed,
        raising=False,
    )
    from app.services.market_data_ingestion import calendar_utils as cal

    monkeypatch.setattr(cal, "expected_last_completed_session", lambda now=None: completed)
    dates, high_m, low_m, close_m, vol_m, index, source = await fill_missing_completed_sessions(
        dates, high_m, low_m, close_m, vol_m, index, ["EPL-EQ"]
    )
    assert source == "completed_history"
    assert dates[-1] == completed
    assert close_m["EPL-EQ"][completed] == 270.1


def test_apply_session_fills_missing_completed_day():
    """EOD store ended 19 Aug; TV Pine used 20 Aug. Insert the confirmed bar, not 21 Aug quotes."""
    stored = date(2026, 8, 19)
    completed = date(2026, 8, 20)
    dates = [stored]
    high_m = {"EPL-EQ": {stored: 255.7}}
    low_m = {"EPL-EQ": {stored: 244.5}}
    close_m = {"EPL-EQ": {stored: 250.8}}
    vol_m = {"EPL-EQ": {stored: 5_477_431.0}}
    index = {stored: 23000.0}
    dates, high_m, low_m, close_m, vol_m, index = apply_session_bars(
        dates,
        high_m,
        low_m,
        close_m,
        vol_m,
        index,
        session=completed,
        equity_bars={
            "EPL-EQ": {"high": 273.0, "low": 251.0, "close": 270.1, "volume": 6_480_002.0}
        },
        index_close=23150.0,
    )
    assert dates == [stored, completed]
    assert close_m["EPL-EQ"][stored] == 250.8
    assert close_m["EPL-EQ"][completed] == 270.1
    assert vol_m["EPL-EQ"][completed] == 6_480_002.0
    assert index[completed] == 23150.0
    assert screener_pass(
        market_ok_flag=True,
        close=270.1,
        prior_high=259.83,
        volume=6_480_002.0,
        vol_sma=1_949_188.05,
    )


def test_tv_screener_legs_match_user_pine_print():
    """TradingView STR-001 print from 2026-08-21: same three legs as screener_pass."""
    rows = [
        ("ACMESOLAR", 408.15, 406.50, 2_927_881.0, 2_216_116.20),
        ("IIFL", 679.30, 675.00, 9_104_172.0, 2_082_536.90),
        ("JINDALSAW", 291.55, 281.00, 7_408_855.0, 1_339_828.95),
        ("NETWEB", 5650.00, 5449.90, 3_433_460.0, 1_930_464.95),
        ("WELCORP", 2338.40, 2017.50, 13_941_119.0, 1_403_040.40),
    ]
    for _symbol, close, prior, volume, sma in rows:
        assert screener_pass(
            market_ok_flag=True,
            close=close,
            prior_high=prior,
            volume=volume,
            vol_sma=sma,
        )
    # Yesterday's completed NETWEB close is not the TV print.
    assert not screener_pass(
        market_ok_flag=True,
        close=5419.80,
        prior_high=5449.90,
        volume=4_457_308.0,
        vol_sma=1_930_464.95,
    )


def test_partial_session_volume_fails_names_that_passed_yesterday():
    """Morning overlay volume < SMA20 is why TV's EPL/KTKBANK vanished from the app list."""
    assert screener_pass(
        market_ok_flag=True,
        close=270.1,
        prior_high=259.83,
        volume=6_480_002.0,
        vol_sma=1_949_188.05,
    )
    assert not screener_pass(
        market_ok_flag=True,
        close=268.38,
        prior_high=259.83,
        volume=328_687.0,
        vol_sma=1_423_933.45,
    )


def test_evaluate_picks_live_breakout_as_watch_or_buy():
    n = 270
    start = date(2025, 7, 1)
    dates = []
    d = start
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)
    today = dates[-1]
    # Yesterday never broke the 252 high; today does, with volume.
    highs = lows = closes = vols = {}
    highs = {"CHENNPETRO-EQ": [100.0 + min(i, 200) * 0.1 for i in range(n)]}
    lows = {"CHENNPETRO-EQ": [99.0 for _ in range(n)]}
    closes = {"CHENNPETRO-EQ": [100.0 + min(i, 200) * 0.1 for i in range(n)]}
    vols = {"CHENNPETRO-EQ": [1_000.0 for _ in range(n)]}
    highs["CHENNPETRO-EQ"][-1] = 150.0
    closes["CHENNPETRO-EQ"][-1] = 148.0
    vols["CHENNPETRO-EQ"][-1] = 50_000.0
    bench = [1_000.0 + i for i in range(n)]
    from app.services.strategies.breakout52w.book_engine import BookState

    ev = evaluate_session(
        session_index=n - 1,
        dates=dates,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=vols,
        benchmark=bench,
        universe={"CHENNPETRO-EQ"},
        state=BookState(),
    )
    row = ev["rows"][0]
    assert row["symbol"] == "CHENNPETRO-EQ"
    assert row["buy_signal"] is True
    assert row.get("screener_pass") is True
    assert row["signal"] in {"BUY", "WATCH"}
    assert today == dates[-1]
