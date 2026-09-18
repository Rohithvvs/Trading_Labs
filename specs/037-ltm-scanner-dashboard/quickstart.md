# Quickstart: Validate Long-Term Buy & Hold Momentum Scanner

**Feature**: `037-ltm-scanner-dashboard`  
**Audience**: Implementer / reviewer after `/speckit-implement`  
**Do not** treat this file as a task list. Tasks live in `tasks.md` (not created by `/speckit-plan`).

---

## Prerequisites

- Backend Python 3.11+ venv with existing `backend/requirements.txt`
- PostgreSQL with strategy-grade tables from spec 033 (`daily_ohlcv`, `index_ohlcv`)
- NIFTY 500 universe seeded (`UniverseService.get_active_nifty500_symbols` non-empty)
- Latest completed NSE session present (or freshness gate will block)
- Authenticated user with feature `advanced_scanner`
- Frontend dev server as in the existing README

---

## 1. Algorithm kernel (no server)

From `backend/`:

```text
pytest tests/unit/test_ltm_momentum.py tests/unit/test_ltm_clock.py tests/unit/test_ltm_selection.py -q
```

**Expect:**

| Case | Result |
|------|--------|
| C_t=150, C_t-252=100 | ineligible |
| C_t=150.01, C_t-252=100 | eligible |
| Missing C_t-252 | ineligible |
| Session 251 | no orders |
| 15 eligible on first rebalance | exactly 10 names, highest momentum |
| 0 eligible | 100% cash, clock resets |
| Tie on momentum | ticker ascending |

If a frozen published calendar is available, also run membership tests for the six cohort dates in [spec.md](./spec.md) Acceptance Fixtures.

---

## 2. Attribution / boards

```text
pytest tests/unit/test_ltm_attribution.py -q
```

**Expect:**

- History-valid name never selected in last 1Y → backtest object exists, **absent** from Top 5 / Least 5
- Insufficient history → no backtest object
- Failed +50% today but selected last cohort → may appear on boards
- Open holding → 1Y return includes MTM; no exit order emitted
- Board window is last 1Y even if detail asks for 3Y

---

## 3. Freshness block

With latest session withheld (or gate forced stale):

```text
POST /scanner/ltm/runs
```

**Expect:** `MARKET_DATA_STALE`; Production `GET /scanner/latest` unchanged.

---

## 4. End-to-end scan (warm data)

1. `POST /scanner/ltm/runs`
2. Poll `GET /scanner/ltm/runs/{scan_id}` until `completed` (or watch progress: evaluating → backtesting → publishing)
3. `GET /scanner/ltm/latest`

**Expect:**

- `recommendations_final` is true only on `completed`
- `strategy_id` is `17_long_term_mom`
- `rejection_breakdown` uses LTM codes only
- `top5_positive` length ≤ 5 and all returns > 0
- Production `GET /scanner/latest` payload is bit-for-bit the same as before the LTM run (no overwrite)

---

## 5. UI walkthrough

1. Open Scanner, select **Long-Term Buy & Hold Momentum** (name visible).
2. Run LTM scan. Confirm the recommendation table stays non-final until backtesting finishes.
3. Read summary cards and Rejection Breakdown.
4. Confirm Top 5 period label is the last 1 year.
5. Open a BUY or WATCH name → Technicals show momentum / closes / rank / gate only.
6. Open Backtest → switch to 3Y; Top 5 on the list view still 1Y.
7. Mid-cycle: selected names are WATCH, sessions-to-rebalance visible, no new BUY.
8. Warmup dataset (if available): STATUS=WARMUP, zero BUY/WATCH.

---

## 6. Regression (Production)

```text
pytest backend/tests/unit/test_market_data_scanner_gate.py backend/app/tests/test_scanner_routes_cached.py -q
```

Production scan start, cache key `scanner:latest:v1`, and composite scoring MUST still pass.

---

## Mapping

| Check | Spec / contract |
|-------|-----------------|
| Formulas and fixtures | [contracts/ltm-algorithm.md](./contracts/ltm-algorithm.md), spec Acceptance Fixtures |
| Payload / routes | [contracts/ltm-scan-api.md](./contracts/ltm-scan-api.md) |
| Dashboard behaviour | [contracts/ltm-ui-contract.md](./contracts/ltm-ui-contract.md) |
| Tables / JSON | [data-model.md](./data-model.md) |
