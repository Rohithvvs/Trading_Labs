# GLAXO 52W Backtest Parity Audit

**Date:** 2026-08-19  
**Golden case:** TradingView `GLAXO` vs Trading Labs `GLAXO-EQ`  
**Status:** Diagnosis complete. 038 kernel unchanged. Pine Script still unavailable.  
**Pine Script:** Not found in the repo, Google Drive, or local `*.pine` files.  
**Updated Labs blotter:** 4 completed `atr_trail` trades + 1 open MTM on 2026-08-19 @ 3032.40 (not a completed trade).

Replay evidence: `scratch/w52_glaxo_parity_audit.py`, `scratch/glaxo_w52_parity_daily.csv`.

---

## ROOT CAUSE ANALYSIS

```text
Primary mismatch:
TradingView "52W Breakout - Test" and Trading Labs "52-Week High Breakout"
are different algorithms. They are not two ports of the same rules.

Labs implements the 038 kernel:
  close >= prior 252-session HIGH
  AND volume > 20-session average
  AND NIFTY500 close > SMA50
  hold until close < HWM-based 3x SMA-ATR trail
  one position, no pyramid, no same-session rebuy
  fill at signal close
  Mode B: 10% of equity

On GLAXO-EQ over 2023-08-21..2026-08-18 that kernel produces exactly
the 4 trades the UI reported. Replaying the stored series confirms
those four fills. This is not a cache, symbol-mix, or rounding bug.

A true 52-week (252-session) breakout cannot generate 241 trades on
this series. In the test window GLAXO has:
  761 daily bars
  19 days with close >= prior 252 high
  16 distinct 252-high streaks
  52 days with high  >= prior 252 high
Even "enter every 52-week-high day, exit next bar" maxes at 19 (close)
or 52 (intraday high). 241 trades requires a much shorter cycle
(~3 sessions average hold if nearly always in the market).

Secondary mismatch:
Position sizing, costs, and capital:
  TV: ₹10,00,000, commission 0%, P&L ₹701.40, largest win ₹230
      ⇒ qty is 1 share (₹230 = 2025-05-28 close-to-close of +230.00)
  Labs: ₹1,00,000, NSE delivery costs, 10% of equity per fill
These change rupee P&L, not trade count.

TradingView entry logic:
UNKNOWN — script "52W Breakout - Test" was not in the workspace.
Inferred from the report + GLAXO series:
  - 241 trades / 761 bars ≈ 1 round-trip per ~3 sessions
  - avg win ~+1.25%, avg loss ~-1.28%, PF 1.126
  - largest profit ₹230.00 equals GLAXO 2025-05-28 close-to-close
    (prev close 3118.20 → close 3348.20)
  That is a 1-day capture of a +230 up-day, not a 3-ATR hold.
  No 252-bar definition on this data produces ~241 trades.

Trading Labs entry logic (verified in code):
  BuySignal(s,t) ⇔
    MarketOK(t)
    AND close(t) >= max(high[t-252 : t])   # today excluded
    AND volume(t) > mean(volume[t-19 : t]) # today included
    AND not held AND not sold today
  Fill = that session's adjusted close.
  Warmup: no entries while session_index < 252.

TradingView exit logic:
UNKNOWN. Report shape (avg ±1.25%, 241 trades, 0 breakeven,
largest win = one daily close-to-close) is incompatible with a
3x ATR trailing hold. Likely a short Donchian / 1-bar / tight %
or ATR stop, possibly long+short. Cannot confirm without Pine.

Trading Labs exit logic (verified):
  No exit on the entry bar.
  HWM = highest CLOSE since entry (not highest high).
  TSL starts at fill - 3 * ATR14_SMA (or 0.90*fill if ATR NaN).
  TSL never decreases.
  Exit iff close < TSL (intraday pierce that recovers is NOT an exit).
  End of sample: eod_liquidation (live must not invent that day).
  All 4 GLAXO window trades exited with reason atr_trail.

TradingView ATR logic:
UNKNOWN. Pine ta.atr() is Wilder/RMA. Labs explicitly forbids Wilder.
TV largest win/loss and average ±1.25% do not match 3x ATR on GLAXO
(3x ATR is several percent; Labs losers are -5.2% and -12.3%).

Trading Labs ATR logic (verified):
  TR = max(H-L, |H-C_prev|, |L-C_prev|)
  ATR14 = SMA of 14 TRs including today. Not Wilder.
  Trail multiplier = 3.

TradingView trade count: 241
Trading Labs trade count: 4

Why trade counts differ:
1. Different entry frequency. Labs fires on a 252-session closing
   breakout (19 candidate days, 4 actual round-trips after the trail
   holds through consecutive new highs). TV's 241 fills require a
   condition that is true on the order of every few sessions.
2. Different exit. Labs holds 1–3 months on a 3x ATR close trail.
   TV's average win/loss of ~1.25% and the exact ₹230 one-day capture
   are short-hold / tight-stop behaviour.
3. Not explained by: 2-day date window, ₹10L vs ₹1L, commission,
   slippage, cache, or GLAXO vs GLAXO-EQ mapping.

Data differences:
  Labs store: daily_ohlcv symbol=GLAXO-EQ, 4493 bars,
  2008-07-22 → 2026-08-18, source FYERS / historical_candles.
  No GLAXO alias rows. NIFTY500 index 4474 bars, same span.
  Window: 761 sessions, first 2023-08-21 close 1404.6,
  last 2026-08-18 close 2877.4.
  TV OHLCV was not exported, so bar-by-bar TV vs Labs compare is
  pending. Prices of the 4 Labs trades (1544.05, 1647.95, 2594.30,
  3348.20) are consistent with NSE GLAXO. The +230.00 close-to-close
  on 2025-05-28 matching TV's largest profit suggests the two
  series agree on at least that bar at 1-share precision.

Cache/state differences:
  Not the 241 vs 4 cause. The 4 fills replay from GLAXO-EQ OHLCV
  with no result cache. Frontend GET /scanner/w52/symbols/{symbol}
  uses cache: "no-store" and rejects a mismatched symbol.
  Scan-latest Redis key is strategy-scoped
  (scanner:latest:09_52w_breakout:v1), not a per-symbol backtest key.

Position-sizing differences:
  TV ~1 share on ₹10L, 0% commission, total P&L ₹701.40.
  Labs 10% of ₹1L, NSE delivery fees. Affects rupees, not count.

Date/timeframe differences:
  TV: 2023-08-19 → 2026-08-19, 1D. 2023-08-19 was Saturday;
      first NSE session is 2023-08-21.
  Labs: 2023-08-21 → 2026-08-18 (last stored EOD; 2026-08-19 may
      still be the live session). Functionally the same 3Y daily
      window. Timezone: Asia/Kolkata session dates.
```

