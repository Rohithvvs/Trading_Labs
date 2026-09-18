"""Deterministic evaluator tests for the 52-week breakout scan indicator."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.indicator_scanner.compiler import compile_source
from app.services.indicator_scanner.evaluator import BarData, evaluate_indicator
from app.services.indicator_scanner.filters import row_matches, validate_filters
from app.services.indicator_scanner.ta_functions import sma
from app.services.indicator_scanner.ema_pullback_template import EMA_PULLBACK_SCAN_SOURCE
from app.services.indicator_scanner.template import BREAKOUT_SCAN_SOURCE


def _dates(n: int, start: date = date(2023, 1, 2)) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _bars(
    n: int = 320,
    *,
    start_px: float = 100.0,
    breakout: bool = False,
    volume_spike: bool = True,
) -> BarData:
    dates = _dates(n)
    close = [start_px + i * 0.05 for i in range(n)]
    if breakout:
        prior_high = max(close[-253:-1])
        close[-1] = prior_high + 1.0
    high = [c + 0.4 for c in close]
    low = [c - 0.4 for c in close]
    open_px = list(close)
    vol = [1_000.0 + (i % 5) * 10 for i in range(n)]
    if volume_spike:
        vol[-1] = (sum(vol[-20:]) / 20.0) + 500
    else:
        vol[-1] = max(10.0, (sum(vol[-21:-1]) / 20.0) - 200)
    return BarData(dates=dates, open=open_px, high=high, low=low, close=close, volume=vol)


def _benchmark(n: int = 320, *, bullish: bool = True) -> BarData:
    dates = _dates(n)
    if bullish:
        close = [10_000.0 + i * 2.0 for i in range(n)]
    else:
        close = [12_000.0 - i * 2.0 for i in range(n)]
    return BarData(
        dates=dates,
        open=list(close),
        high=[c + 5 for c in close],
        low=[c - 5 for c in close],
        close=close,
        volume=[1_000_000.0] * n,
    )


def _bench_map(bars: BarData) -> dict[str, BarData]:
    return {"NSE:CNX500": bars, "NIFTY500": bars}


def test_sma_highest_index_and_na_behavior():
    values = [float(i) for i in range(1, 11)]
    s = sma(values, 3)
    assert s[1] is None
    assert s[2] == 2.0
    compiled = compile_source(
        '//@version=6\nindicator("t")\nx = close[1]\nplot(x, "Prev")\nplot(na(x) ? 1 : 0, "IsNA")\n'
    )
    bars = _bars(5, start_px=10)
    result = evaluate_indicator(compiled, bars)
    assert result.status == "ok"
    assert result.outputs["Prev"] == bars.close[-2]
    assert result.outputs["IsNA"] == 0


def test_true_range_math_max_and_custom_atr():
    compiled = compile_source(BREAKOUT_SCAN_SOURCE)
    stock = _bars(320, breakout=True, volume_spike=True)
    bench = _benchmark(320, bullish=True)
    result = evaluate_indicator(compiled, stock, benchmark_by_symbol=_bench_map(bench))
    assert result.status == "ok"
    i = len(stock.close) - 1
    prev = stock.close[i - 1]
    expected_tr = max(
        stock.high[i] - stock.low[i],
        abs(stock.high[i] - prev),
        abs(stock.low[i] - prev),
    )
    trs = []
    for j in range(len(stock.close)):
        pc = stock.close[j - 1] if j else None
        if pc is None:
            trs.append(stock.high[j] - stock.low[j])
        else:
            trs.append(max(stock.high[j] - stock.low[j], abs(stock.high[j] - pc), abs(stock.low[j] - pc)))
    expected_atr = sum(trs[-14:]) / 14.0
    assert abs(float(result.outputs["Custom ATR 14"]) - expected_atr) < 1e-6
    assert abs(expected_tr - trs[-1]) < 1e-9


def test_breakout_fixture_and_filters():
    compiled = compile_source(BREAKOUT_SCAN_SOURCE)
    bull = _benchmark(320, bullish=True)
    bear = _benchmark(320, bullish=False)
    match = _bars(320, breakout=True, volume_spike=True)
    vol_fail = _bars(320, breakout=True, volume_spike=False)

    ok = evaluate_indicator(compiled, match, benchmark_by_symbol=_bench_map(bull))
    no_vol = evaluate_indicator(compiled, vol_fail, benchmark_by_symbol=_bench_map(bull))
    no_mkt = evaluate_indicator(compiled, match, benchmark_by_symbol=_bench_map(bear))

    assert ok.outputs["52W Breakout Signal"] == 1
    assert ok.outputs["52W Breakout"] is True
    assert ok.outputs["52W Breakout Scan"] is True
    assert no_vol.outputs["52W Breakout Signal"] == 0
    assert no_mkt.outputs["52W Breakout Signal"] == 0

    prior = max(match.high[-253:-1])
    assert abs(float(ok.outputs["Prior 252 High"]) - prior) < 1e-9
    assert abs(float(ok.outputs["Close"]) - match.close[-1]) < 1e-9
    vol_sma = sum(match.volume[-20:]) / 20.0
    assert abs(float(ok.outputs["Volume SMA 20"]) - vol_sma) < 1e-6
    assert float(ok.outputs["NIFTY 500 Close"]) == bull.close[-1]
    nifty_sma = sum(bull.close[-50:]) / 50.0
    assert abs(float(ok.outputs["NIFTY 500 SMA 50"]) - nifty_sma) < 1e-6

    filters = validate_filters(compiled, [{"field": "52W Breakout Signal", "operator": "=", "value": 1}])
    assert row_matches(ok.outputs, filters)
    assert not row_matches(no_vol.outputs, filters)
    assert not row_matches(no_mkt.outputs, filters)
    above = validate_filters(
        compiled,
        [{"field": "52W Breakout", "operator": ">", "value": 0, "condition": "above", "setup_type": "signal"}],
    )
    assert above[0]["condition"] == "above"
    assert row_matches(ok.outputs, above)
    assert not row_matches({"52W Breakout": False}, above)
    outside = [{"field": "Close", "operator": "outside", "low": 0, "high": 1}]
    assert row_matches({"Close": 1500.0}, outside)

    names = [item["name"] for item in ok.conditions]
    assert names == [
        "NIFTY 500 Close > NIFTY 500 SMA 50",
        "Close >= Prior 252 High",
        "Volume > Average Volume 20",
    ]
    assert all(item["passed"] is True for item in ok.conditions)
    vol_by_name = {item["name"]: item["passed"] for item in no_vol.conditions}
    assert vol_by_name["Volume > Average Volume 20"] is False
    assert vol_by_name["Close >= Prior 252 High"] is True
    mkt_by_name = {item["name"]: item["passed"] for item in no_mkt.conditions}
    assert mkt_by_name["NIFTY 500 Close > NIFTY 500 SMA 50"] is False


def test_no_lookahead_in_prior_high():
    compiled = compile_source(BREAKOUT_SCAN_SOURCE)
    stock = _bars(320, breakout=True, volume_spike=True)
    spiked = BarData(
        dates=list(stock.dates),
        open=list(stock.open),
        high=list(stock.high),
        low=list(stock.low),
        close=list(stock.close),
        volume=list(stock.volume),
    )
    spiked.high[-1] = 1_000_000.0
    bench = _bench_map(_benchmark(320, bullish=True))
    a = evaluate_indicator(compiled, stock, benchmark_by_symbol=bench)
    b = evaluate_indicator(compiled, spiked, benchmark_by_symbol=bench)
    assert a.outputs["Prior 252 High"] == b.outputs["Prior 252 High"]


def test_missing_bars_insufficient_history():
    compiled = compile_source(BREAKOUT_SCAN_SOURCE)
    short = _bars(20)
    result = evaluate_indicator(compiled, short, benchmark_by_symbol=_bench_map(_benchmark(20)))
    assert result.status == "insufficient_history"


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


def test_ltm_entry_conditions_are_individual_comparisons():
    compiled = compile_source(LTM_SOURCE)
    bars = _bars(320, start_px=100.0)
    result = evaluate_indicator(compiled, bars)
    assert result.status == "ok"
    names = [item["name"] for item in result.conditions]
    assert names == ["Momentum 252 > 0.5"]
    assert "LTM Eligible Signal = 1" not in names
    assert "Close > SMA 50" not in names


MOMENTUM_PULSE_SOURCE = """
//@version=6
indicator("Momentum Pulse Finder", overlay=true)
emaLength = input.int(20, "EMA Length")
rsiLength = input.int(14, "RSI Length")
ema20 = ta.ema(close, emaLength)
rsiValue = ta.rsi(close, rsiLength)
buySignal = close > ema20 and ta.crossover(rsiValue, 50)
plot(ema20, title="EMA 20")
plotshape(buySignal, title="Momentum Signal", style=shape.triangleup, location=location.belowbar, size=size.small, text="BUY")
alertcondition(buySignal, title="Momentum Pulse", message="Momentum Pulse detected")
"""

CROSS_ONLY_SOURCE = """
//@version=6
indicator("Close Cross 50", overlay=true)
buySignal = ta.crossover(close, 50)
plotshape(buySignal, title="Momentum Signal")
"""


def test_momentum_pulse_uses_buy_signal_not_ema_equals_one():
    from app.services.indicator_scanner.entry_conditions import entry_condition_defs
    from app.services.indicator_scanner.scan_service import _row_from_eval

    compiled = compile_source(MOMENTUM_PULSE_SOURCE)
    names = [item["name"] for item in entry_condition_defs(compiled)]
    assert names == ["Close > EMA 20", "RSI 14 crosses above 50"]
    warning_codes = [w.code for w in compiled.warnings]
    assert "MISSING_SCREENER_SIGNAL_PLOT" in warning_codes

    rising = _bars(80, start_px=100.0)
    result = evaluate_indicator(compiled, rising)
    assert result.status == "ok"
    by_name = {item["name"]: item["passed"] for item in result.conditions}
    assert by_name["Close > EMA 20"] is True
    assert by_name["RSI 14 crosses above 50"] is False
    assert result.outputs["Momentum Signal"] is False
    row = _row_from_eval("AAA", "AAA Ltd", result, [])
    assert row["matched"] is False


def test_crossover_matches_only_the_bar_it_fires():
    from app.services.indicator_scanner.scan_service import _row_from_eval

    compiled = compile_source(CROSS_ONLY_SOURCE)
    dates = _dates(6)
    base = [40.0, 40.0, 40.0, 40.0, 40.0, 51.0]
    on_cross = BarData(
        dates=dates,
        open=list(base),
        high=[c + 0.2 for c in base],
        low=[c - 0.2 for c in base],
        close=list(base),
        volume=[1_000.0] * 6,
    )
    after_cross = BarData(
        dates=dates,
        open=[40.0, 40.0, 40.0, 40.0, 51.0, 52.0],
        high=[40.2, 40.2, 40.2, 40.2, 51.2, 52.2],
        low=[39.8, 39.8, 39.8, 39.8, 50.8, 51.8],
        close=[40.0, 40.0, 40.0, 40.0, 51.0, 52.0],
        volume=[1_000.0] * 6,
    )
    fired = evaluate_indicator(compiled, on_cross)
    stale = evaluate_indicator(compiled, after_cross)
    assert fired.outputs["Momentum Signal"] is True
    assert stale.outputs["Momentum Signal"] is False
    assert _row_from_eval("AAA", "A", fired, [])["matched"] is True
    assert _row_from_eval("BBB", "B", stale, [])["matched"] is False
    tv_filters = [{"field": "Momentum Signal", "operator": "=", "value": 1}]
    assert _row_from_eval("AAA", "A", fired, tv_filters)["matched"] is True
    assert _row_from_eval("BBB", "B", stale, tv_filters)["matched"] is False


def _rsi_cross_above_50_bars(n: int = 80) -> BarData:
    """Last bar: close > EMA 20 and RSI 14 crosses above 50."""
    dates = _dates(n)
    close = [100.0 - i * 0.35 for i in range(n - 1)]
    close.append(close[-1] + 18.0)
    return BarData(
        dates=dates,
        open=list(close),
        high=[c + 0.4 for c in close],
        low=[c - 0.4 for c in close],
        close=list(close),
        volume=[1_000.0] * n,
    )


def test_rsi_matches_wilder_rma_formulation():
    from app.services.indicator_scanner.ta_functions import rma, rsi

    closes = [float(100 + (i % 7) - 3) for i in range(40)]
    values = rsi(closes, 14)
    gains = [None]
    losses = [None]
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(delta if delta > 0 else 0.0)
        losses.append(-delta if delta < 0 else 0.0)
    avg_gain = rma(gains, 14)
    avg_loss = rma(losses, 14)
    last = values[-1]
    g = avg_gain[-1]
    loss = avg_loss[-1]
    assert last is not None and g is not None and loss is not None
    expected = 100.0 if loss == 0 else 100.0 - (100.0 / (1.0 + g / loss))
    assert abs(float(last) - expected) < 1e-9


def test_pine_screener_ema20_equals_one_matches_nothing():
    """TradingView Pine Screener: first plot EMA 20 filtered to 1 → no symbols."""
    from app.services.indicator_scanner.scan_service import _row_from_eval

    compiled = compile_source(MOMENTUM_PULSE_SOURCE)
    bars = _rsi_cross_above_50_bars()
    result = evaluate_indicator(compiled, bars)
    assert result.status == "ok"
    by_name = {item["name"]: item["passed"] for item in result.conditions}
    assert by_name["Close > EMA 20"] is True
    assert by_name["RSI 14 crosses above 50"] is True
    assert result.outputs["Momentum Signal"] is True

    tv_filter = _row_from_eval("AEGISLOG", "Aegis", result, [{"field": "EMA 20", "operator": "=", "value": 1}])
    assert tv_filter["matched"] is False
    pulse = _row_from_eval("AEGISLOG", "Aegis", result, [{"field": "Momentum Signal", "operator": "is_true"}])
    assert pulse["matched"] is True
    tv_both = _row_from_eval(
        "AEGISLOG",
        "Aegis",
        result,
        [
            {"field": "Momentum Signal", "operator": "=", "value": 1},
            {"field": "Momentum Pulse", "operator": "is_true"},
        ],
    )
    assert tv_both["matched"] is True
    no_filter = _row_from_eval("AEGISLOG", "Aegis", result, [])
    assert no_filter["matched"] is True


MOMENTUM_SCAN_SOURCE = """
//@version=6
indicator("Momentum Strategy [SCAN]", overlay=false)
sma50 = ta.sma(close, 50)
sma200 = ta.sma(close, 200)
rsi14 = ta.rsi(close, 14)
avgVol = ta.sma(volume, 20)
cond1 = close > sma50
cond2 = sma50 > sma200
cond3 = rsi14 > 55
cond4 = volume > avgVol
scanSignal = cond1 and cond2 and cond3 and cond4
plot(scanSignal ? 1 : 0, "Eligible Signal")
plot(close, "Close")
plot(sma50, "SMA 50")
plot(sma200, "SMA 200")
plot(rsi14, "RSI 14")
plot(volume, "Volume")
plot(avgVol, "Average Volume 20")
"""


def test_momentum_strategy_exposes_all_entry_conditions():
    from app.services.indicator_scanner.entry_conditions import entry_condition_defs
    from app.services.indicator_scanner.scan_service import _row_from_eval

    compiled = compile_source(MOMENTUM_SCAN_SOURCE)
    names = [item["name"] for item in entry_condition_defs(compiled)]
    assert names == [
        "Close > SMA 50",
        "SMA 50 > SMA 200",
        "RSI 14 > 55",
        "Volume > Average Volume 20",
    ]
    assert "Eligible Signal = 1" not in names

    ok_bars = _bars(320, start_px=100.0, volume_spike=True)
    ok = evaluate_indicator(compiled, ok_bars)
    assert ok.status == "ok"
    assert [item["name"] for item in ok.conditions] == names
    assert all(item["passed"] is True for item in ok.conditions)

    fail_vol = _bars(320, start_px=100.0, volume_spike=False)
    failed = evaluate_indicator(compiled, fail_vol)
    by_name = {item["name"]: item["passed"] for item in failed.conditions}
    assert by_name["Volume > Average Volume 20"] is False
    assert by_name["Close > SMA 50"] is True

    matched = _row_from_eval("AAA", "AAA Ltd", ok, [{"field": "Eligible Signal", "operator": "=", "value": 1}])
    unmatched = _row_from_eval("BBB", "BBB Ltd", failed, [{"field": "Eligible Signal", "operator": "=", "value": 1}])
    assert matched["matched"] is True
    assert unmatched["matched"] is False


def test_scan_analytics_uses_all_strategy_conditions():
    from app.services.indicator_scanner.entry_conditions import CONDITIONS_OUTPUT_KEY
    from app.services.indicator_scanner.scan_analytics import build_indicator_scan_analytics

    rows = [
        {
            "symbol": "AAA",
            "display_name": "AAA Ltd",
            "status": "ok",
            "matched": True,
            "outputs": {
                "Close": 120.0,
                "Close t-252": 100.0,
                CONDITIONS_OUTPUT_KEY: [
                    {"name": "Close > SMA 50", "passed": True},
                    {"name": "RSI 14 > 55", "passed": True},
                ],
            },
            "ohlcv": {"close": 120.0},
        },
        {
            "symbol": "BBB",
            "display_name": "BBB Ltd",
            "status": "ok",
            "matched": False,
            "outputs": {
                "Close": 80.0,
                "Close t-252": 100.0,
                CONDITIONS_OUTPUT_KEY: [
                    {"name": "Close > SMA 50", "passed": True},
                    {"name": "RSI 14 > 55", "passed": False},
                ],
            },
            "ohlcv": {"close": 80.0},
        },
        {
            "symbol": "CCC",
            "status": "insufficient_history",
            "matched": False,
            "outputs": {},
            "ohlcv": {},
        },
    ]
    out = build_indicator_scan_analytics(rows, universe_size=3)
    assert out["matched"] == 1
    assert out["unmatched_count"] == 1
    assert out["skipped_count"] == 1
    assert [item["label"] for item in out["filter_analytics"]] == ["Close > SMA 50", "RSI 14 > 55"]
    assert out["filter_analytics"][1]["failed"] == 1
    assert out["filter_funnel"][-1]["label"] == "Final MATCHED Signals"
    assert out["filter_funnel"][-1]["remaining"] == 1
    assert out["top_positive"][0]["symbol"] == "AAA"
    assert out["top_negative"][0]["symbol"] == "BBB"
    assert out["top_positive"][0]["signal"] == "MATCH"
    assert out["top_negative"][0]["signal"] == "REJECT"


def test_return_pct_falls_back_to_prior_high_when_momentum_missing():
    from app.services.indicator_scanner.scan_analytics import row_return_pct

    pct = row_return_pct({"Close": 1400.0, "Prior 252 High": 1000.0}, {"close": 1400.0})
    assert pct is not None
    assert abs(pct - 40.0) < 1e-9


def test_ema_pullback_scanner_evaluates_without_strategy_state():
    compiled = compile_source(EMA_PULLBACK_SCAN_SOURCE)
    result = evaluate_indicator(compiled, _bars(320, start_px=100.0, volume_spike=True))
    assert result.status == "ok"
    assert result.outputs["Signal"] in (0, 1)
    assert result.outputs["Close"] == _bars(320, start_px=100.0, volume_spike=True).close[-1]


def test_evaluate_indicator_stores_252_day_hold_return():
    compiled = compile_source(BREAKOUT_SCAN_SOURCE)
    bars = _bars(320, breakout=True, volume_spike=True)
    result = evaluate_indicator(compiled, bars, benchmark_by_symbol=_bench_map(_benchmark(320, bullish=True)))
    assert result.status == "ok"
    assert result.return_pct is not None
    expected = (bars.close[-1] / bars.close[-253] - 1.0) * 100.0
    assert abs(result.return_pct - expected) < 1e-6


def test_paginate_orders_match_then_reject_then_skipped():
    from types import SimpleNamespace

    from app.services.indicator_scanner.scan_analytics import RETURN_OUTPUT_KEY
    from app.services.indicator_scanner.scan_service import paginate_results

    def row(symbol: str, status: str, matched: bool, ret: float | None) -> SimpleNamespace:
        outputs = {"Close": 100.0}
        if ret is not None:
            outputs[RETURN_OUTPUT_KEY] = ret
        return SimpleNamespace(
            symbol=symbol,
            display_name=f"{symbol} Ltd",
            exchange="NSE",
            timeframe="1D",
            as_of="2026-09-07",
            status=status,
            matched=matched,
            outputs=outputs,
            ohlcv={"close": 100.0},
            error_detail=None,
            bar_count=320,
        )

    rows = [
        row("SKIP1", "insufficient_history", False, None),
        row("REJ1", "ok", False, 8.0),
        row("MATCH2", "ok", True, 5.0),
        row("MATCH1", "ok", True, 20.0),
        row("REJ2", "ok", False, 1.0),
    ]
    page, total = paginate_results(
        rows,
        page=1,
        page_size=50,
        search=None,
        matched_only=False,
        sort_field="symbol",
        sort_dir="asc",
        output_names=["Close"],
    )
    assert total == 5
    assert [item["symbol"] for item in page] == ["MATCH1", "MATCH2", "REJ1", "REJ2", "SKIP1"]
    assert [item["signal"] for item in page] == ["MATCH", "MATCH", "REJECT", "REJECT", "SKIPPED"]

    matched_only, matched_total = paginate_results(
        rows,
        page=1,
        page_size=50,
        search=None,
        matched_only=False,
        sort_field="signal",
        sort_dir="asc",
        output_names=["Close"],
        signal="MATCH",
    )
    assert matched_total == 2
    assert {item["symbol"] for item in matched_only} == {"MATCH1", "MATCH2"}

    rejected_only, rejected_total = paginate_results(
        rows,
        page=1,
        page_size=50,
        search=None,
        matched_only=False,
        sort_field="signal",
        sort_dir="asc",
        output_names=["Close"],
        signal="REJECT",
    )
    assert rejected_total == 2
    assert {item["symbol"] for item in rejected_only} == {"REJ1", "REJ2"}

    skipped_only, skipped_total = paginate_results(
        rows,
        page=1,
        page_size=50,
        search=None,
        matched_only=False,
        sort_field="signal",
        sort_dir="asc",
        output_names=["Close"],
        signal="SKIPPED",
    )
    assert skipped_total == 1
    assert skipped_only[0]["symbol"] == "SKIP1"
