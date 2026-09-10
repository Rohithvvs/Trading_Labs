"""NSE cash session filter: holidays/weekends/clones never count as bars."""

from datetime import date

from app.services.indicator_scanner.compiler import compile_source
from app.services.indicator_scanner.evaluator import BarData, evaluate_indicator
from app.services.indicator_scanner.scan_data_quality import validate_and_sanitize_universe
from app.services.market_data_ingestion.nse_sessions import (
    filter_session_ohlcv_rows,
    is_nse_cash_session,
    nse_session_dates,
    nth_session_ending,
    split_like_factor,
)
from app.services.strategy_tester.indicators import BarSeries
from app.services.strategy_tester.scan_service import _series_from_rows


LTM_SOURCE = """
//@version=6
indicator("LTM Momentum 252 [SCAN]", overlay=false)
closeNow = close
closePast = close[252]
hasHistory = not na(closeNow) and not na(closePast) and closePast > 0 and closeNow > 0
momentum252 = hasHistory ? (closeNow / closePast - 1.0) : na
eligible = hasHistory and not na(momentum252) and momentum252 > 0.50
scanSignal = eligible ? 1 : 0
plot(scanSignal, "LTM Eligible Signal")
plot(momentum252, "Momentum 252")
plot(closeNow, "Close")
plot(closePast, "Close t-252")
"""


def test_friday_28_aug_2026_is_a_cash_session_christmas_is_not():
    assert is_nse_cash_session(date(2026, 8, 28)) is True
    assert is_nse_cash_session(date(2026, 8, 29)) is False
    assert is_nse_cash_session(date(2025, 12, 25)) is False
    assert is_nse_cash_session(date(2025, 10, 2)) is False


def test_nth_session_ending_counts_trading_days_not_calendar():
    end = date(2026, 8, 28)
    start = nth_session_ending(end, 5)
    # 28 Fri, 27 Thu, 26 Wed, 25 Tue, 24 Mon
    assert start == date(2026, 8, 24)


def test_index_dates_are_the_session_calendar_when_present():
    idx = {date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28)}
    sessions = nse_session_dates(date(2026, 8, 20), date(2026, 8, 28), index_dates=idx)
    assert date(2026, 8, 22) not in sessions  # Saturday
    assert idx <= sessions
    assert date(2026, 8, 21) in sessions  # calendar cash session is not dropped


def test_gappy_index_does_not_drop_cash_sessions():
    """A NIFTY500 tape missing 1-2 Sep must not strip those equity bars."""
    idx = {date(2026, 8, 31), date(2026, 9, 3), date(2026, 9, 4)}
    sessions = nse_session_dates(date(2026, 8, 31), date(2026, 9, 4), index_dates=idx)
    assert date(2026, 9, 1) in sessions
    assert date(2026, 9, 2) in sessions
    assert date(2026, 9, 3) in sessions


def test_index_weekday_prints_win_over_holiday_json():
    """TradingView counted NIFTY weekday prints, including Diwali rows on that tape."""
    idx = {
        date(2025, 10, 20),
        date(2025, 10, 21),
        date(2025, 10, 23),
        date(2025, 10, 24),
    }
    sessions = nse_session_dates(date(2025, 10, 20), date(2025, 10, 24), index_dates=idx)
    assert date(2025, 10, 20) in sessions
    assert date(2025, 10, 23) in sessions
    assert date(2025, 10, 24) in sessions


def test_whitelist_keeps_index_session_even_on_holiday_json():
    rows = [
        (date(2025, 10, 17), 10, 11, 9, 10.0, 100),
        (date(2025, 10, 20), 11, 12, 10, 11.0, 110),
        (date(2025, 10, 23), 12, 13, 11, 12.0, 120),
    ]
    kept, stats = filter_session_ohlcv_rows(
        rows,
        session_dates={date(2025, 10, 17), date(2025, 10, 20), date(2025, 10, 23)},
    )
    assert [row[0] for row in kept] == [date(2025, 10, 17), date(2025, 10, 20), date(2025, 10, 23)]
    assert stats.dropped_holiday == 0


def test_filter_drops_holiday_weekend_and_cloned_rows():
    rows = [
        (date(2026, 8, 26), 10, 11, 9, 10.0, 100),
        (date(2026, 8, 27), 11, 12, 10, 11.0, 110),
        (date(2026, 8, 28), 11, 12, 10, 11.0, 110),  # cloned Friday
        (date(2026, 8, 29), 11, 12, 10, 11.0, 110),  # Saturday
    ]
    kept, stats = filter_session_ohlcv_rows(rows)
    assert [row[0] for row in kept] == [date(2026, 8, 26), date(2026, 8, 27)]
    assert stats.dropped_cloned == 1
    assert stats.dropped_weekend == 1


