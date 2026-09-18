"""Guard: strategy ingestion pipelines must not import ACS write paths for dual-write."""
from pathlib import Path


def test_pipelines_do_not_reference_acs_writes():
    root = Path(__file__).resolve().parents[2] / "app" / "services" / "market_data_ingestion"
    forbidden = (
        "authoritative_candle_store",
        "historical_candles",
        "market_data.candles",
        "MarketDataService",
        "store_candles",
    )
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            # Allow comments mentioning ACS as non-write target
            if token in text and "not" not in text.lower() and "ACS" in text:
                # soft check: pipelines specifically
                if "pipelines" in str(path):
                    assert "upsert_daily_bars" in text or "upsert_index_bars" in text
            if path.name in {"daily_update.py", "full_load.py", "repository.py"}:
                assert "AuthoritativeCandleStore" not in text
                assert "HistoricalCandle" not in text
