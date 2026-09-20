# Root cause: invalid `daily_ohlcv` bars (August 2026)

Status: **code investigation + upsert gate**. No live rows were repaired, deleted, or migrated. Turso was not touched.

## What can write `daily_ohlcv` / `index_ohlcv`

All persistence goes through `repository.upsert_daily_bars` / `upsert_index_bars` (OHLC **overwrites** on conflict; delivery fields COALESCE).

| Path | File | `source` tag | When |
|---|---|---|---|
| FYERS EOD full load | `pipelines/full_load.py` | `FYERS` | CLI `full-load` / 18y backfill |
| FYERS EOD daily ensure | `ensure.py` | `FYERS` | scheduler 16:45 IST, scanner preflight |
| Session repair / thin history | `session_repair.py` | `FYERS` | scan repair |
| Scripted 18y backfill | `scripts/backfill_equity_history.py` | `FYERS` | operator CLI |
| Live 1D quote overlay | `breakout52w/session_overlay.py`, `strategy_tester/scan_service.py`, `scripts/fetch_w52_live_1d.py` | `FYERS_LIVE_1D` | during cash session |
| **ACS 1D copy** | `strategies/ltm/candle_backfill.py` | **`historical_candles`** | LTM scan if distinct `trade_date` count &lt; 253 |

Read-only ACS fallbacks (do **not** upsert): LTM `_load_matrix_from_historical_candles`, 52W `_load_from_candles`, strategy tester `fill_missing_from_historical_candles`.

Official ingestion (`full_load` / `ensure` / `fyers_eod.py`) does **not** import ACS/`HistoricalCandle`. That is covered by `test_market_data_no_acs_dual_write.py`.

## Path that created the August 2026 batch

**`backfill_daily_ohlcv_from_candles`** in `backend/app/services/strategies/ltm/candle_backfill.py`, invoked from LTM scan via `ensure_strategy_daily_ready` when the strategy store had fewer than 253 distinct session dates.

Evidence that matches the anomaly report:

1. It is the **only** writer that sets `source = "historical_candles"` (line 66, pre-patch).
2. LTM scan always calls it when `strategy_session_count() < 253` (`ltm/scan_service.py`). Strategy tables landed 2026-08-08; documented 18y FYERS load is 2026-08-18. A 2026-08-15 12:20 IST `loaded_at` sits in that window.
3. Mapping is a raw 1D ACS dump: `timestamp → trade_date` via **`.date()` on the stored datetime (UTC calendar, not IST session)**; OHLC copied 1:1; `volume = int(vol or 0)` with **no OHLC check**.
4. **No `ORDER BY`**. First row for `(session, symbol)` was kept (`seen` set). Multiple ACS 1D timestamps collapsing to one calendar date could keep an incomplete/low-volume print.
5. Upsert **overwrites** open/high/low/close/volume/source. A later FYERS load only fills **missing date ranges** (`missing_ohlcv_ranges`), so already-present corrupt keys are not repaired. Daily sync only fetches the latest session.

That explains: `source=historical_candles`, cluster on `2026-08-01`, tiny volumes vs adjacent millions, opens equal to prior close (shifted/incomplete ACS bar), and survival after the 18y FYERS load.

`historical_candles` / ACS is a chart/quote cache (UTC timestamps, mixed resolutions, possible in-progress bars). It must **not** be a source of truth for the scanner/backtest daily store. FYERS EOD (`resolution=1D`, `date_format=1`) is the SoT.

## Daily-store source-of-truth rule

`daily_ohlcv` and `index_ohlcv` may be written only with allowlisted `source` values. Enforced in `source_policy.py` at `upsert_daily_bars` / `upsert_index_bars` (and Turso upserts). The OHLC gate is separate and unchanged.

**Allowlisted today:** `FYERS` (FyersEodProvider EOD history).

**Rejected (not rewritten):** `historical_candles`, `FYERS_LIVE_1D` (in-session quotes), ACS/chart-cache tags, missing/unrecognized identifiers.

ACS/`historical_candles` persistence is **not** governed by this allowlist. New daily-store sources require an explicit code review and allowlist update. Existing 77 bad rows are not altered by this policy (it only blocks new writes).

## Can daily sync repeat this?

- **Scheduled `ensure` / `daily-update`:** no ACS copy. Uses `FyersEodProvider`. Will not rewrite 2026-08-01. **Will not heal** existing bad keys.
- **LTM `ensure_strategy_daily_ready`:** will not copy again while distinct session dates ≥ 253 (true after the 18y load).
- **`FYERS_LIVE_1D` overlay:** in-memory overlay may still run; persist to `daily_ohlcv` is **rejected** by the source allowlist (quote-cache, not finalized EOD).
- **Tick-size cases** (BEL close 410.70 vs high 410.65): 0.05 NSE tick; gate allows `DEFAULT_TICK_EPSILON = 0.05`.

## Patch (code only; no row repair)

1. `validators/ohlcv_gate.py` — reject missing/non-finite OHLC, `high < low`, open/close outside `[low, high]` beyond 0.05, negative volume. **No clamp/fix.**
2. `upsert_daily_bars` / `upsert_index_bars` (and Turso upserts) filter before write.
3. ACS backfill: IST session date, last timestamp wins, skip invalid bars before upsert.