def test_split_like_factor_detects_two_for_one():
    assert split_like_factor(513.0, 256.5) == 2.0
    assert split_like_factor(100.0, 101.0) is None


def _bars_with_junk(n_valid: int = 260) -> BarSeries:
    """n_valid NSE sessions plus holiday/weekend clones that must not count."""
    sessions = []
    day = date(2025, 8, 1)
    while len(sessions) < n_valid:
        if is_nse_cash_session(day):
            sessions.append(day)
        day = date.fromordinal(day.toordinal() + 1)
    rows = []
    for i, sess in enumerate(sessions):
        px = 100.0 + i
        rows.append((sess, px, px + 1, px - 1, px, 1000.0 + i))
        # Holiday clone the next calendar day when that day is not a session.
        nxt = date.fromordinal(sess.toordinal() + 1)
        if not is_nse_cash_session(nxt):
            rows.append((nxt, px, px + 1, px - 1, px, 1000.0 + i))
    return _series_from_rows(rows)


def test_close_252_uses_valid_sessions_not_holiday_rows():
    series = _bars_with_junk(260)
    assert len(series.dates) == 260
    compiled = compile_source(LTM_SOURCE)
    assert compiled.required_bars == 253
    bars = BarData(
        dates=list(series.dates),
        open=list(series.open),
        high=list(series.high),
        low=list(series.low),
        close=list(series.close),
        volume=list(series.volume),
    )
    result = evaluate_indicator(compiled, bars)
    assert result.status == "ok"
    assert result.outputs["Close"] == series.close[-1]
    assert result.outputs["Close t-252"] == series.close[-253]
    expected = series.close[-1] / series.close[-253] - 1.0
    assert abs(float(result.outputs["Momentum 252"]) - expected) < 1e-12


def test_insufficient_history_requires_253_valid_sessions():
    series = _bars_with_junk(252)
    compiled = compile_source(LTM_SOURCE)
    bars = BarData(
        dates=list(series.dates),
        open=list(series.open),
        high=list(series.high),
        low=list(series.low),
        close=list(series.close),
        volume=list(series.volume),
    )
    result = evaluate_indicator(compiled, bars)
    assert result.status == "insufficient_history"
    assert result.bar_count == 252


def test_sanitize_drops_non_index_sessions_before_scan():
    series = BarSeries(
        dates=[date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 29)],
        open=[1, 2, 3, 4],
        high=[1, 2, 3, 4],
        low=[1, 2, 3, 4],
        close=[10.0, 11.0, 11.0, 11.0],
        volume=[1, 2, 2, 2],
    )
    cleaned, _bench, report = validate_and_sanitize_universe(
        {"AAA": series},
        end_session=date(2026, 8, 27),
        session_dates={date(2026, 8, 26), date(2026, 8, 27)},
        min_bars=2,
    )
    assert cleaned["AAA"].dates == [date(2026, 8, 26), date(2026, 8, 27)]
    assert report.dropped_non_session + report.dropped_cloned + report.dropped_weekend >= 1
    assert report.missing_end_session == []


def test_live_session_is_kept_when_index_tape_lags_today():
    """Pine Screener's forming 1D bar must not be dropped because NIFTY500 EOD is still yesterday."""
    from app.services.market_data_ingestion.nse_sessions import is_nse_cash_session, nse_session_dates

    end = date(2026, 9, 4)
    assert is_nse_cash_session(end)
    index_only_yesterday = {date(2026, 9, 2), date(2026, 9, 3)}
    sessions = nse_session_dates(date(2026, 9, 2), end, index_dates=index_only_yesterday)
    sessions = set(sessions)
    sessions.add(end)
    series = BarSeries(
        dates=[date(2026, 9, 3), date(2026, 9, 4)],
        open=[100.0, 101.0],
        high=[101.0, 103.0],
        low=[99.0, 100.0],
        close=[100.5, 102.0],
        volume=[1000.0, 1100.0],
    )
    cleaned, _bench, report = validate_and_sanitize_universe(
        {"RATEGAIN": series},
        end_session=end,
        session_dates=sessions,
        min_bars=2,
    )
    assert cleaned["RATEGAIN"].dates[-1] == end
    assert cleaned["RATEGAIN"].close[-1] == 102.0
    assert "RATEGAIN" not in report.missing_end_session
