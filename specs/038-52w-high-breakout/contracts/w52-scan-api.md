# Contract: 52-Week High Breakout Scanner API

**Feature**: `038-52w-high-breakout`  
**Auth**: Existing session; feature key `advanced_scanner`  
**Isolation**: These routes MUST NOT read or write Production `GET /scanner/latest` or LTM `/scanner/ltm/*`

Logical paths (mounted under `/scanner`):

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/scanner/strategies` | List registered strategies (Production + LTM + **52W**) |
| POST | `/scanner/w52/runs` | Start 52W scan only |
| GET | `/scanner/w52/runs/{scan_id}` | Progress / status |
| GET | `/scanner/w52/latest` | Latest 52W payload |
| GET | `/scanner/w52/symbols/{symbol}` | Detail: technicals + backtest windows |

---

## GET /scanner/strategies

Existing endpoint. MUST add:

```json
{ "id": "09_52w_breakout", "display_name": "52-Week High Breakout", "short_name": "52W" }
```

Order: Production (if listed), Long-Term Buy & Hold Momentum, **52-Week High Breakout** immediately after LTM.

---

## POST /scanner/w52/runs

Starts **only** `09_52w_breakout`. MUST NOT start LTM or Production.

**Preconditions:** freshness gate pass; no other 52W scan in `queued` / `evaluating` / `backtesting` / `publishing`.

**Blocked stale:** `409` or `423` with `MARKET_DATA_STALE` (same body as 033).

**Already running (clarify Q2):** `409`

```json
{
  "error_code": "W52_SCAN_IN_PROGRESS",
  "scan_id": "uuid-of-in-flight-run",
  "status": "evaluating",
  "strategy_id": "09_52w_breakout"
}
```

Do **not** cancel the in-flight run. Do **not** queue a second run.

**Accepted:** `{ "scan_id", "status": "queued"|"evaluating", "strategy_id": "09_52w_breakout" }`

**Body (optional):** `{ "mode": "B"|"A" }` — default `B`.

Progress stages the client MUST understand:

`queued` → `evaluating` → `backtesting` → `publishing` → `completed`  
or `blocked_stale` / `failed`

While `evaluating` or `backtesting`, `recommendations_final` is false. The UI must not show a final BUY/HOLD/WATCH/REJECT table, Top 5 / Least 5, or rejection percents-as-final.

Partial per-name attribution failure does **not** keep the run in `backtesting`. Once every history-valid job has succeeded or failed, the run completes (clarify Q3).

---

## GET /scanner/w52/runs/{scan_id}

```json
{
  "scan_id": "uuid",
  "strategy_id": "09_52w_breakout",
  "status": "backtesting",
  "progress_pct": 40,
  "stage": "Replaying book / attributing names",
  "error_code": null,
  "recommendations_final": false,
  "payload": null
}
```

`payload` is present only when `status == completed`.

---

## GET /scanner/w52/latest

**200** with ScanPayload (see data-model.md) when a run exists.

**404** `{ "available": false, "message": "No 52-Week High Breakout scan yet", "strategy_id": "09_52w_breakout" }`

Cache key: `scanner:latest:09_52w_breakout:v1`. Production and LTM caches untouched.

Required top-level fields:

```json
{
  "strategy_id": "09_52w_breakout",
  "display_name": "52-Week High Breakout",
  "scan_id": "uuid",
  "status": "completed",
  "recommendations_final": true,
  "evaluation_date": "2026-08-14",
  "book_status": "ACTIVE",
  "market_ok": true,
  "free_slots": 3,
  "survivorship_biased": true,
  "summary": {
    "total": 500,
    "data_valid": 480,
    "evaluated": 480,
    "final_candidates": 7,
    "buy": 3,
    "hold": 7,
    "watch": 4,
    "reject": 466,
    "data_failures": 12
  },
  "rejection_breakdown": [],
  "recommendations": [],
  "orders": [],
  "holdings": [],
  "top5_positive": [],
  "least5": [],
  "book_metrics": {},
  "limitations": []
}
```

`recommendations_final` MUST be false unless `status == completed`.

`book_status` is `WARMUP` | `MARKET_OFF` | `ACTIVE` (not LTM’s MID_CYCLE / REBALANCE).

---

## GET /scanner/w52/symbols/{symbol}

Returns 52W Technicals + per-name backtest. Query `window=1Y|3Y|5Y|All` (default `1Y`) affects **detail charts only**, never scan-level boards.

Missing symbol in last scan: `404`.

Technicals object MUST include strategy-owned fields only (see UI contract). Missing indicators are `null`, never `0`.

If this name’s scan-time attribution failed: `backtest.failed = true` and `reason = data_source_failure`; today’s signal from evaluation is still returned.

---

## Isolation tests (contract)

| Action | Production latest | LTM latest | 52W latest |
|--------|-------------------|------------|------------|
| POST `/scanner/w52/runs` | unchanged | unchanged | new run |
| POST `/scanner/ltm/runs` | unchanged | new run | unchanged |
| Production Run from Markets | new Production scan | unchanged | unchanged |
| Second POST `/scanner/w52/runs` while in flight | unchanged | unchanged | 409; same in-flight `scan_id` |
