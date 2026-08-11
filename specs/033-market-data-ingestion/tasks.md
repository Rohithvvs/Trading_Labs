# Tasks: Market Data Ingestion & Daily Update System

**Input**: Design documents from `/specs/033-market-data-ingestion/`  
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/, quickstart.md  
**Branch**: `033-market-data-ingestion`

**Tests**: Included selectively (plan §16 + acceptance criteria). Prefer unit tests with mocked providers; integration tests optional where PG fixtures exist.

**Organization**: Phases follow user-story priority (US1/US2 P1 → US3/US4 P2 → US5 P3). Foundational work blocks all stories. Brownfield: extend under `backend/app/`; do not dual-write ACS.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: US1–US5 maps to spec user stories
- Paths are repo-relative from project root

## Path Conventions

- Backend: `backend/app/`
- Models: `backend/app/models/`
- Ingestion package: `backend/app/services/market_data_ingestion/`
- CLI: `backend/app/cli/`
- Migrations: `backend/alembic/versions/`
- Tests: `backend/tests/unit/` and `backend/app/tests/` as appropriate

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton and settings hooks so implementation has a home without changing runtime behavior yet.

- [x] T001 Create package skeleton directories and `__init__.py` files under `backend/app/services/market_data_ingestion/`, `backend/app/services/market_data_ingestion/providers/`, `backend/app/services/market_data_ingestion/pipelines/`, `backend/app/services/market_data_ingestion/validators/`, and `backend/app/cli/`
- [x] T002 [P] Add strategy market-data settings (gate flag, post-close cron hour/minute, index provider symbol, load concurrency, coverage threshold) in `backend/app/config/settings.py`
- [x] T003 [P] Document env keys for strategy market data in `.env.template` (no secrets; defaults only)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema, models, repository, providers, derived fields, and load-log primitives required by every user story.

**⚠️ CRITICAL**: No user story implementation begins until this phase is complete.

- [x] T004 Extend `StockMaster` with `industry`, `is_nifty500`, `first_seen`, `last_seen` (nullable/safe defaults) in `backend/app/models/stock.py`
- [x] T005 [P] Create SQLAlchemy models `DailyOhlcv`, `IndexOhlcv`, `DataLoadLog` in `backend/app/models/strategy_market_data.py` per `specs/033-market-data-ingestion/data-model.md`
- [x] T006 Export new models from `backend/app/models/__init__.py`
- [x] T007 Create Alembic migration for `daily_ohlcv`, `index_ohlcv`, `data_load_log` and `stocks_master` column adds under `backend/alembic/versions/`
- [x] T008 Implement bulk upsert + query helpers (max trade date, session coverage, index exists, load log CRUD) in `backend/app/services/market_data_ingestion/repository.py`
- [x] T009 [P] Implement null-safe `delivery_pct` and `turnover` helpers in `backend/app/services/market_data_ingestion/derived.py` (never invent delivery; zero traded_qty → null pct)
- [x] T010 [P] Implement delivery row validation rules in `backend/app/services/market_data_ingestion/validators/delivery_rules.py`
- [x] T011 [P] Implement session completeness validator (coverage ratio, missing symbol sample, index present) in `backend/app/services/market_data_ingestion/validators/completeness.py`
- [x] T012 Implement FYERS EOD adapter wrapping existing `FyersService` history for equity and index daily bars in `backend/app/services/market_data_ingestion/providers/fyers_eod.py`
- [x] T013 Implement NSE delivery provider (session file download + parse + ISIN/symbol join; null-safe) in `backend/app/services/market_data_ingestion/providers/nse_delivery.py`
- [x] T014 Extend universe active-NIFTY500 helpers and lifecycle touch (`first_seen`/`last_seen`/`is_nifty500`) in `backend/app/services/universe_service.py`
- [x] T015 Update CSV import to set `is_nifty500` / lifecycle fields when seeding in `backend/scripts/import_stocks_master.py`
- [x] T016 Implement single-flight load lock helper using `acquire_singleton_lease` (shared name for FULL+DAILY) in `backend/app/services/market_data_ingestion/locks.py`
- [x] T017 Implement shared load-run lifecycle (start/finish counters, SUCCESS|PARTIAL|FAILED|SKIPPED_LOCKED, trigger_source) in `backend/app/services/market_data_ingestion/load_tracking.py`

