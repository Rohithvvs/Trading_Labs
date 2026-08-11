# Feature Specification: Market Data Ingestion & Daily Update System

**Feature Branch**: `033-market-data-ingestion`  
**Created**: 2026-08-08  
**Status**: Clarified (session 2026-08-08)  
**Input**: User description: Market Data Ingestion & Daily Update System for NIFTY 500 Stock Scanner (10 strategies) — full historical load, daily incremental update, delivery %, NIFTY 500 index bars, ADTV support, and pre-scanner freshness gate.

**Workspace audit reference**: See conversation Audit Summary (2026-08-08). Existing platform already provides NIFTY 500 universe seeding, multi-tier OHLCV candle storage/fetch (FYERS + yfinance fallback), and scanner scheduling, but does **not** provide strategy-grade daily equity bars with NSE delivery statistics, dedicated index OHLCV persistence for `NIFTY500`, load-run tracking, operator full-load/daily-update commands, or a hard pre-scanner data-freshness gate.

## Clarifications

### Session 2026-08-08

- Q: Where should strategy-grade daily market data live relative to existing candle stores (ACS / historical_candles / market_data.candles)? → A: Dedicated strategy-grade daily dataset is source of truth for scanners/strategies; existing ACS/intraday paths remain for current consumers (optional later convergence).
- Q: How strict is NSE delivery % for acceptance and scanner gating? → A: Soft global gate (OHLCV + index); hard for STR-041 and other delivery-dependent strategies when delivery is missing.
- Q: How should the daily incremental update be triggered in production? → A: Built-in post-close schedule (exchange-calendar aware) plus CLI for catch-up/recovery.
- Q: If a daily update is already running, what should a second CLI or schedule trigger do? → A: Single-flight — reject/skip second run with clear already-running outcome; only one FULL or DAILY market-data load mutates data at a time.
- Q: When the pre-scanner freshness gate blocks a run, what must “operator-visible alert” include? → A: Structured logs plus visible status on existing operator-facing diagnostics/health/scheduler surface; push email not required for v1.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Daily Incremental Market Update (Priority: P1)

As a trading-system operator, I run a single daily update after the cash market session so that every active NIFTY 500 stock and the NIFTY 500 index receive only the latest completed trading day’s bars (and related delivery fields where applicable), without reloading multi-year history.

**Why this priority**: Daily freshness is the operational bottleneck. Scanners and strategies are useless or misleading without the latest session. Incremental updates must be fast, idempotent, and safe to re-run.

**Independent Test**: On a database that already has multi-year history, run the daily update twice for the same session; both runs succeed, no duplicate bars exist, and the latest session is present for the full active universe plus index.

**Acceptance Scenarios**:

1. **Given** the latest NSE cash trading day is complete and history already exists, **When** the operator runs the daily update **or** the scheduled post-close job runs, **Then** only that day’s equity and index bars are fetched and upserted for the active NIFTY 500 universe.
2. **Given** the daily update already succeeded for session date D, **When** the operator runs the daily update again for D, **Then** the operation completes successfully without creating duplicates and without changing load integrity (idempotent).
3. **Given** a subset of symbols fails during fetch, **When** the daily update finishes, **Then** successful symbols are persisted, failures are recorded in the load log, and the overall run status reflects partial failure (not silent success).
4. **Given** a normal trading day after cash market close, **When** no operator has run the CLI yet, **Then** the built-in scheduled daily update still attempts to load session D so scanners can later pass the freshness gate.

---

### User Story 2 - Pre-Scanner Data Freshness Gate (Priority: P1)

As a scanner operator, I need every strategy scan to be blocked when the latest completed trading day is missing for the required universe or index, so that scanners never run on stale data.

**Why this priority**: Guaranteeing “freshest data before scanners start” is an explicit product goal and prevents false signals from incomplete history.

**Independent Test**: Remove or withhold the latest session bars for a material portion of the universe; attempt to start a scanner run; the run is blocked with a clear alert and does not produce strategy signals.

**Acceptance Scenarios**:

