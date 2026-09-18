# Research: 52-Week High Breakout Scanner

**Feature**: `038-52w-high-breakout`  
**Date**: 2026-08-16  
**Status**: Phase 0 complete — no `NEEDS CLARIFICATION` remaining in Technical Context

---

## 1. Where 52-Week High Breakout lives relative to Production / LTM / RE

**Decision:** Register **52-Week High Breakout** (`09_52w_breakout`) as a **third first-class Scanner strategy**, sibling to Production and Long-Term Buy & Hold Momentum (`17_long_term_mom`). New package `backend/app/services/strategies/breakout52w`. It is **not** a Production scoring tweak, **not** a Rec Lab Decision Object, and **not** a mode inside the LTM engine.

**Rationale:** The spec requires a button immediately beside Long-Term Buy & Hold Momentum, a dedicated view, and an isolated Run that starts only this book. LTM already owns `/scanner/ltm/*`, lock `scan:17_long_term_mom`, and `ltm_book_state`. Mixing 52W math (close vs prior 252-high, volume average, 3-ATR trail) into that clocked 252-session momentum book would violate both products.

**Alternatives considered:**

| Alternative | Why rejected |
|-------------|--------------|
| Score Production with a 52-week flag | Would change live advisory; spec forbids it |
| Add a “mode” flag on LTM evaluate | Different calendar, gates, exits, and book state |
| Lab engine (RE-00x) | Spec is Scanner-dashboard first |
| Silent tag on LTM rows | Operator would not see a distinct strategy name or isolated Run |

---

## 2. How “backtest every history-valid name” is computed

**Decision:** Run **one vectorized book replay** on aligned high / low / close / volume + benchmark close, then **attribute** each name’s fills from that true 10-slot book. Do **not** launch hundreds of independent per-symbol engines.

Every name with valid 252-session high history receives a backtest result object (possibly an empty blotter). A name whose attribution errors or times out is recorded as `data_source_failure` and omitted from Top 5 / Least 5; the rest of the scan **still publishes** (clarify Q3).

**Rationale:** Slot allocation is cross-sectional (highest 60-session return into free 10% slots). An isolated single-name “if this name alone broke out” replay is a different strategy and would invent trades that the 10-name book never took. One matrix pass for indicators + a small Python loop over ≤10 holdings per session matches the published engine and stays inside the scan budget.

**Pipeline:**

1. Load adjusted OHLCV for active NIFTY 500 + NIFTY 500 index onto the master calendar. Missing print ⇒ NaN, never forward-filled to force a breakout.
2. Vectorize: `high_252_prior`, `vol_sma20` (includes today), `atr14` = SMA of true range (not Wilder), `mom60`, `market_ok` = index close `>` SMA50.
3. Session loop after warmup (`i >= 252`): update HWM/TSL for open names (skip entry bar); queue `atr_trail` exits; mark equity; if market-ok and free slots > 0, rank remaining buy-signal names and buy 10% of equity each.
4. Replay fills at signal close (research). Live recommended fill remains next-open (label on payload, not used for boards).
5. Slice each symbol’s blotter. Last 1 year of completed sessions: closed book trades overlapping the window + mark-to-market of a still-open book position at the scan session.
6. Top 5 / Least 5 require **≥ 1 real book trade** in that window.

**Alternatives considered:**

| Alternative | Why rejected |
|-------------|--------------|
| 500 independent trail engines | Wrong economics; boards would not be “real book trades” |
| Backtest only today’s BUY names | Today’s REJECT can legitimately top the 1Y board |
| Buy-and-hold 1Y return | Violates filter parity |
| Block the whole scan if one name’s attribution fails | Violates clarify Q3 |

---

## 3. Persistence isolation

**Decision:**

- Reuse existing **`strategy_scan_latest`** and **`strategy_scan_runs`** with `strategy_id = 09_52w_breakout`.
- Add **`w52_book_state`** (new table) for cash, holdings with **HWM + TSL**, last session processed, fill model. Do **not** write `ltm_book_state` or Production `scan_results`.
- Cache key: `scanner:latest:09_52w_breakout:v1`.

**Rationale:** 037 already namespaced latest-scan by `strategy_id`. LTM book state is a rebalance clock (`sessions_since_rebalance`). This book is event-driven and must persist trailing stops across restarts (FR-062). Sharing `ltm_book_state` would collide clocks and drop HWM/TSL.

**Alternatives considered:**

| Alternative | Why rejected |
|-------------|--------------|
| Overwrite Production latest | Breaks existing Scanner |
| Reuse `ltm_book_state` | Wrong lifecycle; missing HWM/TSL |
| Compute on GET with no persist | Restart would lower a ratcheted stop (defect) |

---

## 4. Market data source

**Decision:** Read **only** strategy-grade `daily_ohlcv` (open, high, low, close, volume) and `index_ohlcv` via `market_data_ingestion.reader`. Start is blocked by the existing 033 freshness gate (`MARKET_DATA_STALE`).

