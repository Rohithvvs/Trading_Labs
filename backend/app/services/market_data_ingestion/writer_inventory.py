"""Static inventory of daily_ohlcv / index_ohlcv writers. No database I/O."""

DAILY_INDEX_WRITERS = [
    {
        "path": "backend/app/services/market_data_ingestion/pipelines/full_load.py",
        "source": "FYERS",
        "writes": True,
        "notes": "Official EOD full history.",
    },
    {
        "path": "backend/app/services/market_data_ingestion/ensure.py",
        "source": "FYERS",
        "writes": True,
        "notes": "Daily latest-session ensure / scheduler.",
    },
    {
        "path": "backend/app/services/market_data_ingestion/session_repair.py",
        "source": "FYERS",
        "writes": True,
        "notes": "Session repair and thin-history backfill.",
    },
    {
        "path": "backend/scripts/backfill_equity_history.py",
        "source": "FYERS",
        "writes": True,
        "notes": "Operator 18y backfill.",
    },
    {
        "path": "backend/app/services/strategies/breakout52w/session_overlay.py",
        "source": "FYERS_LIVE_1D",
        "writes": True,
        "notes": "In-session quote overlay. Persist to daily_ohlcv is rejected by source policy.",
    },
    {
        "path": "backend/app/services/strategy_tester/scan_service.py",
        "source": "FYERS_LIVE_1D",
        "writes": True,
        "notes": "Strategy tester live 1D persist. Rejected at daily_ohlcv write boundary.",
    },
    {
        "path": "backend/scripts/fetch_w52_live_1d.py",
        "source": "FYERS_LIVE_1D",
        "writes": True,
        "notes": "Operator live 1D fetch. Rejected at daily_ohlcv write boundary.",
    },
    {
        "path": "backend/app/services/strategies/ltm/candle_backfill.py",
        "source": "historical_candles",
        "writes": True,
        "notes": "ACS 1D copy. Rejected at daily_ohlcv write boundary (source policy).",
    },
    {
        "path": "backend/app/services/strategies/ltm/scan_service.py",
        "source": "historical_candles",
        "writes": False,
        "notes": "Read-only ACS fallback for LTM matrix.",
    },
    {
        "path": "backend/app/services/strategies/breakout52w/scan_service.py",
        "source": "historical_candles",
        "writes": False,
        "notes": "Read-only ACS fallback for 52W matrices.",
    },
    {
        "path": "backend/app/services/strategy_tester/scan_service.py",
        "source": "historical_candles",
        "writes": False,
        "notes": "fill_missing_from_historical_candles is in-memory only.",
    },
]