1. **Given** latest trading day D is present for ≥99% of active NIFTY 500 symbols and for the NIFTY 500 index, **When** a scanner run starts, **Then** the freshness check passes and the scanner proceeds.
2. **Given** latest trading day D is missing for the index or for more than the allowed shortfall of equity symbols, **When** a scanner run starts, **Then** the scanner is blocked, structured logs record the freshness failure, operator-facing status surfaces the fail reason, and no strategy evaluations execute.
3. **Given** today is an NSE holiday (no cash session), **When** freshness is evaluated, **Then** the check uses the previous completed trading day and does not require a bar for the holiday date.
4. **Given** OHLCV + index freshness for session D passes but delivery fields are missing for some symbols, **When** a general scanner run starts, **Then** the run proceeds; **When** STR-041 (or another delivery-dependent strategy) evaluates a symbol without delivery for D, **Then** that strategy skips or blocks only that evaluation with an explicit delivery-missing reason (it does not fail the global gate).

---

### User Story 3 - Initial Full Historical Load (Priority: P2)

As a system administrator standing up a new environment (or rebuilding history), I run a full load that stores at least three years of daily equity OHLCV for the current NIFTY 500 membership, plus NIFTY 500 index daily OHLCV, with delivery percentage and turnover computed at load time where source data exists.

**Why this priority**: Full load is required once (or rarely) but is foundational for all ten strategies. Daily update depends on an existing baseline.

**Independent Test**: Against an empty or truncated history store, run full load; verify every active NIFTY 500 symbol has ≥3 years of daily bars (or full available life if listed more recently), index history is present, and delivery_pct/turnover are populated when delivery quantities are available.

**Acceptance Scenarios**:

1. **Given** an empty history store and a current NIFTY 500 membership list, **When** full load completes successfully, **Then** daily equity bars cover at least three calendar years for each active constituent that has been listed that long.
2. **Given** source data includes delivery quantity and traded quantity, **When** a bar is inserted, **Then** delivery percentage equals delivery quantity ÷ traded quantity × 100 and turnover equals close × volume (or provider turnover when that is the authoritative source definition documented at plan time).
3. **Given** full load is interrupted mid-run, **When** the operator restarts full load, **Then** already-loaded symbols/dates are skipped or safely upserted and the job can complete without requiring a manual wipe.

---

### User Story 4 - Operator Load Commands & Observability (Priority: P2)

As an operator, I invoke explicit full-load and daily-update commands and inspect load outcomes (counts, duration, failures, last successful session) so that operations are repeatable and auditable.

**Why this priority**: Without operator-facing commands and load tracking, production support cannot verify data readiness or diagnose gaps.

**Independent Test**: Run full-load and daily-update commands; confirm each run writes a load-tracking record with status, scope, row counts, and errors; confirm operators can list recent load runs.

**Acceptance Scenarios**:

1. **Given** valid configuration and credentials, **When** the operator runs the full-load command, **Then** a load-run record is created with type FULL, start/end time, status, and summary metrics.
2. **Given** valid configuration, **When** the operator runs the daily-update command **or** the scheduled job runs, **Then** a load-run record is created with type DAILY (or equivalent), target trade date, trigger source (CLI vs schedule), and success/partial/fail status.
3. **Given** a failed load run, **When** the operator inspects load history, **Then** they can see which symbols/steps failed and the error reason.

---

### User Story 5 - Strategy-Ready Derived Views (Priority: P3)

As a strategy author (STR-041, STR-005/021/025, STR-045, STR-071), I consume delivery %, index OHLCV, on-the-fly weekly bars, and 20-day average daily traded value without maintaining separate permanent weekly storage or sector index feeds.

**Why this priority**: Completes data contracts for the ten-strategy scanner; can ship after core load + freshness.

**Independent Test**: For a sample symbol with known history, compute weekly bars from daily series, ADTV-20 from close×volume, and read delivery % and NIFTY500 index series; confirm values match formulas and no weekly table is required.

**Acceptance Scenarios**:

1. **Given** daily equity bars exist, **When** a strategy requests weekly OHLCV, **Then** weekly bars are produced by resampling daily data on demand (not stored as permanent weekly history).
2. **Given** at least 20 trading days of close and volume, **When** ADTV-20 is requested, **Then** the value equals the average of (close × volume) over the last 20 sessions.
3. **Given** strategies STR-005/021/025 need a benchmark, **When** they request NIFTY500 index series, **Then** daily index OHLCV is available under a stable index identity (`NIFTY500`).

