# Implementation Plan: 52-Week High Breakout Scanner

**Branch**: `038-52w-high-breakout` | **Date**: 2026-08-16 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/038-52w-high-breakout/spec.md` (Clarified session 2026-08-16)  
**Status**: Design complete — **no application code, migrations, or schema changes in this step**

**Note**: This is the master implementation plan. It explains *how* the feature will be built. It does **not** contain implementation bodies or `tasks.md` (`/speckit-tasks` produces that).

---

## Summary

Add **52-Week High Breakout** (`09_52w_breakout`) as a **first-class Scanner strategy**, independent of Production, RE-001 / RE-002, and Long-Term Buy & Hold Momentum (`17_long_term_mom`).

A dedicated 52W scan:

1. Reads the **strategy-grade** daily dataset (`daily_ohlcv` high/low/close/volume + `index_ohlcv`).
2. Evaluates NIFTY 500 with the locked rules (close ≥ prior 252-session high, volume > SMA20, NIFTY 500 > SMA50, 10% × 10 slots, 3-ATR trail).
3. Runs **one vectorized book replay** (same filters) **before** publishing recommendations.
4. Attributes per-name 1-year book-trade returns (closed trades + open mark-to-market) for Top 5 / Least 5.
5. Surfaces strategy-owned Rejection Breakdown, BUY / **HOLD** / WATCH / REJECT, today’s EXIT-then-BUY order list, Technicals, and Backtest on the existing Scanner dashboard.

**Brownfield approach:** new `services/strategies/breakout52w` package + `w52_book_state` + reuse namespaced `strategy_scan_*` + thin Scanner UI button beside LTM. Do **not** rewrite `OrchestratorAgent`, do **not** overwrite Production or LTM latest scans, do **not** feed 52W into the composite score engine.

**Clarifications locked (2026-08-16):**

| ID | Decision |
|----|----------|
| Q1 | Still-open names show **HOLD** in Scan results; omitted from Rejection Breakdown; same-session EXIT is not HOLD |
| Q2 | Second Run while in flight is **ignored** (409 `W52_SCAN_IN_PROGRESS`); no cancel, no queue |
| Q3 | Per-name backtest/attribution failure = `data_source_failure`; publish the rest; do not cancel today’s evaluation signal |

---

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript / React 18 (frontend)  
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Alembic, Pydantic, pandas (aligned OHLCV matrices + vectorized indicators), existing Vite React SPA, existing Scanner / StockDetailPanel / LTM switcher  
**Storage**: PostgreSQL — strategy-grade `daily_ohlcv` / `index_ohlcv` (read); reuse `strategy_scan_latest` / `strategy_scan_runs` keyed by `09_52w_breakout`; **new** `w52_book_state` (HWM/TSL). Production `scan_results` and `ltm_book_state` **untouched**.  
**Testing**: pytest + pytest-asyncio (indicators, trail, book, fixtures, scan contract); Vitest for switcher / HOLD / boards / Technicals / Backtest  
**Target Platform**: Existing FastAPI + React two-tier app  
**Project Type**: Brownfield web application (backend + frontend)  
**Performance Goals**: 52W scan of ~500 names + one daily-trail book replay + 1-year attribution in **≤ 90 seconds** p95 on a warm dataset (heavier than LTM’s annual clock); recommendation list withheld until every history-valid backtest is terminal  
**Constraints**: Same filters for scan and backtest; isolated Run; ignore second click; SMA-ATR not Wilder; market filter does not flatten; HOLD is not a rejection; survivorship label when PIT membership is missing; feature permission `advanced_scanner`; freshness gate `MARKET_DATA_STALE` blocks start  
**Scale/Scope**: ~500–755 NIFTY 500 symbols; ≥253 sessions of highs + 50 of the index; published fixture window ~1,720 sessions; one 52W scan at a time

---

## Constitution Check

*GATE: Constitution template is placeholder (not project-specific principles). Apply brownfield + clarified-spec gates.*

| Gate | Status | Notes |
|------|--------|-------|
| Reuse before rewrite | PASS | Reuse strategy-grade reader, universe, freshness gate, Scanner shell, paper handoff, `strategy_scan_*` |
| Production / LTM scan authority | PASS | 52W never writes Production `scan_results` or `ltm_book_state` |
| Clarified spec honored | PASS | Q1 HOLD, Q2 ignore second Run, Q3 partial attribution publish |
| Filter parity | PASS | One indicator/signal/trail module used by live evaluate **and** book replay |
| No extra technicals | PASS | Technicals tab is 52W-owned (ATR/HWM/TSL yes; RSI/EMA/LTM +50% no) |
| Freshness before scan | PASS | Reuse 033 `MARKET_DATA_STALE` gate |
| Isolated run | PASS | Dedicated lock + routes; LTM/Production start paths unchanged |
| Trail persistence | PASS | `w52_book_state` stores HWM/TSL; restart must not lower TSL |
| Tech stack fit | PASS | Python/PG/pandas/React already in repo |
| Advisory only | PASS | No live broker orders; paper prefill reused |

**Post-design re-check:** PASS — design is additive (new package + one table + UI button). No constitution/complexity violations.

---

## Project Structure

### Documentation (this feature)

```text
specs/038-52w-high-breakout/
├── plan.md                 # This file
├── research.md             # Phase 0
├── data-model.md           # Phase 1
├── quickstart.md           # Phase 1
├── contracts/
│   ├── w52-algorithm.md    # Normative compute contract
│   ├── w52-scan-api.md     # HTTP / payload contract
│   └── w52-ui-contract.md  # Scanner / detail surfaces
├── checklists/requirements.md
└── tasks.md                # /speckit-tasks (not this command)
```

### Source Code (repository root) — planned placement

```text
backend/app/
├── models/
│   └── w52_strategy.py                 # NEW: w52_book_state
├── services/
│   ├── market_data_ingestion/          # REUSE reader + freshness
│   ├── universe_service.py             # REUSE NIFTY 500 membership
│   ├── scan_execution_service.py       # UNCHANGED production path
│   └── strategies/
│       ├── ltm/                        # UNCHANGED
│       └── breakout52w/                # NEW package
│           ├── __init__.py
│           ├── identity.py             # ids, lock, cache, failure codes
│           ├── indicators.py           # High_252_prior, Vol_SMA20, ATR14 SMA, MarketOK, Mom60
│           ├── signal.py               # BuySignal state + first-failure
│           ├── trail.py                # HWM / TSL ratchet, NaN-ATR fallback
│           ├── portfolio.py            # Mode B 10% × 10
│           ├── costs.py                # NSE delivery (or thin wrapper on backtest_service)
│           ├── book_engine.py          # session order: exits then entries; vectorized replay
│           ├── attribution.py          # per-name 1Y book trades + open MTM
│           ├── rejection.py            # first-failure buckets (HOLD excluded)
│           ├── scan_service.py         # freshness → evaluate → replay → publish
│           └── persistence.py          # book state + namespaced scan payload
├── routes/
│   └── scanner.py                      # EXTEND: strategies list + /w52/* routes
└── tests/ + backend/tests/unit/
    └── test_w52_*.py                   # NEW kernel / trail / fixture / contract tests

