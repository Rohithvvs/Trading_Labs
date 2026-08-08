# Automated Paper Trading — Engine Comparison

**Status:** Implemented (brownfield)  
**Date:** 2026-08-07

## Purpose

Independently paper-trade every **BUY** from:

| Engine | Label |
|--------|--------|
| Production recommendation engine | `Production` |
| RE-001 Trend Continuation | `RE-001` |
| RE-002 Relative Strength Momentum | `RE-002` |

Same symbol may hold **up to three** open paper positions (one per engine). Positions are never merged.

## Apply migration

```bash
cd backend
alembic upgrade head
```

Revision: `20260807_auto_paper_engine`  
File: `backend/alembic/versions/20260807_auto_paper_engine_attribution.py`

## Configuration

| Env / setting | Default | Meaning |
|---------------|---------|---------|
| `AUTO_PAPER_TRADING_ENABLED` | `true` | Master switch |
| `AUTO_PAPER_TRADING_LAB_REQUIRES_PAPER_LINKED` | `false` | If `true`, RE lab BUY only auto-trades when stage is `PAPER_LINKED` |
| `AUTO_PAPER_TRADING_FORCE_LAB` | `false` | Bypass paper-linked gate for RE engines |
| `AUTO_PAPER_TRADING_ALLOCATION_PCT` | `0.05` | Fraction of available cash per auto BUY |
| `AUTO_PAPER_TRADING_USER_ID` | unset | Optional fixed user for system scans |
| `AUTO_PAPER_TRADING_SYSTEM_SCOPE` | `all` | When no scan user: `all` paper accounts, or `none` |

## Auto execution path

```
Production BUY (orchestrator) ──► place_auto_paper_buy(engine=Production)
RE-001 BUY (persist after eval) ──► place_auto_paper_buy(engine=RE-001)
RE-002 BUY (persist after eval) ──► place_auto_paper_buy(engine=RE-002)
         │
         ▼
PaperTradingService.place_order (MARKET CNC)  →  always lands on Orders first
         │
         ├─ market CLOSED → WAITING_FOR_MARKET (no position)
         └─ market OPEN   → READY_TO_EXECUTE → fill → Position (source_engine_id)
         │
         ▼  (09:15 IST + heartbeat retries)
execute_all_pending_market_open_orders → Positions + Portfolio
```

See also: `docs/AUTO_PAPER_ORDER_EXECUTION.md` for full status machine and UI columns.

Duplicate prevention: skip if OPEN position **or** open BUY order already exists for `(account, symbol, engine)`.

## Unique constraint

Open positions are unique on:

```text
(account_id, symbol, source_engine_id) WHERE status = 'OPEN'
```

## Validation scenarios

| # | Input | Expected |
|---|--------|----------|
| 1 | ABC Production/RE-001/RE-002 all BUY | 3 paper positions |
| 2 | XYZ Production BUY, RE-001 WATCH, RE-002 REJECT | 1 position (Production) |
| 3 | ABC Production open + new Production BUY | No duplicate |
| 4 | ABC Production open + RE-001 BUY | New RE-001 position |
| 5 | Paper Desk | Engine badge on every row |
| 6 | Analytics | `by_engine` metrics independent |

## Analytics API

```
GET /api/v1/paper-trading/analytics?period=all&recommendation_engine=RE-001
```

Response always includes `by_engine.Production`, `by_engine.RE-001`, `by_engine.RE-002`.
