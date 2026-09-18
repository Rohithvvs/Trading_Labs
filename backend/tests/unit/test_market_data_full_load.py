from datetime import date
from decimal import Decimal

from app.services.market_data_ingestion.derived import compute_delivery_pct, compute_turnover
from app.services.market_data_ingestion.pipelines.full_load import missing_ohlcv_ranges


def test_full_load_formulas():
    assert compute_delivery_pct(400, 800) == Decimal("50.0000")
    assert compute_turnover(12.5, 4) == Decimal("50.0000")


def test_missing_ohlcv_ranges_empty_symbol():
    start, end = date(2008, 8, 14), date(2026, 8, 14)
    assert missing_ohlcv_ranges(start, end, None, None) == [(start, end)]


def test_missing_ohlcv_ranges_older_gap_only():
    start, end = date(2008, 8, 14), date(2026, 8, 14)
    min_d, max_d = date(2025, 6, 18), date(2026, 8, 14)
    assert missing_ohlcv_ranges(start, end, min_d, max_d) == [
        (date(2008, 8, 14), date(2025, 6, 17))
    ]


def test_missing_ohlcv_ranges_complete():
    start, end = date(2008, 8, 14), date(2026, 8, 14)
    assert missing_ohlcv_ranges(start, end, start, end) == []
