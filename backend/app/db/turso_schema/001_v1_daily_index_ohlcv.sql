-- Turso/libSQL v1 candle history (daily equity + index only).
-- Idempotent. v1 is daily equity + index only (ACS/intraday tables are a later phase).
--
-- PostgreSQL → libSQL mapping:
--   date              → TEXT ISO date (YYYY-MM-DD, NSE session date)
--   numeric(18,8)     → REAL
--   bigint            → INTEGER (64-bit)
--   timestamptz       → TEXT ISO-8601 UTC
--   varchar           → TEXT
--
-- Identity matches Postgres: PRIMARY KEY (trade_date, symbol).
-- Weekly bars are derived in Python and are not stored.

CREATE TABLE IF NOT EXISTS daily_ohlcv (
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL DEFAULT 0,
    delivery_qty INTEGER,
    delivery_pct REAL,
    turnover REAL,
    adtv_20 REAL,
    source TEXT,
    loaded_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_daily_ohlcv_symbol_trade_date
ON daily_ohlcv (symbol, trade_date);

CREATE INDEX IF NOT EXISTS idx_daily_ohlcv_trade_date
ON daily_ohlcv (trade_date);

CREATE TABLE IF NOT EXISTS index_ohlcv (
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER,
    source TEXT,
    loaded_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_index_ohlcv_symbol_trade_date
ON index_ohlcv (symbol, trade_date);
