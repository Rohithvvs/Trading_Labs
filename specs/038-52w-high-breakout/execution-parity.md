# 52W Backtest Execution Parity

**Date:** 2026-08-21  
**Scope:** Make the existing 52-Week High Breakout book replay explicit about signal vs order vs fill, without rewriting the scanner or the Production `BacktestService`.

---

## 1. Root-cause analysis

TradingView screenshots (3Y 242 / 5Y 490 / 8Y 860 trades, ~±1.3% average, rupee P&L consistent with **1 share** and **0% commission**) are **not** produced by the published 038 kernel.

The 038 kernel (still the Scanner default, profile `KERNEL`) is:

- `close >= prior 252-session high` (current bar excluded)
- `volume > SMA20` (today included)
- NIFTY 500 close `> SMA50`
- hold until **close < HWM-based 3× SMA-ATR**
- fill at **signal close**
- Mode B 10% × 10 book, NSE delivery costs, ₹1,00,000

A true 252-session closing breakout cannot emit ~242 round-trips on a ~760-bar 3Y window (see `parity-audit-glaxo.md`). That gap is a **strategy-definition** difference, not a fill-timing bug.

Separately, the engine **did** have real execution defects relative to a TradingView-style broker emulator:

| Issue | Before | After |
| --- | --- | --- |
| Signal vs fill | Signal close was the fill | Explicit order then fill |
| Fill delay | Hard-coded same-bar close | `SAME_BAR_CLOSE` (KERNEL) or `NEXT_BAR_OPEN` (TV_COMPAT) |
| Open prices | Loaded in `daily_ohlcv` but **not used** by window replay | `open_m` passed into `replay_book` |
| Intrabar stops | Close-only; an intraday pierce that recovers is not an exit | `CLOSE_CROSS` vs `INTRABAR_TOUCH` |
| `eod_liquidation` | Name implied daily EOD | Still stored as `eod_liquidation` for 038 fixtures; canonical `BACKTEST_END_LIQUIDATION` is end-of-sample only |
| Trade stats | Frontend recomputed win/loss from rounded `%` | Canonical `ledger` from net P&L |
| 3 vs 5 vs 16 trades | Different **windows** (3Y / 5Y / ALL), not a cache mix | Documented; same backtest id + symbol + range is cached by config+data hash |

The Production engine in `backtest_service.py` already had FEAT-008 `REALISTIC` next-bar-open fills. The 52W scanner **does not** use that engine (it must remain a 10-slot book). This work extends `breakout52w.book_engine`, it does not replace `BacktestService`.

---

## 2. Existing backtest execution flow

```
GET /scanner/w52/symbols/{symbol}?window=&start_date=&end_date=&execution_profile=
  → window_backtest.run_symbol_window_backtest
    → fetch_equity_history / fetch_index_history  (daily_ohlcv, includes open)
    → slice_replay_dates (252-session warmup before the performance window)
    → book_engine.replay_book
         1. (TV_COMPAT) fill pending entries at next open
         2. delist
         3. trail / stop  (CLOSE_CROSS or INTRABAR_TOUCH)
         4. last candle only → BACKTEST_END_LIQUIDATION
         5. BuySignal → ORDER_CREATED
            KERNEL: fill at signal close
            TV_COMPAT: ENTRY_PENDING until next open
    → ledger.aggregate_closed_trades
    → analytics.build_symbol_dashboard
  → frontend BacktestAnalyticsDashboard (ledger-first stats)

POST /scanner/w52/runs
  → scan_service.run_scan
    → one vectorized replay_book over the universe (Mode B book)
    → per-symbol failure recorded; scan status completed_partial if incomplete
```

Position lifecycle: `FLAT → ENTRY_PENDING → LONG → FLAT`. Pyramiding stays 0. Same-session rebuy stays blocked (`sold_today`).

---

## 3. TradingView vs TradingLabs (remaining)

These remain legitimate differences even after execution-model work. **Do not force 242 / 490 / 860.**

| Factor | TradingView reference | TradingLabs KERNEL | TradingLabs TV_COMPAT |
| --- | --- | --- | --- |
| Entry rule | Unknown (too frequent for 252-high) | 038 BuySignal | Same BuySignal |
| Fill | Typically next open | Signal close | Next open |
| Stop | Unknown; avg ±1.3% implies tight | Close < 3×SMA ATR | Intrabar touch of 3× ATR |
| ATR | Pine `ta.atr` is Wilder | SMA TR(14) | SMA TR(14) |
| Sizing | ~1 share, ₹10L | 10% of ₹1L | 10% of ₹1L |
| Commission | 0% | NSE delivery | NSE delivery |
| Data | TV NSE | FYERS `daily_ohlcv` | Same |
| 3Y trades (GLAXO-class) | 242 | ~4 closing breakouts | Still a 252-high book; count will not jump to 242 |

Pine for `52W Breakout - Test` is still not in the repo. TV_COMPAT only aligns **broker timing**, not the unknown TV entry/exit formula.

---

## 4. Files changed

- `backend/app/services/strategies/breakout52w/execution.py` (new)
- `backend/app/services/strategies/breakout52w/ledger.py` (new)
- `backend/app/services/strategies/breakout52w/book_engine.py`
- `backend/app/services/strategies/breakout52w/window_backtest.py`
- `backend/app/services/strategies/breakout52w/analytics.py`
- `backend/app/services/strategies/breakout52w/attribution.py`
- `backend/app/services/strategies/breakout52w/period.py`
- `backend/app/services/strategies/breakout52w/scan_service.py`
- `backend/app/routes/scanner.py`
- `backend/app/config/settings.py`
- frontend dashboard / API / stock-detail period bounds
- `backend/tests/unit/test_w52_execution.py`

No new tables. Open already exists on `daily_ohlcv`.

---

## 5. How to compare with TradingView

```
GET /api/v1/scanner/w52/symbols/GLAXO-EQ?window=3Y&start_date=2023-08-21&end_date=2026-08-21
GET /api/v1/scanner/w52/symbols/GLAXO-EQ?window=3Y&start_date=2023-08-21&end_date=2026-08-21&execution_profile=TV_COMPAT
```

`W52_EXECUTION_PROFILE=KERNEL` remains the published scan default so 038 fixtures stay intact.

`historical_fill_mode=LOWER_TIMEFRAME` uses `historical_candles` 60m/15m when present; otherwise it **falls back to DEFAULT_OHLC** and records `diagnostics.lower_timeframe_fallback`. It never synthesizes ticks.

---

## 6. 3Y / 5Y / 8Y windows

Inclusive calendar ends matching the screenshots (clamped to last stored session):

- 3Y: 2023-08-21 → 2026-08-21
- 5Y: 2021-08-21 → 2026-08-21
- 8Y: 2018-08-21 → 2026-08-21

The Detailed Trade Log **grows** from 3 → 5 → 16 trades when the operator switches 3Y → 5Y → ALL because trades are counted by **entry date inside the requested window**. That is not pagination and not a stale merge: the Backtest tab sends `start_date`/`end_date` on every range change, and the API uses `cache: "no-store"`.

---

## 7. 755-stock portfolio

Scan replay remains **one book**, not 755 independent concatenations. Cash, slots, and ranking are cross-sectional. Per-symbol signal/trail exceptions are recorded on `failed_symbols`; a non-empty list sets `incomplete=true` and run status `completed_partial`.

The previous 100+ minute hang was O(N²) prior-high recomputation; sliding-window maps in `replay_book` already addressed that. Portfolio timeout remains `W52_PORTFOLIO_BACKTEST_TIMEOUT_SECONDS` (default 300s).
