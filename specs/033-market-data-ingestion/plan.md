# Implementation Plan: Market Data Ingestion & Daily Update System

**Branch**: `033-market-data-ingestion` | **Date**: 2026-08-08 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/033-market-data-ingestion/spec.md` (Clarified session 2026-08-08)  
**Status**: Design complete — **no application code, migrations, or schema changes in this step**

---

## Summary

Build a **strategy-grade daily market-data foundation** for the NIFTY 500 scanner: full historical load (≥3 years), daily incremental EOD update, NSE delivery %, NIFTY500 index bars, load tracking, operator CLI, scheduled post-close job, and a hard pre-scanner freshness gate (`MARKET_DATA_STALE`).

**Architectural decision (clarified):** a **dedicated strategy-grade dataset** is the source of truth for scanners/strategies. Existing ACS / `historical_candles` / `market_data.candles` remain for current non-strategy consumers; **no dual-write** in this feature.

**Brownfield approach:** extend and wrap existing FYERS clients, universe seed, trading calendar, advisory locks, argparse CLI patterns, scanner entrypoints, and logging — do not rewrite ACS or the scanner engine.

---

## Technical Context

**Language/Version**: Python 3.11+ (existing backend)  
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Alembic, APScheduler, Pydantic Settings, FYERS API v3 (`fyers_apiv3`), pandas (already dominant; Polars optional later only if needed), httpx/aiohttp, pytest  
**Storage**: PostgreSQL 15+ (existing); new tables in public schema (or `market_data` schema if preferred at migration time) for strategy-grade daily data  
**Testing**: pytest + pytest-asyncio (existing `backend/tests`, `backend/app/tests`)  
**Target Platform**: Backend service (Linux/Windows), ops CLI on same host  
**Project Type**: Brownfield web/backend + operator CLI  
**Performance Goals**: Daily update full universe ≤15 minutes under normal provider conditions; full load resumable; bulk upserts; bounded provider concurrency  
**Constraints**: Single-flight FULL/DAILY loads; no ACS dual-write; do not invent delivery values; scanners blocked on stale OHLCV+index; STR-041 hard-fails without delivery; sector indices out of scope  
**Scale/Scope**: ~500–755 NIFTY500-class symbols; ≥3 years daily bars (~750 sessions × ~500 ≈ ~375k–500k equity rows); 1 index series; daily EOD pipeline  

---

## Constitution Check

*GATE: Constitution template is placeholder (not project-specific principles). Apply brownfield + clarified-spec gates.*

| Gate | Status | Notes |
|------|--------|-------|
| Reuse before rewrite | PASS | Reuse FYERS, StockMaster, TradingHours, locks, ACS left intact |
| Clarified SoT honored | PASS | Strategy-grade dataset, not ACS replacement |
| No dual-write required | PASS | Explicit out of scope |
| Scanner non-regression | PASS | Gate + strategy read path only; ACS path unchanged for non-strategy |
| Idempotent upserts | PASS | PK (trade_date, symbol) + ON CONFLICT |
| Single-flight loads | PASS | Reuse `acquire_singleton_lease` / advisory locks |
| Tech stack fit | PASS | Stay within existing Python/PG/SQLAlchemy stack |

**Post-design re-check:** PASS — design does not force Polars, greenfield package roots, or ACS rewrite.

---

## Project Structure

### Documentation (this feature)

```text
specs/033-market-data-ingestion/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/           # Phase 1
│   ├── cli.md
│   └── freshness_gate.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks (not this command)
```

### Source Code (repository root) — planned placement

```text
backend/
├── app/
│   ├── config/settings.py              # REUSE + small settings additions
│   ├── db/locks.py                     # REUSE single-flight
│   ├── models/
│   │   ├── stock.py                    # EXTEND StockMaster fields OR map view
│   │   └── strategy_market_data.py     # NEW models (daily_ohlcv, index_ohlcv, data_load_log)
│   ├── services/
│   │   ├── fyers_service.py            # REUSE OHLCV/index history
│   │   ├── universe_service.py         # REUSE + lifecycle fields
│   │   ├── trading_hours_service.py    # REUSE expected trade date
│   │   ├── scan_execution_service.py   # INTEGRATE freshness gate early
│   │   ├── market_data_ingestion/      # NEW package (preferred layout under services)
│   │   │   ├── providers/              # FYERS OHLCV + NSE delivery adapter
│   │   │   ├── pipelines/              # full_load, daily_update
│   │   │   ├── validators/             # completeness, delivery rules
│   │   │   ├── freshness.py            # gate
│   │   │   └── derived.py              # turnover, ADTV-20, weekly resample helpers
│   │   └── ...
│   ├── cli/
│   │   └── market_data_cli.py          # NEW (mirror governance experiment_cli style)
│   ├── routes/
│   │   ├── diagnostics.py / health.py  # EXPOSE freshness/status for operators
│   │   └── analysis.py / scheduler.py  # scan entry already exists
│   └── main.py                         # schedule post-close daily update job
├── alembic/versions/                   # NEW migration only at implement time
├── scripts/import_stocks_master.py     # REUSE universe seed
└── tests/                              # NEW unit/integration tests for this feature
```

**Structure Decision:** Prefer **`backend/app/services/market_data_ingestion/`** + **`backend/app/cli/market_data_cli.py`** over new top-level `data_providers/` packages at repo root. This matches the existing monolith layout and the “reuse, don’t duplicate architecture” rule. Logical modules still map to providers / pipelines / validators / cli.

---

## Complexity Tracking

| Topic | Choice | Simpler alternative rejected because |
|-------|--------|--------------------------------------|
| Separate strategy tables | Dedicated `daily_ohlcv` / `index_ohlcv` / `data_load_log` | Extending ACS only would couple delivery + load log to multi-resolution cache and risk scanner/ACS regressions |
| No dual-write | Write strategy tables only | Dual-write doubles load and consistency surface without clarifying benefit |
| ADTV on-demand | Compute from last 20 daily rows | Pre-materializing ADTV duplicates storage for little gain at 500×20 scale |
| Delivery separate provider | NSE delivery feed adapter + FYERS OHLCV | FYERS path does not currently expose delivery % in-app |

---

# MARKET DATA INGESTION SPECIFICATION PLAN

## 1. Audit Summary

### Already Implemented

| Capability | Evidence | Behavior |
|------------|----------|----------|
| NIFTY 500 universe seed | `backend/app/models/stock.py` `StockMaster`; `backend/scripts/import_stocks_master.py`; `main.py` auto-seed; `ind_nifty500list.csv` | Upserts symbols, company, sector, ISIN, universe=`NIFTY500`, `is_active` |
| Universe query | `backend/app/services/universe_service.py` | Active symbols by universe / all active |
| Daily/intraday OHLCV fetch | `backend/app/services/fyers_service.py` `fetch_ohlcv`, `_fetch_fyers_candles`, `fetch_incremental_ohlcv` | FYERS history + yfinance fallback; retries; symbol normalize |
| Candle persistence | `HistoricalCandle` model; `MarketDataService.upsert_candles`; `market_data.candles` (partitioned); ACS | Multi-resolution OHLCV; **no delivery/turnover columns** |
| Incremental fetch helper | `FyersService.fetch_incremental_ohlcv` | True incremental by last bar date (per symbol, not universe EOD job) |
| Trading calendar | `TradingHoursService` + `backend/data/nse_trading_holidays.json` | Open/close, weekends, holidays |
| Single-flight locks | `backend/app/db/locks.py` `acquire_singleton_lease` | PG advisory locks |
| Scanner entry | `ScanExecutionService.execute_scan`; routes `analysis.py`, `scheduler.py`; `main.py` jobs | Lock → broker check → scan; **no MARKET_DATA_STALE gate** |
| Benchmark helpers | `feat004_regime_overlay.resolve_benchmark_ohlcv` | Fetch/staleness for FEAT-004; not strategy-grade store |
| CLI pattern | `app.governance.experiment_cli` argparse + `python -m` | Reusable ops CLI pattern |
| Settings | `app.config.settings` Pydantic Settings + `.env` | Universe, FYERS, ACS flags |
| Scheduler | APScheduler in `main.py` | Heartbeats, retention; **no EOD strategy daily-update job** |
| Weekly resample (ad hoc) | `routes/analysis.py` pandas `resample("W")` | Not shared strategy contract |
| Logging | `get_logger`, logger_service, observability | Structured logs exist |

### Partially Implemented

| Capability | Gap |
|------------|-----|
| Universe schema | Missing `industry`, `is_nifty500`, `first_seen`, `last_seen` as first-class fields (have sector, created/updated, universe string) |
| Daily OHLCV product | Exists as general candles; not strategy-grade with delivery/turnover/load ownership |
| NIFTY500 index | Consumed via provider/fetch helpers; **no `index_ohlcv` product table** |
| Freshness | Cache health / FEAT-004 staleness; **no hard scanner block** with `MARKET_DATA_STALE` payload |
| Incremental update | Per-symbol helper only; **no universe-wide daily EOD pipeline + log** |
| CLI | Governance CLI only; **no market-data full-load/daily-update/status/verify** |

### Completely Missing

| Capability | Notes |
|------------|-------|
| `daily_ohlcv` strategy table | With delivery_qty, delivery_pct, turnover |
| `index_ohlcv` | symbol=`NIFTY500` |
| `data_load_log` | FULL/DAILY tracking |
| NSE delivery ingestion | `research_service` explicitly sets `delivery_pct: NA` |
| ADTV-20 contract | Not a shared helper for STR-071 |
| Strategy weekly helper | Shared on-demand resample for STR-045 |
| Post-close scheduled daily update | Spec FR-020 |
| Freshness gate integration | At `execute_scan` (and scheduled scan job) |
| Market-data operator CLI | full-load / daily-update / status / verify |
| Packages under `market_data_ingestion` | providers, pipelines, validators |

### Classification matrix (requirements)

| Requirement | Class | Evidence / Gap |
|-------------|-------|----------------|
| Daily OHLCV ≥3y NIFTY500 | PARTIAL | FYERS + candle stores; no full-load pipeline or strategy table |
| Delivery qty/pct | MISSING | No provider; NA in research_service |
| NIFTY500 index store | PARTIAL | Fetch possible via FYERS index symbols; no store |
| Weekly on-demand | PARTIAL | Ad-hoc in analysis route |
| ADTV-20 | MISSING | Formula not productized |
| Sector indices | N/A | Out of scope |
| Universe management | PARTIAL | stocks_master exists; lifecycle fields incomplete |
| Full load pipeline | MISSING | |
| Daily update pipeline | MISSING | |
| Idempotent upserts | PARTIAL | Pattern exists on candles; not on strategy tables |
| Freshness gate | PARTIAL | Helpers only |
| CLI | MISSING | Pattern exists elsewhere |
| Load log | MISSING | |

---

## 2. Current Architecture

```text
[CSV / settings] → StockMaster (universe)
                          ↓
