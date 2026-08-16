# Research: Long-Term Buy & Hold Momentum Scanner

**Feature**: `037-ltm-scanner-dashboard`  
**Date**: 2026-08-15  
**Status**: Phase 0 complete — no `NEEDS CLARIFICATION` remaining in Technical Context

---

## 1. Where LTM lives relative to Production / RE engines

**Decision:** LTM is a **selectable Scanner strategy** with its own evaluate → backtest → publish pipeline. It is **not** a lab Decision Object engine and **not** a change to Production composite scoring.

**Rationale:** The spec forbids confusing LTM with Production, RE-001, RE-002, or Buy-and-Hold Top Momentum. Current `score_recommendation_service` classifies BUY/WATCH/REJECT from a composite score (70 / 55). LTM classifies from a cross-sectional rank after a +50% gate. Mixing those in one shortlist would violate both products.

**Alternatives considered:**

| Alternative | Why rejected |
|-------------|--------------|
| Score Production with 252-session momentum | Would change live advisory; spec forbids it |
| Lab engine (RE-00x) emitting Decision Objects | Spec is Scanner-dashboard first, not Rec Lab |
| Silent strategy tag on Production rows | Operator would not see a distinct strategy name |

---

## 2. How “backtest every history-valid name” is computed

**Decision:** Run **one vectorized book replay** on the aligned close matrix, then **attribute** each name’s fills. Every name with valid 252-session history receives a completed backtest result (possibly an empty blotter). Do **not** launch hundreds of independent per-symbol strategy engines.

**Rationale:** LTM selection is cross-sectional (top 10 of the universe). A per-symbol isolated replay (apply +50% only to that name) is a different strategy (clarify Q3 rejected this). One matrix pass is how the published engine works and finishes well inside a 60-second scan budget.

**Pipeline:**

1. Load adjusted closes for active NIFTY 500 + NIFTY 500 index onto the master calendar.
2. `momentum = close.pct_change(252)` with no fill of missing prints.
3. On each rebalance session (`i >= 252` then every 252 sessions): eligible = finite momentum `> 0.50`; take top `min(10, n)` by momentum desc, ticker asc.
4. Mode A: sell all, split cash equally across selected names (0 → 100% cash).
5. Replay fills at signal close (research). Live default remains next-open (not used for boards).
6. Slice each symbol’s blotter. For the last 1 year of completed sessions: closed trades overlapping the window + mark-to-market of a still-open book position at the scan session.
7. Top 5 / Least 5 require **≥ 1 real book trade** in that window.

**Alternatives considered:**

| Alternative | Why rejected |
|-------------|--------------|
| 500 independent backtests | Wrong economics; violates Q3; slow |
| Backtest only today’s top 10 | Violates Q1; Top 5 could not include today’s REJECT |
| Buy-and-hold 1Y return | Violates filter parity and Q3 |

---

## 3. Persistence isolation

**Decision:** Store LTM latest scan under `strategy_id = 17_long_term_mom`. **Never** write Production `scan_results` or cache key `scanner:latest:v1`.

**Rationale:** `scan_store` is a singleton latest-scan. Overwriting it would swap Production favorites for LTM overnight. 017/018/021 cache + single-write contracts assume Production shape.

**Shape:**

- `strategy_scan_latest(strategy_id PK, payload JSONB, computed_at, status)`
- `strategy_scan_runs` for history / progress
- `ltm_book_state` singleton (or per-account later) for `sessions_since_rebalance`, `last_rebalance_date`, cash, holdings

Cache key: `scanner:latest:17_long_term_mom:v1`.

**Alternatives considered:**

| Alternative | Why rejected |
|-------------|--------------|
| Overwrite Production latest | Breaks existing Scanner |
| Add optional field on same payload | Cache consumers assume Production columns |
| No persistence (compute on GET) | Restart would lose the 252-session clock |

---

## 4. Market data source

**Decision:** LTM reads **only** strategy-grade `daily_ohlcv` and `index_ohlcv` via `market_data_ingestion.reader`. Start is blocked by the existing freshness gate (`MARKET_DATA_STALE`) from spec 033.

**Rationale:** 033 already made strategy tables the SoT for strategy scanners. ACS / `historical_candles` remain for Production swing analysis. Mixing unadjusted ACS closes into 252-session momentum would let splits dominate rank (spec FR-008).

**Index identity:** `NIFTY500` as stored by 033 (`settings.strategy_index_store_symbol`).

**Membership:** `UniverseService.get_active_nifty500_symbols()`. If point-in-time history is absent, label results `SURVIVORSHIP_BIASED`.

---

## 5. Scan locking and concurrency

**Decision:** LTM uses lock name `scan:17_long_term_mom` (one LTM scan at a time). Production keeps its existing lock. LTM start still requires freshness. UI withholds the recommendation table while status is `evaluating` or `backtesting`.

**Rationale:** A shared global lock would block Production whenever someone runs LTM. Separate locks preserve Production. Two simultaneous universe scans are rare from the current UI.

---

## 6. Frontend composition

**Decision:** Add a strategy switcher on the existing Scanner page. When LTM is selected, render LTM summary, Rejection Breakdown, Top 5 / Least 5, and CandidateTable from the LTM payload. Stock detail Technicals / Backtest **branch** on `strategy_id` so Production tiles (EMA, RSI, ATR) are not shown as LTM decision inputs.

**Rationale:** Spec UI references are layout-only. Reusing CandidateTable and StockDetailPanel shell avoids a second dashboard.

**Run control:** `Run from Markets` stays for Production. LTM gets an explicit **Run LTM scan** on the LTM switcher so operators do not accidentally start Production.

---

## 7. Signals on rebalance vs mid-cycle

**Decision:** Reuse locked spec rules: rebalance session → selected names **BUY**; mid-cycle → selected names **WATCH**; all others **REJECT**; warmup → no BUY/WATCH.

**Rationale:** Already clarified in specify/clarify. Implementation must expose `clock_status` (`WARMUP` | `MID_CYCLE` | `REBALANCE`) on the payload.

---

## 8. Costs, Mode A / B, fills

**Decision:**

- Default book: **Mode A** + 25 bps/side for research replay (spec FR-049 / FR-020).
- Optional Mode B + NSE delivery fee model for comparison only.
- Board / replay fills: **signal close**, sells before buys.
- Live recommended fill (orders, not boards): **next open** — out of LTM scan MVP except as a labeled field on the payload.

**Rationale:** Matches spec assumptions. Mode B rupee fixtures are not DoD unless the Mode B switch is implemented.

---

## 9. Feature permission

**Decision:** Reuse existing `advanced_scanner` for LTM Scanner surfaces. No new permission key in MVP.

**Rationale:** Spec FR-054 says follow the existing feature-permission model. A second key would block traders who already have Scanner.

---

## 10. Deleted STR-005 bytecode

**Decision:** Do **not** import `services.strategies.str005` (pyc-only, no source on this branch). Copy **ideas** (scan_service / gates / backtest_ranking layout) as a new `strategies/ltm` package.

**Rationale:** Importing pyc-only modules is unreproducible and would drag STR-500 gate names (RS percentile, base width) into LTM — forbidden by FR-038.
