# Database Split Verification Report

**Verification Timestamp**: `2026-09-20T06:29:42.055880+00:00`  
**Audit Mode**: READ-ONLY (No data was written, deleted, or modified)

---

## 1. Connection Safety Confirmation

| Database | Provider | Host / Target | Verified State |
|---|---|---|---|
| **Local PostgreSQL** | PostgreSQL 18.6 | `localhost:5432/trading_data` | **Complete original source (Read-only)** |
| **Turso Cloud** | libSQL / SQLite | `tradinghistory` | **Migrated daily/index history (Read-only)** |
| **Neon Cloud** | PostgreSQL 16.15 | `ep-patient-bonus-aonma8xh.c-2.ap-southeast-1.aws.neon.tech:5432/neondb` | **Operational data only (Read-only)** |

---

## 2. Local Database Inventory Summary

- **Total Local Database Size**: **893.56 MB** (0.8726 GB)
- **Total Tables Count**: **117** (across `public` and `market_data` schemas)
- **Candle / Market-History Storage**: **718.77 MB** (80.45% of DB)
- **Operational / Application Storage**: **163.03 MB** (18.24% of DB)
- **Cache / Reconciliation Metadata Storage**: **0.06 MB** (0.01% of DB)
- **Uncertain Storage**: **0.00 MB** (0.00%)

---

## 3. Turso Verification Results

### `daily_ohlcv`
- **Earliest Date**: `2003-12-10`
- **Latest Date**: `2026-09-18`
- **Total Rows**: **2,248,290** *(Expected: 2,248,290 | **MATCH**)*
- **Symbol Count**: **766** *(Expected: 766 | **MATCH**)*

### `index_ohlcv`
- **Symbol**: `NIFTY500`
- **Earliest Date**: `2008-07-22`
- **Latest Date**: `2026-09-18`
- **Total Rows**: **4,493** *(Expected: 4,493 | **MATCH**)*

### Row Count Reconciliation against Local Source
- **Local `daily_ohlcv`**: 2,248,338 rows vs **Turso**: 2,248,290 rows
  - **Difference**: **-48 rows** (Explains the 48 Saturday phantom daily rows deliberately excluded per `turso_exclusions.py`).
- **Local `index_ohlcv`**: 4,494 rows vs **Turso**: 4,493 rows
  - **Difference**: **-1 row** (Explains the single invalid NIFTY500 record on 2009-05-18 deliberately excluded).
- **Total Turso Rows**: **2,252,783** *(Expected: 2,252,783 | **MATCH**)*

---

## 4. Neon Verification Results

- **Neon Database Size**: **161.38 MB**
- **Schemas Present**: `['public', 'market_data']`
- **Alembic Version**: `20260829_indicator_scanner` *(Matches Local: True)*
- **Excluded Candle/History Tables**: All **32 tables** exist on Neon with **exactly 0 rows** (**PASS**).
- **Operational Tables**: All **85 operational tables** match local row counts with **0 mismatches** (**PASS**).

---

## 5. Final Reconciliation Table

| Data category | Local PostgreSQL | Turso | Neon | Verification result |
|---|---|---|---|---|
| **Daily equity OHLCV** | 2,248,338 rows (2003-2026) | 2,248,290 rows (2003-2026) | 0 rows (schema only) | **PASS** |
| **Index OHLCV** | 4,494 rows (2008-2026) | 4,493 rows (2008-2026) | 0 rows (schema only) | **PASS** |
| **ACS / historical candles** | 431,159 rows (2025-2026) | Not copied (Not in v1) | 0 rows (schema only) | **PASS** |
| **Partitioned market-data candles** | 53,986 rows (2024-2026) | Not copied (Not in v1) | 0 rows (schema only) | **PASS** |
| **Cache / reconciliation metadata** | 9 rows (`ltp_cache`), 0 rows (`empty_gaps`) | Not copied | 0 rows (schema only) | **PASS** |
| **Operational app data** | 85 tables (170,948,608 bytes) | Not copied | 85 tables (100% matched) | **PASS** |

---

## Final Answers

1. **Is local PostgreSQL still the complete original copy?**  
   **Yes.** Local PostgreSQL retains 100% of all original tables, candle history (2.25M rows), ACS candles (431k rows), legacy partitions, and operational data.
2. **Does Turso contain the intended daily/index historical data?**  
   **Yes.** Turso holds exactly 2,248,290 daily equity rows and 4,493 index rows (2,252,783 total rows), perfectly reflecting the intended 49-row exclusion policy.
3. **Does Neon contain all operational data with matching row counts?**  
   **Yes.** All 85 operational tables in Neon match the local database row counts with zero discrepancies, and all candle tables contain exactly 0 rows.
4. **Which local data is not present in either Turso or Neon?**  
   - `public.historical_candles` (431,159 rows of ACS/intraday candle cache)
   - `market_data.candles_1d_*` partitions (53,986 rows of legacy daily market bars)
   Both datasets remain fully preserved in Local PostgreSQL.
5. **List every mismatch or unexpected table/row count:**  
   **None.** Zero mismatches or unexpected table counts were detected across any of the three stores.
6. **State whether the intended split is verified:**  
   **VERIFIED.** The three-database split adheres strictly to the approved architecture.

DATABASE SPLIT VERIFICATION COMPLETE — NO DATA WAS WRITTEN, DELETED, OR MODIFIED