[Scanner / Analysis] → FyersService / ACS → FYERS API / yfinance
                          ↓
              HistoricalCandle / market_data.candles (OHLCV only)
                          ↓
              Indicators / strategies (no delivery, no strategy load log)

Scheduler: market engine heartbeats, paper orders, retention
CLI: governance experiments only
```

**Problems for 10 strategies:** no delivery, no durable index product, no EOD ownership, no hard freshness block, scanners can run on incomplete strategy data while ACS may still serve partial OHLCV.

---

## 3. Existing Components To Reuse

| Component | Path | Reuse mode |
|-----------|------|------------|
| `StockMaster` + import script | `models/stock.py`, `scripts/import_stocks_master.py` | Extend fields or thin adapter as universe |
| `UniverseService` | `services/universe_service.py` | Active NIFTY500 list for loads/scans |
| `FyersService` | `services/fyers_service.py` | Equity + index daily history; retries; normalize |
| `TradingHoursService` | `services/trading_hours_service.py` | Expected last completed trade date |
| `acquire_singleton_lease` | `db/locks.py` | Single-flight FULL/DAILY |
| `ScanExecutionService.execute_scan` | `services/scan_execution_service.py` | Gate immediately after lock acquire / before data work |
| `experiment_cli` pattern | `governance/experiment_cli.py` | argparse + asyncio CLI |
| Settings / logging | `config/settings.py`, `utils/logger` | New settings keys, structured logs |
| Diagnostics/health routes | `routes/diagnostics.py`, `health.py` | Operator status surface |
| `sanitize_ohlcv_row` | `utils/safe_convert.py` | Row sanitization |
| ACS | leave **unchanged** as non-strategy path | Do not dual-write |
| Holidays JSON | `backend/data/nse_trading_holidays.json` | Calendar |

---

## 4. Gaps

1. Strategy-grade schema (`daily_ohlcv`, `index_ohlcv`, `data_load_log`) + models + Alembic (implement phase only).  
2. Universe lifecycle fields (`first_seen`, `last_seen`, `is_nifty500`, optional `industry`).  
3. NSE delivery provider adapter (new; no existing client).  
4. Full-load + daily-update pipelines with checkpointing and bulk upsert.  
5. Derived field rules (delivery_pct, turnover); ADTV-20/weekly helpers on read.  
6. Freshness gate service + `MARKET_DATA_STALE` contract.  
7. Wire gate into scanner start; schedule post-close daily job.  
8. CLI: full-load, daily-update, status, verify.  
9. Tests listed in Phase 10 / §16.  

---

## 5. Proposed Architecture

### Source of truth

- **Strategy scanners / STR-*** strategies:** `daily_ohlcv` + `index_ohlcv` + universe active set + `data_load_log` / freshness API.  
- **ACS / legacy candles:** remain for analysis paths that already use them; **not** written by this feature’s loaders.

### Data flow (dependency graph)

```text
Universe (StockMaster / active NIFTY500)
        ↓
