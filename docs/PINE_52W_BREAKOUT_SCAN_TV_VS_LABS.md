# 52-Week High Breakout — TradingView vs Trading Labs (pin to pin)

This is the full scan-path comparison for the Pine you pasted: why TradingView’s Pine Screener and Trading Labs Strategy Tester printed **different stock names**, what each platform actually evaluates, and what you have to change so Labs matches TradingView.

It is **not** the WELCORP Strategy Tester tape (1-share always-in). That lifecycle lives in `docs/TRADINGVIEW_VS_TRADING_LABS.md`.

---

## 0. One-line answer

The Pine **rules** are now the same. The names still differed because the two products were **not looking at the same daily candle**.

TradingView Pine Screener evaluates **only the last 1D bar** (your 14 names).

Trading Labs Strategy Tester was evaluating **whatever last bar was sitting in Postgres**, often **one or more sessions behind**, and sometimes a **mix of dates** across the 755 names. A 52-week breakout list rotates every session. Different bar → different stocks.

| | TradingView Pine Screener | Trading Labs (the run you pasted) | Trading Labs (after this fix) |
|---|---|---|---|
| Result | **14 BUY** | **11 BUY**, different names | Same three legs, **same last 1D bar** |
| Breakout | `close >= ta.highest(high, 252)[1]` | `CLOSE >= HIGH 252` (correct) | same |
| Volume | `volume > sma(volume, 20)` | `VOLUME > AVG_VOLUME 20` (correct) | same |
| Market gate | Nifty 500 close > SMA 50 | same | same |
| Which bar? | Last 1D candle on the screener | Last stored FYERS bar (often S−1, mixed) | Last completed NSE session + live overlay |
| Example close | LAURUSLABS **₹1,938.50** | LAURUSLABS **₹1,915.00** | Must match TV Close on **Scan Date** |

Overlap on your paste: **only LAURUSLABS, DIVISLAB, ENTERO**. That is not a different strategy. Those three were still 52-week highs on **both** sessions. The other names flipped when the candle changed.

---

## 1. The Pine you actually ran (two scripts, one scan idea)

You used **two Pine scripts** that share the same three **scan** legs. They are not the same product surface.

### 1.1 Trading Labs — `strategy(...)` (entries + trailing stop)

```pine
//@version=6
strategy("52-Week High Breakout - Trading Labs", overlay=true, pyramiding=0,
     process_orders_on_close=true, initial_capital=100000)
```

This script **buys and sells**. On TradingView it would drive **Strategy Tester** (trade list, ATR trail). In Labs it is imported so the **Builder filters** can scan the universe.

### 1.2 TradingView — `indicator(...)` (Pine Screener)

```pine
//@version=6
indicator("52-Week High Breakout [SCAN]", overlay=false)
```

This script **does not place orders**. The screener plots `scanSignal ? 1 : 0` and you keep rows where that column is `1`.

### 1.3 The only three legs that print a name

```
scanSignal / longCondition  ⇔
    marketOk
    AND close >= high252Prior
    AND volume > volumeSma20
    AND close is finite and > 0
```

| Pin | Pine | Plain English |
|---|---|---|
| **H** | `high252Prior = ta.highest(high, breakoutLength)[1]` with `breakoutLength = 252` | Highest **high** of the previous **252 sessions**. **Today is excluded.** Equal close **passes**. |
| **V** | `volumeSma20 = ta.sma(volume, volumeLength)` with `volumeLength = 20`; `volume > volumeSma20` | Today’s volume **strictly greater** than the 20-session SMA. **Today is included.** Equal volume **fails**. |
| **M** | `benchmarkClose > benchmarkSma50` on `NSE:CNX500` (Nifty 500), SMA length **50** | Index close **strictly above** its 50-session SMA. |

Everything else in the `strategy()` script is **not** part of the screener:

| Pine | Role | TradingView screener? | Labs Builder? |
|---|---|---|---|
| `strategy.position_size == 0` | Already in a trade? | No | Ignored (`POSITION_STATE`) |
| `not soldThisBar` | No same-bar rebuy | No | Ignored (`ORDER_CONTROL`) |
| `bar_index > entryBarIndex` | No trail update on entry bar | No | Ignored (`ENTRY_BAR_PROTECTION`) |
| `close < trailingStop` | 3× SMA-ATR trail exit | No | Exit / risk, not a scan filter |
| `not na(...)` | Warmup | Implicit | Ignored (`VALIDITY_GUARD`) |
| ATR / True Range / HWM | Risk | Plotted only | Risk rule, not a BUY leaf |

