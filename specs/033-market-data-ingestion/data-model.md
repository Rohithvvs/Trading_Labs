# Data Model: Market Data Ingestion & Daily Update System

**Feature**: `033-market-data-ingestion`  
**Date**: 2026-08-08

---

## Entity relationship (logical)

```text
StockMaster (Universe Member)
    │ 1
    │ supplies active symbol list
    ▼
DailyEquityBar (daily_ohlcv) ── many per symbol
IndexBar (index_ohlcv)        ── series symbol = NIFTY500
DataLoadRun (data_load_log)   ── operational, no hard FK to bars
FreshnessCheckResult          ── computed, not necessarily persisted
```

---

## 1. Universe Member (physical: `stocks_master`)

**Reuse** existing table; extend columns.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| symbol | string, unique | yes | PK practical key; e.g. `RELIANCE-EQ` |
| isin | string | no | Join key for delivery |
| name | string | no | maps from `company_name` |
| sector | string | no | existing |
| industry | string | no | **add** if not present |
| is_nifty500 | bool | yes | **add**; true when membership active |
| first_seen | date/timestamptz | no | **add**; set on first import |
| last_seen | date/timestamptz | no | **add**; updated each load seeing symbol |
| active | bool | yes | maps from `is_active` |
| universe | string | no | existing `NIFTY500` tag |
| series | string | no | existing EQ |

### Validation / lifecycle

- Active NIFTY500 load set: `is_active AND (is_nifty500 OR universe='NIFTY500')` during transition.
- Soft-deactivate members removed from CSV; retain historical `daily_ohlcv` rows.
- Empty active set → fail loads and gate.

### State

`active=true|false`; not a multi-state machine.

---

## 2. Daily Equity Bar (`daily_ohlcv`)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| trade_date | date | yes | NSE session date |
| symbol | string | yes | platform symbol |
| open | decimal | yes | |
| high | decimal | yes | ≥ low |
| low | decimal | yes | |
| close | decimal | yes | |
| volume | bigint | yes | ≥ 0 |
| delivery_qty | bigint | no | null if missing |
| delivery_pct | decimal | no | null if not computable |
| turnover | decimal | no | close × volume at write |
| source | string | no | provenance |
| loaded_at | timestamptz | yes | audit |

**Identity:** PRIMARY KEY `(trade_date, symbol)`

### Derived rules

- `turnover = close * volume` when writing (do not invent if OHLC missing — row should not insert without OHLCV).
- `delivery_pct = (delivery_qty / traded_qty) * 100` only if `traded_qty > 0` and `delivery_qty` is not null.
- Prefer `volume` as traded_qty when report aligns; if report has separate traded_qty, use report for pct denominator and keep OHLCV volume from FYERS.
- Never invent delivery_qty or delivery_pct.

### Relationships

- Logical association to universe by `symbol`; no mandatory FK.

---

## 3. Index Bar (`index_ohlcv`)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| trade_date | date | yes | |
| symbol | string | yes | canonical `NIFTY500` |
| open, high, low, close | decimal | yes | |
| volume | bigint | no | |
| source | string | no | |
| loaded_at | timestamptz | yes | |

**Identity:** PRIMARY KEY `(trade_date, symbol)`

---

## 4. Data Load Run (`data_load_log`)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | uuid/serial | yes | PK |
| load_type | enum string | yes | `FULL`, `DAILY` |
| trigger_source | string | yes | `CLI`, `SCHEDULE` |
| status | string | yes | see states |
| data_date | date | no | target session for DAILY |
| range_from | date | no | FULL |
| range_to | date | no | FULL |
| started_at | timestamptz | yes | |
| ended_at | timestamptz | no | |
| duration_ms | int | no | |
| rows_fetched | int | no | |
| rows_inserted | int | no | |
| rows_updated | int | no | |
| rows_failed | int | no | |
| rows_skipped | int | no | |
| provider | string | no | |
| error_summary | text | no | |
| details_json | json | no | samples, coverage |

### Status state machine

```text
RUNNING → SUCCESS
RUNNING → PARTIAL
RUNNING → FAILED
(no run) → SKIPPED_LOCKED   # never acquired / immediate skip
```

- **SUCCESS:** DAILY expected_date equity coverage ≥99% and index present (FULL: meets history policy for attempted set).
- **PARTIAL:** some symbols/dates failed or coverage below success threshold but some data written.
- **FAILED:** hard abort (auth, DB down, zero progress when progress required).
- **SKIPPED_LOCKED:** single-flight rejection.

---

## 5. Freshness Check Result (computed)

Not required as a table; may be embedded in API/CLI JSON.

| Field | Notes |
|-------|-------|
| ok | bool |
| code | `OK` or `MARKET_DATA_STALE` |
| expected_trade_date | date |
| latest_equity_trade_date | date \| null |
| latest_index_trade_date | date \| null |
| equity_coverage_ratio | 0–1 |
| missing_symbol_count | int |
| missing_symbols_sample | list[str] |
| index_present | bool |
| reason | string |
| remediation | string |

---

## 6. Read-side derived products (not stored)

| Product | Formula / method | Consumer |
|---------|------------------|----------|
| ADTV-20 | mean of last 20 sessions’ `turnover` (or close×volume) | STR-071 |
| Weekly OHLCV | resample daily O→first H→max L→min C→last V→sum | STR-045 |

---

## 7. Indexes (physical)

| Table | Index |
|-------|-------|
| daily_ohlcv | PK (trade_date, symbol) |
| daily_ohlcv | (symbol, trade_date DESC) |
| daily_ohlcv | (trade_date) |
| index_ohlcv | PK (trade_date, symbol) |
| index_ohlcv | (symbol, trade_date DESC) |
| data_load_log | (started_at DESC) |
| data_load_log | (load_type, data_date DESC) |
| stocks_master | existing symbol unique; index is_nifty500 + is_active |

---

## 8. Volume estimates

| Entity | Rows (order) |
|--------|----------------|
| daily_ohlcv | ~500 symbols × ~750 days ≈ 375k (3y); grows ~500/day |
| index_ohlcv | ~750 rows / 3y |
| data_load_log | low hundreds/year |
