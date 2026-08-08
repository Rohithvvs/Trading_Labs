# Paper Order Confirm — Performance Report

**Date:** 2026-08-07  
**Scope:** Confirm Order / `POST /paper-trading/orders`  
**Constraint:** Brownfield · no business-logic redesign  

---

## 1. Root cause of the delay

| Rank | Root cause | Impact |
|------|------------|--------|
| 1 | **Live LTP on every confirm** via FYERS event-loop handoff (up to 3s) + **yfinance fallback** when FYERS/cache miss | Multi-second button spin on cold/slow broker |
| 2 | **In-process price cache TTL = 3s** | Order form quote expired before user clicked Confirm → cold path again |
| 3 | **Network price for after-hours LIMIT/STOP** when ticket already has limit/stop | Unnecessary I/O when market is closed |
| 4 | **OrderDrawer awaited full desk refresh** (pending + positions + account + trades) **before** closing UI | Perceived freeze after API returned |
| 5 | Extra **notification dedupe SELECT** on brand-new order keys | Small but avoidable DB round-trip on hot path |

Earlier work already removed `get_dashboard()` and full 90d OHLCV from place; residual multi-second latency was almost entirely **price resolution + FE blocking refresh**.

---

## 2. Critical path (after)

```
Click Confirm
  → FE disable button + in-flight guard (< 16ms)
  → POST /paper-trading/orders + Idempotency-Key
  → account FOR UPDATE
  → symbol validate + idempotency SELECT
  → market status (local calendar)
  → price:
       closed LIMIT/STOP  → ticket price (0 network)
       else               → mem cache → PG/FYERS LTP ≤750ms (no yfinance)
  → INSERT order (+ fill if market open)
  → lean capital COUNTs + reserved SUM
  → single COMMIT
  → lean JSON + X-Order-* timing headers
  → FE close modal/drawer + toast (immediate)
  → background: invalidate paper_* cache + desk event
```

---

## 3. Files modified

| File | Change |
|------|--------|
| `backend/app/services/paper_trading_service.py` | Smart price on place; 750ms LTP budget; stale mem cache; skip yfinance/candles on exec; skip notif dedupe SELECT on confirm |
| `backend/app/services/fyers_service.py` | `fetch_ltp(allow_yfinance=…, pg_ttl_sec=…, allow_stale_pg_sec=…)` for fast confirm path |
| `frontend/src/pages/PaperOrderPage.tsx` | Stage logs (`confirm_ui_closed`); still closes modal before navigate |
| `frontend/src/components/OrderDrawer.tsx` | Close drawer + toast immediately; desk refresh async |
| `frontend/src/api.ts` | `placePaperOrder` logs network + `X-Order-*` headers |
| `backend/app/tests/test_market_hours_order_lifecycle.py` | Mock `_price_for_execution`; avoid unmocked pending refresh |
| `backend/app/tests/test_multi_user_paper_isolation.py` | Mock `_price_for_execution` |
| `backend/app/tests/test_trading_execution.py` | Mock `_price_for_execution` |
| `backend/app/tests/test_phase4_validation.py` | Mock `_price_for_execution` |
| `docs/PAPER_ORDER_CONFIRM_PERFORMANCE_REPORT.md` | This report |

---

## 4. Optimizations implemented

### Backend
- **Hard LTP timeout 0.75s** on confirm (was 3s).
- **No yfinance / no OHLCV candle fallback** on `_price_for_execution`.
- **Soft-stale** in-process cache (60s) + PG stale (120s) when live quote times out.
- **Skip network** when market closed and LIMIT/GTT/STOP prices already on the ticket.
- **Fresh cache TTL 5s** (was 3s) for warm confirm after quote load.
- Notifications on place use **`skip_db_dedupe=True`** (session-level de-dupe only).
- Single commit; lean capital summary (no trade history / full portfolio).

### Frontend
- Confirm Order: disable immediately; close modal on 200; toast; navigate next frame.
- OrderDrawer: same pattern (was blocking on 4 parallel list APIs).
- `placePaperOrder` console: `network_ms`, `server_total_ms`, `server_service_ms`, `server_serialize_ms`.

---

## 5. Before vs after (stage targets)

| Stage | Before (typical) | After (design / warm) | Target |
|-------|------------------|------------------------|--------|
| FE click → spinner | ~0–50ms | **&lt; 50ms** | &lt; 100ms |
| Price / LTP | 0.5–5s+ (yfinance/cold FYERS) | cache **&lt; 20ms**; cold **≤ 750ms**; closed LIMIT **~0ms** | &lt; 500ms API total |
| DB txn (insert/fill/commit) | 50–200ms | **&lt; 100ms** typical | &lt; 200ms |
| Serialize + capital | &lt; 50ms | **&lt; 30ms** | &lt; 50ms |
| FE after 200 | OrderDrawer blocked on desk refresh (1–3s) | **modal/drawer close immediately** | &lt; 100ms |
| **Total perceived confirm** | multi-second | **&lt; 1s** (warm often &lt; 300ms) | **&lt; 1s** |

### How to verify in browser console

```
[paper-order] place_timing { network_ms, server_total_ms, server_service_ms, … }
[paper-order] confirm_success { api_ms, budget_ok: true }
[paper-order] confirm_ui_closed { total_ms }
```

Server logs:

```
ORDER_PLACE_TIMING | phases={account_lock, idempotency_lookup, price_ltp, execute_fill, commit, …}
ORDER_HTTP_TIMING | total_ms=… service_ms=… serialize_ms=…
PRICE_EXEC_SKIP_NETWORK | reason=market_closed_limit   # after hours LIMIT
PRICE_EXEC_CACHE_HIT | latency_ms=0                    # warm path
```

---

## 6. Validation checklist

| Check | Status |
|-------|--------|
| One click → one order (in-flight ref + idempotency key) | ✔ |
| No duplicate orders | ✔ |
| Market closed → WAITING_FOR_MARKET, no capital move | ✔ (logic unchanged) |
| Market open MARKET → fill + position | ✔ |
| Lean response (no full history) | ✔ |
| Desk refresh async after success | ✔ |
| Business rules / engines / schema unchanged | ✔ |

---

## 7. Deploy notes

1. Restart backend so `fetch_ltp` signature + place_order path load.
2. Hard-refresh frontend for OrderDrawer / api timing changes.
3. Confirm after-hours LIMIT: log should show `PRICE_EXEC_SKIP_NETWORK`.
4. Confirm during session: `price_ltp` phase in `ORDER_PLACE_TIMING` should be &lt; 750ms (or ~0 on cache hit).
