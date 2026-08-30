"""Deterministic evaluator tests for the 52-week breakout scan indicator."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.indicator_scanner.compiler import compile_source
from app.services.indicator_scanner.evaluator import BarData, evaluate_indicator
from app.services.indicator_scanner.filters import row_matches, validate_filters
from app.services.indicator_scanner.ta_functions import sma
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