---

## STRATEGY PARITY MATRIX

| Behavior | TradingView | Trading Labs | Same? |
| --- | --- | --- | --- |
| Symbol | GLAXO | GLAXO-EQ (only alias in `daily_ohlcv`) | Yes (mapping) |
| Exchange | NSE (assumed) | NSE / FYERS EOD | Likely |
| Timeframe | 1D | 1D `daily_ohlcv` | Yes |
| 52W lookback | **Not verified** (script missing). 241 trades is incompatible with 252-bar highs on this series | `max(high[t-252:t])`, today excluded | **No / unverified** |
| Breakout formula | Unknown | `close >= prior_252_high` (high-only print fails) | **Unverified** |
| Uses previous 252 bars? | Unknown | Yes, `highs[t-252:t]` | Unverified |
| Entry condition | Unknown; far more frequent than 252-high | Close breakout + volume > SMA20 + MarketOK + not held/sold today | **No** |
| Entry timing | Unknown (`process_orders_on_close` unknown) | Signal-session close | Unverified |
| Exit condition | Unknown; avg ±1.25% | `close < TSL` after entry bar; reason `atr_trail` | **No** |
| ATR calculation | Unknown; Pine `ta.atr` would be Wilder | SMA of true range, not Wilder | Unverified / likely no |
| ATR period | Unknown | 14 | Unverified |
| ATR multiplier | Unknown; not 3x given trade size | 3.0 | **Likely no** |
| ATR trailing logic | Unknown | HWM = highest close; TSL never decreases; ratchet only on new closing high | **Likely no** |
| Stop update timing | Unknown; TV `strategy.exit` can fill intrabar | Evaluated on session close; intrabar pierce that recovers does not exit | **Likely no** |
| Position sizing | ~1 share (₹230 max win on 1 share) | 10% of current equity, fractional shares allowed | **No** |
| Pyramiding | Unknown | None (`MAX_POSITIONS` still 1 name here; no add-ons) | Unverified |
| Commission | 0.00% | NSE delivery breakdown (brokerage cap 20, STT, stamp, GST, DP) | **No** |
| Slippage | Unknown / 0 | None beyond published fees | Unverified |
| Initial capital | ₹10,00,000 | ₹1,00,000 | **No** |
| Date range | 2023-08-19 → 2026-08-19 | 2023-08-21 → 2026-08-18 | Functionally same |
| Warm-up period | Unknown | 252 sessions before entries; fetch pads ~400 calendar days | Unverified |
| Candle source | TradingView NSE GLAXO | FYERS daily → `daily_ohlcv` | Unverified bar-for-bar |
| Corporate adjustments | Unknown | FYERS history (typically split-adjusted) | Unverified |
| Order fill model | Unknown (TV default = next open unless `process_orders_on_close`) | Signal close | **Likely no** |
| Open-position handling | Unknown | Window blotter counts closed trades; open MTM tagged `open_mtm` and excluded from win rate | Unverified |
| Volume filter | Unknown | `volume > SMA20` (equal fails) | Unverified |
| Market filter | Unknown | NIFTY500 close > SMA50 | Unverified |
| Book / slots | Single-name TV strategy | Scan book is 10 names × 10%; stock-detail replay uses universe `{symbol}` so GLAXO always gets the slot when it signals | **No** (scan vs single-name) |
| Re-entry | Unknown; 241 fills imply frequent re-entry | After trail exit, next session may rebuy if still a buy-signal; same-session rebuy blocked | **No** |
| Signal debounce | Unknown | `held` and `sold_today` suppress additional BUYs | **Likely no** |
| Shorts | 0 breakeven; 118/241 winners — could be long-only or L/S | Long only | Unverified |
| Timezone | TV exchange timezone for NSE | `Asia/Kolkata` session dates | Likely |

