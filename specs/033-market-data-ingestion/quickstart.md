# Quickstart Validation: Market Data Ingestion

**Feature**: `033-market-data-ingestion`  
**Purpose:** Validate the feature end-to-end after implementation (not runnable until implement phase).

---

## Prerequisites

- PostgreSQL available (`DATABASE_URL`)
- Migrations applied (strategy tables + universe columns)
- FYERS credentials/token valid
- Universe seeded (`ind_nifty500list.csv` / import script)
- NSE holiday file present for current year

---

## 1. Schema sanity

```bash
# From backend venv
alembic upgrade head
python -c "print('migrations ok')"
```

**Expect:** tables `daily_ohlcv`, `index_ohlcv`, `data_load_log` exist; `stocks_master` has lifecycle columns.

---

## 2. Full load (ops window)

```bash
cd backend
python -m app.cli.market_data_cli full-load --years 3
```

**Expect:**

- Exit 0 or documented PARTIAL with few failures
- `data_load_log` row type=FULL status=SUCCESS|PARTIAL
- Active symbols have multi-year daily rows
- `index_ohlcv` has NIFTY500 history

---

## 3. Daily update (idempotent)

```bash
python -m app.cli.market_data_cli daily-update
python -m app.cli.market_data_cli daily-update
```

**Expect:**

- Both runs succeed without duplicate PK errors
- Second run updates or no-ops; row counts stable for session
- Load log shows two DAILY entries

---

## 4. Status & verify

```bash
python -m app.cli.market_data_cli status
python -m app.cli.market_data_cli verify
```

**Expect:** `verify` exit 0 when data fresh; JSON/text shows expected_trade_date and coverage.

---

## 5. Freshness block

1. Delete or withhold latest session rows for many symbols (test DB only).  
2. Start a scanner via API/UI or test harness calling `ScanExecutionService.execute_scan`.  

**Expect:** Scan does not evaluate strategies; error/progress contains `MARKET_DATA_STALE` with remediation.

---

## 6. Freshness allow

1. Run `daily-update` successfully.  
2. Re-run scanner.  

**Expect:** Gate passes; scan proceeds (subject to existing broker/token rules).

---

## 7. Delivery behavior

- Symbol with OHLCV but null delivery: global verify still OK if coverage/index OK.  
- STR-041 evaluation for that symbol: no signal; `DELIVERY_DATA_MISSING` (or equivalent).  
- Sample with known delivery: `delivery_pct ≈ delivery_qty/traded_qty*100` within 0.01 pp.

---

## 8. Single-flight

Start long `full-load` (or hold lock in test); concurrently `daily-update`.

**Expect:** Second command exit locked / SKIPPED_LOCKED; no second writer.

---

## 9. Automated schedule

On a trading day after configured post-close time, with app running:

**Expect:** DAILY `data_load_log` row with `trigger_source=SCHEDULE` without manual CLI.

---

## References

- [plan.md](./plan.md)
- [data-model.md](./data-model.md)
- [contracts/cli.md](./contracts/cli.md)
- [contracts/freshness_gate.md](./contracts/freshness_gate.md)
- [spec.md](./spec.md)