Your Debug output already showed this split is correct:

```
CLOSE >= HIGH 252                         ENTRY_FILTER
VOLUME > AVG_VOLUME 20                    ENTRY_FILTER
benchmarkClose > benchmarkSma50           BENCHMARK_FILTER
strategy.position_size / soldThisBar / ATR trail   ignored
```

So you were **not** missing a filter, and you were **not** scanning `HIGH null` / `AVG_VOLUME 50` anymore. The remaining bug was **which candle** those three filters ran on.

---

## 2. Your two result sets (the smoking gun is the Close)

### 2.1 TradingView Pine Screener — 14 names (`52W Breakout Signal = 1`)

| # | Symbol | Close | Prior 252 High |
|---|---|---:|---:|
| 1 | AETHER | 1,696.80 | 1,696.10 |
| 2 | ATHERENERG | 1,616.30 | 1,580.00 |
| 3 | COFORGE | 2,014.60 | 1,989.70 |
| 4 | CRAFTSMAN | 11,118.00 | 10,960.00 |
| 5 | DIVISLAB | 9,239.00 | 9,150.00 |
| 6 | ENTERO | 1,808.60 | 1,786.40 |
| 7 | GLENMARK | 2,515.00 | 2,484.00 |
| 8 | KRN | 1,609.70 | 1,598.20 |
| 9 | LAURUSLABS | 1,938.50 | 1,930.00 |
| 10 | NAZARA | 374.60 | 365.00 |
| 11 | OFSS | 12,190.00 | 12,060.00 |
| 12 | PTCIL | 22,110.00 | 21,800.00 |
| 13 | SHYAMMETL | 1,099.80 | 1,090.00 |
| 14 | STLTECH | 723.75 | 695.85 |

Nifty 500 printed two nearby values (23,528.55 vs 23,482.00) because `request.security` aligns to each stock’s last session. That is normal.

### 2.2 Trading Labs Strategy Tester — 11 BUY

| Rank | Symbol | Labs Close | Labs Prior 252 High | Hold Return (window) |
|---|---|---:|---:|---:|
| 17 | LAURUSLABS | 1,915.00 | 1,870.80 | +342.21% |
| 50 | SOLARINDS | 20,445.00 | — | +201.64% |
| 59 | HFCL | 246.99 | — | +192.12% |
| 81 | YATHARTH | 949.95 | — | +154.00% |
| 98 | DIVISLAB | 9,056.00 | — | +131.26% |
| 161 | SAILIFE | 1,491.40 | — | +95.04% |
| 247 | ENTERO | 1,761.00 | — | +53.19% |
| 261 | DCBBANK | 218.99 | — | +50.72% |
| 280 | JINDALSAW | 308.10 | — | +45.96% |
| 353 | ANTHEM | 929.25 | — | +27.23% |
| 656 | QUESS | 359.25 | — | **−30.69%** |

WATCH (2 of 3 filters): GVT&D failed `CLOSE >= HIGH 252`; SHILPAMED failed `VOLUME > AVG_VOLUME 20`. That WATCH logic is correct and is **not** how TradingView screener works (TV is binary 1/0, no WATCH).

### 2.3 Why these cannot be the same report

Same symbol, same formula, different Close:

| Symbol | TV Close | Labs Close | Gap |
|---|---:|---:|---|
| LAURUSLABS | 1,938.50 | 1,915.00 | ~1.2% — a **session**, not a tick |
| DIVISLAB | 9,239.00 | 9,056.00 | ~2% |
| ENTERO | 1,808.60 | 1,761.00 | ~2.7% |

Same-day FYERS vs TradingView for liquid NSE names is usually **paise to a rupee**, not ₹23–₹180. Labs was on an **older daily bar**.

QUESS as BUY with **−30.69% hold return** is the other tell. Hold Return is **buy-and-hold from Start Date (2024-01-01) to the scan bar**, not the 52-week trade. QUESS can still pass `close >= prior 252 high` on a bounce while being down from January 2024. TradingView never showed that column, so it looked like a “bad 52W signal”. It was a different number.

Names only on TV (AETHER, COFORGE, OFSS, …) broke the 252-high **on TV’s last bar**. On Labs’ older bar their close was still under that high (AETHER was 1,696.80 vs 1,696.10 — one session later they pass; one session earlier they fail).

