# Data Model: Long-Term Buy & Hold Momentum Scanner

**Feature**: `037-ltm-scanner-dashboard`  
**Date**: 2026-08-15  
**Storage**: PostgreSQL (new tables) + read-only use of existing strategy-grade OHLCV

---

## Existing entities (read)

### DailyOhlcv (`daily_ohlcv`)

Strategy-grade adjusted daily bar. LTM uses `trade_date`, `symbol`, `close` (and open for live-fill metadata only). Missing row ⇒ missing print (NaN), never forward-filled for eligibility.

### IndexOhlcv (`index_ohlcv`)

Master calendar and NIFTY 500 benchmark. Identity `NIFTY500`.

### StockMaster

Active NIFTY 500 membership via `is_nifty500` / `universe == NIFTY500` and `is_active`.

### Production scan_results

**Out of bounds for LTM writes.** LTM must not upsert this singleton.

---

## New entities

### LtmBookState

Persisted 252-session clock and live/research book. Restart must not reset the clock (FR-019).

| Field | Type | Rules |
|-------|------|--------|
| id | singleton key (e.g. `default`) | One row for MVP |
| strategy_id | string | Always `17_long_term_mom` |
| mode | `A` \| `B` | Default `A` |
| fill_model | `signal_close` \| `next_open` | Replay `signal_close`; live label `next_open` |
| cash | decimal | ≥ 0 |
| equity | decimal | cash + marked holdings |
| initial_capital | decimal | Default 100000 INR |
| session_index | int | Index of last processed master session |
| sessions_since_rebalance | int | 0 just after a rebalance |
| last_rebalance_date | date \| null | |
| clock_status | `WARMUP` \| `MID_CYCLE` \| `REBALANCE` | Derived + stored for UI |
| holdings | JSON list | See Holding |
| pending_orders | JSON list | Optional |
| survivorship_biased | bool | True if membership is current-list-only |
| updated_at | timestamptz | |

#### Holding (embedded)

| Field | Type |
|-------|------|
| symbol | string |
| shares | decimal (fractional allowed in research; whole in live) |
| avg_cost | decimal |
| entry_date | date |
| entry_session_index | int |

**Transitions**

```text
WARMUP --[session_index >= 252]--> REBALANCE
REBALANCE --[clock reset to 0]--> MID_CYCLE
MID_CYCLE --[sessions_since_rebalance == 252]--> REBALANCE
any --[delist]--> exit that holding immediately
```

---

### StrategyScanLatest

Namespaced “latest completed (or in-flight) scan” per strategy.

| Field | Type | Rules |
|-------|------|--------|
| strategy_id | string PK | `17_long_term_mom` |
| scan_id | uuid | |
| status | `queued` \| `evaluating` \| `backtesting` \| `publishing` \| `completed` \| `failed` \| `blocked_stale` | Recommendations final only when `completed` |
| payload | JSONB | See ScanPayload |
| error_code | string \| null | e.g. `MARKET_DATA_STALE` |
| started_at | timestamptz | |
| computed_at | timestamptz \| null | |

### StrategyScanRun

One row per attempt (progress + audit).

| Field | Type |
|-------|------|
| scan_id | uuid PK |
| strategy_id | string |
| status | same enum |
| progress_pct | int 0–100 |
| stage | string |
| payload | JSONB \| null (filled on complete) |
| error_code / error_detail | |
| started_at / finished_at | |

---

## ScanPayload (JSON)

Logical document published only after book replay finishes (or failed/blocked).

```text
strategy_id, display_name, scan_id, evaluation_date
clock_status, sessions_to_rebalance, last_rebalance_date, next_rebalance_estimate
survivorship_biased
summary: { total, data_valid, evaluated, final_candidates, buy, watch, reject, data_failures }
rejection_breakdown: [ { code, label, count, pct, caption: "First failure" } ]
recommendations: [ RecommendationRow ]
top5_positive: [ BoardRow ]      # 1Y book-trade return > 0
least5: [ BoardRow ]             # lowest 1Y book-trade return
book_metrics: { total_return, cagr, max_dd, win_rate, trades, calmar, excess_vs_nifty500, ... }
limitations: [ string ]
warmup: bool
```

Recommendations **must not** be present (or must be flagged `final: false`) while status ∈ {evaluating, backtesting}.

---

### RecommendationRow

| Field | Rules |
|-------|--------|
| rank | Eligible rank or null |
| symbol | NSE ticker |
| signal | `BUY` \| `WATCH` \| `REJECT` |
| momentum_252 | decimal \| null (null ≠ 0) |
| gate_pass | bool |
| selected | bool |
| first_failure | reason code or null |
| target_weight / target_notional | set when selected on REBALANCE |
| technicals | LtmTechnicals snapshot |
| backtest_1y | PerNameBacktest or null if not history-valid |

Signal rules: REBALANCE + selected → BUY; MID_CYCLE + selected → WATCH; else REJECT; WARMUP → no BUY/WATCH.

---

### First-failure codes (canonical)

Ordered earliest-to-latest (FR-037: count once):

| code | When |
|------|------|
| `not_in_universe` | Not an active NIFTY 500 constituent on T |
| `insufficient_history` | No valid adjusted close at T−252 |
| `missing_close_t` | No valid adjusted close on T |
| `momentum_undefined` | Non-finite momentum |
| `failed_momentum_gate` | Momentum defined and `<= 0.50` |
| `ranked_outside_top_10` | Eligible but rank > 10 |
| `data_source_failure` | Reader/provider error for that name |
| `other` | Catch-all |

Do **not** use STR-500 names (rs_percentile, consolidation_maturity, base_width, breakout, sector_mrs, volume).

---

### PerNameBacktest

| Field | Rules |
|-------|--------|
| window_start / window_end | Last 1 year of completed sessions for boards |
| trades | Real book trades only |
| trade_count | Includes open marked position if any |
| net_return | Closed PnL in window + open MTM |
| win_rate | Closed + marked-open (win if return > 0) |
| max_drawdown, profit_factor | On that name’s attributed equity path |
| best_trade / worst_trade | |
| equity_curve | Optional for detail tab |
| never_selected_in_window | true ⇒ excluded from boards |

---

### BoardRow

rank, symbol, signal (today), return, trades, win_rate, max_dd, profit_factor.

**Inclusion:** history-valid **and** `never_selected_in_window = false`.  
**Top 5:** `net_return > 0`, desc.  
**Least 5:** lowest `net_return`, including negatives / zeros that still had a trade.

---

### LtmTechnicals

| Field | Notes |
|-------|--------|
| momentum_252 | null if unavailable |
| close_t / close_t_minus_252 | |
| rank_among_eligible | null if ineligible |
| gate_pass | strict `>` 0.50 |
| selected | |
| clock_status / sessions_to_rebalance | |
| hard_filters_pass | alias of eligibility (data + gate), not EMA/RSI |

Forbidden as decision tiles: RSI, SMA/EMA stack, ATR, volume multiple, RS vs index, sector rotation.

---

## Validation summary

- Momentum undefined ⇒ ineligible; render unavailable, never 0.
- Exact +50% ⇒ failed_momentum_gate.
- `sessions_since_rebalance` must survive process restart.
- Open MTM uses scan-session adjusted close or last mark; **no live exit**.
- Survivorship: if PIT membership missing, `survivorship_biased = true` and UI must label it.
