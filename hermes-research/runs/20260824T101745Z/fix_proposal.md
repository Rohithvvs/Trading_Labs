# Fix proposal (NOT applied) — iteration 3

**Run:** `hermes-research/runs/20260824T101745Z`  
Tick rounding, session filter, and FYERS 2003–2008 backfill are already in. Scanner KERNEL is unchanged.

**Do not apply until APPROVE.**

---

## First divergent trade

```
Trade 1: TV 2002-08-22 @ 16.3 → 2002-09-03 @ 16.3
         TL 2003-12-11 @ 49.8 → 2003-12-12 @ 48.5
bar: FYERS WELCORP-EQ has no candles 2002-08-22 … 2003-12-09 (verified empty fetch)
```

## TV behavior not reproduced

1. **2002-08-22 through 2003-12-09 daily opens** — FYERS returned none. Not an engine bug.
2. **Same-session prices in 2003** — 2003-12-11 TV 101.6 vs Labs open 49.8 (≈2×). Adjustment/vendor series, not fill delay.
3. **0.05 quote differences** — 2008-09-01 Labs O=315.25 vs TV 315.3. Half-even tick gives 315.2; half-up would break the already-matching 356.65→356.6 case.

## Proposed patch

Do **not** change `buy_signal`, ATR trail, or invent 2002 OHLC.

### Step 1 — optional golden OHLC for TV_TESTER only

If `hermes-research/tradingview_reference/Strategy_001/ohlc.csv` exists (columns at least `date,open,high,low,close,volume`), `run_symbol_window_backtest(..., execution_profile="TV_TESTER")` loads that series instead of `daily_ohlcv` for WELCORP.

File is **not** in the repo today. This step is dormant until you drop the TradingView chart export (same symbol/range as the tester) into that path.

Harness already allowed; engine hook: `window_backtest.load_symbol_window_bars` branch when profile is TV_TESTER and the CSV is present.

Tests: synthetic CSV of 5 sessions drives the tape; KERNEL still uses DB.

### Step 2 — do not add a second rounding mode

Leave `round_to_tick` as `round(px, 1)`. Further 0.05 discrepancies are treated as vendor OHLC until Step 1 CSV exists.

### Step 3 — data you must supply for Trade 1

Export TradingView NSE:WELCORP 1D OHLC **2000-06-23 → 2026-08-24** (same chart as `trades.csv`) as `ohlc.csv` next to `trades.csv`. FYERS cannot fill 2002–2003-12-09.

## Risk

KERNEL/TV_COMPAT/scanner unchanged. CSV override is TV_TESTER-only and off unless the file exists.

## Tests / re-compare

Existing w52 + tape tests. After you add `ohlc.csv`, re-run the harness; index scan from Trade 1. PASS only if sequence matches within 0.01.

Without that file, Trade 1 cannot match. This proposal does not pretend otherwise.

```
APPROVAL REQUIRED
Reply APPROVE to apply this proposal via code changes.
Reply REJECT <reason> for a revised proposal.
Do not modify the backtesting engine until then.
```
