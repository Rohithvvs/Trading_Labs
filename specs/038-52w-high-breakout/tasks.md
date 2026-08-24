# Tasks: 52-Week High Breakout Scanner

**Input**: Design documents from `/specs/038-52w-high-breakout/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md  
**Branch**: `038-52w-high-breakout`

**Tests**: Included where the spec’s Acceptance Fixtures, clarify Q1–Q3, and `quickstart.md` require them (indicators, signal, trail, book, attribution, isolation).

**Organization**: Phases follow user-story priority (US1–US5 P1 → US6–US8 P2 → US9 P3). Foundational work blocks all stories. Brownfield: new `backend/app/services/strategies/breakout52w/` + `w52_book_state`. Do **not** write Production `scan_results` or `ltm_book_state`. Do **not** start LTM from the 52W Run control.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: US1–US9 maps to spec user stories
- Paths are repo-relative from project root

## Path Conventions

- Backend package: `backend/app/services/strategies/breakout52w/`
- Models: `backend/app/models/w52_strategy.py`
- Routes: `backend/app/routes/scanner.py`
- Migrations: `backend/alembic/versions/`
- Tests: `backend/tests/unit/test_w52_*.py`
- Frontend: `frontend/src/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package home and identity constants so later slices have a place to land without changing LTM or Production runtime.

