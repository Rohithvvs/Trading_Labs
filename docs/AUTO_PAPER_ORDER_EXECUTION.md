# Automatic Paper Order Execution Workflow

**Status:** Implemented (brownfield)  
**Date:** 2026-08-07

## Purpose

Whenever **Production**, **RE-001**, or **RE-002** emits a **BUY** signal, automatically create an independent paper order. Orders appear first on **Paper Desk → Orders**, never jump straight to Positions. When the market opens, waiting orders are executed into engine-scoped positions.

## End-to-end flow

```
Recommendation Engine (Production | RE-001 | RE-002)
        │
        ▼  BUY only
place_auto_paper_buy (auto_paper_trading_service)
        │
        ▼
PaperTradingService.place_order (MARKET CNC, source_engine_id tagged)
        │
        ├─ Market CLOSED ──► status = WAITING_FOR_MARKET
        │                    Orders tab only · no position · no capital hold
        │
        └─ Market OPEN ────► READY_TO_EXECUTE → fill → Position + Portfolio
                             (order still created first in the same path)

Market open (09:15 IST scheduler + intraday heartbeat retry)
        │
        ▼
execute_all_pending_market_open_orders
        │
        ▼
WAITING_FOR_MARKET / FAILED / READY_TO_EXECUTE
        │
        ▼  success
EXECUTED/FILLED → Position (same engine) → Portfolio → History (on exit)
```

## Supported engines (independent)

| Engine | Label |
|--------|--------|
| Production recommendation engine | `Production` |
| RE-001 Trend Continuation | `RE-001` |
| RE-002 Relative Strength Momentum | `RE-002` |

Same symbol may create **up to three** open orders/positions (one per engine). Orders and positions are **never merged**.

### Example

```
ABC  Production = BUY
ABC  RE-001     = BUY
ABC  RE-002     = BUY
```

**Orders tab (market closed):**

| Symbol | Engine | Status |
|--------|--------|--------|
| ABC | Production | WAITING_FOR_MARKET |
| ABC | RE-001 | WAITING_FOR_MARKET |
| ABC | RE-002 | WAITING_FOR_MARKET |

**Positions:** none until market open.

## Order statuses

| Status | Meaning |
|--------|---------|
| `PENDING` | Working order (e.g. limit not yet triggered) |
| `WAITING_FOR_MARKET` | Market closed; held on Orders tab |
| `PENDING_MARKET_OPEN` | Legacy alias of `WAITING_FOR_MARKET` (still accepted) |
| `READY_TO_EXECUTE` | Market open; about to fill / fill in progress |
| `FAILED` | Retryable execution failure (price unavailable, etc.) |
| `FILLED` / `EXECUTED` | Successfully executed into a position |
| `CANCELLED` | User/system cancelled |
| `REJECTED` | Terminal reject (e.g. insufficient cash) |

## Duplicate prevention

Skip auto order only when **all** match:

1. Same **symbol**
2. Same **recommendation engine**
3. Existing **open order** (`OPEN_ORDER_STATUSES`) **or** open **position** for that engine

Allowed:

- `ABC + Production` open → still place `ABC + RE-001` and `ABC + RE-002`

## Market-open execution

| Trigger | When |
|---------|------|
| Cron `execute_pending_market_open_orders` | Mon–Fri 09:15 IST |
| Intraday heartbeat | Every 15 min while market open (retries `FAILED`) |
| `POST /api/v1/paper-trading/orders/execute-pending-market-open` | Manual / recovery |
| Market engine ticks | Live fill path for working orders |
| Dashboard refresh | Account-scoped `_refresh_pending_orders` |

On success: remove from open orders, create/update **engine-scoped** position, update portfolio cash, leave trade history for later exit.

On failure: keep order on Orders tab as `FAILED` with `paused_reason`; automatic retry on next sweep.

## Hooks (do not change recommendation algorithms)

| Source | Hook |
|--------|------|
| Production | `orchestrator_agent` → `maybe_auto_paper_from_production` |
| RE-001 | `re001/runner._persist_safe` → `maybe_auto_paper_from_lab_decision` |
| RE-002 | `re002/runner` → `maybe_auto_paper_from_lab_decision` |

All hooks are **fail-open** (never abort scanner / lab pipeline).

## Configuration

| Env / setting | Default | Meaning |
|---------------|---------|---------|
| `AUTO_PAPER_TRADING_ENABLED` | `true` | Master switch |
| `AUTO_PAPER_TRADING_LAB_REQUIRES_PAPER_LINKED` | `false` | If true, RE lab BUY only when stage is `PAPER_LINKED` |
| `AUTO_PAPER_TRADING_FORCE_LAB` | `false` | Bypass paper-linked gate |
| `AUTO_PAPER_TRADING_ALLOCATION_PCT` | `0.05` | Fraction of available cash per auto BUY |
| `AUTO_PAPER_TRADING_USER_ID` | unset | Optional fixed user for system scans |
| `AUTO_PAPER_TRADING_SYSTEM_SCOPE` | `all` | `all` paper accounts, or `none` |

## Schema

Migration: `20260807_auto_paper_engine`  
- `source_engine_id` NOT NULL on orders/positions/trade history  
- Unique open position: `(account_id, symbol, source_engine_id) WHERE status = 'OPEN'`

## Paper Desk UI

**Orders** columns: Order ID, Symbol, Recommendation Engine, Signal, Order Type, Quantity, Order Price, Current Price, Order Status, Created Time, Execution Time, Remarks.

**Positions / History:** Recommendation Engine badge on every row; analytics remain engine-specific via `by_engine` / `recommendation_engine` filter.

## Validation scenarios

| # | Input | Expected |
|---|--------|----------|
| 1 | 3 engines BUY, market closed | 3 Orders (`WAITING_FOR_MARKET`), 0 Positions |
| 2 | Market opens | 3 executed → 3 Positions (one per engine) |
| 3 | Production BUY, RE-001 WATCH, RE-002 REJECT | 1 Order → 1 Position after execution |
| 4 | Duplicate BUY same engine while order pending | No second order |
| 5 | Paper Desk Orders → Positions → History | Engine badge at every stage |

## Related

- `docs/AUTO_PAPER_TRADING_ENGINE_COMPARISON.md` — engine comparison analytics
- `backend/app/services/auto_paper_trading_service.py` — BUY hooks
- `backend/app/services/paper_trading_service.py` — place + market-open fill