---

### Edge Cases

- NSE holiday or special trading session: latest required trade date must follow the exchange calendar, not the civil calendar.
- Newly listed or recently added NIFTY 500 members: full load stores available history only; daily update adds them once active in universe.
- Symbol renamed/delisted mid-membership: universe active flag and last_seen prevent scanners from requiring bars for inactive names.
- Missing delivery statistics for a session: equity OHLCV still loads; delivery fields may be null; load log records delivery coverage shortfall. Global freshness gate requires OHLCV + index only. STR-041 and other delivery-dependent strategies MUST treat missing delivery as a hard per-strategy data failure (skip/block that strategy evaluation with a clear reason), not a silent null.
- Provider outage or rate limits during daily update: partial progress preserved; clear failure status; scanners remain blocked until freshness is satisfied.
- Duplicate operator invocations / concurrent daily updates: only one market-data FULL or DAILY load may mutate data at a time (single-flight). A second CLI or schedule trigger MUST be rejected or skipped with an explicit already-running outcome and MUST NOT start a second writer.
- Corporate actions / adjusted vs unadjusted prices: use the same adjustment policy as the primary market provider already used by the platform unless explicitly overridden at plan time.
- Empty universe (membership not seeded): full load and daily update fail fast with a clear error rather than loading zero symbols successfully.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST maintain an active equity universe representing the current NIFTY 500 membership, including identity attributes needed for operations (symbol, ISIN, name, sector/industry, active lifecycle timestamps).
- **FR-002**: System MUST store daily equity market bars for each active universe symbol with open, high, low, close, volume, and optional delivery quantity, delivery percentage, and turnover, uniquely keyed by trade date and symbol.
- **FR-003**: System MUST store daily NIFTY 500 index OHLCV under a stable index identity (`NIFTY500`), uniquely keyed by trade date and symbol.
- **FR-004**: System MUST support an initial/full historical load of at least three years of daily data for the current NIFTY 500 equity universe and for the NIFTY 500 index.
- **FR-005**: During insert/upsert of equity bars, system MUST compute `delivery_pct = delivery_qty / traded_qty × 100` when both quantities are available, and MUST compute turnover as close × volume when not supplied by the source.
- **FR-019**: Global pre-scanner freshness (FR-009) MUST require latest-session equity OHLCV coverage and index presence only; it MUST NOT fail solely because delivery fields are null. Delivery-dependent strategies (at minimum STR-041) MUST NOT produce signals for a symbol/session when delivery data required for that strategy is missing; they MUST record an explicit delivery-missing outcome.
- **FR-006**: System MUST support a daily incremental update that fetches only the latest completed trading day’s data for active equities and the index, then upserts it idempotently.
- **FR-007**: Daily update MUST be safe to re-run for the same trade date without creating duplicate rows or incorrect aggregates.
- **FR-008**: System MUST record each load attempt (full or daily) in a load-tracking log with type, target date/range, status, timing, counts, and error summary.
- **FR-009**: Before any strategy scanner run starts, system MUST verify that the latest completed trading day’s equity and index data is present **in the strategy-grade daily dataset**; if not, system MUST block the run and raise an operator-visible alert consisting of (1) structured failure logs and (2) a visible freshness/load status on an existing operator-facing diagnostics, health, or scheduler surface. Push email/SMTP is not required for this feature’s acceptance.
- **FR-010**: Operators MUST be able to trigger full load and daily update via explicit commands (CLI or equivalent operator interface).
- **FR-020**: System MUST run the daily incremental update automatically after cash market close on NSE trading days (exchange-calendar aware), in addition to the operator CLI. Full load remains operator-initiated (not on the daily schedule). Schedule timing MUST allow provider EOD data to be available; exact clock time is a planning detail.
- **FR-021**: System MUST enforce single-flight for market-data FULL and DAILY loads: while one such load is in progress, additional triggers MUST NOT open a concurrent mutating load; they MUST return or log an already-running result.
- **FR-017**: Strategy scanners and the ten strategies MUST read daily equity OHLCV, delivery fields, index OHLCV, and load/freshness status from the **strategy-grade daily dataset** (not from ACS/intraday candle caches). Existing Authoritative Candle Store and related candle tables remain for current non-strategy consumers and MUST NOT be required as the write target of this feature’s full/daily loads.
- **FR-018**: Full load and daily update MUST write strategy-grade daily equity bars, index bars, and load-log records. They MUST NOT be required to dual-write into ACS / `historical_candles` / `market_data.candles` in this feature (optional later convergence is out of scope unless planned separately).
- **FR-011**: Weekly OHLCV MUST NOT be stored as permanent history; strategies that need weekly bars MUST obtain them by resampling daily bars on demand.
- **FR-012**: System MUST support computation of 20-session average daily traded value (ADTV-20) from daily close and volume for strategy consumers (STR-071); permanent storage of ADTV is not required if it can be derived reliably.
- **FR-013**: Sector index data is out of scope and MUST NOT be required for acceptance of this feature.
- **FR-014**: Load processes MUST log successes, partial failures, and hard failures with enough detail to identify failed symbols and retry safely.
- **FR-015**: Universe membership changes (additions/removals) MUST be reflected so that daily updates target only active NIFTY 500 symbols, while historical bars for formerly active symbols may remain for audit.
- **FR-016**: Freshness evaluation MUST respect the NSE trading calendar (holidays and weekends), not raw calendar days.

