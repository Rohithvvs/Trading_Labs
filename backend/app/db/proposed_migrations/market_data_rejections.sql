-- PROPOSED ONLY. Do not apply until explicitly approved.
-- Postgres operational audit for bars rejected by the daily/index OHLC gate.
-- Not part of the Alembic chain. Rejected rows must never enter daily_ohlcv.

CREATE TABLE IF NOT EXISTS market_data_rejections (
    id              BIGSERIAL PRIMARY KEY,
    attempted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    context         TEXT NOT NULL,          -- upsert_daily_bars | upsert_index_bars | repair
    table_name      TEXT NOT NULL,          -- daily_ohlcv | index_ohlcv
    symbol          TEXT NOT NULL,
    trade_date      DATE,
    source          TEXT,                   -- historical_candles | FYERS | FYERS_LIVE_1D | ...
    provider        TEXT,                   -- fyers_eod | acs_copy | live_quote
    request_id      TEXT,                   -- non-secret correlation id only
    open            NUMERIC(18, 8),
    high            NUMERIC(18, 8),
    low             NUMERIC(18, 8),
    close           NUMERIC(18, 8),
    volume          NUMERIC(18, 8),
    payload_json    JSONB,                  -- OHLCV + optional delivery fields; never tokens/URLs
    material_reasons TEXT[] NOT NULL,
    rounding_reasons TEXT[],
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_market_data_rejections_symbol_date
    ON market_data_rejections (symbol, trade_date);

CREATE INDEX IF NOT EXISTS ix_market_data_rejections_attempted_at
    ON market_data_rejections (attempted_at);
