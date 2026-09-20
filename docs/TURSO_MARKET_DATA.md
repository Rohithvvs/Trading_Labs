# Two-database architecture (v1): Postgres operational + Turso daily/index history

Status: **Phase 2–4 scaffolding**. Default runtime is unchanged: candle history still reads and writes Postgres. Turso schema is not applied, data is not copied, and `CANDLE_HISTORY_BACKEND` stays `postgres` until you set it.

```text
 FYERS / NSE
      │
      ▼
 ingestion / scanners / backtests / UI
      │
      │  CANDLE_HISTORY_BACKEND=postgres  (default, current)
      │  CANDLE_HISTORY_BACKEND=turso     (future, after your approval)
      │
      ├──────── DATABASE_URL (Postgres) ────────┐
      │  users, paper, scans, backtest summaries │
      │  stocks_master, data_load_log            │
      │  daily_ohlcv / index_ohlcv (still here)  │
      │  historical_candles / ACS (not in v1)    │
      └─────────────────────────────────────────┘
      │
      └──────── Turso (future v1 history SoT) ──┐
         daily_ohlcv                             │
         index_ohlcv                             │
         NOT historical_candles                  │
      ──────────────────────────────────────────┘
```

## V1 table ownership

| Store | Tables |
|---|---|
| **Turso (after approved copy)** | `daily_ohlcv`, `index_ohlcv` (includes delivery / turnover / `adtv_20`) |
| **Postgres (`DATABASE_URL`)** | All operational tables **and** current candle tables until a later drop approval |
| **Not in v1** | `historical_candles`, ACS, `market_data.candles` |

**Runtime source-of-truth rule:** ACS/`historical_candles` must not populate `daily_ohlcv` or `index_ohlcv` through normal writers. The only allowlisted **runtime** writer `source` is `FYERS` (official EOD). `FYERS_LIVE_1D` and unrecognized tags are rejected at the daily/index upsert boundary. Chart/ACS cache writes to `historical_candles` are unchanged. Adding a new daily-store source requires an explicit allowlist review in `source_policy.py`.

**One-time Turso V1 copy policy (`validated_legacy_backfill_v1`):** separate from runtime writes. The migrator may copy validated legacy rows from `FYERS`, `historical_candles`, and **finalized** `FYERS_LIVE_1D`. Original `source` is preserved and never rewritten. Runtime upserts stay FYERS-only.

LIVE_1D finalization uses an IST **next-day** rule: a `FYERS_LIVE_1D` bar for session `D` is copied only when the current Asia/Kolkata calendar date is strictly after `D`. Today's (and future) LIVE_1D rows are excluded for review, including after 15:30 / 16:45 IST. They are not deleted.

Always excluded from copy (not deleted locally): 48 Saturday keys in `phantom_rows_delete_review.json`; `index_ohlcv / NIFTY500 / 2009-05-18`; material-invalid OHLC; missing required key/OHLC fields; duplicate `(trade_date, symbol)` conflicts that cannot be resolved. If two source rows ever shared a key, precedence is `FYERS` > finalized `FYERS_LIVE_1D` > `historical_candles`; same-rank ties are excluded as unresolved. The current Postgres PK already has 0 duplicate groups, so each key has one stored source.

Postgres candle tables must **not** be dropped, truncated, renamed, or have writes stopped without a separate explicit approval after: real Turso copy, validation, scanner/backtest smoke, daily-update-on-Turso test, and your cutover OK.

## ACS flags (unchanged defaults)

| Flag | Current default | Note |
|---|---|---|
| `AUTHORITATIVE_CANDLE_STORE_ENABLED` | `false` | ACS / charts / paper OHLCV still Postgres `historical_candles` |
| `CANDLE_STORE_DUAL_WRITE` | `true` | Can dual-write ACS candles into Postgres |

v1 does **not** refactor ACS. After a future ACS migration, leaving `CANDLE_STORE_DUAL_WRITE=true` would refill Neon with large candle rows. Review those flags before any ACS cutover; do not flip them as part of daily/index Turso work.

## Environment (exactly one operational URL)

