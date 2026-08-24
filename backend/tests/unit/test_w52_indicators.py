"""52W indicator fixtures from spec Acceptance Fixtures."""

from app.services.strategies.breakout52w.indicators import (
    atr14,
    market_ok,
    prior_high_252,
    vol_sma20,
    wilder_atr14,
)


def test_prior_high_excludes_today():
    highs = [float(i) for i in range(253)]
    # indices 0..251 highs are 0..251; bar 252 high is 252
    assert prior_high_252(highs, 252) == 251.0
    assert prior_high_252(highs, 251) is None


def test_vol_sma_includes_today_and_strict_gate():
    vols = [10.0] * 19 + [30.0]
    sma = vol_sma20(vols, 19)
    assert sma == 11.0
    assert 30.0 > sma


def test_market_ok_strict():
    bench = [100.0] * 50
    assert market_ok(bench, 49) is False
    bench2 = [100.0] * 49 + [101.0]
    assert market_ok(bench2, 49) is True


def test_atr_is_sma_not_wilder():
    highs = [10.0] * 20
    lows = [8.0] * 20
    closes = [9.0] * 20
    sma = atr14(highs, lows, closes, 13)
    wilder = wilder_atr14(highs, lows, closes, 13)
    assert sma == 2.0
    # After several expanding bars SMA and Wilder diverge
    extra_h = [20.0, 21.0, 22.0, 23.0, 24.0]
    extra_l = [8.0, 8.0, 8.0, 8.0, 8.0]
    extra_c = [15.0, 16.0, 17.0, 18.0, 19.0]
    highs2 = highs + extra_h
    lows2 = lows + extra_l
    closes2 = closes + extra_c
    t = len(highs2) - 1
    sma2 = atr14(highs2, lows2, closes2, t)
    wilder2 = wilder_atr14(highs2, lows2, closes2, t)
    assert sma2 is not None and wilder2 is not None
    assert sma2 != wilder2
