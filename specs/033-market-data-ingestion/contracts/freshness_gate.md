# Contract: Market Data Freshness Gate

**Feature**: `033-market-data-ingestion`  
**Code:** `MARKET_DATA_STALE` on failure  
**Consumers:** `ScanExecutionService.execute_scan`, CLI `verify`, diagnostics/status API

---

## Preconditions (all must pass)

1. Database session available.
2. Active NIFTY 500 universe count > 0.
3. `expected_trade_date` = last **completed** NSE cash session (weekend/holiday aware via `TradingHoursService` + holiday file).
4. Equity bars present in **strategy** `daily_ohlcv` for `expected_trade_date` covering ≥ **99%** of active universe symbols.
5. Index bar present in `index_ohlcv` for `symbol='NIFTY500'` and `trade_date=expected_trade_date`.

**Not required for global pass:** delivery_qty / delivery_pct completeness.

---

## Failure response shape

When used from API/scanner progress/error channel:

```json
{
  "code": "MARKET_DATA_STALE",
  "message": "Strategy market data is not fresh enough to start scanner",
  "expected_trade_date": "2026-08-07",
  "latest_equity_trade_date": "2026-08-06",
  "latest_index_trade_date": "2026-08-07",
  "equity_coverage_ratio": 0.972,
  "missing_symbol_count": 14,
  "missing_symbols_sample": ["ABC-EQ", "XYZ-EQ"],
  "index_present": true,
  "reason": "equity_incomplete",
  "remediation": "Run: python -m app.cli.market_data_cli daily-update  (or wait for post-close schedule)"
}
```

### Reason codes (normative set)

| reason | Meaning |
|--------|---------|
| `db_unavailable` | Cannot query |
| `universe_empty` | No active symbols |
| `equity_incomplete` | Coverage < 99% for expected date |
| `index_missing` | No NIFTY500 bar for expected date |
| `no_equity_data` | Empty strategy equity store |
| `calendar_error` | Cannot resolve expected date |

---

## Scanner behavior

- On failure: **do not** run strategy evaluation; release scan lock cleanly; emit structured log + operator status.
- On success: proceed with existing scan pipeline.

---

## Strategy-level delivery (STR-041)

Separate from global gate:

```json
{
  "code": "DELIVERY_DATA_MISSING",
  "symbol": "RELIANCE-EQ",
  "trade_date": "2026-08-07",
  "message": "Delivery fields required for STR-041 are null"
}
```

STR-041 must not emit a buy/sell signal for that symbol/session when delivery is missing.

---

## Operator status surface

Diagnostics/health (or status CLI) SHOULD expose:

- `market_data_freshness`: same fields as verify payload
- last load log summary

Email/SMTP not required for v1.
