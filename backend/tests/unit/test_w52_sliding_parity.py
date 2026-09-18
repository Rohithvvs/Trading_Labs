"""Parity tests: O(N) sliding precompute vs the reference indicator functions.

These guard the perf fix in ``book_engine.replay_book``. The candidate-scan
hot loop was replaced by precomputed per-symbol maps; the maps must return
exactly the same values the original ``prior_high_252`` / ``vol_sma20`` /
``momentum_60`` produced for every native index where the symbol traded.
"""

import math
import random
from datetime import date, timedelta

from app.services.strategies.breakout52w.book_engine import (
    _sliding_momentum,
    _sliding_prior_high,
    _sliding_vol_sma,
)
from app.services.strategies.breakout52w.indicators import (
    momentum_60,
    prior_high_252,
    vol_sma20,
)


def _dates(n):
    start = date(2010, 1, 1)
    return [start + timedelta(days=i) for i in range(n)]


def test_sliding_prior_high_matches_reference_clean():
    values = [float(i) + 1.0 for i in range(600)]
    dates = _dates(600)
    got = _sliding_prior_high(values, dates)
    for j in range(len(values)):
        expected = prior_high_252(values, j)
        assert got.get(dates[j]) == expected, f"j={j} {got.get(dates[j])} != {expected}"


def test_sliding_prior_high_matches_reference_with_none_and_nan():
    rng = random.Random(123)
    n = 800
    values: list[float | None] = []
    for i in range(n):
        r = rng.random()
        if r < 0.05:
            values.append(None)
        elif r < 0.07:
            values.append(float("nan"))
        elif r < 0.08:
            values.append(float("inf"))
        else:
            values.append(rng.uniform(1.0, 1000.0))
    dates = _dates(n)
    got = _sliding_prior_high(values, dates)  # type: ignore[arg-type]
    for j in range(n):
        expected = prior_high_252(values, j)
        g = got.get(dates[j])
        if expected is None:
            assert g is None, f"j={j} expected None got {g}"
        else:
            assert g is not None and math.isclose(g, expected), f"j={j} {g} != {expected}"


def test_sliding_vol_sma_matches_reference():
    rng = random.Random(9)
    n = 500
    values: list[float | None] = []
    for i in range(n):
        r = rng.random()
        if r < 0.04:
            values.append(None)
        elif r < 0.05:
            values.append(float("nan"))
        else:
            values.append(rng.uniform(1e5, 1e7))
    dates = _dates(n)
    got = _sliding_vol_sma(values, dates)  # type: ignore[arg-type]
    for t in range(n):
        expected = vol_sma20(values, t)
        g = got.get(dates[t])
        if expected is None:
            assert g is None, f"t={t} expected None got {g}"
        else:
            assert g is not None and math.isclose(g, expected), f"t={t} {g} != {expected}"


def test_sliding_momentum_matches_reference():
    rng = random.Random(5)
    n = 400
    values: list[float | None] = []
    for i in range(n):
        r = rng.random()
        if r < 0.03:
            values.append(None)
        elif r < 0.04:
            values.append(0.0)
        else:
            values.append(rng.uniform(1.0, 500.0))
    dates = _dates(n)
    got = _sliding_momentum(values, dates)  # type: ignore[arg-type]
    for t in range(n):
        expected = momentum_60(values, t)
        g = got.get(dates[t])
        if expected is None:
            assert g is None, f"t={t} expected None got {g}"
        else:
            assert g is not None and math.isclose(g, expected), f"t={t} {g} != {expected}"


def test_sliding_short_series_returns_empty_or_none():
    short = [1.0, 2.0, 3.0]
    assert _sliding_prior_high(short, _dates(3)) == {}
    assert _sliding_vol_sma(short, _dates(3)) == {}
    assert _sliding_momentum(short, _dates(3)) == {}
