-- Once-per-IST-day candle sync lock and result. Shared by every Render
-- instance. Not candle data. Idempotent.

CREATE TABLE IF NOT EXISTS candle_sync_day (
    sync_date TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    backend TEXT NOT NULL,
    owner TEXT,
    lease_expires_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    target_session TEXT,
    bar_state TEXT,
    latest_equity_date TEXT,
    latest_index_date TEXT,
    symbols_processed INTEGER,
    symbols_updated INTEGER,
    symbols_failed INTEGER,
    rows_upserted INTEGER,
    duration_ms INTEGER,
    error TEXT
);
