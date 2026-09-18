# Data Model: 52-Week High Breakout Scanner

**Feature**: `038-52w-high-breakout`  
**Date**: 2026-08-16  
**Storage**: PostgreSQL — new `w52_book_state`; reuse `strategy_scan_latest` / `strategy_scan_runs`; read-only strategy-grade OHLCV

---

## Existing entities (read)

### DailyOhlcv (`daily_ohlcv`)

Strategy-grade adjusted daily bar. 52W uses `trade_date`, `symbol`, `open`, `high`, `low`, `close`, `volume`. Missing row ⇒ missing print (NaN). Never forward-fill a close or high solely to force a breakout.

### IndexOhlcv (`index_ohlcv`)

Master calendar, MarketOK (close `>` SMA50), and NIFTY 500 benchmark. Identity `NIFTY500`.

### StockMaster / UniverseService

Active NIFTY 500 membership via existing universe service.

### Production `scan_results` and `ltm_book_state`

**Out of bounds for 52W writes.** This strategy must not upsert either.

### StrategyScanLatest / StrategyScanRun

Already created by 037. Reuse with `strategy_id = 09_52w_breakout`. No schema change required if `strategy_id` remains a 64-char string.

---

## New entities

### W52BookState (`w52_book_state`)

Persisted event-driven book. Restart must not lose HWM/TSL (FR-062).

| Field | Type | Rules |
|-------|------|--------|
| id | string PK | Singleton `default` for MVP |
| strategy_id | string | Always `09_52w_breakout` |
| mode | `B` \| `A` | Default `B` (canonical 10% × 10) |
| fill_model | `signal_close` \| `next_open` | Replay `signal_close`; live label `next_open` |
| cash | decimal | ≥ 0 |
| equity | decimal | cash + marked holdings |
| initial_capital | decimal | Default 100000 INR |
| last_session_processed | date \| null | Last master session applied |
| session_index | int | Index of last processed master session (−1 if none) |
| book_status | `WARMUP` \| `MARKET_OFF` \| `ACTIVE` | Derived + stored for UI |
| market_ok | bool | Last computed MarketOK |
| nifty_close | decimal \| null | |
| nifty_sma50 | decimal \| null | |
| holdings | JSON list | See Holding |
| pending_orders | JSON list | Optional |
| sold_today | JSON list of symbols | Same-session rebuy forbidden |
| survivorship_biased | bool | True if membership is current-list-only |
| updated_at | timestamptz | |

#### Holding (embedded)

| Field | Type | Rules |
|-------|------|--------|
| symbol | string | Unique in the list |
| shares | decimal | Fractional allowed in research; whole in live |
| entry_date | date | |
| entry_session_index | int | |
| entry_price | decimal | Fill used to seed HWM/TSL |
| hwm | decimal | Highest **close** since entry; never below entry close unless data repair |
| tsl | decimal | Current trailing stop; **never decreases** |

**If trail state is lost:** reconstruct `tsl = max(last_known_tsl, hwm − 3 × ATR)` using last known HWM. Never set a stop lower than the last known stop.

**Transitions**

```text
WARMUP --[session_index >= 252]--> ACTIVE or MARKET_OFF
ACTIVE --[not MarketOK]--> MARKET_OFF     # no flatten
MARKET_OFF --[MarketOK]--> ACTIVE         # new buys allowed again
any --[close < TSL and not entry bar]--> EXIT that holding
any --[delist]--> exit at last print immediately
```

There is no `sessions_since_rebalance` clock.

---

## Reused scan documents

### StrategyScanLatest

| Field | Type | Rules |
|-------|------|--------|
| strategy_id | string PK | `09_52w_breakout` |
| scan_id | uuid | |
| status | `queued` \| `evaluating` \| `backtesting` \| `publishing` \| `completed` \| `failed` \| `blocked_stale` | Recommendations final only when `completed` |
| payload | JSONB | See ScanPayload |
| error_code | string \| null | `MARKET_DATA_STALE`, `W52_SCAN_IN_PROGRESS`, `W52_SCAN_FAILED` |
| started_at / computed_at | timestamptz | |

