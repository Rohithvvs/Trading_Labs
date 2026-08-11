# Contract: Market Data Operator CLI

**Feature**: `033-market-data-ingestion`  
**Invocation pattern**: `python -m app.cli.market_data_cli <command> [options]`  
(Align with existing `python -m app.governance.experiment_cli`.)

---

## Commands

### `full-load`

**Purpose:** Initial/resumable historical population of strategy-grade tables.

| Option | Default | Description |
|--------|---------|-------------|
| `--years` | `3` | Minimum calendar years of history |
| `--symbols` | all active NIFTY500 | Optional comma list for debug |
| `--dry-run` | off | Optional: plan only if implemented |

**Effects:** Writes `daily_ohlcv`, `index_ohlcv`, `data_load_log` (FULL). Single-flight.

**Stdout (human):** summary counts, status, duration.  
**Stderr:** warnings/errors.  
**Exit codes:** `0` SUCCESS; `1` FAILED; `3` SKIPPED_LOCKED; `4` PARTIAL (optional convention — if used, document in help).

---

### `daily-update`

**Purpose:** Incremental load for latest completed session (or explicit date).

| Option | Default | Description |
|--------|---------|-------------|
| `--date` | expected last session | ISO date `YYYY-MM-DD` |
| `--force` | off | Re-fetch even if coverage already OK |

**Effects:** Upserts session rows; load log DAILY; single-flight.

**Exit codes:** `0` SUCCESS; `1` FAILED; `3` SKIPPED_LOCKED; `4` PARTIAL.

---

### `status`

**Purpose:** Operator snapshot without mutating data.

**Output fields (JSON and/or text):**

- `expected_trade_date`
- `latest_equity_trade_date`
- `latest_index_trade_date`
- `equity_coverage_ratio` (for expected date)
- `index_present`
- `active_universe_count`
- `last_load` (type, status, started_at, data_date, duration_ms)
- `lock_held` (bool if detectable)
- `gate_ok` (bool)

**Exit:** `0` always if status query succeeds; `1` if DB unavailable.

---

### `verify`

**Purpose:** Run freshness gate rules; non-mutating.

| Option | Default | Description |
|--------|---------|-------------|
| `--date` | expected session | Override expected date |
| `--json` | off | Machine-readable payload |

**Exit:** `0` if gate OK; `2` if `MARKET_DATA_STALE`; `1` infrastructure error.

**Payload:** See [freshness_gate.md](./freshness_gate.md).

---

## Concurrency

If another FULL/DAILY load holds the lock:

- Command must not mutate.
- Exit `3` with message `already running` / status `SKIPPED_LOCKED`.

---

## Logging

Each mutating command emits structured logs:

- `MARKET_DATA_LOAD_START|END`
- counters: fetched/inserted/updated/failed
- provider errors