Data Providers (FYERS OHLCV+index; NSE Delivery adapter)
        ↓
Raw Market Data (normalized rows)
        ↓
Normalization (symbol, dates IST/UTC policy, types)
        ↓
Derived Fields (delivery_pct, turnover; ADTV/weekly on read)
        ↓
Database (strategy tables, idempotent upsert)
        ↓
Validation (coverage, index present, delivery coverage report)
        ↓
Freshness Gate
        ↓
Scanner (execute_scan)
```

### Module ownership

| Module | Owns |
|--------|------|
| `providers/fyers_eod.py` | Equity/index daily history via existing FyersService |
| `providers/nse_delivery.py` | Delivery qty / traded qty for session(s) |
| `pipelines/full_load.py` | ≥3y backfill, resumable |
| `pipelines/daily_update.py` | Latest session only |
| `validators/*` | Completeness, delivery math, index presence |
| `freshness.py` | Gate decision object |
| `derived.py` | turnover calc at write; ADTV-20 + weekly resample at read |
| `cli/market_data_cli.py` | Operator entry |
| `scan_execution_service` | Call gate before strategy work |

### Scanner consumption (phased)

1. **v1 gate:** scanners **blocked** unless strategy tables pass freshness.  
2. **v1 data:** strategies that need delivery/index/ADTV/weekly **read strategy tables** (or shared helpers fed by them).  
3. **Non-regression:** ACS path for unrelated deep analysis can continue; strategy scanner path must not ignore the gate.

---

## 6. Database Plan

### Reuse

| Table | Action |
|-------|--------|
| `stocks_master` | **REUSE as universe**; ADD columns if missing: `industry` (nullable), `is_nifty500` (bool), `first_seen`, `last_seen` (date/timestamptz). Map `company_name`→name, keep `is_active`→active. Avoid creating parallel `universe` table unless rename migration preferred (not required). |
| `historical_candles` / `market_data.candles` | **DO NOT use** as strategy SoT; leave intact |
| `backfill_progress` | Taxonomy only — **do not reuse** as market load log |

### Create (implement phase)

#### `daily_ohlcv`

| Column | Type (plan) | Notes |
|--------|-------------|-------|
| trade_date | DATE | session date (IST calendar date) |
| symbol | VARCHAR | canonical platform symbol e.g. `RELIANCE-EQ` |
| open, high, low, close | NUMERIC(18,8) | |
| volume | BIGINT | traded qty for OHLCV |
| delivery_qty | BIGINT NULL | null if unavailable |
| delivery_pct | NUMERIC(9,4) NULL | null if cannot compute |
| turnover | NUMERIC(24,4) NULL | close × volume at insert |
| source | VARCHAR NULL | e.g. FYERS / NSE_DELIVERY merge tag |
| loaded_at | TIMESTAMPTZ | |

**PK:** `(trade_date, symbol)`  
**Indexes:**  
- `(symbol, trade_date DESC)` — history / ADTV window  
- `(trade_date)` — coverage counts for a session  
- partial optional later: active-universe queries join stocks_master

#### `index_ohlcv`

| Column | Type | Notes |
|--------|------|-------|
| trade_date | DATE | |
| symbol | VARCHAR | `NIFTY500` canonical |
| open, high, low, close | NUMERIC | |
| volume | BIGINT NULL | index volume if provider supplies |
| source | VARCHAR NULL | |
| loaded_at | TIMESTAMPTZ | |

**PK:** `(trade_date, symbol)`  
**Index:** `(symbol, trade_date DESC)`

#### `data_load_log`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID/BIGSERIAL PK | |
| load_type | VARCHAR | `FULL` \| `DAILY` |
| trigger_source | VARCHAR | `CLI` \| `SCHEDULE` |
| status | VARCHAR | `RUNNING` \| `SUCCESS` \| `PARTIAL` \| `FAILED` \| `SKIPPED_LOCKED` |
| data_date | DATE NULL | target session for DAILY; null or range end for FULL |
| range_from / range_to | DATE NULL | FULL window |
| started_at / ended_at | TIMESTAMPTZ | |
| duration_ms | INT | |
| rows_fetched / inserted / updated / failed / skipped | INT | |
| provider | VARCHAR | |
| error_summary | TEXT | |
| details_json | JSONB | failed symbols sample, delivery coverage % |

**Indexes:** `(started_at DESC)`, `(load_type, data_date DESC)`, `(status)`

### Constraints & rules

- Upserts: `ON CONFLICT (trade_date, symbol) DO UPDATE` for OHLCV + delivery fields.  
- No FK from daily_ohlcv→stocks_master required (symbols may persist after delist); soft integrity via active universe for loads.  
- Delivery: never invent; null on missing/zero-denominator.

### Query patterns to optimize

| Query | Plan |
|-------|------|
| Latest trade date in store | `MAX(trade_date) FROM daily_ohlcv` (+ optional universe filter via join) |
| Session coverage | `COUNT(DISTINCT symbol) WHERE trade_date = :d` vs active universe count |
| Index present | `EXISTS index_ohlcv WHERE symbol='NIFTY500' AND trade_date=:d` |
| Symbol history | `WHERE symbol=:s ORDER BY trade_date` using `(symbol, trade_date DESC)` |
| ADTV-20 | last 20 rows per symbol — index supports |

---

## 7. Provider Plan

### A. Equity daily OHLCV — **FYERS** (existing)

| Item | Detail |
|------|--------|
| Client | `FyersService` history API (`client.history`) already used |
| Auth | Existing FYERS app id + DB access token (`token_service`) |
| Symbol form | `_normalize_symbol` → `NSE:RELIANCE-EQ` style |
| Full load | Range chunks (FYERS history limits) per symbol; reuse patterns in `_fetch_fyers_candles` / multi-range |
| Daily | Single session or `last_stored+1 → today` window; prefer **latest completed session only** for DAILY pipeline |
| Rate limits | Existing `_FYERS_HISTORY_CONCURRENCY`, retries in `_request_history_with_retries` |
| Fallback | yfinance only if policy allows for OHLCV; **must not** fabricate delivery |
| Caching | Do not rely on ACS L1 for strategy load ownership; optional short in-process batch cache during a run |

### B. NIFTY500 index OHLCV — **FYERS index history**

| Item | Detail |
|------|--------|
| Symbol | Platform canonical store key: `NIFTY500`. Provider symbol: resolve via settings (e.g. `NSE:NIFTY500-INDEX` pattern consistent with `NSE:NIFTYIT-INDEX` in `sector_rs_service.py`) — **confirm against live FYERS instrument list at implement** without inventing undocumented endpoints |
| Method | Same `history` API as equities |
| Fallback | Optional yfinance `^CRSLDX` only if already used in research docs; document chosen mapping in settings |

### C. NSE Delivery — **new adapter (required)**

| Item | Detail |
|------|--------|
| Current state | **No client**; delivery not on FYERS path used by app |
| Approach | Dedicated `NseDeliveryProvider` using **official NSE public market reports** (security-wise delivery / bhav-style files) via HTTP download + parse (httpx/aiohttp + csv/zip as published). Exact URL templates and file formats **must be verified against live NSE docs/files at implement time** — plan does not invent stable private APIs |
| Auth | Typically none for public reports; respect NSE rate/ToS; set User-Agent; throttle |
| Join key | Prefer ISIN from `stocks_master`, fallback symbol map |
| Fields | `delivery_qty`, `traded_qty` (or equivalent columns from report) |
| Compute | `delivery_pct = delivery_qty / traded_qty * 100` only if `traded_qty > 0` and delivery_qty present |
| Failure | Leave delivery null; log coverage; do not fail entire OHLCV load |

### D. Universe

| Item | Detail |
|------|--------|
| Source | `ind_nifty500list.csv` + `import_stocks_master` / `UniverseService` |
| Daily/full | Refresh active NIFTY500 set before load; update `last_seen` for seen members; deactivate removed (soft) |

### Provider batching

- Equity: concurrent symbol workers with semaphore (reuse FYERS concurrency knobs).  
- Delivery: one file per session date (preferred) then in-memory join to symbols — **far cheaper** than per-symbol HTTP.  
- Index: 1 series per run.

---

## 8. Full Load Plan

**Goal:** ≥3 calendar years of daily equity + index into strategy tables; delivery where available.

### Flow

1. Acquire single-flight lock `market_data:full_load` (fail → `SKIPPED_LOCKED`).  
2. Insert `data_load_log` RUNNING (`FULL`, CLI).  
3. Ensure universe seeded / active NIFTY500 list loaded.  
4. Compute `range_from = today_ist - 3y` (trading calendar not required for start bound).  
5. Load/upsert index history for range.  
6. For each active symbol (checkpoint by symbol):  
   - Fetch daily OHLCV for range (chunked).  
   - Merge delivery by trade_date if delivery files available for covered years (may be slower; allow delivery backfill as second pass).  
   - Compute turnover, delivery_pct.  
   - Bulk upsert batches (e.g. 500–2000 rows).  
7. Validate sample: row counts, index coverage, delivery coverage %.  
8. Close log SUCCESS / PARTIAL / FAILED.  
9. Release lock.

### Properties

| Property | Mechanism |
|----------|-----------|
| Resumable | Skip symbols with `MAX(trade_date) >= range_to` and sufficient history; or resume list from log details_json |
| Idempotent | PK upsert |
| Retry | Per-symbol provider retries; failed symbols listed for re-run |
| Observable | Counters + structured logs |
| Failure-tolerant | One symbol failure does not abort entire job (PARTIAL) |

### Concurrency

- Symbol workers: low (e.g. 3–8) to protect FYERS + DB pool.  
- DB: executemany / multi-row INSERT … ON CONFLICT.

---

## 9. Daily Update Plan

**Most important pipeline.**

### Flow

```text
1. Acquire lock market_data:daily_update (or shared market_data:load single-flight across FULL+DAILY)
2. expected_date = last completed NSE cash session (TradingHoursService + holidays)
3. latest_stored_equity = MAX(trade_date) on daily_ohlcv for active universe (or global max)
4. latest_stored_index = MAX for NIFTY500
5. If expected_date already complete (≥99% symbols + index) → optional no-op SUCCESS with rows_skipped
6. Else target_dates = missing sessions from (latest_stored+1) … expected_date
   (DAILY primary path: prefer only expected_date; if multi-day gap, process each day ascending)
7. Refresh universe active set
8. For each target_date D:
   a. Fetch equity OHLCV for D (or small range) for all active symbols
   b. Fetch delivery file for D; join
   c. Fetch index bar for D
   d. Derive delivery_pct, turnover
   e. Upsert daily_ohlcv + index_ohlcv
9. Validate completeness for expected_date
10. Log SUCCESS if coverage≥99% and index present; PARTIAL if below; FAILED on hard errors
11. Release lock
```

### Idempotency

Re-running for same `D` updates same PK rows; no duplicates.

### Schedule

- APScheduler job post close (e.g. **16:15–18:00 IST** configurable) Mon–Fri excluding holidays.  
- Exact minute chosen so FYERS EOD + NSE delivery file are usually available; retry/backoff if file not published yet (mark PARTIAL/FAILED with remediation “retry later”).

---

## 10. Freshness Gate Plan

### Rules (global)

| Check | Fail → |
|-------|--------|
| DB reachable | `MARKET_DATA_STALE` reason=db_unavailable |
| Active NIFTY500 universe non-empty | reason=universe_empty |
| `expected_date` = last completed session | calendar logic |
| Equity coverage for `expected_date` ≥ **99%** of active symbols | reason=equity_incomplete |
| Index row exists for `NIFTY500` on `expected_date` | reason=index_missing |
| Optional: no critical multi-day gap flag from last SUCCESSFUL load | reason=load_failed / gap |

Delivery **not** in global gate (clarified).

### STR-041 (and delivery-dependent)

- Per symbol: if `delivery_qty`/`delivery_pct` null for required session → skip/block **that strategy evaluation** with `delivery_missing`.

### Failure payload (`MARKET_DATA_STALE`)

See [contracts/freshness_gate.md](./contracts/freshness_gate.md): expected_date, latest_stored_date, missing_symbols (sample), index_missing, coverage_ratio, remediation.

### Operator visibility

- Structured log on block.  
- Diagnostics/health/status endpoint field `market_data_freshness`.

---

## 11. Scanner Integration Plan

### Entry points (evidence)

| Entry | Path |
|-------|------|
| UI/API scan | `routes/analysis.py` → `ScanExecutionService.execute_scan` |
| Scheduler trigger | `routes/scheduler.py` → `execute_scan` |
| Automated job | `main.py` `automated_screening_job` (may be disabled) |

### Required order

```text
[Optional: scheduled daily-update already ran post-close]
        ↓
execute_scan acquires scan lock
        ↓
FRESHNESS GATE (strategy tables)  ← NEW, fail-closed
        ↓
existing broker/token checks
        ↓
scan / strategies
```

**Do not** start strategy evaluation if gate fails.  
**Do not** silently fall back to ACS to bypass gate for strategy scanners.

### Data read path (strategies)

- Prefer loading history from `daily_ohlcv` / `index_ohlcv` for strategy engines that need delivery/index/ADTV/weekly.  
- Incremental migration allowed: gate first, then switch readers strategy-by-strategy without rewriting entire orchestrator in one PR if tasks split — but gate must not pass on ACS-only data.

---

## 12. CLI Plan

Mirror `python -m app.governance.experiment_cli` style:

```text
python -m app.cli.market_data_cli full-load [--years 3] [--symbols ...]
python -m app.cli.market_data_cli daily-update [--date YYYY-MM-DD]
python -m app.cli.market_data_cli status
python -m app.cli.market_data_cli verify [--date YYYY-MM-DD]
```

| Command | Behavior |
|---------|----------|
| `full-load` | Pipeline A; writes load log |
| `daily-update` | Pipeline B; default expected_date |
| `status` | Latest load runs, expected_date, coverage, index flag, lock state |
| `verify` | Run freshness checks + print MARKET_DATA_STALE or OK |

Exit codes: 0 success; 2 stale/verify fail; 3 locked; 1 error.

Contract: [contracts/cli.md](./contracts/cli.md).

---

## 13. Validation Plan

| Layer | Checks |
|-------|--------|
| Row | OHLC finite; high≥low; volume≥0; dates valid |
| Delivery | if traded_qty=0 or missing → delivery_pct null; never invent |
| Session | coverage %; missing symbol list (cap sample) |
| Index | NIFTY500 present for target dates |
| Load | status alignment with coverage |
| Freshness | unit tests for holiday/weekend expected_date |
| Idempotency | double daily-update row count stable |

---

## 14. Error Handling & Recovery

| Scenario | Behavior |
|----------|----------|
| FYERS rate limit / network | Retry with backoff; symbol PARTIAL |
| Auth expired | Fail run FAILED; remediation re-auth |
| NSE delivery file not yet published | OHLCV still load; delivery null; PARTIAL if many missing; daily job retry next schedule |
| Zero traded qty | delivery_pct null |
| DB failure mid-batch | transaction rollback for batch; log; FAILED/PARTIAL |
| Concurrent load | second → SKIPPED_LOCKED |
| Full load interrupt | re-run resumes by symbol checkpoint |
| Scanner stale | block + status + logs; operator runs `daily-update` or waits for schedule |

---

## 15. Performance Plan

| Lever | Plan |
|-------|------|
| Incremental only | DAILY fetches latest session(s), not 3y |
| Delivery file-per-day | One download, join all symbols |
| Bulk upsert | Multi-row INSERT ON CONFLICT |
| Concurrency bounds | Semaphores; respect DB pool (existing pool_size) |
| Memory | Stream/batch; avoid loading all symbols full history at once in full load |
| ADTV / weekly | On-demand; no extra tables |
| Polars | **Not required for v1** (pandas already in stack); optional later for bulk transforms if profiling warrants |
| Caching | In-run only; Redis not required for EOD tables |
| Scanner startup | Gate = cheap SQL aggregates; not full history scan |

Target: DAILY ≤15 minutes (SC-002).

---

## 16. Testing Plan

| # | Test | Type |
|---|------|------|
| 1 | Full historical load happy path (fixture/mock providers) | integration |
| 2 | Daily update inserts latest session | integration |
| 3 | Duplicate daily update → no duplicate PKs | integration |
| 4 | Missing stock in provider → PARTIAL + listed | unit/integration |
| 5 | Missing trading day gap fill | unit |
| 6 | Missing delivery → nulls; OHLCV kept; STR-041 skip | unit |
| 7 | Zero traded qty → delivery_pct null | unit |
| 8 | Missing NIFTY500 index → gate fail | unit |
| 9 | DB failure → FAILED log | integration |
| 10 | API failure retries then PARTIAL/FAILED | unit |
| 11 | Retry success after transient error | unit |
| 12 | Partial failure status semantics | unit |
| 13 | Freshness holiday/weekend expected_date | unit |
| 14 | execute_scan blocked when stale | integration |
| 15 | execute_scan allowed after successful update | integration |
| + | Single-flight second CLI SKIPPED_LOCKED | unit |
| + | Turnover = close×volume | unit |

Use mocks for FYERS/NSE; optional PG tests in `tests_pg` style if available.

---

## 17. Migration Plan

**Implement phase only (not this command):**

1. Alembic revision: create `daily_ohlcv`, `index_ohlcv`, `data_load_log`.  
2. Alembic: alter `stocks_master` add lifecycle columns (nullable defaults, backfill `is_nifty500` from universe=`NIFTY500`).  
3. Deploy migration before enabling schedule/gate fail-closed.  
4. Feature flag optional: `STRATEGY_MARKET_DATA_GATE_ENABLED` (default on in prod after first successful full load) to avoid blocking scanners pre-backfill.  
5. Run `full-load` offline/ops window.  
6. Enable schedule + gate.  
7. No data migration required from ACS unless ops chooses optional one-time OHLCV copy (optional optimization; not required if full-load from provider).

---

## 18. Implementation Sequence

Safest brownfield order:

1. ~~Audit~~ (done)  
2. Models + Alembic for strategy tables + universe columns  
3. Repository/upsert helpers + load log  
4. FYERS EOD adapter wrapping existing service (equity + index)  
5. NSE delivery adapter + join  
6. Derived field helpers (delivery_pct, turnover; ADTV/weekly read helpers)  
7. Full-load pipeline + CLI `full-load`  
8. Daily-update pipeline + CLI `daily-update`  
9. Validators + CLI `verify` / `status`  
10. Freshness gate service  
11. Wire `execute_scan` + diagnostics status  
12. APScheduler post-close job + single-flight  
13. Tests (unit → integration)  
14. Performance dry-run on sample universe then full  
15. Feature-flag flip gate fail-closed after first SUCCESS full/daily  

---

## 19. Risks

| Risk | Mitigation |
|------|------------|
| NSE delivery file format/URL changes | Isolate adapter; null-safe; observability on coverage drop |
| FYERS rate limits on full load | Low concurrency, checkpoint, multi-day ops window |
| Gate blocks all scanners before first full load | Feature flag / require successful load once |
| Symbol map ISIN mismatch for delivery | Prefer ISIN; report unmatched % |
| Index symbol wrong on FYERS | Settings-driven mapping + verify command |
| Dual data paths confuse strategy vs ACS | Document SoT; gate enforces strategy tables |
| 3y full load long runtime | Resume; do not block daily path |
| Holiday calendar stale | Annual update process for JSON |

---

## 20. Acceptance Criteria

Aligned with spec SC-001–SC-010 + sprint goals:

- [ ] Full load populates ≥3y (or listing life) for active NIFTY500 + index  
- [ ] Daily update ≤15m, idempotent, single-flight  
- [ ] delivery_pct formula correct; null on invalid; no invented values  
- [ ] turnover = close × volume at write  
- [ ] ADTV-20 and weekly available on-demand without permanent weekly table  
- [ ] CLI: full-load, daily-update, status, verify  
- [ ] data_load_log records every run  
- [ ] Freshness gate blocks scanner with `MARKET_DATA_STALE` payload when equity/index incomplete  
- [ ] STR-041 hard-fails without delivery; global gate does not require delivery  
- [ ] Scheduled post-close daily update creates load log without CLI  
- [ ] ACS/legacy paths not dual-written; existing non-strategy consumers unregressed  

---

## 21. Files Expected To Change

| File | Change type |
|------|-------------|
| `backend/app/models/stock.py` | Add universe lifecycle columns |
| `backend/app/models/__init__.py` | Export new models |
| `backend/app/services/universe_service.py` | first_seen/last_seen/is_nifty500 helpers |
| `backend/app/services/scan_execution_service.py` | Call freshness gate early |
| `backend/app/main.py` | Register post-close daily-update job |
| `backend/app/config/settings.py` | Gate flag, schedule time, index provider symbol, concurrency |
| `backend/app/routes/diagnostics.py` and/or `health.py` | Freshness/status fields |
| `backend/scripts/import_stocks_master.py` | Optional set is_nifty500 / first_seen |
| `backend/alembic/versions/*` | New revision (at implement) |

Possibly touch strategy/scanner readers that currently pull only ACS if tasks include read-path cutover (orchestrator/screener) — **prefer minimal** first: gate + helpers, then targeted readers.

---

## 22. Files Expected To Be Created

| Path | Purpose |
|------|---------|
| `backend/app/models/strategy_market_data.py` | ORM: daily_ohlcv, index_ohlcv, data_load_log |
| `backend/app/services/market_data_ingestion/__init__.py` | Package |
| `backend/app/services/market_data_ingestion/providers/fyers_eod.py` | Equity/index EOD |
| `backend/app/services/market_data_ingestion/providers/nse_delivery.py` | Delivery |
| `backend/app/services/market_data_ingestion/pipelines/full_load.py` | Pipeline A |
| `backend/app/services/market_data_ingestion/pipelines/daily_update.py` | Pipeline B |
| `backend/app/services/market_data_ingestion/validators/completeness.py` | Coverage |
| `backend/app/services/market_data_ingestion/validators/delivery_rules.py` | Null-safe pct |
| `backend/app/services/market_data_ingestion/freshness.py` | Gate |
| `backend/app/services/market_data_ingestion/derived.py` | Turnover / ADTV / weekly |
| `backend/app/services/market_data_ingestion/repository.py` | Bulk upsert + queries |
| `backend/app/cli/__init__.py` | CLI package |
| `backend/app/cli/market_data_cli.py` | Operator CLI |
| `backend/alembic/versions/YYYYMMDD_strategy_market_data.py` | Migration |
| `backend/tests/.../test_market_data_*.py` | Unit/integration tests |

**Do not create** top-level repo `data_providers/` unless later refactor; keep under `backend/app/…`.

---

## Phase outputs

| Artifact | Path |
|----------|------|
| Research | [research.md](./research.md) |
| Data model | [data-model.md](./data-model.md) |
| CLI contract | [contracts/cli.md](./contracts/cli.md) |
| Freshness contract | [contracts/freshness_gate.md](./contracts/freshness_gate.md) |
| Quickstart | [quickstart.md](./quickstart.md) |

---

**STOP:** This document is the implementation plan only. **No code, migrations, packages, or schema changes have been applied.** Proceed with `/speckit-tasks` after approval, then implement.
