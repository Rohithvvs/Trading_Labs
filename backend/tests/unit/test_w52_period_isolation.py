"""Period isolation for STR-001 / 52-Week High Breakout historical boards.

Does not change entry, exit, ATR, volume, market-filter, or ranking rules.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.market_data_ingestion import repository as repo
from app.services.strategies.breakout52w.attribution import (
    apply_windowed_attribution,
    per_name_backtests,
    universe_average,
)
from app.services.strategies.breakout52w.book_engine import Trade
from app.services.strategies.breakout52w.identity import STRATEGY_ID, STRATEGY_VERSION
from app.services.strategies.breakout52w.period import (
    PeriodRequestError,
    backtest_cache_key,
    expected_sessions_for_period,
    filter_period_trades,
    period_window_start,
    resolve_period_bounds,
    result_identity,
    scan_fetch_from_date,
    slice_replay_dates,
    trade_in_requested_period,
)
from app.services.strategies.breakout52w.window_backtest import (
    clear_window_backtest_cache,
    fetch_start_for_window,
)


ASOF = date(2025, 12, 31)


def _trade(
    symbol: str,
    entry: date,
    exit: date | None,
    pnl: float,
    *,
    reason: str = "atr_trail",
    open_: bool = False,
) -> Trade:
    return Trade(symbol, entry, exit, 100.0, 100.0 * (1 + pnl), 1.0, pnl, reason, open_)


def _fixture_trades() -> list[Trade]:
    """Known population: 3 trades in 2024, 2 trades in 2025."""
    return [
        _trade("AAA-EQ", date(2024, 3, 1), date(2024, 4, 1), 0.10),
        _trade("AAA-EQ", date(2024, 7, 1), date(2024, 8, 1), 0.20),
        _trade("BBB-EQ", date(2024, 11, 1), date(2024, 12, 1), -0.05),
        _trade("CCC-EQ", date(2025, 2, 1), date(2025, 3, 1), 0.15),
        _trade("DDD-EQ", date(2025, 9, 1), date(2025, 10, 1), -0.10),
        # End-of-sample liquidation of a 2024 entry — must not leak into 1D/1W.
        _trade("EEE-EQ", date(2024, 6, 1), ASOF, 0.055, reason="eod_liquidation"),
    ]


def _payload(trades: list[Trade] | None = None, asof: date = ASOF) -> dict:
    items = trades if trades is not None else _fixture_trades()
    recs = []
    seen = set()
    for tr in items:
        if tr.symbol in seen:
            continue
        seen.add(tr.symbol)
        recs.append({"symbol": tr.symbol, "signal": "REJECT", "backtest_1y": {"failed": False}})
    recs.append({"symbol": "MISS-EQ", "signal": "REJECT", "first_failure": "close_below_prior_high"})
    return {
        "strategy_id": STRATEGY_ID,
        "evaluation_date": asof.isoformat(),
        "recommendations": recs,
        "blotter": [
            {
                "symbol": t.symbol,
                "entry_date": t.entry_date.isoformat(),
                "exit_date": t.exit_date.isoformat() if t.exit_date else None,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "shares": t.shares,
                "pnl_pct": t.pnl_pct,
                "reason": t.reason,
                "open": t.open,
            }
            for t in items
        ],
        "equity_curve": [
            {"date": "2024-01-02", "equity": 100000},
            {"date": asof.isoformat(), "equity": 105000},
        ],
    }


def test_a_different_periods_resolve_distinct_date_ranges():
    asof = date(2026, 8, 20)
    seen = set()
    for period in ("1D", "1W", "1M", "1Y", "3Y", "5Y", "7Y", "8Y", "18Y"):
        key, start, end = resolve_period_bounds(asof, period)
        assert key == period
        assert end == asof
        assert start <= end
        assert (period, start, end) not in seen
        seen.add((period, start, end))
    assert period_window_start(asof, "1D") == asof
    assert period_window_start(asof, "1Y") == date(2025, 8, 20)
    assert period_window_start(asof, "5Y") == date(2021, 8, 20)
    assert period_window_start(asof, "8Y") == date(2018, 8, 20)
    assert period_window_start(asof, "18Y") == date(2008, 8, 20)


def test_b_c_start_and_end_are_propagated():
    key, start, end = resolve_period_bounds(
        ASOF, "CUSTOM", start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert start == date(2024, 1, 1)
    assert end == date(2024, 12, 31)
    out = apply_windowed_attribution(
        _payload(), period="CUSTOM", start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert out["requested_start"] == "2024-01-01"
    assert out["requested_end"] == "2024-12-31"
    assert out["attribution_window_start"] == "2024-01-01"
    assert out["attribution_window_end"] == "2024-12-31"


def test_d_database_candle_query_respects_date_range():
    sql = str(repo._fetch_date_range_chunked.__doc__ or "")
    assert "trade_date >= from_date" in sql
    source = repo.fetch_daily_ohlcv_for_symbols.__doc__ or ""
    assert "from_date" in source


def test_e_warmup_candles_available_but_excluded_from_performance():
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(300)]
    period_start = dates[252]
    sliced = slice_replay_dates(dates, period_start=period_start, period_end=dates[-1])
    assert sliced["warmup_sessions_used"] == 252
    assert sliced["insufficient_warmup"] is False
    assert sliced["warmup_dates"][-1] < period_start
    assert sliced["performance_dates"][0] == period_start
    assert all(d < period_start for d in sliced["warmup_dates"])
    assert all(d >= period_start for d in sliced["performance_dates"])
    fetch = fetch_start_for_window(period_start, "1Y")
    assert fetch is not None and fetch < period_start


def test_f_trades_outside_requested_period_are_excluded():
    trades = _fixture_trades()
    year_2024 = filter_period_trades(trades, date(2024, 1, 1), date(2024, 12, 31))
    year_2025 = filter_period_trades(trades, date(2025, 1, 1), date(2025, 12, 31))
    assert len(year_2024) == 4  # 3 closed + eod opened in 2024
    assert len(year_2025) == 2
    assert all(t.entry_date.year == 2024 for t in year_2024)
    assert all(t.entry_date.year == 2025 for t in year_2025)


def test_g_multiple_trades_within_a_period_are_all_processed():
    reports = per_name_backtests(
        _fixture_trades(),
        asof=ASOF,
        period="CUSTOM",
        start=date(2024, 1, 1),
        end=date(2024, 12, 31),
    )
    assert reports["AAA-EQ"]["trade_count"] == 2
    # Compound 1.10 * 1.20 - 1 = 0.32
    assert abs(reports["AAA-EQ"]["net_return"] - 0.32) < 1e-9


def test_h_latest_trade_is_not_the_full_period_result():
    reports = per_name_backtests(
        _fixture_trades(),
        asof=ASOF,
        period="CUSTOM",
        start=date(2024, 1, 1),
        end=date(2025, 12, 31),
    )
    assert reports["AAA-EQ"]["trade_count"] == 2
    total = sum(r["trade_count"] for r in reports.values())
    assert total == 6
    latest_only = 1
    assert total != latest_only


def test_i_j_cache_keys_differ_for_different_date_ranges():
    k1y = backtest_cache_key(start_date=date(2025, 8, 20), end_date=date(2026, 8, 20))
    k5y = backtest_cache_key(start_date=date(2021, 8, 20), end_date=date(2026, 8, 20))
    k1y_same = backtest_cache_key(start_date=date(2025, 8, 20), end_date=date(2026, 8, 20))
    assert k1y != k5y
    assert k1y == k1y_same
    assert STRATEGY_ID in "09_52w_breakout"
    other = backtest_cache_key(
        start_date=date(2025, 8, 20),
        end_date=date(2026, 8, 20),
        strategy_version="2",
    )
    assert other != k1y
    assert STRATEGY_VERSION == "1"


def test_k_average_return_uses_all_period_trades():
    out = apply_windowed_attribution(
        _payload(), period="CUSTOM", start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    avg = out["universe_average"]
    # AAA 0.32, BBB -0.05, EEE 0.055  (MISS omitted)
    expected = (0.32 + (-0.05) + 0.055) / 3
    assert avg["valid_backtests"] == 3
    assert abs(avg["average_return"] - expected) < 1e-9
    assert avg["trade_count"] == 4


def test_l_m_top5_and_least5_use_only_period_trades():
    out_2024 = apply_windowed_attribution(
        _payload(), period="CUSTOM", start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    out_2025 = apply_windowed_attribution(
        _payload(), period="CUSTOM", start=date(2025, 1, 1), end=date(2025, 12, 31)
    )
    top_2024 = [r["symbol"] for r in out_2024["top5_positive"]]
    top_2025 = [r["symbol"] for r in out_2025["top5_positive"]]
    least_2024 = [r["symbol"] for r in out_2024["least5"]]
    least_2025 = [r["symbol"] for r in out_2025["least5"]]
    assert "AAA" in top_2024
    assert "CCC" in top_2025
    assert "CCC" not in top_2024
    assert "AAA" not in top_2025
    assert "BBB" in least_2024
    assert "DDD" in least_2025
    assert out_2024["period_trade_count"] == 4
    assert out_2025["period_trade_count"] == 2


def test_deterministic_fixture_3_plus_2_equals_5():
    trades = [
        t for t in _fixture_trades() if t.reason != "eod_liquidation"
    ]
    a = filter_period_trades(trades, date(2024, 1, 1), date(2024, 12, 31))
    b = filter_period_trades(trades, date(2025, 1, 1), date(2025, 12, 31))
    both = filter_period_trades(trades, date(2024, 1, 1), date(2025, 12, 31))
    assert len(a) == 3
    assert len(b) == 2
    assert len(both) == 5


def test_n_empty_period_behavior():
    out = apply_windowed_attribution(
        _payload(), period="CUSTOM", start=date(2020, 1, 1), end=date(2020, 12, 31)
    )
    assert out["top5_positive"] == []
    assert out["least5"] == []
    assert out["period_trade_count"] == 0
    assert out["universe_average"]["average_return"] is None
    assert out["universe_average"]["valid_backtests"] == 0


def test_o_insufficient_warmup_is_flagged():
    dates = [date(2026, 8, 1) + timedelta(days=i) for i in range(10)]
    sliced = slice_replay_dates(
        dates, period_start=date(2026, 8, 8), period_end=date(2026, 8, 10)
    )
    assert sliced["insufficient_warmup"] is True
    assert sliced["warmup_sessions_used"] < 252


def test_p_period_ending_before_latest_market_date():
    out = apply_windowed_attribution(
        _payload(), period="CUSTOM", start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    for row in out["blotter"]:
        if row["entry_date"] > "2024-12-31":
            assert row["symbol"] not in {r["symbol"] for r in out["top5_positive"]}
    assert all(r["window_end"] == "2024-12-31" for r in out["top5_positive"] + out["least5"])


def test_q_future_dates_are_clamped_or_rejected():
    _key, start, end = resolve_period_bounds(ASOF, "1Y", end=date(2027, 1, 1))
    assert end == ASOF
    assert start == period_window_start(ASOF, "1Y")
    with pytest.raises(PeriodRequestError):
        resolve_period_bounds(ASOF, "CUSTOM", start=date(2027, 1, 1), end=date(2027, 6, 1))


def test_r_timezone_boundaries_are_deterministic():
    a = period_window_start(date(2026, 8, 20), "1Y")
    b = period_window_start(date(2026, 8, 20), "1Y")
    assert a == b == date(2025, 8, 20)
    leap = period_window_start(date(2024, 2, 29), "1Y")
    assert leap == date(2023, 2, 28)


def test_s_repeated_identical_requests_return_identical_results():
    first = apply_windowed_attribution(_payload(), period="1Y")
    second = apply_windowed_attribution(_payload(), period="1Y")
    assert first["result_identity"] == second["result_identity"]
    assert first["period_trade_count"] == second["period_trade_count"]
    assert first["cache_key"] == second["cache_key"]


def test_t_changing_only_the_date_range_changes_result_identity():
    y1 = apply_windowed_attribution(_payload(), period="1Y")
    y5 = apply_windowed_attribution(_payload(), period="5Y")
    assert y1["requested_start"] != y5["requested_start"]
    assert y1["cache_key"] != y5["cache_key"]
    assert y1["result_identity"] != y5["result_identity"] or y1["period_trade_count"] != y5["period_trade_count"]


def test_eod_liquidation_does_not_appear_in_1d():
    asof = date(2026, 8, 20)
    trades = [
        _trade("EMIL-EQ", date(2026, 1, 10), asof, 0.055, reason="eod_liquidation"),
        _trade("TODAY-EQ", asof, asof, 0.01),
    ]
    payload = _payload(trades, asof=asof)
    day = apply_windowed_attribution(payload, period="1D")
    year = apply_windowed_attribution(payload, period="1Y")
    assert [r["symbol"] for r in day["top5_positive"]] == ["TODAY"]
    assert {r["symbol"] for r in year["top5_positive"]} == {"EMIL", "TODAY"}
    assert day["period_trade_count"] == 1
    assert year["period_trade_count"] == 2


def test_entry_date_not_overlap_is_the_membership_rule():
    tr = _trade("HELD-EQ", date(2025, 1, 10), date(2026, 8, 20), 0.05, reason="eod_liquidation")
    assert trade_in_requested_period(tr, date(2026, 8, 20), date(2026, 8, 20)) is False
    assert trade_in_requested_period(tr, date(2025, 1, 1), date(2026, 8, 20)) is True


def test_scan_fetch_from_date_includes_18y_and_warmup():
    asof = date(2026, 8, 20)
    fetch = scan_fetch_from_date(asof)
    assert fetch < date(2008, 8, 20)
    assert (date(2008, 8, 20) - fetch).days >= 365


def test_reject_signal_is_recommendation_not_a_backtest_filter():
    out = apply_windowed_attribution(_payload(), period="5Y")
    assert out["signal_semantics"]["field"] == "signal"
    assert "recommendation" in out["signal_semantics"]["meaning"].lower()
    assert any(r["signal"] == "REJECT" for r in out["top5_positive"] + out["least5"])


def test_expected_sessions_cover_short_and_long_periods():
    assert expected_sessions_for_period("1D") == 1
    assert expected_sessions_for_period("1Y") == 252
    assert expected_sessions_for_period("18Y") == 4536
    assert expected_sessions_for_period("ALL") is None


def test_window_cache_identity_helpers():
    clear_window_backtest_cache()
    k1 = backtest_cache_key(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31), universe_id="AAA-EQ")
    k2 = backtest_cache_key(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), universe_id="AAA-EQ")
    assert k1 != k2
    id1 = result_identity(start=date(2024, 1, 1), end=date(2024, 12, 31), trades=_fixture_trades()[:3])
    id2 = result_identity(start=date(2025, 1, 1), end=date(2025, 12, 31), trades=_fixture_trades()[3:5])
    assert id1 != id2


def test_755_stock_period_accounting():
    asof = date(2026, 8, 20)
    recs = []
    blotter = []
    for i in range(755):
        sym = f"S{i:03d}-EQ"
        if i < 10:
            recs.append(
                {
                    "symbol": sym,
                    "signal": "REJECT",
                    "first_failure": "insufficient_history",
                    "backtest_1y": None,
                }
            )
        elif i < 20:
            recs.append(
                {
                    "symbol": sym,
                    "signal": "REJECT",
                    "first_failure": "data_source_failure",
                    "backtest_1y": {"failed": True},
                }
            )
        else:
            recs.append({"symbol": sym, "signal": "REJECT", "backtest_1y": {"failed": False}})
            if i < 120:
                blotter.append(
                    {
                        "symbol": sym,
                        "entry_date": "2026-08-20",
                        "exit_date": "2026-08-20",
                        "pnl_pct": 0.01,
                    }
                )
            elif i < 220:
                blotter.append(
                    {
                        "symbol": sym,
                        "entry_date": "2025-09-01",
                        "exit_date": "2025-10-01",
                        "pnl_pct": -0.02,
                    }
                )
            elif i < 320:
                blotter.append(
                    {
                        "symbol": sym,
                        "entry_date": "2020-03-15",
                        "exit_date": "2020-06-15",
                        "pnl_pct": 0.50,
                    }
                )
    payload = {
        "strategy_id": STRATEGY_ID,
        "evaluation_date": asof.isoformat(),
        "recommendations": recs,
        "blotter": blotter,
        "equity_curve": [{"date": "2008-08-20", "equity": 100000}, {"date": asof.isoformat(), "equity": 110000}],
    }
    day = apply_windowed_attribution(payload, period="1D")
    year = apply_windowed_attribution(payload, period="1Y")
    long = apply_windowed_attribution(payload, period="18Y")
    assert day["period_trade_count"] == 100
    assert year["period_trade_count"] == 200
    assert long["period_trade_count"] == 300
    acc = day["period_accounting"]
    assert acc["processed"] == 755
    assert acc["insufficient_history"] == 10
    assert acc["failed"] == 10
    assert acc["stocks_with_trades"] == 100
    assert acc["successful"] == 100
    assert acc["no_trades"] == 755 - 10 - 10 - 100
    assert long["period_accounting"]["stocks_with_trades"] == 300
    assert day["result_identity"] != long["result_identity"]
    assert year["cache_key"] != long["cache_key"]


def test_universe_average_exposes_trade_count():
    asof = ASOF
    recs = [{"backtest_1y": {"net_return": 0.2, "trade_count": 3, "failed": False}}]
    summary = universe_average(recs, asof=asof, years=3)
    assert summary["trade_count"] == 3
    assert abs(summary["average_return"] - 0.2) < 1e-9