- [x] T001 Create 52W package skeleton `__init__.py` files under `backend/app/services/strategies/breakout52w/`
- [x] T002 [P] Add strategy identity constants (`09_52w_breakout`, display name **52-Week High Breakout**, short name `52W`, lock `scan:09_52w_breakout`, cache `scanner:latest:09_52w_breakout:v1`, first-failure codes) in `backend/app/services/strategies/breakout52w/identity.py` per `specs/038-52w-high-breakout/data-model.md`
- [x] T003 [P] Add 52W settings (default capital 100000 INR, lock name, default mode `B`) in `backend/app/config/settings.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared kernel, schema, and persistence required by every user story. No Scanner UI or 52W scan start until this phase is done.

**⚠️ CRITICAL**: No user story implementation begins until this phase is complete.

- [x] T004 Create SQLAlchemy model `W52BookState` (cash, holdings with `hwm`/`tsl`, `sold_today`, `book_status`, `last_session_processed`) in `backend/app/models/w52_strategy.py` per `specs/038-52w-high-breakout/data-model.md`
- [x] T005 Export `W52BookState` from `backend/app/models/__init__.py` (do not alter `LtmBookState`)
- [x] T006 Create Alembic migration for `w52_book_state` only under `backend/alembic/versions/` (reuse existing `strategy_scan_latest` / `strategy_scan_runs`)
- [x] T007 [P] Implement `High_252_prior`, `Vol_SMA20` (today included), SMA `ATR14` (not Wilder), `Momentum_60`, and `MarketOK` in `backend/app/services/strategies/breakout52w/indicators.py` per `specs/038-52w-high-breakout/contracts/w52-algorithm.md`
- [x] T008 [P] Implement BuySignal (state, not cross) and first-failure assignment in `backend/app/services/strategies/breakout52w/signal.py`
- [x] T009 [P] Implement HWM/TSL ratchet, no-exit-on-entry-bar, NaN-ATR 90% fallback, never-decrease stop in `backend/app/services/strategies/breakout52w/trail.py`
- [x] T010 [P] Implement Mode B sizing (10% of current equity, max 10, next-ranked substitute) in `backend/app/services/strategies/breakout52w/portfolio.py`
- [x] T011 Implement NSE delivery cost helper in `backend/app/services/strategies/breakout52w/costs.py` (wrap or match `backend/app/services/backtest_service.py` delivery profile)
- [x] T012 Implement book-state load/save (HWM/TSL must survive reload; never write `ltm_book_state`) in `backend/app/services/strategies/breakout52w/persistence.py`
- [x] T013 Implement namespaced latest-scan + run CRUD for `strategy_id=09_52w_breakout` in `backend/app/services/strategies/breakout52w/persistence.py`
- [x] T014 [P] Unit tests for prior-high exclude-today, close-equals-high, volume-equals-average, MarketOK equality, Wilder-ATR fail, trail ratchet, entry-bar no-exit, NaN-ATR fallback, top-10 slots, sold-today no-rebuy in `backend/tests/unit/test_w52_indicators.py`, `backend/tests/unit/test_w52_signal.py`, `backend/tests/unit/test_w52_trail.py`, and `backend/tests/unit/test_w52_book.py`

**Checkpoint**: Kernel and `w52_book_state` exist; Production and LTM scan paths unchanged; no 52W UI yet.

---

## Phase 3: User Story 1 — See and Select 52-Week High Breakout Beside LTM (Priority: P1)

**Goal**: Operator sees a **52-Week High Breakout** button immediately beside **Long-Term Buy & Hold Momentum**, selects it, and sees that name. Latest payload is scoped to this strategy only.

**Independent Test**: Open Scanner, confirm the 52W button sits beside LTM, select it, confirm display name, switch back to LTM and still see LTM’s latest scan.

### Implementation for User Story 1

- [x] T015 [US1] Extend `GET /scanner/strategies` to list 52-Week High Breakout immediately after LTM in `backend/app/routes/scanner.py` per `specs/038-52w-high-breakout/contracts/w52-scan-api.md`
- [x] T016 [US1] Implement `GET /scanner/w52/latest` (404 when none; 200 namespaced payload; cache key `scanner:latest:09_52w_breakout:v1`) in `backend/app/routes/scanner.py`
- [x] T017 [P] [US1] Add frontend helpers `fetchW52Latest` (and extend strategies fetch if needed) in `frontend/src/api.ts`
- [x] T018 [US1] Add a **52-Week High Breakout** strategy button immediately beside the LTM button in `frontend/src/App.tsx`
- [x] T019 [US1] Scope Scanner subtitle, badge, and result fetch so Production, LTM, and 52W do not share one payload in `frontend/src/App.tsx` and `frontend/src/types.ts`

**Checkpoint**: Switcher shows 52W beside LTM with empty 52W state; LTM and Production latest still load on their tabs.

---

## Phase 4: User Story 2 — Isolated Run Starts Only 52W (Priority: P1)

**Goal**: This view’s Run starts **only** `09_52w_breakout`. A second click while in flight is ignored (409). LTM/Production runs do not start or overwrite 52W.

**Independent Test**: Press 52W Run — only 52W enters a running state. Press again — 409 / disabled, same `scan_id`. Start LTM — 52W latest unchanged.

### Tests for User Story 2

- [x] T020 [P] [US2] Unit tests that a second start returns `W52_SCAN_IN_PROGRESS` without cancelling the first run in `backend/tests/unit/test_w52_scan_lock.py`
- [x] T021 [P] [US2] Unit tests that 52W start does not write LTM or Production latest, and LTM start does not write 52W latest, in `backend/tests/unit/test_w52_scan_isolation.py`

### Implementation for User Story 2

- [x] T022 [US2] Implement `find_active_run` + `start_scan_background` that returns 409 payload `W52_SCAN_IN_PROGRESS` (no cancel, no queue) in `backend/app/services/strategies/breakout52w/scan_service.py` and `backend/app/services/strategies/breakout52w/persistence.py`
- [x] T023 [US2] Acquire lock `scan:09_52w_breakout` only (do not take LTM or Production locks) in `backend/app/services/strategies/breakout52w/scan_service.py`
- [x] T024 [US2] Implement `POST /scanner/w52/runs` and `GET /scanner/w52/runs/{scan_id}` in `backend/app/routes/scanner.py`
- [x] T025 [US2] Add this view’s Run control that calls **only** `POST /scanner/w52/runs` in `frontend/src/App.tsx` and `frontend/src/api.ts`
- [x] T026 [US2] Disable or ignore the 52W Run control while status is queued / evaluating / backtesting / publishing in `frontend/src/App.tsx`

**Checkpoint**: Isolated Run works; second click is a no-op; LTM/Production latest intact.

---

## Phase 5: User Story 3 — Scan Runs Backtest Before Recommendations (Priority: P1) 🎯 MVP

**Goal**: A 52W scan evaluates the universe, runs one book replay + per-name attribution for every history-valid name (same filters), and only then marks recommendations final. Per-name attribution failure is `data_source_failure` and does not block publish (clarify Q3).

**Independent Test**: Start 52W scan; recommendation table stays non-final through `evaluating`/`backtesting`; on `completed`, history-valid successes have backtest objects; failed attributions are data-failures and omitted from boards; insufficient-history names are not backtested; LTM/Production latest unchanged.

### Tests for User Story 3

- [x] T027 [P] [US3] Unit tests that `recommendations_final` stays false until every history-valid job is terminal in `backend/tests/unit/test_w52_scan_gate.py`
- [x] T028 [P] [US3] Unit tests that a failed attribution is `data_source_failure`, excluded from boards, and does not cancel today’s evaluation signal in `backend/tests/unit/test_w52_scan_backtest_scope.py`

### Implementation for User Story 3

- [x] T029 [US3] Implement session-ordered book replay (exits then entries, Mode B, signal-close fills, SMA-ATR trail) in `backend/app/services/strategies/breakout52w/book_engine.py`
- [x] T030 [US3] Implement current-session evaluate using the **same** `indicators.py` / `signal.py` / `trail.py` functions as replay in `backend/app/services/strategies/breakout52w/book_engine.py`
- [x] T031 [US3] Orchestrate freshness gate → evaluate → backtest → persist in `backend/app/services/strategies/breakout52w/scan_service.py` (status `evaluating` → `backtesting` → `publishing` → `completed`)
- [x] T032 [US3] Block start with `MARKET_DATA_STALE` via existing `market_data_ingestion.freshness` in `backend/app/services/strategies/breakout52w/scan_service.py`
- [x] T033 [US3] Load strategy-grade OHLCV (high/low/close/volume + index) only from `backend/app/services/market_data_ingestion/reader.py` inside `backend/app/services/strategies/breakout52w/scan_service.py`
- [x] T034 [US3] Set `recommendations_final` true only when status is `completed`; treat per-name attribution errors as terminal data-failures in `backend/app/services/strategies/breakout52w/scan_service.py`
- [x] T035 [US3] Hide the final recommendation table, boards, and rejection percents until `recommendations_final` in `frontend/src/App.tsx` (progress copy names **52-Week High Breakout** only)

**Checkpoint**: A 52W scan can complete; recommendations are withheld until backtests are terminal; other strategies’ latest scans are intact.

---

## Phase 6: User Story 4 — Recommendations, Orders, and Holdings (Priority: P1)

**Goal**: Completed scan shows summary, recommendation table (BUY / HOLD / WATCH / REJECT), EXIT-then-BUY order list, and holdings with trail state.

**Independent Test**: Scan with a new entry, a still-open name, a skipped buy-signal, and a trail exit: BUY / HOLD / WATCH / REJECT correct; HOLD omitted from rejections; EXIT appears before BUY; new BUY stays BUY (not HOLD) this session.

### Implementation for User Story 4

- [x] T036 [US4] Map evaluation + trail to BUY / HOLD / WATCH / REJECT (HOLD = still open, not a new BUY; EXIT rows not HOLD) in `backend/app/services/strategies/breakout52w/scan_service.py` per clarify Q1
- [x] T037 [US4] Build ScanPayload `summary` including `hold` plus `book_status`, `market_ok`, free slots, cash, equity in `backend/app/services/strategies/breakout52w/scan_service.py`
- [x] T038 [US4] Emit `orders` (EXIT first, then BUY) and `holdings` (hwm, tsl, unrealized_pct) on ScanPayload in `backend/app/services/strategies/breakout52w/scan_service.py`
- [x] T039 [P] [US4] Render 52W scan summary strip, completed-without-new-buys banner, and market-off copy in `frontend/src/components/W52ScanSummary.tsx`
- [x] T040 [P] [US4] Render EXIT-then-BUY order list in `frontend/src/components/W52OrderList.tsx`
- [x] T041 [US4] Bind 52W recommendation rows (including HOLD badge) to existing `frontend/src/components/CandidateTable.tsx` from `frontend/src/App.tsx`
- [x] T042 [US4] Mount summary + order list on the 52W Scanner view in `frontend/src/App.tsx`

**Checkpoint**: Completed 52W scan is readable as BUY/HOLD/WATCH/REJECT plus today’s order list.

---

## Phase 7: User Story 5 — Rejection Breakdown (Priority: P1)

**Goal**: Collapsible first-failure grid with 52W-only buckets; each rejected name counted once; HOLD names omitted.

**Independent Test**: Mixed-failure scan increments exactly one bucket per rejected name; percents match evaluated set; no LTM +50% or STR-500 gate labels; HOLD count stays out of the grid.

### Tests for User Story 5

- [x] T043 [P] [US5] Unit tests for first-failure precedence, single-count, and HOLD exclusion in `backend/tests/unit/test_w52_rejection.py`

### Implementation for User Story 5

- [x] T044 [US5] Implement first-failure assignment (`not_in_universe` → `other` order) in `backend/app/services/strategies/breakout52w/rejection.py` per data-model codes
- [x] T045 [US5] Attach `rejection_breakdown` (code, label, count, pct, “First failure”) to ScanPayload in `backend/app/services/strategies/breakout52w/scan_service.py`
- [x] T046 [US5] Render collapsible 52W rejection card grid in `frontend/src/components/W52RejectionBreakdown.tsx`
- [x] T047 [US5] Mount Rejection Breakdown on the 52W Scanner view in `frontend/src/App.tsx`

**Checkpoint**: Operators can explain why names were rejected from 52W buckets alone.

---

## Phase 8: User Story 6 — Top 5 and Least 5 Backtest Returns (Priority: P2)

**Goal**: After a completed scan, show Top 5 positive and Least 5 1-year **real book-trade** returns, including open MTM; exclude never-selected, insufficient-history, and data-failure names.

**Independent Test**: Fixture with six positive and six negative 1Y book-trade names fills both boards; never-selected and failed-attribution names absent; open holding included via MTM; 3Y detail toggle does not re-sort boards.

### Tests for User Story 6

- [x] T048 [P] [US6] Unit tests for 1Y window, real-book-only return, never-selected exclusion, open MTM, and failed-attribution exclusion in `backend/tests/unit/test_w52_attribution.py`

### Implementation for User Story 6

- [x] T049 [US6] Attribute per-name book trades and 1Y return (closed + scan-session MTM) in `backend/app/services/strategies/breakout52w/attribution.py`
- [x] T050 [US6] Build `top5_positive` and `least5` (no padding; return > 0 for Top 5) in `backend/app/services/strategies/breakout52w/attribution.py`
- [x] T051 [US6] Attach boards + 1Y period dates to ScanPayload in `backend/app/services/strategies/breakout52w/scan_service.py`
- [x] T052 [P] [US6] Render Top 5 / Least 5 tables with period footnote in `frontend/src/components/W52ReturnBoards.tsx`
- [x] T053 [US6] Mount return boards on the 52W Scanner view after summary in `frontend/src/App.tsx`

**Checkpoint**: Boards match clarify Q1/Q3 and spec FR-047–FR-048 / FR-061.

---

## Phase 9: User Story 7 — Strategy-Owned Technicals (Priority: P2)

**Goal**: Stock-detail Technicals show only 52W inputs (prior high, volume vs average, SMA ATR, market filter, rank, HWM/TSL when HOLD).

**Independent Test**: Open BUY, HOLD, volume-failed REJECT, market-off WATCH, and insufficient-history REJECT; confirm 52W tiles and no RSI / EMA / Bollinger / LTM +50% decision tiles.

### Implementation for User Story 7

- [x] T054 [US7] Build 52W Technicals snapshot (missing indicators `null` ≠ 0; include HWM/TSL on HOLD) on each recommendation row in `backend/app/services/strategies/breakout52w/scan_service.py`
- [x] T055 [US7] Implement `GET /scanner/w52/symbols/{symbol}` in `backend/app/routes/scanner.py`
- [x] T056 [P] [US7] Add `fetchW52SymbolDetail` in `frontend/src/api.ts`
- [x] T057 [US7] Branch Technicals on `09_52w_breakout` to render 52W tiles only in `frontend/src/components/StockDetailPanel.tsx`
- [x] T058 [US7] Hide Production RSI / EMA / Bollinger / RS tiles and LTM +50% tiles when 52W is active in `frontend/src/components/StockDetailPanel.tsx`

**Checkpoint**: Technicals explain 52W eligibility and trail without another engine’s indicators.

---

## Phase 10: User Story 8 — Backtest Tab (Priority: P2)

**Goal**: Detail Backtest tab shows book-attributed trades, headline metrics, equity vs NIFTY 500, drawdown, monthly grid, blotter; 1Y/3Y/5Y/All does not change scan-level boards.

**Independent Test**: Name with a historical slot shows trades/metrics; never-selected name shows empty/never-selected; failed attribution shows data-failure (not 0%); switching to 3Y leaves Top 5 on 1Y.

### Implementation for User Story 8

- [x] T059 [US8] Expose per-name backtest windows (`1Y` default, `3Y`, `5Y`, `All`) from book-attributed trades in `backend/app/services/strategies/breakout52w/attribution.py`
- [x] T060 [US8] Include book-level metrics and NIFTY 500 overlay series in ScanPayload / symbol detail in `backend/app/services/strategies/breakout52w/scan_service.py`
- [x] T061 [US8] Branch Backtest tab for 52W (equity, drawdown, monthly returns, trade log, best/worst) in `frontend/src/components/StockDetailPanel.tsx`
- [x] T062 [US8] Keep scan-level Top 5 / Least 5 on the fixed 1Y ranking when the detail window changes in `frontend/src/components/W52ReturnBoards.tsx` and `frontend/src/components/StockDetailPanel.tsx`

**Checkpoint**: Backtest tab is evidence for a name without inventing a different strategy.

---

## Phase 11: User Story 9 — Warmup, Market-Off, Trail Persistence, Disclosures (Priority: P3)

**Goal**: Dashboard shows WARMUP / MARKET_OFF / ACTIVE; market-off does not flatten; HWM/TSL survive restart; survivorship and known limits are visible.

**Independent Test**: Warmup dataset → STATUS=WARMUP and zero BUY; market-off with holdings → zero new BUY, HOLD remains, EXIT may fire; restart → TSL ≥ prior TSL if no new HWM; limitations visible.

### Tests for User Story 9

- [x] T063 [P] [US9] Unit test that reloaded book state does not lower TSL and that MarketOK false emits zero new buys in `backend/tests/unit/test_w52_book_state.py`

### Implementation for User Story 9

- [x] T064 [US9] Surface `book_status`, `market_ok`, `nifty_close`, `nifty_sma50`, and `warmup` on ScanPayload in `backend/app/services/strategies/breakout52w/scan_service.py`
- [x] T065 [US9] Render WARMUP / MARKET_OFF / ACTIVE chips and “no flatten on market-off” copy in `frontend/src/components/W52ScanSummary.tsx`
- [x] T066 [US9] Set and display `survivorship_biased` when only the current NIFTY 500 list is used in `backend/app/services/strategies/breakout52w/scan_service.py` and `frontend/src/components/W52ScanSummary.tsx`
- [x] T067 [US9] Show known-limitations copy (gap-through trail, state-not-cross, win rate vs payoff, look-ahead, not a forecast) on 52W results in `frontend/src/components/W52ScanSummary.tsx`

**Checkpoint**: Operators cannot mistake a market-off or warmup scan for a new-buy day, and trail state survives restart.

---

## Phase 12: Polish & Cross-Cutting Concerns

**Purpose**: Published fixtures, isolation audit, and quickstart validation.

- [x] T068 [P] Published first-cohort membership test (2020-08-27 set SJVN, DIXON, ATUL, JUBLFOOD, TATAELXSI, CDSL, SAREGAMA) in `backend/tests/unit/test_w52_selection_fixtures.py` when a frozen calendar fixture is present
- [x] T069 [P] Confirm no import of `backend/app/services/strategies/ltm` internals that would couple clocks, and no write to Production `scan_results` or `ltm_book_state`, in `backend/app/services/strategies/breakout52w/` and `backend/app/routes/scanner.py`
- [x] T070 Confirm 52W Technicals never render Wilder ATR, Darvas box, or LTM +50% as decision tiles in `frontend/src/components/StockDetailPanel.tsx`
- [x] T071 Run `specs/038-52w-high-breakout/quickstart.md` validation (kernel pytest, isolation POST, e2e latest payload, restart TSL)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS** all user stories
- **US1 (Phase 3)**: After Foundational — switcher only
- **US2 (Phase 4)**: After US1 routes exist (needs `/w52/latest` + strategies list); isolated Run
- **US3 (Phase 5)**: After US2 start/progress routes — 🎯 MVP scan
- **US4 (Phase 6)**: After US3 payload exists — signals, orders, holdings
- **US5 (Phase 7)**: After US4 evaluation rows exist — rejection grid
- **US6 (Phase 8)**: After US3 replay — boards (can overlap US4/US5 if payload fields are stubbed)
- **US7–US8 (Phases 9–10)**: After US3/US4 rows exist — detail tabs
- **US9 (Phase 11)**: After US4 summary exists — status + disclosures
- **Polish (Phase 12)**: After desired stories

### User Story Dependencies

| Story | Can start after | Depends on other stories? |
|-------|-----------------|---------------------------|
| US1 | Foundational | No |
| US2 | Foundational + US1 routes | Integrates with US1 switcher |
| US3 | US2 start/progress | Needs isolated Run |
| US4 | US3 payload | Needs completed scan |
| US5 | US3/US4 rows | Needs first-failure on rows |
| US6 | US3 replay | Independent of UI breakdown |
| US7 | US4 rows | Needs symbol in last scan |
| US8 | US6 attribution | Shares attribution module |
| US9 | US4 summary | Extends summary chips |

### Parallel Opportunities

- T002 / T003 after T001
- T007 / T008 / T009 / T010 after T003 (different files)
- T014 tests after kernel files exist (can be written first to fail)
- T017 with T015/T016
- T020 / T021
- T027 / T028
- T039 / T040
- T052 with T049–T051
- T056 with T054/T055
- T068 / T069

### Parallel Example: Foundational kernel

```text
Task: "Implement indicators in backend/app/services/strategies/breakout52w/indicators.py"
Task: "Implement BuySignal in backend/app/services/strategies/breakout52w/signal.py"
Task: "Implement trail in backend/app/services/strategies/breakout52w/trail.py"
Task: "Implement Mode B sizing in backend/app/services/strategies/breakout52w/portfolio.py"
```

### Parallel Example: User Story 4 UI

```text
Task: "Render W52ScanSummary in frontend/src/components/W52ScanSummary.tsx"
Task: "Render W52OrderList in frontend/src/components/W52OrderList.tsx"
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL)
3. Complete US1: button beside LTM
4. Complete US2: isolated Run + ignore second click
5. Complete US3: evaluate → replay → withhold recs until terminal 🎯
6. **STOP and VALIDATE** using `quickstart.md` sections 1, 3, and 4

### Incremental Delivery

1. Setup + Foundational → kernel ready
2. US1 → switcher demo
3. US2 → isolated Run demo
4. US3 → usable scan (MVP)
5. US4 → readable BUY/HOLD/WATCH/REJECT + orders
6. US5 → rejection honesty
7. US6 → Top 5 / Least 5
8. US7 + US8 → detail evidence
9. US9 → warmup / market-off / persist / disclosures
10. Polish → fixtures + isolation audit

### Parallel Team Strategy

After Foundational:

- Dev A: US1 → US2 → US3 (scan path)
- Dev B: US5 rejection + US6 attribution (backend-first)
- Dev C: US4 / US7 / US8 UI once payload fields land

---

## Notes

- [P] tasks = different files, no incomplete dependencies
- [Story] label maps task to spec user stories US1–US9
- Filter parity: live evaluate and replay MUST call the same indicator / signal / trail functions
- Isolated Run: 52W Run MUST NOT call `/scanner/ltm/runs` or Production start
- HOLD is a first-class signal (clarify Q1); do not count it as REJECT
- Second Run → 409, no cancel (clarify Q2)
- Per-name attribution failure publishes the rest (clarify Q3)
- Commit after each task or logical group
- Stop at any checkpoint to validate the story independently