**Checkpoint**: Models migrated; repository and providers callable; no scanner behavior change yet.

---

## Phase 3: User Story 1 — Daily Incremental Market Update (Priority: P1) 🎯 MVP

**Goal**: Idempotent daily EOD load for active NIFTY 500 equities + NIFTY500 index (latest completed session), with delivery merge when available, load log, single-flight, and scheduled post-close run.

**Independent Test**: With baseline history present, run daily update twice for the same session; both succeed; no duplicate PKs; latest session present for universe + index; second concurrent trigger yields SKIPPED_LOCKED.

### Implementation for User Story 1

- [x] T018 [US1] Implement expected last completed trade date helper (reuse `TradingHoursService` + holidays) in `backend/app/services/market_data_ingestion/calendar_utils.py`
- [x] T019 [US1] Implement daily update pipeline (detect missing/latest date, fetch equities, delivery join, index bar, derive fields, bulk upsert, validate, log) in `backend/app/services/market_data_ingestion/pipelines/daily_update.py`
- [x] T020 [US1] Wire PARTIAL vs SUCCESS status using completeness validator (≥99% equity + index present) inside `backend/app/services/market_data_ingestion/pipelines/daily_update.py`
- [x] T021 [US1] Register APScheduler post-close job calling daily update with `trigger_source=SCHEDULE` in `backend/app/main.py`
- [x] T022 [US1] Add structured logging (`MARKET_DATA_LOAD_START|END`, counters, provider errors) in `backend/app/services/market_data_ingestion/pipelines/daily_update.py`
- [x] T023 [P] [US1] Unit tests for daily update idempotency, partial failure, and zero traded_qty delivery null in `backend/tests/unit/test_market_data_daily_update.py`

**Checkpoint**: MVP — daily incremental path works via pipeline function (CLI can come in US4); schedule registered.

---

## Phase 4: User Story 2 — Pre-Scanner Data Freshness Gate (Priority: P1)

**Goal**: Fail-closed `MARKET_DATA_STALE` gate before strategy scan work; operator-visible logs + diagnostics/status; delivery does not fail global gate; STR-041 hard-fails per symbol when delivery missing.

**Independent Test**: Withhold latest session for many symbols or drop index bar → `execute_scan` blocks with payload; restore data → scan proceeds past gate; missing delivery alone does not block general scan.

### Implementation for User Story 2

- [x] T024 [US2] Implement freshness gate service returning OK / `MARKET_DATA_STALE` payload per `specs/033-market-data-ingestion/contracts/freshness_gate.md` in `backend/app/services/market_data_ingestion/freshness.py`
- [x] T025 [US2] Honor `STRATEGY_MARKET_DATA_GATE_ENABLED` (or settings name from T002) fail-open vs fail-closed in `backend/app/services/market_data_ingestion/freshness.py`
- [x] T026 [US2] Call freshness gate early in `ScanExecutionService.execute_scan` after scan lock acquire and before strategy/data work in `backend/app/services/scan_execution_service.py`
- [x] T027 [US2] Emit structured log + progress/error channel with expected_date, coverage, missing sample, remediation on gate fail in `backend/app/services/scan_execution_service.py`
- [x] T028 [US2] Expose `market_data_freshness` (and last load summary if available) on operator diagnostics/health surface in `backend/app/routes/diagnostics.py` and/or `backend/app/routes/health.py`
- [x] T029 [US2] Add STR-041 delivery-missing helper (`DELIVERY_DATA_MISSING`) for per-strategy hard fail in `backend/app/services/market_data_ingestion/freshness.py` (or `derived.py` if cleaner)
- [x] T030 [P] [US2] Unit tests for holiday/weekend expected date, coverage threshold, index missing, gate bypass flag in `backend/tests/unit/test_market_data_freshness.py`
- [x] T031 [US2] Integration-style test that `execute_scan` blocks when stale (mocked gate/repo) in `backend/tests/unit/test_market_data_scanner_gate.py`

**Checkpoint**: Scanners cannot start strategy evaluation on stale strategy-grade data when gate enabled.

---

## Phase 5: User Story 3 — Initial Full Historical Load (Priority: P2)

