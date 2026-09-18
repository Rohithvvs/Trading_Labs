# Implementation Plan: Long-Term Buy & Hold Momentum Scanner

**Branch**: `037-ltm-scanner-dashboard` | **Date**: 2026-08-15 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/037-ltm-scanner-dashboard/spec.md` (Clarified session 2026-08-15)  
**Status**: Design complete — **no application code, migrations, or schema changes in this step**

**Note**: This is the master implementation plan. It explains *how* the feature will be built. It does **not** contain implementation bodies or `tasks.md` (`/speckit-tasks` produces that).

---

## Summary

Add **Long-Term Buy & Hold Momentum** (`17_long_term_mom`) as a **first-class Scanner strategy**, independent of the Production composite screener and of RE-001 / RE-002 lab engines.

A dedicated LTM scan:

1. Reads the **strategy-grade** daily dataset (`daily_ohlcv` + `index_ohlcv`).
2. Evaluates NIFTY 500 with the locked rules (252-session momentum, strict `> +50%` gate, top 10, 252-session rebalance clock).
3. Runs **one vectorized book replay** (same filters) **before** publishing recommendations.
4. Attributes per-name 1-year book-trade returns (closed trades + open mark-to-market) for Top 5 / Least 5.
5. Surfaces strategy-owned Rejection Breakdown, recommendations, Technicals, and Backtest on the existing Scanner dashboard.

**Brownfield approach:** new strategy package + namespaced scan persistence + thin Scanner UI switcher. Do **not** rewrite `OrchestratorAgent`, do **not** overwrite Production `scan_results`, do **not** feed LTM into the composite score engine.

**Clarifications locked (2026-08-15):**

| ID | Decision |
|----|----------|
| Q1 | Backtest every name with valid 252-session history; skip data-failure / insufficient-history names |
| Q2 | Top 5 / Least 5 use a **fixed last-1-year** window; detail tab may still toggle 1Y / 3Y / 5Y / All |
| Q3 | Board return = that name’s **real top-10 book trades** only; never selected in the year → excluded |
| Q4 | Include **mark-to-market** of still-open book positions as of the scan session (not a live exit) |

---

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript / React 18 (frontend)  
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Alembic, Pydantic, pandas (aligned close matrix + vectorized rank), existing Vite React SPA, existing Scanner / StockDetailPanel  
**Storage**: PostgreSQL — strategy-grade `daily_ohlcv` / `index_ohlcv` (read); **new** namespaced strategy-scan + LTM book-state tables (write). Production `scan_results` singleton **untouched**.  
**Testing**: pytest + pytest-asyncio (formula, clock, fixtures, scan contract); Vitest for Scanner switcher / boards / Technicals / Backtest tabs  
**Target Platform**: Existing FastAPI + React two-tier app  
**Project Type**: Brownfield web application (backend + frontend)  
**Performance Goals**: LTM scan of ~500 names + one book replay + 1-year attribution in **≤ 60 seconds** p95 on a warm dataset; recommendation list withheld until that replay finishes  
**Constraints**: Same filters for scan and backtest; no Production/RE overwrite; no shorts/leverage/stops; Mode A default; survivorship label when PIT membership is missing; feature permission `advanced_scanner`; freshness gate `MARKET_DATA_STALE` blocks start  
**Scale/Scope**: ~500–755 NIFTY 500 symbols; ≥252+ sessions required; published fixture window ~1,720 sessions; one LTM scan at a time

---

## Constitution Check

*GATE: Constitution template is placeholder (not project-specific principles). Apply brownfield + clarified-spec gates.*

| Gate | Status | Notes |
|------|--------|-------|
| Reuse before rewrite | PASS | Reuse strategy-grade reader, universe, freshness gate, Scanner shell, paper handoff |
| Production scan authority | PASS | LTM never writes Production `scan_results` / `scanner:latest:v1` |
| Clarified spec honored | PASS | Q1–Q4 encoded in engine + UI contracts |
| Filter parity | PASS | One eligibility/rank module used by live evaluate **and** book replay |
| No extra technicals | PASS | Technicals tab is LTM-owned only (no RSI/EMA/ATR decision tiles) |
| Freshness before scan | PASS | Reuse 033 `MARKET_DATA_STALE` gate |
| Tech stack fit | PASS | Python/PG/pandas/React already in repo |
| Advisory only | PASS | No live broker orders; paper prefill reused |

**Post-design re-check:** PASS — design is additive (new package + namespaced tables + UI switcher). No constitution/complexity violations.

---

## Project Structure

### Documentation (this feature)

```text
specs/037-ltm-scanner-dashboard/
├── plan.md                 # This file
├── research.md             # Phase 0
├── data-model.md           # Phase 1
├── quickstart.md           # Phase 1
├── contracts/
│   ├── ltm-algorithm.md    # Normative compute contract
│   ├── ltm-scan-api.md     # HTTP / payload contract
│   └── ltm-ui-contract.md  # Scanner / detail surfaces
├── checklists/requirements.md
└── tasks.md                # /speckit-tasks (not this command)
```

### Source Code (repository root) — planned placement

```text
backend/app/
├── models/
│   └── ltm_strategy.py                 # NEW: book state + strategy scan latest/runs
├── services/
│   ├── market_data_ingestion/          # REUSE reader + freshness
│   ├── universe_service.py             # REUSE NIFTY 500 membership
│   ├── scan_execution_service.py       # UNCHANGED production path
│   └── strategies/
│       └── ltm/                        # NEW package
│           ├── __init__.py
│           ├── identity.py             # ids, display name, reason codes
│           ├── calendar.py             # master session index, warmup, rebalance clock
│           ├── momentum.py             # Momentum_252, eligibility, deterministic rank
│           ├── portfolio.py            # Mode A (default) + optional Mode B
│           ├── book_engine.py          # vectorized book replay + current evaluate
│           ├── attribution.py          # per-name 1Y book trades + open MTM
│           ├── rejection.py            # first-failure buckets
│           ├── scan_service.py         # orchestrate evaluate → replay → publish
│           └── persistence.py          # book state + namespaced scan payload
├── routes/
│   └── scanner.py                      # EXTEND: strategy query + LTM routes
└── tests/ + backend/tests/unit/
    └── test_ltm_*.py                   # NEW formula / clock / fixture / contract tests