**Rationale:** `DailyOhlcv` already stores adjusted high/low/volume — 52W needs those fields; LTM only needed close. ACS / `historical_candles` stay for Production swing analysis. Mixing unadjusted highs with adjusted closes would invent false 52-week highs (FR-012).

**Index identity:** `NIFTY500` (`settings.strategy_index_store_symbol`). Used for MarketOK **and** reporting. NIFTY 50 is research-only and not the Scanner default.

**Membership:** `UniverseService.get_active_nifty500_symbols()`. If point-in-time history is absent, label `SURVIVORSHIP_BIASED`.

---

## 5. Scan locking and second Run (clarify Q2)

**Decision:** Lock name `scan:09_52w_breakout` (one 52W scan at a time). Production and LTM keep their own locks. `POST /scanner/w52/runs` while a 52W run is `queued` / `evaluating` / `backtesting` / `publishing` returns **409** `W52_SCAN_IN_PROGRESS` and **does not** cancel or queue. UI disables the 52W Run control while in-flight.

**Rationale:** Clarify Q2: ignore the second click. A shared global lock would block LTM/Production. Two parallel 52W runs would race HWM/TSL persistence.

---

## 6. Frontend composition

**Decision:** Extend the existing Scanner strategy tablist (currently LTM-only buttons beside the result views) with a **52-Week High Breakout** button immediately beside **Long-Term Buy & Hold Momentum**. Selecting it loads `/scanner/w52/latest` and does not replace LTM or Production in-memory state.

Reuse CandidateTable. Parameterize or lightly fork LTM summary / breakdown / boards so bucket labels and HOLD are strategy-owned. StockDetailPanel **branches** on `strategy_id` so LTM momentum tiles and Production EMA/RSI/ATR tiles are not shown as 52W decision inputs.

**Run control:** This view’s Run calls **only** `POST /scanner/w52/runs`. It MUST NOT call `/scanner/ltm/runs` or Production `Run from Markets`.

**Rationale:** Spec UI references are layout-only. Reusing the Scanner shell avoids a second dashboard. Clarify Q1 requires a distinct HOLD signal in the same table.

---

## 7. Signals and book status

**Decision:**

| Condition | Scan-results signal | Notes |
|-----------|---------------------|--------|
| New slot filled today | **BUY** | Stays BUY this session even though now open |
| Remains open after trail; not a new BUY | **HOLD** | Clarify Q1; omitted from Rejection Breakdown |
| Trail hit today (entry bar ≠ today) | Order-list **EXIT**; row is not HOLD | Sold-today if it would otherwise buy-signal |
| Buy signal, no free slot | **WATCH** | Ranked out / book full |
| Market filter off, stock legs would pass | **WATCH** + `blocked_by=market_filter` | No flatten |
| Failed a new-entry gate | **REJECT** | Exactly one first-failure bucket |
| Warmup | no BUY | STATUS=`WARMUP` |

Book status on the payload: `WARMUP` | `MARKET_OFF` | `ACTIVE`. There is **no** 252-session rebalance clock.

---

## 8. Costs, Mode B, fills, ATR

**Decision:**

- Default book: **Mode B** — 10% of current equity, max 10 names (published / canonical).
- Replay cost: published NSE delivery breakdown. Reuse the delivery profile already encoded in `backtest_service` cost helpers (brokerage cap, exchange, SEBI, stamp, GST, STT on sell, DP on sell). Do not invent a second fee engine unless those helpers cannot express the published formula; then add `breakout52w/costs.py` as a pure function.
- Replay / board fills: **signal close**, exits before entries.
- Live recommended fill: **next open** — labeled on the payload; not used for boards.
- ATR: **SMA of true range, period 14**, today’s bar included. Wilder / RMA is a defect.
- NaN ATR at entry: TSL = 90% of entry.

**Rationale:** Spec FR-016 / FR-031 / FR-057. LTM’s 25 bps Mode A default is the other book.

---

## 9. Partial backtest failure (clarify Q3)

**Decision:** After the shared book replay:

- Successful attribution → completed backtest object (empty blotter is valid).
- Attribution error / timeout / unusable series for that symbol → `data_source_failure`; exclude from boards; **do not** keep `recommendations_final` false for the whole run.
- Today’s evaluation signal (BUY / HOLD / WATCH / EXIT) is **not** cancelled solely because historical attribution failed.
- If the **shared** book replay itself throws, status is `failed` and recommendations stay non-final (that is not “one name failed”).

**Rationale:** Clarify Q3. Operators must still see today’s order list if one name’s history is corrupt.

---

## 10. Technical Context unknowns — resolved

| Topic | Resolution |
|-------|------------|
| Language / stack | Existing Python 3.11+ / FastAPI / React 18 |
| Storage | Reuse `strategy_scan_*`; new `w52_book_state` |
| Data | `daily_ohlcv` + `index_ohlcv` (already has high/low/volume) |
| Concurrency | Dedicated lock; 409 on second start |
| Scan budget | ≤ 90s p95 for ~500 names × ~1,720 sessions (heavier daily trail than LTM’s annual clock) |
| Auth | `advanced_scanner` |
| Live broker | Out of scope; paper prefill reused |