**Goal**: Resumable ≥3-year full load for active NIFTY 500 + index with turnover/delivery_pct at insert; idempotent upserts; load log.

**Independent Test**: Empty/truncated strategy tables → full load → multi-year equity + index present; restart mid-run completes without wipe; delivery_pct formula holds on samples.

### Implementation for User Story 3

- [x] T032 [US3] Implement full-load pipeline (range calc, index history, per-symbol chunked OHLCV, optional delivery backfill pass, checkpoint/resume, bulk upsert, log) in `backend/app/services/market_data_ingestion/pipelines/full_load.py`
- [x] T033 [US3] Bound symbol concurrency and reuse FYERS rate-limit/retry behavior via `backend/app/services/market_data_ingestion/providers/fyers_eod.py` from full-load pipeline
- [x] T034 [US3] Ensure interrupted full-load resume skips complete symbols / upserts safely in `backend/app/services/market_data_ingestion/pipelines/full_load.py`
- [x] T035 [P] [US3] Unit tests for full-load resume, delivery_pct formula, turnover=close×volume with mocks in `backend/tests/unit/test_market_data_full_load.py`

**Checkpoint**: Operators can bootstrap history without relying on ACS dual-write.

---

## Phase 6: User Story 4 — Operator Load Commands & Observability (Priority: P2)

**Goal**: CLI commands `full-load`, `daily-update`, `status`, `verify` with load-log inspection; exit codes per contracts.

**Independent Test**: Run CLI commands; each mutating run writes `data_load_log`; status/verify reflect freshness; concurrent second load exits locked.

### Implementation for User Story 4

- [x] T036 [US4] Implement CLI entrypoint argparse commands (`full-load`, `daily-update`, `status`, `verify`) per `specs/033-market-data-ingestion/contracts/cli.md` in `backend/app/cli/market_data_cli.py`
- [x] T037 [US4] Wire CLI to pipelines + freshness + repository; set `trigger_source=CLI` and exit codes 0/1/2/3/4 in `backend/app/cli/market_data_cli.py`
- [x] T038 [US4] Implement `status` output (expected date, coverage, index, last loads, lock, gate_ok) using repository + freshness in `backend/app/cli/market_data_cli.py`
- [x] T039 [US4] Implement `verify` emitting freshness payload (human + optional `--json`) in `backend/app/cli/market_data_cli.py`
- [x] T040 [P] [US4] Unit tests for CLI argument parsing and locked/stale exit codes (mocked pipelines) in `backend/tests/unit/test_market_data_cli.py`

**Checkpoint**: Ops can run and inspect loads without manual SQL.

---

## Phase 7: User Story 5 — Strategy-Ready Derived Views (Priority: P3)

**Goal**: Shared helpers for on-demand weekly OHLCV, ADTV-20, index series read, and delivery fields from strategy tables (no weekly table; no sector indices).

**Independent Test**: Known sample series → weekly resample and ADTV-20 match formulas; index series returns `NIFTY500` rows from `index_ohlcv`.

### Implementation for User Story 5

- [x] T041 [P] [US5] Implement on-demand weekly OHLCV resample from daily bars in `backend/app/services/market_data_ingestion/derived.py`
- [x] T042 [P] [US5] Implement ADTV-20 (mean of last 20 session turnovers/close×volume) in `backend/app/services/market_data_ingestion/derived.py`
- [x] T043 [US5] Implement strategy data reader (equity history, delivery fields, index series by `NIFTY500`) in `backend/app/services/market_data_ingestion/reader.py`
- [x] T044 [US5] Document public import surface for strategies in `backend/app/services/market_data_ingestion/__init__.py`
- [x] T045 [P] [US5] Unit tests for weekly resample and ADTV-20 edge cases (<20 bars) in `backend/tests/unit/test_market_data_derived.py`

**Checkpoint**: Strategy authors have a single read path for STR-041/005/021/025/045/071 data needs without sector indices.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Hardening, docs, quickstart dry-run checklist, and remaining plan §16 scenarios.