Nothing is marked "same" for strategy math except symbol mapping, daily timeframe, and the calendar window.

---

## FIRST DIVERGENCE

**Earliest Labs signal in the window**

| | |
| --- | --- |
| Date | 2023-09-13 |
| OHLC | O 1465.95 / H 1552.00 / L 1455.40 / C 1544.05 |
| Prior 252 high | 1480.85 |
| Condition | `1544.05 >= 1480.85` (pass), volume 335,670 vs SMA20 (pass) |
| Labs action | BUY @ 1544.05, hold until 2023-10-23 @ 1463.80, −5.20%, `atr_trail` |

**Before that date (2023-08-21 → 2023-09-12)**

Labs generated **zero** entries. First bar 2023-08-21: close 1404.60 vs prior-252 high 1487.00 — not a 52-week closing breakout.

TV produced 241 trades over the same ~761 sessions (~0.32 fills per session). That rate implies on the order of **5–10 TV fills in the 17 sessions before 2023-09-13**.

**Therefore the first divergence is not 2023-09-13.** It is the first TV fill inside 2023-08-21..2023-09-12 (possibly the first session), where:

```text
TradingView: BUY (unknown short-cycle rule)
Trading Labs: no BUY (close still below the prior 252-session high)
```

Without the Pine Script and without a TV trade list, the exact TV fill date/price of that first extra trade cannot be named.

**Clearest later illustration (same bar, opposite action)**

| 2025-05-28 GLAXO | |
| --- | --- |
| OHLC | O 3131.00 / H 3398.00 / L 3105.90 / C 3348.20 |
| Prev close | 3118.20 |
| Close-to-close | **+230.00 = TV largest profit** |

- TradingView: a completed trade that realized ₹230 (1 share), i.e. it captured that 1-day up-move as a round-trip.  
- Trading Labs: **opened** the 4th window trade that morning-of-close (entry 3348.20) and held on the 3x ATR trail until 2025-08-01 @ 2936.50 (**−12.30%**).

Same stock, same day, opposite lifecycle. That is an exit/hold-rule mismatch, not a data glitch.

---

## Labs GLAXO 3Y blotter (replay-confirmed)

| # | Entry | Exit | Entry px | Exit px | Return | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2023-09-13 | 2023-10-23 | 1544.05 | 1463.80 | −5.20% | atr_trail |
| 2 | 2023-11-20 | 2024-02-14 | 1647.95 | 2153.50 | +30.68% | atr_trail |
| 3 | 2024-05-30 | 2024-08-30 | 2594.30 | 2745.10 | +5.81% | atr_trail |
| 4 | 2025-05-28 | 2025-08-01 | 3348.20 | 2936.50 | −12.30% | atr_trail |

Full-history replay also has 8 earlier GLAXO trades (2013–2020) that sit outside the 3Y window. The Backtest tab correctly filters them out.

---

## Symbol isolation / cache (phases 15–17)

Verified, not the 241 vs 4 cause:

- Request path: `GET /scanner/w52/symbols/{symbol}?window=&start_date=&end_date=`
- Engine input is `match["symbol"]` from the 52W scan payload, then `fetch_equity_history(symbol)` on `daily_ohlcv`.
- Only `GLAXO-EQ` rows exist; prices match GLAXO.
- `dataset_fingerprint` includes symbol, first/last close, bar count.
- Frontend `fetchW52SymbolDetail` uses `cache: "no-store"` and throws if `body.symbol` ≠ requested symbol.
- `hydrateStrategyBacktest` rejects `replay_kind !== "symbol_window"` and mismatched symbol (covered by unit tests).
- Backtest tab `useEffect` deps: `row.symbol`, `range`, `startDate`, `endDate`.
- Scan Redis key is per-strategy, not per-symbol backtest. Window backtest does not cache results.

---

## What was not changed

No strategy, fill, trail, or metric code was modified. Forcing Labs to print 241 / 48.96% / 1.126 would be fabricating TV numbers, which is forbidden.

Faithful parity requires the actual Pine source (or a TV trade-by-trade export). Until that exists, Labs already matches **its own** published 038 kernel on GLAXO.

---

## Blocked implementation work

Cannot start rule changes until one of:

1. Paste the full Pine Script for `52W Breakout - Test`, or  
2. Export TV's GLAXO trade list + OHLCV for 2023-08-19 → 2026-08-19, or  
3. Explicitly decide that the 038 kernel (252-high + 3x ATR book) is the product, and TV "Test" is not the reference.

If (3): GLAXO stock-detail backtest is already behaving as specified (4 trail-held breakouts). Remaining work is optional data-export parity, not a 241-trade rewrite.
