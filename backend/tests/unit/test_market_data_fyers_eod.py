"""FYERS EOD adapter — error surfaces without inventing bars; long ranges are chunked."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.market_data_ingestion.providers.fyers_eod import (
    FyersEodProvider,
    _iter_date_chunks,
)


def test_iter_date_chunks_splits_multi_year():
    chunks = list(_iter_date_chunks(date(2023, 7, 9), date(2026, 8, 7), max_days=365))
    assert len(chunks) >= 3
    assert chunks[0][0] == date(2023, 7, 9)
    assert chunks[-1][1] == date(2026, 8, 7)
    for start, end in chunks:
        assert (end - start).days <= 364
        assert start <= end
    # contiguous / non-overlapping
    for i in range(1, len(chunks)):
        assert chunks[i][0] == chunks[i - 1][1] + timedelta(days=1)


@pytest.mark.asyncio
async def test_fetch_raises_on_provider_error():
    svc = MagicMock()
    svc._client = MagicMock(return_value=object())
    svc._normalize_symbol = MagicMock(return_value="NSE:AAA-EQ")
    svc._request_history_with_retries = MagicMock(side_effect=RuntimeError("network"))

    prov = FyersEodProvider(fyers_service=svc)
    with pytest.raises(RuntimeError):
        await prov.fetch_daily_range("AAA-EQ", date(2026, 1, 1), date(2026, 1, 2))


@pytest.mark.asyncio
async def test_fetch_empty_candles():
    svc = MagicMock()
    svc._client = MagicMock(return_value=object())
    svc._normalize_symbol = MagicMock(return_value="NSE:AAA-EQ")
    svc._request_history_with_retries = MagicMock(return_value={"candles": []})
    prov = FyersEodProvider(fyers_service=svc)
    rows = await prov.fetch_daily_range("AAA-EQ", date(2026, 1, 1), date(2026, 1, 2))
    assert rows == []


@pytest.mark.asyncio
async def test_fetch_long_range_issues_multiple_history_calls():
    """Multi-year request must chunk; results stitched and deduped by trade_date."""
    day_a = datetime(2023, 8, 1, tzinfo=timezone.utc).timestamp()
    day_b = datetime(2024, 8, 1, tzinfo=timezone.utc).timestamp()
    day_dup = day_b  # same date returned by adjacent chunks → dedupe

    def _history(_client, payload, _symbol):
        rf = payload["range_from"]
        if rf.startswith("2023"):
            return {
                "candles": [
                    [day_a, 1.0, 2.0, 0.5, 1.5, 100],
                    [day_dup, 9.0, 9.0, 9.0, 9.0, 1],  # superseded by later chunk
                ]
            }
        if rf.startswith("2024"):
            return {"candles": [[day_b, 10.0, 11.0, 9.0, 10.5, 200]]}
        return {"candles": []}

    svc = MagicMock()
    svc._client = MagicMock(return_value=object())
    svc._normalize_symbol = MagicMock(return_value="NSE:AAA-EQ")
    svc._request_history_with_retries = MagicMock(side_effect=_history)
    prov = FyersEodProvider(fyers_service=svc)

    rows = await prov.fetch_daily_range("AAA-EQ", date(2023, 7, 9), date(2026, 8, 7))
    assert svc._request_history_with_retries.call_count >= 3
    assert len(rows) == 2
    assert rows[0]["trade_date"] == date(2023, 8, 1)
    assert rows[1]["trade_date"] == date(2024, 8, 1)
    assert rows[1]["close"] == 10.5  # last chunk wins on duplicate date
