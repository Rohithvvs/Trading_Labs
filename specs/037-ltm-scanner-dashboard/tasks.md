# Tasks: Long-Term Buy & Hold Momentum Scanner

**Input**: Design documents from `/specs/037-ltm-scanner-dashboard/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md  
**Branch**: `037-ltm-scanner-dashboard`

**Tests**: Included where the spec’s Acceptance Fixtures, clarify Q1–Q4, and `quickstart.md` require them (formula, clock, selection, attribution, Production isolation).

**Organization**: Phases follow user-story priority (US1–US4 P1 → US5–US7 P2 → US8 P3). Foundational work blocks all stories. Brownfield: new `backend/app/services/strategies/ltm/` + namespaced scan tables. Do **not** write Production `scan_results` or import leftover `strategies/str005` bytecode.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: US1–US8 maps to spec user stories
- Paths are repo-relative from project root

## Path Conventions

- Backend package: `backend/app/services/strategies/ltm/`
- Models: `backend/app/models/ltm_strategy.py`
- Routes: `backend/app/routes/scanner.py`
- Migrations: `backend/alembic/versions/`
- Tests: `backend/tests/unit/test_ltm_*.py`
- Frontend: `frontend/src/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package home and identity constants so later slices have a place to land without changing runtime.

- [x] T001 Create LTM package skeleton `__init__.py` files under `backend/app/services/strategies/` and `backend/app/services/strategies/ltm/`
- [x] T002 [P] Add strategy identity constants (`17_long_term_mom`, display name, short name LTM, reason-code enum) in `backend/app/services/strategies/ltm/identity.py` per `specs/037-ltm-scanner-dashboard/data-model.md`
- [x] T003 [P] Add LTM settings (default capital 100000 INR, lock name `scan:17_long_term_mom`, default mode `A`) in `backend/app/config/settings.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared kernel, schema, and persistence required by every user story. No Scanner UI or LTM scan start until this phase is done.

**⚠️ CRITICAL**: No user story implementation begins until this phase is complete.

- [x] T004 Create SQLAlchemy models `LtmBookState`, `StrategyScanLatest`, `StrategyScanRun` in `backend/app/models/ltm_strategy.py` per `specs/037-ltm-scanner-dashboard/data-model.md`
- [x] T005 Export new models from `backend/app/models/__init__.py`
- [x] T006 Create Alembic migration for `ltm_book_state`, `strategy_scan_latest`, and `strategy_scan_runs` under `backend/alembic/versions/`
- [x] T007 [P] Implement master-calendar session index, warmup (`i < 252`), and 252-session rebalance clock in `backend/app/services/strategies/ltm/calendar.py` per `specs/037-ltm-scanner-dashboard/contracts/ltm-algorithm.md`
- [x] T008 [P] Implement `Momentum_252`, strict `> 0.50` eligibility, and deterministic rank (momentum desc, ticker asc) in `backend/app/services/strategies/ltm/momentum.py`
- [x] T009 [P] Implement Mode A equal-weight sizing after full sell (optional Mode B stub only) in `backend/app/services/strategies/ltm/portfolio.py`
- [x] T010 Implement book-state load/save (`sessions_since_rebalance`, `last_rebalance_date`, holdings, cash) in `backend/app/services/strategies/ltm/persistence.py`
- [x] T011 Implement namespaced latest-scan + run CRUD (never touch Production `scan_results`) in `backend/app/services/strategies/ltm/persistence.py`
- [x] T012 [P] Unit tests for exact +50% ineligible, missing lookback, warmup session 251, top-10 cap, zero-eligible cash, ticker tie-break in `backend/tests/unit/test_ltm_momentum.py` and `backend/tests/unit/test_ltm_clock.py` and `backend/tests/unit/test_ltm_selection.py`

**Checkpoint**: Kernel and tables exist; Production scan path unchanged; no LTM UI yet.

---

## Phase 3: User Story 1 — See and Select LTM on the Scanner (Priority: P1)

**Goal**: Operator can select **Long-Term Buy & Hold Momentum** on the Scanner and see that name. Empty/latest LTM payload is scoped to this strategy only.

**Independent Test**: Open Scanner, switch to LTM, confirm display name and that Production latest scan is still available when switching back.

### Implementation for User Story 1

- [x] T013 [US1] Implement `GET /scanner/strategies` listing Production + `17_long_term_mom` in `backend/app/routes/scanner.py` per `specs/037-ltm-scanner-dashboard/contracts/ltm-scan-api.md`
- [x] T014 [US1] Implement `GET /scanner/ltm/latest` (404 when none; 200 namespaced payload; cache key `scanner:latest:17_long_term_mom:v1`) in `backend/app/routes/scanner.py`
- [x] T015 [P] [US1] Add frontend fetch helpers `fetchScannerStrategies` and `fetchLtmLatest` in `frontend/src/api.ts`
- [x] T016 [US1] Add Scanner strategy switcher showing the full display name **Long-Term Buy & Hold Momentum** in `frontend/src/App.tsx`
- [x] T017 [US1] Scope Scanner subtitle, badge, and result fetch to the selected strategy so Production and LTM do not share one payload in `frontend/src/App.tsx`

**Checkpoint**: Switcher works with empty LTM state; Production `/scanner/latest` still serves Production.

---

## Phase 4: User Story 2 — Scan Runs Backtest Before Recommendations (Priority: P1) 🎯 MVP

**Goal**: Start an LTM scan that evaluates the universe, runs one book replay for every history-valid name (same filters), and only then marks recommendations final.

**Independent Test**: Start LTM scan; recommendation table stays non-final through `evaluating`/`backtesting`; on `completed`, every history-valid name has a backtest object; insufficient-history names do not; Production latest payload unchanged.

### Tests for User Story 2

- [x] T018 [P] [US2] Unit tests that recommendations stay non-final until replay finishes and that Production `scan_results` is not written in `backend/tests/unit/test_ltm_scan_gate.py`
- [x] T019 [P] [US2] Unit tests that failed-gate / ranked-out names still get a backtest object and data-failure names do not in `backend/tests/unit/test_ltm_scan_backtest_scope.py`

### Implementation for User Story 2

- [x] T020 [US2] Implement vectorized book replay (aligned close matrix, Mode A, 25 bps/side, signal-close fills, sells before buys) in `backend/app/services/strategies/ltm/book_engine.py`
- [x] T021 [US2] Implement current-session evaluate using the **same** `momentum.py` / `calendar.py` functions as replay in `backend/app/services/strategies/ltm/book_engine.py`
- [x] T022 [US2] Orchestrate freshness gate → evaluate → backtest → persist in `backend/app/services/strategies/ltm/scan_service.py` (status `evaluating` → `backtesting` → `publishing` → `completed`)
- [x] T023 [US2] Acquire single-flight lock `scan:17_long_term_mom` (do not take Production scan lock) inside `backend/app/services/strategies/ltm/scan_service.py`
- [x] T024 [US2] Block start with `MARKET_DATA_STALE` via existing `market_data_ingestion.freshness` in `backend/app/services/strategies/ltm/scan_service.py`
- [x] T025 [US2] Load strategy-grade bars only from `backend/app/services/market_data_ingestion/reader.py` inside `backend/app/services/strategies/ltm/scan_service.py`
- [x] T026 [US2] Implement `POST /scanner/ltm/runs` and `GET /scanner/ltm/runs/{scan_id}` in `backend/app/routes/scanner.py`
- [x] T027 [US2] Set `recommendations_final` true only when status is `completed` in the ScanPayload builder in `backend/app/services/strategies/ltm/scan_service.py`
- [x] T028 [US2] Add **Run LTM scan** + progress UI that hides the final recommendation table until `recommendations_final` in `frontend/src/App.tsx` and `frontend/src/components/ScannerProgress.tsx`

**Checkpoint**: An LTM scan can complete; recommendations are withheld until book replay finishes; Production latest is intact.

---

## Phase 5: User Story 3 — Read Recommendations After the Scan (Priority: P1)

**Goal**: Completed scan shows summary cards and a recommendation table: BUY on rebalance, WATCH mid-cycle, REJECT otherwise; empty-gate banner when none selected.

**Independent Test**: Complete a rebalance-day fixture (15 eligible → 10 BUY); mid-cycle fixture (WATCH, no new BUY); zero-eligible fixture (empty banner + 100% cash).

### Implementation for User Story 3

- [x] T029 [US3] Map clock + selection to BUY / WATCH / REJECT (WARMUP emits neither) in `backend/app/services/strategies/ltm/scan_service.py`
- [x] T030 [US3] Build ScanPayload `summary` (total, data_valid, evaluated, final_candidates, buy, watch, reject, data_failures) in `backend/app/services/strategies/ltm/scan_service.py`
- [x] T031 [US3] Emit recommendation rows (rank, symbol, signal, momentum_252, weights on rebalance) in `backend/app/services/strategies/ltm/scan_service.py`
- [x] T032 [P] [US3] Render LTM scan summary strip and zero-eligible banner in `frontend/src/components/LtmScanSummary.tsx`
- [x] T033 [US3] Bind LTM recommendation rows to existing `frontend/src/components/CandidateTable.tsx` from `frontend/src/App.tsx`
- [x] T034 [US3] Show mid-cycle status and sessions remaining next to the table in `frontend/src/components/LtmScanSummary.tsx`

**Checkpoint**: Completed LTM scan is readable as a recommendation list with correct signals.

---

## Phase 6: User Story 4 — Rejection Breakdown (Priority: P1)

**Goal**: Collapsible first-failure grid with LTM-only buckets; each rejected name counted once.

**Independent Test**: Mixed-failure scan increments exactly one bucket per rejected name; percents match evaluated set; no STR-500 gate labels.

### Tests for User Story 4

- [x] T035 [P] [US4] Unit tests for first-failure precedence and single-count in `backend/tests/unit/test_ltm_rejection.py`

### Implementation for User Story 4

- [x] T036 [US4] Implement first-failure assignment (`not_in_universe` → `other` order) in `backend/app/services/strategies/ltm/rejection.py` per data-model codes
- [x] T037 [US4] Attach `rejection_breakdown` (code, label, count, pct, “First failure”) to ScanPayload in `backend/app/services/strategies/ltm/scan_service.py`
- [x] T038 [US4] Render collapsible LTM rejection card grid in `frontend/src/components/LtmRejectionBreakdown.tsx`
- [x] T039 [US4] Mount Rejection Breakdown on the LTM Scanner view in `frontend/src/App.tsx`

**Checkpoint**: Operators can explain why names were rejected from LTM buckets alone.

---

## Phase 7: User Story 5 — Top 5 and Least 5 Backtest Returns (Priority: P2)

**Goal**: After a completed scan, show Top 5 positive and Least 5 1-year **real book-trade** returns, including open MTM; exclude never-selected and incomplete-history names.

**Independent Test**: Fixture with six positive and six negative 1Y book-trade names fills both boards; never-selected name absent; open holding included via MTM; 3Y detail toggle does not re-sort boards.

### Tests for User Story 5

- [x] T040 [P] [US5] Unit tests for 1Y window, real-book-only return, never-selected exclusion, and open MTM in `backend/tests/unit/test_ltm_attribution.py`

### Implementation for User Story 5

- [x] T041 [US5] Attribute per-name book trades and 1Y return (closed + scan-session MTM) in `backend/app/services/strategies/ltm/attribution.py`
- [x] T042 [US5] Build `top5_positive` and `least5` (no padding; return > 0 for Top 5) in `backend/app/services/strategies/ltm/attribution.py`
- [x] T043 [US5] Attach boards + 1Y period dates to ScanPayload in `backend/app/services/strategies/ltm/scan_service.py`
- [x] T044 [P] [US5] Render Top 5 / Least 5 tables with period footnote in `frontend/src/components/LtmReturnBoards.tsx`
- [x] T045 [US5] Mount return boards on the LTM Scanner view after summary in `frontend/src/App.tsx`

**Checkpoint**: Boards match clarify Q1–Q4.

---

## Phase 8: User Story 6 — Strategy-Owned Technicals (Priority: P2)

**Goal**: Stock-detail Technicals show only LTM inputs (momentum, closes, rank, gate, selection, clock).

**Independent Test**: Open BUY, failed-gate REJECT, and insufficient-history REJECT; confirm LTM tiles and no RSI/EMA/ATR decision tiles.

### Implementation for User Story 6

- [x] T046 [US6] Build `LtmTechnicals` snapshot (momentum null ≠ 0) on each recommendation row in `backend/app/services/strategies/ltm/scan_service.py`
- [x] T047 [US6] Implement `GET /scanner/ltm/symbols/{symbol}` in `backend/app/routes/scanner.py`
- [x] T048 [P] [US6] Add `fetchLtmSymbolDetail` in `frontend/src/api.ts`
- [x] T049 [US6] Branch `TechnicalsTab` on LTM strategy to render LTM tiles only in `frontend/src/components/StockDetailPanel.tsx`
- [x] T050 [US6] Hide Production RSI / EMA / ATR / Bollinger / volume / RS tiles when LTM is active in `frontend/src/components/StockDetailPanel.tsx`

**Checkpoint**: Technicals explain LTM eligibility without another engine’s indicators.

---

## Phase 9: User Story 7 — Backtest Tab (Priority: P2)

**Goal**: Detail Backtest tab shows book-attributed trades, headline metrics, equity vs NIFTY 500, drawdown, monthly grid, blotter; 1Y/3Y/5Y/All does not change scan-level boards.

**Independent Test**: Name with a historical cohort shows trades/metrics; never-selected name shows empty/never-selected; switching to 3Y leaves Top 5 on 1Y.

### Implementation for User Story 7

- [x] T051 [US7] Expose per-name backtest windows (`1Y` default, `3Y`, `5Y`, `All`) from book-attributed trades in `backend/app/services/strategies/ltm/attribution.py`
- [x] T052 [US7] Include book-level metrics and NIFTY 500 overlay series in ScanPayload / symbol detail in `backend/app/services/strategies/ltm/scan_service.py`
- [x] T053 [US7] Branch `BacktestTab` for LTM (equity, drawdown, monthly returns, trade log, best/worst) in `frontend/src/components/StockDetailPanel.tsx`
- [x] T054 [US7] Keep scan-level Top 5 / Least 5 on the fixed 1Y ranking when the detail window changes in `frontend/src/components/LtmReturnBoards.tsx` and `frontend/src/components/StockDetailPanel.tsx`

**Checkpoint**: Backtest tab is evidence for a name without inventing a different strategy.

---

## Phase 10: User Story 8 — Clock, Warmup, and Limitations (Priority: P3)

**Goal**: Dashboard shows WARMUP / MID_CYCLE / REBALANCE, persists the clock across restart, labels survivorship, and discloses known limits.

**Independent Test**: Warmup dataset → STATUS=WARMUP and zero BUY/WATCH; mid-cycle → sessions remaining and no liquidate-today copy; restart process → same `sessions_since_rebalance`; limitations visible.

### Tests for User Story 8

- [x] T055 [P] [US8] Unit test that book state survives reload (clock not reset) in `backend/tests/unit/test_ltm_book_state.py`

### Implementation for User Story 8

- [x] T056 [US8] Surface `clock_status`, `sessions_to_rebalance`, `next_rebalance_estimate`, and `warmup` on ScanPayload in `backend/app/services/strategies/ltm/scan_service.py`
- [x] T057 [US8] Render WARMUP / mid-cycle / rebalance chips and “no entries during warmup” copy in `frontend/src/components/LtmScanSummary.tsx`
- [x] T058 [US8] Set and display `survivorship_biased` when only the current NIFTY 500 list is used in `backend/app/services/strategies/ltm/scan_service.py` and `frontend/src/components/LtmScanSummary.tsx`
- [x] T059 [US8] Show known-limitations copy (no stop, concentration, look-ahead, not a forecast) on LTM results in `frontend/src/components/LtmScanSummary.tsx`

**Checkpoint**: Operators cannot mistake a mid-cycle or warmup scan for a live rebalance day.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Isolation, optional Mode B, and quickstart validation.

- [x] T060 [P] Optional Mode B research switch (10% × 10, NSE delivery costs) in `backend/app/services/strategies/ltm/portfolio.py` without changing default Mode A
- [x] T061 [P] Published six-cohort membership tests against a frozen calendar fixture in `backend/tests/unit/test_ltm_selection_fixtures.py`
- [x] T062 Confirm no import of `backend/app/services/strategies/str005` and no write to Production `scan_results` in `backend/app/services/strategies/ltm/` and `backend/app/routes/scanner.py`
- [x] T063 [P] Production regression: existing scanner cache/gate tests still pass via `backend/tests/unit/test_market_data_scanner_gate.py` and `backend/app/tests/test_scanner_routes_cached.py`
- [x] T064 Walk `specs/037-ltm-scanner-dashboard/quickstart.md` (kernel pytest, stale block, UI switcher, 1Y boards, Technicals, Backtest window)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**
- **US1 (Phase 3)**: After Foundational — switcher can ship with empty latest
- **US2 (Phase 4)**: After Foundational; uses persistence from Phase 2; unlocks a useful scan MVP
- **US3 (Phase 5)**: After US2 (needs completed ScanPayload)
- **US4 (Phase 6)**: After US2 (needs evaluate outcomes); can parallel US3 if payload fields are added independently
- **US5 (Phase 7)**: After US2 (needs book replay)
- **US6 (Phase 8)**: After US3 (needs a row to open)
- **US7 (Phase 9)**: After US5 (needs attribution)
- **US8 (Phase 10)**: After US2 (clock already in kernel; this is display + persist test)
- **Polish (Phase 11)**: After desired stories

### User Story Dependencies

- **US1**: Independent after Phase 2
- **US2**: Independent after Phase 2 (core scan)
- **US3**: Depends on US2 payload
- **US4**: Depends on US2 evaluate
- **US5**: Depends on US2 replay
- **US6**: Depends on US3 rows
- **US7**: Depends on US5 attribution
- **US8**: Can start after US2; display-only plus persist test

### Parallel Opportunities

- T002 / T003 after T001
- T007 / T008 / T009 / T012 after T001–T002
- T015 while T013–T014 land
- T018 / T019 while T020 is written (fail-first)
- T032 / T038 / T044 as separate frontend files
- T060 / T061 / T063 in polish

### Parallel Example: User Story 2

```text
Task: "Unit tests that recommendations stay non-final in backend/tests/unit/test_ltm_scan_gate.py"
Task: "Unit tests for backtest scope in backend/tests/unit/test_ltm_scan_backtest_scope.py"
# Then sequential:
Task: "Vectorized book replay in backend/app/services/strategies/ltm/book_engine.py"
Task: "Scan orchestrator in backend/app/services/strategies/ltm/scan_service.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Phase 1 Setup  
2. Phase 2 Foundational (kernel + tables)  
3. Phase 3 US1 (named switcher)  
4. Phase 4 US2 (scan + backtest-before-recommend)  
5. **STOP and VALIDATE** with `quickstart.md` sections 1–4  

US1 alone is only the switcher. **US1+US2 is the operator-useful MVP.**

### Incremental Delivery

1. US3 — readable recommendations  
2. US4 — rejection honesty  
3. US5 — Top 5 / Least 5  
4. US6 / US7 — detail tabs  
5. US8 — clock + disclosures  
6. Polish — Mode B optional, fixture membership, Production regression  

### Suggested sequential order

T001 → T002/T003 → T004–T012 → T013–T017 → T018–T028 → T029–T034 → T035–T039 → T040–T045 → T046–T050 → T051–T054 → T055–T059 → T060–T064

---

## Notes

- [P] = different files, no incomplete dependencies
- Do not overwrite Production `scan_results` or cache `scanner:latest:v1`
- Do not import `strategies/str005`
- Same `momentum.py` / `calendar.py` for evaluate and replay (filter parity)
- Commit after each task or logical group
- Stop at any checkpoint to validate the story independently