frontend/src/
├── App.tsx                             # EXTEND: 52W button beside LTM; isolated Run
├── api.ts                              # EXTEND: fetch / start / poll w52
├── types.ts                            # EXTEND: HOLD + w52 fields
├── components/
│   ├── W52ScanSummary.tsx              # NEW summary + empty / market-off banners
│   ├── W52RejectionBreakdown.tsx       # NEW first-failure grid
│   ├── W52ReturnBoards.tsx             # NEW Top 5 / Least 5
│   ├── W52OrderList.tsx                # NEW EXIT then BUY
│   ├── CandidateTable.tsx              # REUSE (HOLD badge)
│   └── StockDetailPanel.tsx            # EXTEND: 52W Technicals + Backtest branch
```

**Structure Decision**: Brownfield two-tier app. New isolated `services/strategies/breakout52w` package, same idea as `services/strategies/ltm`. Production orchestrator and LTM package stay closed. Scanner UI grows a third strategy tab, not a new dashboard.

---

## Complexity Tracking

> No constitution violations. Table left empty on purpose.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

---

## Phase 0 — Research outcomes

See [research.md](./research.md). All Technical Context unknowns resolved:

- 52W is a **separate Scanner strategy**, not an LTM mode and not a Production scoring tweak.
- Scan-time “backtest every history-valid name” is **one book replay + per-name attribution**, not 500 independent engines.
- Persistence is **namespaced** (`strategy_scan_*` + `w52_book_state`) so Production and LTM latest scans are never overwritten.
- Data SoT is strategy-grade `daily_ohlcv` (high/low/volume required) + `index_ohlcv` with the 033 freshness gate.
- Second Run → 409; partial attribution failure still publishes.

---

## Phase 1 — Design artifacts

| Artifact | Role |
|----------|------|
| [data-model.md](./data-model.md) | Book state with HWM/TSL, scan run, payload, HOLD, first-failure, boards |
| [contracts/w52-algorithm.md](./contracts/w52-algorithm.md) | Indicators, state signal, trail, Mode B, fixtures |
| [contracts/w52-scan-api.md](./contracts/w52-scan-api.md) | `/scanner/w52/*` start / progress / latest / detail; isolation |
| [contracts/w52-ui-contract.md](./contracts/w52-ui-contract.md) | Button beside LTM, isolated Run, HOLD, breakdown, boards, Technicals, Backtest |
| [quickstart.md](./quickstart.md) | How to validate trail fixtures + a dry isolated scan |

---

## Implementation approach (for `/speckit-tasks`)

### Slice 0 — Identity and algorithm kernel (P1)

Pure functions: prior 252-high, volume SMA, SMA-ATR (fail Wilder), MarketOK, Momentum_60, BuySignal, first-failure order, Mode B sizing. Fixture tests from spec Acceptance Fixtures (close-equals-high passes; volume-equals-average fails; trail ratchet; first-day 2020-08-27 set when frozen data is present).

### Slice 1 — Book engine + trail persistence + 1Y attribution (P1)

Session-ordered replay on aligned OHLCV. Persist cash, holdings, HWM, TSL, `sold_today`, last session. Restart must not lower TSL. Attribute per-name closed trades + open MTM. Top 5 / Least 5 builders. Per-name attribution failure → `data_source_failure` without failing the run.

### Slice 2 — Scan service + API (P1)

Freshness gate → evaluate today → run book replay → **then** persist namespaced payload → stream progress (`evaluating` → `backtesting` → `publishing`). Recommendations never marked final before every history-valid job is terminal. `POST` while active → 409 `W52_SCAN_IN_PROGRESS`. LTM and Production routes unchanged.

### Slice 3 — Scanner UI (P1/P2)

52-Week High Breakout button beside LTM, this view’s Run only, summary (including HOLD), empty / market-off banners, Rejection Breakdown, recommendation table with HOLD, EXIT-then-BUY order list, Top 5 / Least 5, warmup / market-off / active badges. Disable Run while in flight.

### Slice 4 — Detail Technicals + Backtest (P2)

52W-owned tiles only (prior high, volume vs average, SMA ATR, market filter, HWM/TSL). Backtest tab consumes book-attributed trades; window toggle does not re-rank boards.

### Slice 5 — Disclosures (P3)

Survivorship label, known-limitations copy (gap-through trail, state-not-cross, win rate vs payoff, open 2026 drawdown).

---

## Non-goals (plan-level)

- Changing Production composite scoring, RE-001 / RE-002, or LTM rules / tables.
- Point-in-time NIFTY 500 vendor work (label survivorship if only current list exists).
- Live broker adapter.
- Darvas box, Wilder ATR, market-off flatten, 2× volume, 365-calendar highs.
- Optimizing the 3-ATR multiple, 252 window, or 10-name cap.
- A shared “run all strategies” action.
- Redesigning the entire Scanner chrome beyond the 52W button, Run, summary, breakdown, boards, table, Technicals, and Backtest.