### StrategyScanRun

One row per attempt. Same status enum. `find_active_run` for this `strategy_id` implements clarify Q2 (second start → in progress, no cancel).

---

## ScanPayload (JSON)

Published when status is `completed` (including runs where some per-name attributions failed). `recommendations_final` is true only then.

```text
strategy_id            = 09_52w_breakout
display_name           = 52-Week High Breakout
scan_id, evaluation_date
book_status            = WARMUP | MARKET_OFF | ACTIVE
market_ok, nifty_close, nifty_sma50
n_positions, cash, equity, free_slots
survivorship_biased
recommendations_final
summary: {
  total, data_valid, evaluated, final_candidates,
  buy, hold, watch, reject, data_failures
}
rejection_breakdown: [ { code, label, count, pct, caption: "First failure" } ]
recommendations: [ RecommendationRow ]
orders: [ OrderRow ]            # EXIT first, then BUY
holdings: [ HoldingView ]
top5_positive: [ BoardRow ]     # 1Y book-trade return > 0
least5: [ BoardRow ]
book_metrics: { total_return, cagr, max_dd, win_rate, trades, calmar, excess_vs_nifty500, ... }
limitations: [ string ]
warmup: bool
```

### RecommendationRow

| Field | Rules |
|-------|--------|
| symbol | |
| signal | `BUY` \| `HOLD` \| `WATCH` \| `REJECT` |
| rank | Momentum_60 rank among today’s buy-signal names; null if not a candidate |
| close, high_252_prior, volume, vol_sma20, atr14, mom60 | Numbers or null (never 0 for missing) |
| market_ok | bool |
| blocked_by | `market_filter` \| `no_slot` \| `sold_today` \| null |
| first_failure | code or null (null for BUY/HOLD) |
| target_weight, target_notional, tsl0 | set on BUY |
| hwm, tsl, unrealized_pct | set on HOLD |
| backtest | per-name object or `{ "failed": true, "reason": "data_source_failure" }` |

HOLD rows MUST have `first_failure = null` and MUST NOT increment rejection buckets.

### OrderRow

| Field | Rules |
|-------|--------|
| side | `EXIT` \| `BUY` |
| symbol, shares, fill_model | |
| reason | `atr_trail` on EXIT; `breakout` on BUY |
| close, tsl, hwm | EXIT |
| tsl0, atr, target_notional | BUY |

Order list is sorted: all EXIT, then BUY by rank.

### BoardRow

rank, symbol, signal (today’s BUY/HOLD/WATCH/REJECT), return, trades, win_rate, max_dd, profit_factor.

Inclusion: ≥ 1 real book trade in the last 1 year of completed sessions. Top 5 additionally requires return `> 0`. Open MTM counts as one trade (FR-061). Failed attributions excluded.

### First-failure codes

| Code | Label |
|------|--------|
| `not_in_universe` | Not in investable universe |
| `insufficient_history` | Insufficient historical data |
| `missing_bar` | Missing or invalid close, high, or volume |
| `close_below_prior_high` | Close below the prior 252-session high |
| `volume_not_above_average` | Volume not above the 20-session average |
| `market_filter_off` | Market filter off |
| `sold_today` | Sold today (same-day rebuy blocked) |
| `no_free_slot` | Buy signal but no free slot |
| `data_source_failure` | Data source failure |
| `other` | Other |

Earliest failing rule wins. Already-held still-open names are HOLD, not a bucket.

---

## Validation rules

- At most 10 holdings.
- Gross exposure ≤ 100% of equity except microscopic rounding.
- `tsl` is non-increasing never — each persist MUST have `tsl >= previous tsl` for the same open lot.
- `sold_today` cleared at the start of the next session.
- `recommendations_final` false unless `status == completed`.
- A `data_source_failure` attribution does not by itself flip a BUY/HOLD/EXIT from today’s evaluation.
