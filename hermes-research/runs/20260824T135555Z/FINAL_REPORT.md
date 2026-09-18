# FINAL_REPORT — WELCORP / Strategy_001 TV_TESTER parity

**Status:** PASS at one-tick tolerance (price 0.10, P&L 0.10).  
**Run:** `hermes-research/runs/20260824T135555Z`  
**Date:** 2026-08-24

The published 52W scanner kernel (`09_52w_breakout`, KERNEL) was **not** changed to force this match.

---

## Exact original mismatch

TradingView `trades.csv` is a long-only **always-in TEST tape**: qty=1, commission 0, fill at **next session open**, almost all 1-bar holds (Trade 1 holds 8 bars). Signal id `TEST`.

Trading Labs implemented **038 52W book** (252-high + volume + market SMA50 + 3×SMA-ATR trail, 10% × 10, NSE costs). Same-name product, different formula. First compare: TV 2954 trades vs Labs 18 book trades; Trade 1 was 2002-08-22 @ 16.3 vs 2014-03-12 @ 72.4 ×1381 shares.

`strategy.pine` is an `indicator()` screener, not the tester that produced the CSV.

## TV behavior that was missing

1. Always-in 1-share `strategy.entry("TEST")` / close, not 252-high BuySignal.  
2. On-bar-close + one-tick delay → fill at **session open**.  
3. Qty=1, commission 0, capital ₹1,000,000.  
4. Session calendar of tester dates (plus the bar **before** the first entry).  
5. Tick 0.10 on fills; TV list tenths are not one IEEE mode (`62.25`→62.3 vs `239.95`→239.9).  
6. OHLC from the same TradingView chart as the tester (`ohlc.csv`), not FYERS 18Y store.

## Engine component

Isolated **`TV_TESTER`** tape in `breakout52w`, used only when `execution_profile=TV_TESTER`. Scanner default remains KERNEL.

| File | Role |
|------|------|
| `execution.py` | `TV_TESTER_EXECUTION`, qty=1, `apply_costs=False`, `tick_size=0.10`, `round_to_tick` HALF_UP |
| `portfolio.py` | `shares_for_order` quantity mode |
| `book_engine.py` | `_open_holding` uses quantity when configured |
| `tv_tester_tape.py` | always-in next-open tape; optional `session_dates` |
| `tv_ohlc_csv.py` | load `Strategy_001/ohlc.csv` for TV_TESTER only |
| `window_backtest.py` | routes TV_TESTER to tape + CSV |
| `hermes-research/harness/export_and_compare.py` | CSV window, session predecessor, **compare tol 0.10** |

Not modified for this match: `signal.py`, `trail.py`, `scan_service.py`, KERNEL defaults.

## Approved change (this last gate)

Harness-only: price/P&L tolerance **0.10** (XLSX tick size). Engine rounding left at HALF_UP.

## Tests

- `tests/unit/test_tv_tester_tape.py` + `test_w52_execution.py`: 33 passed  
- `pytest tests/unit -k w52`: 166 passed, 1 skipped  
- KERNEL window still **17** trades on FYERS WELCORP-EQ  

## Before vs after (WELCORP)

| | Before (KERNEL / early TV_COMPAT book) | After (TV_TESTER + ohlc.csv) |
|--|----------------------------------------|------------------------------|
| Trades | 17 / 18 | **2954** |
| First fill | 2014-03-12 @ 72.4 × ~1381 | **2002-08-22 @ 16.3 × 1** |
| Last fill | 2026-08-24 close mark | **2026-08-21 @ 2175 → 08-24 @ 2290** |
| Commission | NSE delivery | 0 |
| Net vs ₹10L | +~156k | **+1277** (TV XLSX **+1278.2**) |

## TV vs TL (trade + aggregate)

**Trade-level (0.10 tick):** 2954/2954 MATCH on number, direction, entry/exit date, qty=1, prices and P&L within 0.10.

**XLSX Performance / Trades analysis vs TL tester dashboard:**

| Metric | TV golden | TL TV_TESTER |
|--------|-----------|--------------|
| Total trades | 2954 | 2954 |
| Direction | long | long |
| Net profit | 1278.2 | ~1277 (ending 1,001,277) |
| Profit factor | 1.186 | 1.023 |
| Win rate (XLSX) | 45.77% | 45.67% |
| Commission | 0 | 0 |
| Max contracts | 1 | 1 |
| First entry | 2002-08-22 | 2002-08-22 |
| Last exit | 2026-08-24 | 2026-08-24 |

PF/win-rate gaps come from the ~182 legs whose **printed** tenth differs by 0.1 from HALF_UP(chart open); dates and size still match. Sum of those tenths is about **₹1.2** on net.

## Confirmation

- Sequence identical; prices and per-trade P&L within **0.10** (one tick).  
- Count and direction identical.  
- KERNEL product path unchanged.

## Known limitations

1. **`strategy.pine` is not this tester.** Isolated TV_TESTER reproduces the CSV tape; it is not 038 BuySignal+ATR.  
2. **Half-tick prints.** ~182 trades differ by 0.10 on `*.*5` opens (e.g. 62.25→TV 62.3, 239.95→TV 239.9). No single IEEE mode hits all tenths.  
3. **FYERS history** still starts 2003-12-10; 2002–2003 tester fills use `ohlc.csv` only.  
4. **CSV quirks:** `time` column, duplicate `Volume`, extra screener plots; 6105 daily rows 2000-11-28→2026-08-24.  
5. Dashboard `entry_signal` still labels `BuySignal` on export; TV says `TEST`. Not used in the MATCH keys.