Names only on Labs (HFCL, SOLARINDS, YATHARTH, …) were 52-week highs **on Labs’ older bar** and had already fallen off TV’s current bar.

Universe is **not** the cause. AETHER, ATHERENERG, COFORGE, CRAFTSMAN, GLENMARK, KRN, NAZARA, OFSS, PTCIL, SHYAMMETL, STLTECH are all in `ind_nifty500list.csv`.

---

## 3. TradingView — complete workflow (pin to pin)

TradingView is a **chart + Pine** product. The Pine Screener is: run this indicator on many symbols, keep rows where a plot is 1.

```text
Login TradingView
        │
        ▼
Open Pine Editor  →  paste indicator("52-Week High Breakout [SCAN]")
        │
        ▼
Add to chart (any symbol, timeframe 1D)
        │              Pine compiles. Inputs:
        │                Breakout Lookback     = 252
        │                Volume SMA Length     = 20
        │                ATR Length            = 14     (plotted only)
        │                ATR Multiplier        = 3.0    (unused in scan)
        │                Market SMA Length     = 50
        │                Benchmark             = NSE:CNX500
        │
        ▼
Open Pine Screener
        │  Watchlist / list:  755_Stocks_52W_Breakout
        │  Timeframe:         1D
        │  Column:            "52W Breakout Signal"  ==  1
        │
        ▼
For EACH symbol in the 755 list, on the LAST daily bar T
(the forming candle while the market is open; the official
close after 15:30 IST):
        │
        │  1. Load that symbol’s daily OHLC from TradingView’s NSE feed
        │  2. Load NSE:CNX500 on the same timeframe (request.security,
        │     gaps off, no lookahead)
        │  3. Compute pins on bar T only (no position, no orders):
        │
        │       high252Prior[T] = max(high[T-252] … high[T-1])
        │       volumeSma20[T]  = mean(volume[T-19] … volume[T])
        │       niftyClose[T]   = CNX500 close[T]
        │       niftySma50[T]   = mean(CNX500 close[T-49] … close[T])
        │
        │       H = close[T] >= high252Prior[T]     (equal is a PASS)
        │       V = volume[T]  >  volumeSma20[T]    (equal is a FAIL)
        │       M = niftyClose[T] > niftySma50[T]
        │
        │       scanSignal[T] = M AND H AND V AND close[T] > 0
        │
        │  4. Plot 1 or 0. Screener keeps the row if plot == 1
        │
        ▼
Result table (your 14 names)
```

### 3.1 What TradingView does **not** do in this screener pass

- It does **not** walk history and open a position.
- It does **not** apply the 3× ATR trailing stop.
- It does **not** skip a name because you already hold it.
- It does **not** size 10% of a 10-slot book.
- It does **not** use a Start Date / End Date. The signal is always the last 1D bar.
- It does **not** use FYERS or Labs Postgres. The feed is TradingView NSE.

If you instead add the **`strategy()`** script to **one chart** and open **Strategy Tester**, you get a **single-symbol trade list** (entries at `process_orders_on_close`, exits when `close < trailingStop`). That is a different report from the 14-name screener.

---

## 4. Trading Labs — complete workflow (pin to pin)

Trading Labs is a **universe scanner**. Pine is imported into **filters**, then those filters run on **FYERS daily bars in PostgreSQL** (plus an optional live session overlay).