frontend/src/
├── App.tsx                             # EXTEND: strategy switcher on Scanner
├── api.ts                              # EXTEND: fetch LTM latest / start LTM scan
├── components/
│   ├── LtmScanSummary.tsx              # NEW summary + empty banner
│   ├── LtmRejectionBreakdown.tsx       # NEW first-failure grid
│   ├── LtmReturnBoards.tsx             # NEW Top 5 / Least 5
│   ├── CandidateTable.tsx              # REUSE for recommendation rows
│   └── StockDetailPanel.tsx            # EXTEND: LTM Technicals + Backtest branches
```

**Structure Decision**: Brownfield two-tier app. New isolated `services/strategies/ltm` package (same idea as the leftover STR-005 layout, but **new source**, not a revival of that bytecode). Production orchestrator and RE lab packages stay closed.

---

## Complexity Tracking

> No constitution violations. Table left empty on purpose.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

---

## Phase 0 — Research outcomes

See [research.md](./research.md). All Technical Context unknowns resolved:

- LTM is a **separate Scanner strategy**, not a Production scoring tweak.
- Scan-time “backtest every history-valid name” is implemented as **one book replay + per-name attribution**, not 500 independent engines.
- Persistence is **namespaced by `strategy_id`** so Production latest scan is never overwritten.
- Data SoT is strategy-grade `daily_ohlcv` / `index_ohlcv` with the 033 freshness gate.

---

## Phase 1 — Design artifacts

| Artifact | Role |
|----------|------|
| [data-model.md](./data-model.md) | Book state, scan run, result payload, first-failure, trade, board row |
| [contracts/ltm-algorithm.md](./contracts/ltm-algorithm.md) | Formulas, clock, Mode A, fill models, 1Y MTM boards |
| [contracts/ltm-scan-api.md](./contracts/ltm-scan-api.md) | Start / progress / latest / detail endpoints |
| [contracts/ltm-ui-contract.md](./contracts/ltm-ui-contract.md) | Switcher, summary, breakdown, boards, Technicals, Backtest |
| [quickstart.md](./quickstart.md) | How to validate formula fixtures + a dry scan |

---

## Implementation approach (for `/speckit-tasks`)

### Slice 0 — Identity and algorithm kernel (P1)

Pure functions: momentum, eligibility, rank, selection, clock, Mode A sizing. Fixture tests from spec Acceptance Fixtures (exact +50% ineligible; six published membership sets when frozen data is present).

### Slice 1 — Book engine + 1Y attribution (P1)

Vectorized replay on an aligned close matrix. Persist `sessions_since_rebalance` / `last_rebalance_date`. Attribute per-name closed trades + open MTM. Top 5 / Least 5 builders.

### Slice 2 — Scan service + API (P1)

Freshness gate → evaluate today → run book replay → **then** persist namespaced payload → stream progress (`evaluating` → `backtesting` → `publishing`). Recommendations never marked final before replay completes.

### Slice 3 — Scanner UI (P1/P2)

Strategy switcher, LTM summary, empty BUY banner, Rejection Breakdown, recommendation table, Top 5 / Least 5, warmup / mid-cycle / rebalance badges.

### Slice 4 — Detail Technicals + Backtest (P2)

LTM-owned tiles only. Backtest tab consumes book-attributed trades; window toggle does not re-rank boards.

### Slice 5 — Disclosures + Mode B switch (P3)

Survivorship label, known-limitations copy, optional Mode B research toggle (does not change default live book).

---

## Non-goals (plan-level)

- Changing Production composite scoring or RE-001 / RE-002.
- Point-in-time NIFTY 500 vendor work (label survivorship if only current list exists).
- Live broker adapter / netting remaining names.
- Optimizing the 0.50 threshold or 10-name cap.
- Restoring deleted STR-005 Python sources; LTM does not import that package.
