"""Unit tests for strategy market-data derived helpers."""
from datetime import date, timedelta
from decimal import Decimal

from app.services.market_data_ingestion.derived import (
    adtv_20,
    attach_adtv_20_series,
    compute_adtv_20_for_bar,
    compute_delivery_pct,
    compute_turnover,
    weekly_ohlcv,
)


def test_delivery_pct_formula():
    assert compute_delivery_pct(250, 1000) == Decimal("25.0000")


def test_delivery_pct_zero_traded():
    assert compute_delivery_pct(10, 0) is None


def test_delivery_pct_missing():
    assert compute_delivery_pct(None, 100) is None
    assert compute_delivery_pct(10, None) is None


def test_turnover():
    assert compute_turnover(100.5, 10) == Decimal("1005.0000")


def test_adtv_20():
    rows = [{"turnover": 100.0 + i} for i in range(20)]
    val = adtv_20(rows)
    assert val is not None
    assert abs(val - (sum(100.0 + i for i in range(20)) / 20)) < 1e-6


def test_adtv_short_history():
    rows = [{"close": 10, "volume": 2} for _ in range(5)]
    assert adtv_20(rows) == 20.0


def test_attach_adtv_20_series():
    rows = [{"close": 10.0, "volume": 100, "trade_date": date(2026, 1, i + 1)} for i in range(25)]
    out = attach_adtv_20_series(rows)
    assert out[0]["adtv_20"] == 1000.0
    assert out[19]["adtv_20"] == 1000.0
    assert out[24]["adtv_20"] == 1000.0


def test_compute_adtv_20_for_bar():
    prior = [{"close": 10, "volume": 2} for _ in range(19)]
    bar = {"close": 10, "volume": 2}
    assert compute_adtv_20_for_bar(prior, bar) == 20.0


def test_weekly_resample():
    base = date(2026, 1, 5)  # Monday
    rows = []
    for i in range(10):
        d = base + timedelta(days=i)
        rows.append(
            {
                "trade_date": d,
                "open": 100 + i,
                "high": 110 + i,
                "low": 90 + i,
                "close": 105 + i,
                "volume": 1000 + i,
            }
        )
    weekly = weekly_ohlcv(rows)
    assert len(weekly) >= 1
    assert "close" in weekly[0]