```text
Login Trading Labs  →  FYERS token saved
        │
        ▼
Open Strategy Tester
        │  End Date defaults to IST today (Pine Screener’s “now”)
        │  A leftover End Date from sessionStorage is advanced to today
        │
        ▼
Strategy Builder  →  Pine Script tab
        │  Paste strategy("52-Week High Breakout - Trading Labs")
        │  (or the indicator() scan script — both are accepted)
        │
        ▼
Observe Filters
        │  Lexer → AST → semantic roles → Builder leaves
        │
        │  KEEP as scan filters:
        │    M  NIFTY 500 Close > NIFTY 500 SMA 50
        │    H  Close >= Previous 252-Session High
        │    V  Volume > Average Volume 20
        │
        │  DROP (shown in Debug, not sent to the scan):
        │    strategy.position_size, soldThisBar, bar_index,
        │    not na(...), close > 0, ATR / trailing stop, HWM
        │
        ▼
Save & Apply  →  POST /api/v1/strategy-tester/runs
        │  Payload leaves:
        │    BENCHMARK_CLOSE  >  { indicator: SMA, period: 50 }
        │    CLOSE           >=  { indicator: HIGH, period: 252 }
        │    VOLUME           >  { indicator: AVG_VOLUME, period: 20 }
        │  logic: ALL (every leaf must pass)
        │  universe: ALL_755
        │  timeframe: 1D
        │  end_date: IST today  (backend also advances a stale end_date)
        │
        ▼
Backend run (async)
        │  1. Load 755 NIFTY 500 names (stocks_master, CSV fallback if truncated)
        │  2. Ensure FYERS EOD is fresh in daily_ohlcv (45s budget)
        │  3. Load OHLCV per symbol + NIFTY 500 index series
        │  4. Fill MISSING completed 1D bars PER SYMBOL up to last NSE session
        │     (a name that already has Friday must not skip names still on Thursday)
        │  5. Overlay today’s live FYERS 1D quote if the cash session exists
        │  6. For EACH symbol, evaluate ONLY the last bar T ≤ end_date:
        │
        │       H = close[T] >= prior_252_high[T]
        │           prior_252_high = max(high[T-252] … high[T-1])
        │       V = volume[T] > sma(volume, 20)[T]
        │       M = nifty_close[T] > sma(nifty_close, 50)[T]
        │           (index bar aligned on/before the stock’s date)
        │
        │       BUY    if M AND H AND V
        │       WATCH  if some leaves pass (Labs-only; TV has no WATCH)
        │       REJECT otherwise
        │
        ▼
Results table
        Scan Date · Close · Prior 252 High · Volume · Avg Volume
        Hold Return % = window start → scan bar (NOT the 52W trade)
```

### 4.1 Evaluation math (matches Pine)

| Labs series | Formula | Pine equivalent |
|---|---|---|
| `HIGH` period 252 | `max(high[t-252] … high[t-1])` | `ta.highest(high, 252)[1]` |
| `AVG_VOLUME` period 20 | SMA of volume including today | `ta.sma(volume, 20)` |
| `BENCHMARK_CLOSE` vs `SMA 50` | Index close vs SMA 50, aligned on/before the stock date | `request.security("NSE:CNX500", …)` |
| Last bar | `index_on_or_before(end_date)` after fill + live overlay | Pine Screener last 1D candle |

`close == prior high` **passes**. `volume == average` **fails**. Intraday high above the 252 level with close below it **fails**. Same as `specs/038-52w-high-breakout/contracts/w52-algorithm.md`.

### 4.2 What you must not compare

| Labs column | What it actually is | TradingView screener |
|---|---|---|
| Window Start / Entry ₹433 on LAURUSLABS | Close on **Start Date** (2024-01-01) | Not a screener column |
| Hold Return % +342% | Buy-and-hold from Start Date to scan bar | Not computed |
| BUY | Three filters true on Labs’ scan bar | `scanSignal = 1` on TV’s last 1D bar |
| WATCH | Partial filter match | Does not exist |

---

## 5. What was missing (the issues, in order)

### Issue A — parser (already fixed, you already passed this)

Your Pine stores lengths in **inputs**:

```pine
breakoutLength = input.int(252, "Breakout Lookback", minval=1)
volumeLength   = input.int(20,  "Volume SMA Length", minval=1)
high252Prior   = ta.highest(high, breakoutLength)[1]
volumeSma20    = ta.sma(volume, volumeLength)
```

The first Labs importer treated those as unknown numbers → `CLOSE >= HIGH null` (today’s high) and `VOLUME > AVG_VOLUME 50`. That produced **1 BUY (QPOWER)** vs TV’s 14, disjoint.

**What you change:** nothing now. Debug must show `HIGH 252` and `AVG_VOLUME 20`. Yours does.

### Issue B — stale / mixed last bar (this is why you still had 11 vs 14)

Three concrete bugs stacked:

1. **Saved End Date.** Strategy Tester remembered `endDate` in sessionStorage (often `2026-08-26` from an earlier run). Pine Screener has no such picker — it always uses today. Labs evaluated `last bar ≤ end_date`, so it scanned Wednesday while TV scanned Friday.

2. **Fill skipped the universe if ANY name was current.** `fill_missing_completed_bar_series` used `max(last_dates)` across 755 names. If RELIANCE already had Friday and KRN was still on Thursday, the fill returned “fresh” and **KRN stayed on Thursday**. Mixed scan dates → mixed BUY lists.

3. **Weekend / after-hours.** On a Saturday, live overlay is off (`should_overlay_session` is None). The scan depends entirely on the completed-bar fill. If that fill was skipped (bug 2) or FYERS history was empty, Labs scanned the last stored EOD.

