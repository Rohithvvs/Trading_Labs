from decimal import Decimal

from app.services.market_data_ingestion.derived import compute_delivery_pct, compute_turnover


def test_full_load_formulas():
    assert compute_delivery_pct(400, 800) == Decimal("50.0000")
    assert compute_turnover(12.5, 4) == Decimal("50.0000")