### Key Entities

- **Universe Member**: A stock in the NIFTY 500 membership set — symbol (unique), ISIN, name, sector, industry, NIFTY 500 flag, first_seen, last_seen, active.
- **Daily Equity Bar**: One trading session of OHLCV for a stock — trade_date, symbol, open, high, low, close, volume, delivery_qty, delivery_pct, turnover.
- **Index Bar**: One trading session of OHLCV for a benchmark index — trade_date, symbol (`NIFTY500`), open, high, low, close, volume (if available).
- **Data Load Run**: An operational record of a full or daily ingestion — run id, load type, target date/range, status, started/finished timestamps, rows written, failure details.
- **Freshness Check Result**: Outcome of the pre-scanner gate — expected trade date, equity coverage ratio, index present flag, pass/fail, reason.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a successful full load, 100% of active NIFTY 500 symbols that have ≥3 years of market history retain at least 3 years of daily bars; newer listings retain all available sessions since listing.
- **SC-002**: A daily update for a completed session finishes within 15 minutes for the full NIFTY 500 universe under normal provider conditions, and can be re-run with zero duplicate keys.
- **SC-009**: On a normal trading day, if the operator does not run the CLI, the scheduled post-close daily update still produces a load-run record for that session (success, partial, or fail) without manual intervention.
- **SC-010**: When a load is already running, a second concurrent trigger results in zero additional mutating writers and an explicit already-running outcome in 100% of observed attempts.
- **SC-003**: When latest-session equity coverage is below 99% of active symbols **or** the index bar for that session is missing, 100% of attempted scanner starts are blocked with an explicit freshness failure visible in structured logs and on an operator-facing status surface.
- **SC-004**: For sample sessions with known delivery quantities, computed delivery percentage matches delivery_qty / traded_qty × 100 within 0.01 percentage points.
- **SC-008**: When OHLCV + index freshness passes but delivery is missing for a symbol, general scanner start is not blocked; STR-041 produces zero signals for that symbol and surfaces a delivery-missing reason in 100% of such cases.
- **SC-005**: Operators can complete both full-load and daily-update workflows using documented commands without manual database edits, and each run leaves an inspectable load-history record.
- **SC-006**: Strategies that need weekly bars or ADTV-20 can obtain correct values from daily history alone (weekly not permanently stored; ADTV-20 uses last 20 sessions of close × volume).
- **SC-007**: On an NSE holiday, freshness checks pass against the prior completed session without requiring same-day bars.

---

## Assumptions