That is why LAURUSLABS Close was ₹1,915 in Labs and ₹1,938.50 on TradingView.

**What you change to fix it (now in the code):**

| Where | Change |
|---|---|
| Frontend `StrategyTesterPage` | End Date advances to **IST today** on load and on Run (Pine Screener “now”) |
| Backend `parse_run_dates` | A stale `end_date` is advanced to IST today |
| Backend `fill_missing_completed_bar_series` | Fill is **per-symbol**. Stale names are fetched even if one liquid name is current |
| Results | **Scan Date**, **Close**, **Prior 252 High** are first-class columns. Run card shows the scan bar. A mixed-date run warns you. |

### Issue C — leftover residual (after A and B)

Even on the **same** Scan Date, a name can still differ if:

| Cause | Why |
|---|---|
| FYERS close ≠ TradingView close by enough to flip `close >= high252` | Vendor print / adjustment. AETHER was 0.70 above the high on TV — a 1 rupee gap flips it. |
| FYERS volume ≠ TradingView volume | `volume > sma(volume, 20)` is strict. One extra lot vs average flips V. |
| Live overlay vs official EOD | During market hours TV and Labs both use the forming candle; after close both should use EOD. If FYERS live volume is session-so-far and TV has official volume, V can differ. |
| Index alignment | Two Nifty 500 prints on TV (23,528 vs 23,482). Labs uses the NIFTY 500 store series. M is slow-moving; this rarely flips the list by itself. |

Those are data gaps, not a different breakout rule.

---

## 6. Pin-to-pin map (every line of the Pine)

### 6.1 Inputs

| Pin | Pine | TradingView | Trading Labs |
|---|---|---|---|
| Breakout lookback | `input.int(252, …)` | 252 | 252 |
| Volume SMA | `input.int(20, …)` | 20 | 20 |
| ATR length | `input.int(14, …)` | 14 (plot only in scan) | 14 (risk, not a BUY leaf) |
| ATR multiplier | `input.float(3.0, …)` | unused in screener | risk rule 3× |
| Market SMA | `input.int(50, …)` | 50 | 50 |
| Benchmark | `input.symbol("NSE:CNX500")` | TV ticker CNX500 | NIFTY 500 (`CNX500` mapped) |

### 6.2 Indicators and conditions

| Pin | Pine | TV screener | Labs scan |
|---|---|---|---|
| Prior 252 high | `ta.highest(high, 252)[1]` | yes | yes (HIGH 252, current bar excluded) |
| Volume SMA 20 | `ta.sma(volume, 20)` | yes | yes |
| True Range / custom ATR | SMA of TR, length 14 | plotted, **not** in `scanSignal` | risk / plot, **not** a BUY leaf |
| `request.security` benchmark | CNX500 close and SMA 50 | yes | NIFTY 500 close and SMA 50 |
| `marketOk` | index close > SMA 50 | required | required |
| `breakoutCondition` | `close >= high252Prior` | required | required |
| `volumeCondition` | `volume > volumeSma20` | required | required |
| `not na(close)` / `close > 0` | validity | implicit | ignored in Builder (engine still rejects bad prices) |
| `strategy.entry("Long")` | order | **not in indicator()** | not executed on scan; BUY = filters true on last bar |
| `strategy.close` / trail | exit | **not in screener** | not used to include/exclude scan rows |
| `plotshape` / `alertcondition` | display | triangle / alert | ignored |
| `scanSignal` (indicator) | screener column | **this is the 1/0** | same three leaves if you paste the scan script |

### 6.3 Last-bar vs history

| | TradingView Pine Screener | Trading Labs Strategy Tester scan |
|---|---|---|
| Which bar is tested? | Last daily bar on the chart / screener | Last bar on or before End Date, after fill + live overlay |
| History used for? | Warmup of 252 / 50 / 20 windows | Same warmup from Postgres + FYERS |
| Does a past 52W breakout create a BUY today? | **No.** Only today’s `scanSignal`. | **No.** Only today’s leaves. |
| Does being in a trade block a BUY? | **No** (no position in `indicator()`) | **No** (position guards are stripped) |

Both products, on this path, are **last-bar filter scans**, not the 10-slot 52W book (`09_52w_breakout`).

---

## 7. Side-by-side user loop