```env
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME
LOCAL_POSTGRES_DATABASE_URL=
TURSO_DATABASE_URL=libsql://YOUR-DB.turso.io
TURSO_AUTH_TOKEN=
CANDLE_HISTORY_BACKEND=postgres
```

- App runtime uses **`DATABASE_URL` only**.
- `LOCAL_POSTGRES_DATABASE_URL` is the migrator source. Live migration **refuses** if it is unset and **does not** fall back to `DATABASE_URL`.
- Do not put two `DATABASE_URL` lines in `.env` (last-wins). Do not commit `.env`.
- This repo does not edit your real `.env`.

## Safe local development

Keep `CANDLE_HISTORY_BACKEND=postgres`. Scanners, backtests, and `market_data_cli daily-update` keep using Postgres `daily_ohlcv` / `index_ohlcv`.

## Commands

Schema preview (no Turso write):

```powershell
python -m app.cli.turso_cli schema-apply
```

Dry-run migration (models only; no DB connections):

```powershell
python -m app.cli.turso_migrate_daily_ohlcv --dry-run
python -m app.cli.turso_migrate_daily_ohlcv --dry-run --limit 100 --symbols RELIANCE-EQ --batch-size 200
```

Source-read-only preflight (**future approval**; reads local `trading_data` only, never Turso, never `DATABASE_URL`):

```powershell
python -m app.cli.turso_migrate_daily_ohlcv --source-inspect
python -m app.cli.turso_migrate_daily_ohlcv --source-inspect --json --limit 100 --symbols RELIANCE-EQ --batch-size 500
```

Requires `LOCAL_POSTGRES_DATABASE_URL` pointing at localhost. Refuses Neon/remote hosts. Prints `PREFLIGHT PASSED — NO DATA WAS WRITTEN` or `PREFLIGHT FAILED — NO DATA WAS WRITTEN`.

Invalid-bar diagnosis (read-only; does not fix, clamp, or drop rows):

```powershell
python -m app.cli.turso_migrate_daily_ohlcv --source-anomalies --json
python -m app.cli.turso_migrate_daily_ohlcv --source-anomalies --json --output anomaly_report.json
```

Prints `ANOMALY REPORT COMPLETE — NO DATA WAS WRITTEN`. External FYERS bar comparison is **not** invoked; verify later manually if needed.

Writer inventory (no database):

```powershell
python -m app.cli.ohlcv_writer_audit
```

Future repair dry-run (no fetch, no UPDATE):

```powershell
python -m app.cli.ohlcv_repair_plan --dry-run --from-anomaly-json anomaly_report.json
```

FYERS provider preview (no database; process-env credentials only):

```powershell
$env:FYERS_APP_ID = "..."
$env:FYERS_ACCESS_TOKEN = "..."
python -m app.cli.ohlcv_repair_plan --preview-provider --from-anomaly-json anomaly_report.json --json --output preview_report.json
Remove-Item Env:\FYERS_APP_ID
Remove-Item Env:\FYERS_ACCESS_TOKEN
```

Statuses include `REPAIRABLE`, `NON_TRADING_DAY_PHANTOM` (weekends/stored NSE holidays; FYERS is not called), `NO_FYERS_BAR_ON_EXPECTED_TRADING_DAY`, `NO_FYERS_BAR_ON_UNKNOWN_CALENDAR_DAY`, `FYERS_BAR_INVALID`, `REQUIRES_MANUAL_REVIEW`, `TOKEN_MISSING`, `FYERS_AUTH_FAILED`, `FYERS_REQUEST_FAILED`, `FYERS_RATE_LIMITED`. Saturday 2026-08-01 is classified as a weekend phantom (ACS UTC→IST session-date bug), not a FYERS replacement candidate.

ACS timestamps are UTC; using UTC `.date()` as `trade_date` can land a Friday IST session on Saturday. Those rows are phantoms, not missing EOD. Weekday rows with a valid FYERS 1D bar are the only UPDATE candidates. Weekdays with no FYERS bar stay unchanged for manual review.

