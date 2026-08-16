# Contract: LTM Scanner API

**Feature**: `037-ltm-scanner-dashboard`  
**Auth**: Existing session; feature key `advanced_scanner`  
**Isolation**: These routes MUST NOT read or write Production `GET /scanner/latest` (`scanner:latest:v1`)

Logical paths (names may be mounted under `/scanner`):

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/scanner/strategies` | List registered scanner strategies (includes LTM + Production) |
| POST | `/scanner/ltm/runs` | Start LTM scan (async) |
| GET | `/scanner/ltm/runs/{scan_id}` | Progress / status |
| GET | `/scanner/ltm/latest` | Latest LTM payload (`?force=true` bypasses LTM cache only) |
| GET | `/scanner/ltm/symbols/{symbol}` | Detail: technicals + backtest windows |

---

## POST /scanner/ltm/runs

**Preconditions:** freshness gate pass; no other LTM scan in evaluating/backtesting.

**Blocked stale:** `409` or `423` with `MARKET_DATA_STALE` body (same fields as 033 freshness contract).

**Accepted:** `{ "scan_id", "status": "queued"|"evaluating" }`

**Body (optional):** `{ "mode": "A"|"B" }` — default `A`.

Progress stages the client MUST understand:

`queued` → `evaluating` → `backtesting` → `publishing` → `completed`  
or `blocked_stale` / `failed`

While `evaluating` or `backtesting`, `recommendations_final` is false and the UI must not show a final BUY/WATCH table.

---

## GET /scanner/ltm/latest

**200** with ScanPayload (see data-model.md) when a run exists.

**404** `{ "available": false, "message": "No LTM scan yet" }`

Cache key: `scanner:latest:17_long_term_mom:v1`. Production cache untouched.

Required top-level fields:

```json
{
  "strategy_id": "17_long_term_mom",
  "display_name": "Long-Term Buy & Hold Momentum",
  "scan_id": "uuid",
  "status": "completed",
  "recommendations_final": true,
  "evaluation_date": "2026-08-14",
  "clock_status": "MID_CYCLE",
  "sessions_to_rebalance": 41,
  "survivorship_biased": true,
  "summary": {
    "total": 500,
    "data_valid": 480,
    "evaluated": 480,
    "final_candidates": 10,
    "buy": 0,
    "watch": 10,
    "reject": 470,
    "data_failures": 20
  },
  "rejection_breakdown": [],
  "recommendations": [],
  "top5_positive": [],
  "least5": [],
  "book_metrics": {},
  "limitations": []
}
```

`recommendations_final` MUST be false unless `status == completed`.

---

## GET /scanner/ltm/symbols/{symbol}

Returns LTM Technicals + per-name backtest. Query `window=1Y|3Y|5Y|All` (default `1Y`) affects **detail charts only**, never scan-level boards.

Missing symbol in last scan: `404`.

---

## GET /scanner/strategies

```json
{
  "strategies": [
    { "id": "production", "display_name": "Production" },
    { "id": "17_long_term_mom", "display_name": "Long-Term Buy & Hold Momentum", "short_name": "LTM" }
  ]
}
```

---

## Errors

| Code | When |
|------|------|
| `MARKET_DATA_STALE` | Freshness gate failed |
| `LTM_SCAN_IN_PROGRESS` | Second start while one is running |
| `LTM_WARMUP` | Completed scan with no entries (not an error — status completed + warmup true) |
| `401` / `403` | Auth / missing `advanced_scanner` |

---

## Compatibility

Existing `GET /scanner/latest`, `GET /scanner/results`, `GET /scanner/statistics` remain Production-only unless a later feature unifies them. LTM clients MUST call the LTM routes (or `?strategy=17_long_term_mom` aliases that resolve to the same namespaced store).