```text
TRADINGVIEW                              TRADING LABS
───────────                              ────────────
Login TV                                 Login Labs + FYERS token
Pine Editor → indicator() [SCAN]         Strategy Tester → Pine tab
                                         → strategy() or indicator()
Add to chart, 1D                         Observe Filters → Save & Apply
Pine Screener                            Backend run on 755 names
  list = 755_Stocks_52W_Breakout           FYERS EOD + per-symbol fill
  col  = 52W Breakout Signal == 1          + live overlay
For each name, last bar:                 For each name, last bar:
  M ∧ H ∧ V  →  row                      M ∧ H ∧ V  →  BUY
14 names                                 should match TV’s 14
                                         (vendor / timestamp permitting)
```

```text
Do NOT mix with these other “52W” paths
────────────────────────────────────────
TV Strategy Tester on strategy()   →  one symbol, entries + ATR trail
Labs 09_52w_breakout kernel        →  10-slot book, 10% equity, NSE costs
Labs “TradingView tester” tab      →  WELCORP always-in 1-share CSV tape
```

---

## 8. How to re-run in Labs so it matches TradingView

1. Confirm FYERS token is valid.
2. Strategy Tester → Strategy Builder → **Pine Script**.
3. Paste either script (strategy or scan indicator).
4. **Observe Filters**. Debug must show:
   - `CLOSE >= HIGH 252` (Previous 252-Session High)
   - `VOLUME > AVG_VOLUME 20`
   - `NIFTY 500 Close > NIFTY 500 SMA 50`
   - no `HIGH null`, no `AVG_VOLUME 50`
5. **End Date (scan bar)** = IST today. Do not leave an old date.
6. Save & Apply.
7. When the run finishes, read the run card **Scan bar** date. It must be the same session as the TradingView 1D screener.
8. Compare **only** these columns to TradingView:

| Labs | TradingView |
|---|---|
| Scan Date | the 1D bar the screener is on |
| Close | Close |
| Prior 252 High | Prior 252 High |
| Volume / Avg Volume | Volume SMA 20 (Labs volume vs that SMA) |
| BUY | `52W Breakout Signal = 1` |

If Close and Prior 252 High match TV on that Scan Date, BUY names match except for vendor prints sitting right on the 252-high (AETHER was 1,696.80 vs 1,696.10).

Ignore **Hold Return %**, **Window Start**, and **WATCH**. TradingView’s screener does not compute those.

If the run card says symbols were evaluated on **different session dates**, data fill did not finish — re-run after FYERS history is available. Do not compare that list to TradingView.

---

## 9. Files changed for this match

| Path | Role |
|---|---|
| `frontend/src/utils/pineParser.ts` | Pine → Builder filters (`input.int` 252 / 20) |
| `frontend/src/utils/strategyFilterPayload.ts` | Builder → API leaves |
| `frontend/src/pages/StrategyTesterPage.tsx` | End Date = IST today (Pine Screener “now”) |
| `frontend/src/components/strategy_tester/RunStatusRow.tsx` | Shows Scan bar / mixed-date warning |
| `backend/app/services/strategy_tester/scan_service.py` | Per-symbol completed-bar fill; IST end-date advance |
| `backend/app/services/strategy_tester/engine.py` | Last-bar evaluate; snapshot Close / 252-high / Scan Date |
| `backend/app/services/strategy_tester/indicators.py` | `HIGH` 252 = prior window; `AVG_VOLUME` = SMA |
| `backend/app/services/strategy_tester/filter_engine.py` | AND / comparisons |
| `specs/038-52w-high-breakout/contracts/w52-algorithm.md` | Canonical BuySignal math |
| `docs/TRADINGVIEW_VS_TRADING_LABS.md` | WELCORP tester tape vs 52W kernel (not this scan) |

---

## 10. Memory aid

| If you ask… | You are in… |
|---|---|
| “Which names print `scanSignal = 1` on the last daily bar?” | **TradingView Pine Screener** and **Labs Strategy Tester Pine scan** (same three legs, same bar) |
| “What trades would the ATR trail take on one chart?” | **TradingView Strategy Tester** on the `strategy()` script |
| “What did the 10-slot 52W book do on FYERS history?” | **Labs kernel** `09_52w_breakout` |
| “Why did Labs show 1 name and TV 14?” | Labs was scanning **close at today’s high** and **volume vs 50-SMA** (parser). Fixed. |
| “Why did Labs then show 11 different names vs TV 14?” | Same three legs, **different last bar** (stale / mixed EOD). Fixed by scanning IST today and filling every name up to that session. |