Phantom rows go to `phantom_rows_delete_review.json` (review only, **no DELETE command**). The UPDATE manifest still contains only `REPAIRABLE` FYERS rows. Automatic deletion is not implemented.

Build a pending manifest (no UPDATE). Keep `repair_manifest.json` as evidence; rebuild v2 fingerprints to a new file:

```powershell
python -m app.cli.ohlcv_repair_plan --build-manifest --from-preview-json preview_report.json --output repair_manifest_v2.json
```

Repair execution is **disabled** until explicit approval (`REPAIR EXECUTION IS DISABLED UNTIL EXPLICIT APPROVAL`). Do not apply Turso schema or migrate until this repair is completed and revalidated.

Limited test migration (**future**, still refused until approved):

```powershell
python -m app.cli.turso_migrate_daily_ohlcv --execute --confirm-local-backup --limit 100
```

Requires `LOCAL_POSTGRES_DATABASE_URL` and `--confirm-local-backup`. This phase still will not open Turso or local Postgres.

Validation (static now; live later):

```powershell
python -m app.cli.turso_validate_daily_ohlcv --json
python -m app.cli.turso_validate_daily_ohlcv --live
```

`--live` is skipped/refused until you approve a real compare.

Future cutover (you do this, after validation):

```env
CANDLE_HISTORY_BACKEND=turso
```

Then restart. Daily/index reads and upserts route to Turso. ACS/`historical_candles` stay on Postgres.

## Live execution runbook (future — do not run until you approve each step)

1. Confirm **one** active `DATABASE_URL` in the environment (operational Postgres). Do not add a second `DATABASE_URL` line.
2. Set `LOCAL_POSTGRES_DATABASE_URL` to local `trading_data` only (localhost). The migrator will not fall back to `DATABASE_URL`.
3. Back up local Postgres yourself (placeholder only; do not embed credentials):

   ```bash
   pg_dump "$LOCAL_POSTGRES_DATABASE_URL" --format=custom --file=trading_data_before_turso.dump
   ```

4. Run source-read-only preflight:

   ```powershell
   python -m app.cli.turso_migrate_daily_ohlcv --source-inspect
   ```

5. Review the preflight report (row counts, symbols, dates, duplicates, invalid OHLC). Continue only if it prints `PREFLIGHT PASSED — NO DATA WAS WRITTEN`.
6. Explicitly approve, then apply Turso schema (`python -m app.cli.turso_cli schema-apply --execute`). Not run in this phase.
7. Limited migration for one symbol / small limit (`--execute --confirm-local-backup --limit N --symbols SYMBOL`).
8. Live validation for that subset (`python -m app.cli.turso_validate_daily_ohlcv --live`).
9. Approve full migration.
10. Full migration only after explicit approval of the exact command, including `--migration-policy validated_legacy_backfill_v1` (`--full --execute --confirm-local-backup`). Do not use FYERS-only exclusion of valid `historical_candles` / finalized `FYERS_LIVE_1D`.
11. Full validation.
12. Smoke-test scanner/backtest workflows against Turso (still without dropping Postgres candles).
13. Only then **you** set `CANDLE_HISTORY_BACKEND=turso` and restart.
14. Keep Postgres candle data untouched until a **separate** later approval to stop writes or drop tables.

Rollback at any point before step 13: leave `CANDLE_HISTORY_BACKEND=postgres` and restart. No automatic deletes.

## Backup and rollback

1. Dump local `trading_data` before any real Turso upsert (see runbook step 3).
2. Keep Postgres history in place.
3. Rollback = leave `CANDLE_HISTORY_BACKEND=postgres` and restart.
4. No automatic deletes. Dropping Postgres candle tables needs a later exact command + your approval.

## Type mapping (Postgres → Turso)

| Postgres | Turso/libSQL |
|---|---|
| `date` | `TEXT` `YYYY-MM-DD` (NSE session) |
| `numeric(18,8)` | `REAL` |
| `bigint` | `INTEGER` |
| `timestamptz` | `TEXT` ISO-8601 UTC |
| `varchar` | `TEXT` |