- [x] T046 [P] Add API failure / retry behavior tests for FYERS EOD adapter mocks in `backend/tests/unit/test_market_data_fyers_eod.py`
- [x] T047 [P] Add NSE delivery missing-file and malformed-row tests in `backend/tests/unit/test_market_data_nse_delivery.py`
- [x] T048 Verify ACS / `historical_candles` / `market_data.candles` are never written by ingestion pipelines (code review + grep guard test) in `backend/tests/unit/test_market_data_no_acs_dual_write.py`
- [x] T049 Align structured log field names with existing logger conventions in `backend/app/services/market_data_ingestion/`
- [x] T050 Run through `specs/033-market-data-ingestion/quickstart.md` validation steps on a dev DB and record results in `specs/033-market-data-ingestion/quickstart.md` (notes section) or ops runbook comment
- [x] T051 [P] Ensure `backend/data/nse_trading_holidays.json` includes current year holidays needed for expected_date tests
- [x] T052 Final pass: feature flag default recommendation documented in `backend/app/config/settings.py` docstring (gate off until first successful full/daily load in new envs)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: Immediate
- **Phase 2 Foundational**: After Setup — **blocks all user stories**
- **Phase 3 US1 (Daily)**: After Foundational — **MVP**
- **Phase 4 US2 (Gate)**: After Foundational; ideally after US1 so “fresh” path can be demonstrated (can start gate unit tests earlier)
- **Phase 5 US3 (Full load)**: After Foundational; shares providers/repo with US1
- **Phase 6 US4 (CLI)**: After US1 + US3 pipelines exist (status/verify need US2 freshness)
- **Phase 7 US5 (Derived)**: After Foundational (+ sample data from US1/US3 for integration confidence)
- **Phase 8 Polish**: After desired stories complete

### User Story Dependencies

| Story | Depends on | Notes |
|-------|------------|-------|
| US1 Daily update | Phase 2 | MVP; schedule in same phase |
| US2 Freshness gate | Phase 2; best after US1 | Can unit-test with seeded rows |
| US3 Full load | Phase 2 | Independent of US2 |
| US4 CLI | US1 + US3 + US2 (for verify) | Thin wrapper |
| US5 Derived | Phase 2 | Independent of gate/CLI |

### Within Each Story

- Validators/derived before pipelines
- Pipelines before schedule/CLI wiring
- Gate service before `execute_scan` integration
- Tests with mocks preferred before live provider runs

### Parallel Opportunities

- T002/T003; T005/T004 after skeleton
- T009/T010/T011 in parallel after T008 started
- T012/T013 in parallel
- T041/T042/T045 in parallel (US5)
- T046/T047/T048/T051 in polish

---

## Parallel Example: Foundational

```text
# After T001–T003 and models T004–T007:
T009 derived.py
T010 delivery_rules.py
T011 completeness.py
# parallel then:
T012 fyers_eod.py
T013 nse_delivery.py
```

## Parallel Example: User Story 1

```text
T018 calendar_utils.py
# then T019–T022 sequential on daily_update + main.py
T023 tests in parallel with T021 if pipeline API stable
```

## Parallel Example: User Story 5

```text
T041 weekly resample
T042 ADTV-20
T045 derived tests
# then T043 reader depending on both
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 Setup  
2. Phase 2 Foundational  
3. Phase 3 US1 Daily update (+ schedule)  
4. **STOP**: Validate double daily-update idempotency and load log  
5. Optionally enable gate (US2) before production scanners rely on strategy tables  

### Incremental Delivery

1. Setup + Foundational  
2. **US1** Daily update → demo EOD path  
3. **US2** Freshness gate → scanners protected  
4. **US3** Full load → bootstrap empty envs  
5. **US4** CLI → ops self-serve  
6. **US5** Derived helpers → strategy contracts  
7. Polish + quickstart  

### Suggested MVP Scope

**Phases 1–3 (T001–T023)** — daily incremental pipeline + schedule + foundational schema/providers.  
**Next critical**: Phase 4 gate (T024–T031) before claiming scanner protection.

---

## Notes

- Do **not** dual-write ACS/legacy candle stores (research + plan).  
- Delivery: soft global, hard STR-041 (clarification).  
- Single-flight FULL and DAILY (clarification).  
- Exact NSE delivery file URL/format verified at implement in T013 — do not invent private APIs.  
- Commit after each task or logical group.  
- Stop at checkpoints to validate independently.  
- `tasks.md` is the input for `/speckit-implement`; do not implement in this command.