Existing corrupt rows stay until a **later approved** rewrite from FYERS EOD. Do not drop/update them in this change.

## Quarantine table (proposed, not applied)

SQL: `backend/app/db/proposed_migrations/market_data_rejections.sql`

Postgres-only operational audit. Not in the Alembic chain. Would store attempted source, symbol, date, OHLCV payload, material/rounding reasons, provider/request id, timestamps. No tokens or URLs. Rejected bars still must not enter `daily_ohlcv`. Apply only after explicit approval.

## Future repair (not enabled)

1. Read-only anomaly JSON → unique `(table, symbol, trade_date)` keys.
2. Re-fetch **only those keys** from `FyersEodProvider.fetch_daily_session`.
3. Run the OHLC gate on replacements.
4. Require local dump + `--execute --confirm-local-backup`.
5. UPDATE with audit of old/new/provider/time/reason.

```powershell
python -m app.cli.ohlcv_repair_plan --dry-run --from-anomaly-json anomaly_report.json
python -m app.cli.ohlcv_repair_plan --preview-provider --from-anomaly-json anomaly_report.json --json
python -m app.cli.ohlcv_repair_plan --build-manifest --from-preview-json preview_report.json --output repair_manifest.json
python -m app.cli.ohlcv_repair_plan --build-manifest --from-preview-json preview_report.json --output repair_manifest_v2.json
python -m app.cli.ohlcv_repair_plan --build-phantom-review --from-preview-json preview_report.json --output phantom_rows_delete_review.json
```

**Auth split:** the running app may load FYERS tokens from its normal DB-backed flow. Repair **preview** uses **process-environment only** (`FYERS_APP_ID`, `FYERS_ACCESS_TOKEN`). It never uses `DATABASE_URL`, Neon, or `FyersService._client()`.

```powershell
$env:FYERS_APP_ID = "..."
$env:FYERS_ACCESS_TOKEN = "..."
# after preview:
Remove-Item Env:\FYERS_APP_ID
Remove-Item Env:\FYERS_ACCESS_TOKEN
```

`--execute` prints `REPAIR EXECUTION IS DISABLED UNTIL EXPLICIT APPROVAL` and does not open a database. Repair must finish and be revalidated **before** any Turso schema or migration write.

Future UPDATE execution (not implemented as a live write in this phase) must require: `--execute --confirm-local-backup --manifest PATH --approved-repair-run-id ID`, local-only host, exact old-row fingerprint match, a transaction, UPDATE only manifest keys on `daily_ohlcv`/`index_ohlcv`, re-run OHLC gate + source policy, no DELETE, no ACS/Turso changes, audit old/new/provider/run/time/reason.

## Weekend phantom vs weekday repair vs unknown calendar

ACS `historical_candles` timestamps are UTC. Mapping them with `.date()` (UTC calendar) instead of IST session date can place a Friday IST bar on Saturday UTC, or split one session across two calendar keys. Those **weekend/holiday rows in `daily_ohlcv` are phantoms**: FYERS has no EOD session that day, so they are not `REPAIRABLE`.

| Kind | Example | Preview | Next step |
|---|---|---|---|
| Repairable weekday EOD defect | weekday in holiday file, FYERS returns a valid 1D bar | `REPAIRABLE` / `REPAIR_FROM_FYERS` | UPDATE manifest only |
| Weekend/holiday phantom | Sat/Sun or stored NSE holiday | `NON_TRADING_DAY_PHANTOM`; **FYERS not called** | `phantom_rows_delete_review.json` (review only) |
| Uncertain weekday / no FYERS | weekday year missing from holiday JSON, or expected session with empty FYERS | `NO_FYERS_BAR_ON_UNKNOWN_CALENDAR_DAY` or `NO_FYERS_BAR_ON_EXPECTED_TRADING_DAY` | keep row; manual review |

**No row is deleted automatically.** Future DELETE of phantom weekend rows is a **separate later approval** and is **not implemented** as a working command. It would require: backup confirmation, the exact delete-review manifest, local-host check, expected old-row fingerprint match, a transaction, an audit record, and explicit user confirmation.

## Fingerprints (`v2_decimal_8`)

Postgres `NUMERIC(18,8)` and JSON numbers stringify differently (`2016.9` vs `2016.90000000`). Repair fingerprints now use `Decimal(str(value))` quantized to `0.00000001` for OHLC, exact integer volume, and case-sensitive source. That removes format-only false mismatches without a fuzzy epsilon. Keep `repair_manifest.json` as evidence; rebuild:

```powershell
python -m app.cli.ohlcv_repair_plan --build-manifest --from-preview-json preview_report.json --output repair_manifest_v2.json
```

Rerun the 3-row `--repair-dry-run` against `repair_manifest_v2.json` before any UPDATE. V1 fingerprint strings are not compared; expected old fields are re-canonicalized. Unknown fingerprint versions fail with `MANIFEST_FINGERPRINT_VERSION_UNSUPPORTED`.