- Primary equity OHLCV **source** remains the platform’s existing market data provider path (currently FYERS with documented fallback behavior). The **storage target** for this feature is a dedicated strategy-grade daily dataset (equity bars with delivery fields, index bars, load log), which is the source of truth for scanners and strategies.
- Existing ACS / `historical_candles` / `market_data.candles` paths stay available for current consumers; this feature does not require dual-write into those stores. Later convergence is optional and out of scope unless scheduled as a separate change.
- NSE delivery statistics may come from a separate official or licensed feed when the primary OHLCV provider does not supply delivery quantity; absence of delivery for a bar does not block OHLCV load or the global freshness gate, but is recorded for coverage metrics and hard-fails STR-041 (and any other declared delivery-dependent strategy) for affected symbols.
- Delivery is in scope for this feature (not deferred to a later phase); loads MUST attempt to populate delivery fields and report coverage.
- “Latest trading day” means the most recent completed NSE cash equity session according to the exchange calendar used by the platform.
- Minimum history is three calendar years (~750 trading sessions) unless a constituent’s listing age is shorter.
- Turnover for ADTV is defined as close × volume per session unless provider turnover is proven more accurate during planning; the formula will be fixed in the plan and applied consistently.
- Sector indices remain out of scope (consistent with FEAT-007 research notes that sector work is separate).
- Existing `stocks_master` / universe seeding and scanner orchestration will be reused where possible; this feature adds strategy-grade daily dataset, load tracking, operator commands, and the hard freshness gate rather than rebuilding the entire trading platform.
- Single-tenant / admin-operated environment in the current phase (aligned with Phase 0 governance notes): all authenticated operators may run load commands until role split is required.
- Reasonable default freshness threshold: ≥99% of active equity symbols plus mandatory index bar for the expected session; delivery completeness is reported and does not block general scanners. STR-041 is a declared hard delivery dependency at the strategy level.

---

## Scope Boundaries

### In Scope

- NIFTY 500 equity daily OHLCV history and daily incremental updates into the **strategy-grade daily dataset**
- NSE delivery quantity / percentage on equity daily bars when available
- NIFTY 500 index daily OHLCV in the strategy-grade dataset
- On-demand weekly resampling and ADTV-20 derivation from that dataset
- Load tracking and operator full/daily commands
- Built-in post-close scheduled daily update (plus CLI catch-up)
- Pre-scanner freshness gate and alerting/logging against the strategy-grade dataset

### Out of Scope

- Sector index ingestion
- Permanent weekly bar storage
- Intraday (1m/5m/15m) pipeline redesign
- Dual-write or migration of ACS / legacy candle caches as part of this feature
- Replacing ACS for non-strategy consumers
- Live order placement or strategy signal logic changes beyond the data freshness precondition and strategy read-path to the strategy-grade dataset
- Corporate-action adjustment engine redesign

---

## Dependencies

- Exchange calendar / trading-hours knowledge already used by the platform for market open/close jobs
- Existing NIFTY 500 membership source (`ind_nifty500list.csv` / universe import path)
- Market data provider credentials and rate limits
- PostgreSQL-backed persistence already used by the backend
- Scanner entry points that can invoke the freshness gate before strategy evaluation

---

## Current Platform Baseline (Audit Notes)

These notes ground planning; they are observations, not new requirements:

| Area | Baseline finding |
|------|------------------|
| Universe | `stocks_master` + `import_stocks_master.py` + startup auto-seed from `ind_nifty500list.csv` |
| Daily OHLCV | Present via `HistoricalCandle`, `market_data.candles`, Authoritative Candle Store, FYERS `fetch_ohlcv` / incremental fetch |
| Delivery % | Explicitly unavailable (`research_service` marks `delivery_pct` as requiring a separate feed) |
| NIFTY500 index store | Benchmark resolution logic exists for FEAT-004; no dedicated strategy-grade `index_ohlcv` product table as specified |
| ADTV-20 | Not a first-class stored/derived pipeline product |
| Weekly bars | Ad-hoc resample exists in analysis routes; not a shared strategy data contract |
| Full/daily CLI | No dedicated market-data full-load / daily-update operator CLI |
| Load log | No `data_load_log` for market history loads (taxonomy backfill progress is unrelated) |
| Freshness gate | Staleness helpers and cache health exist; no hard block of all scanners on missing latest session |
| Preferred modules | No top-level `data_providers/`, `pipelines/`, `validators/`, `cli/` packages yet; logic lives under `backend/app/services/` |

**Clarified storage decision (2026-08-08):** strategy-grade daily dataset is the SoT for scanners/strategies; ACS and legacy candle stores remain for existing consumers without dual-write in this feature. Planning designs the strategy-grade schema and load paths without regressing non-strategy ACS consumers.
