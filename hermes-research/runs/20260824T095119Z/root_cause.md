# Root cause

**Primary class:** `strategy interpretation`  
**Contributing:** `market/candle data`, `position sizing`, `commission`, `order execution` (fill delay already largely correct on TV_COMPAT)

Evidence class labels: DOCUMENTED / OBSERVED / INFERRED / UNKNOWN.

---

## 1. What TradingView actually ran

**DOCUMENTED** (`test_config.yaml`, XLSX Properties):

- Name: `52W Breakout - Test`
- Symbol `NSE:WELCORP`, 1D, deep backtesting 2000-06-23 → 2026-08-24
- Capital ₹1,000,000; order size **1 quantity**; pyramiding 1
- Commission 0%; slippage 0 ticks
- Script execution: **On bar close**; order execution delay: **One tick**
- Tick size 0.10

**OBSERVED** (`trades.csv`, 2954 round-trips):

- Every entry signal is `TEST`; every exit is `Close entry(s) order TEST`
- Direction long only; qty always 1; commission always 0
- Duration: **2953 trades = 1 bar**, one trade (Trade 1) = 8 bars
- Net profit 1278.2 matches XLSX Performance
- Winners 1352 / losers 1449 / even 153 = XLSX Trades analysis

**OBSERVED** (Labs `WELCORP-EQ` OHLC vs TV prices on overlapping dates):

TV fills are the **session open**, not the close.

| TV trade | Entry date / price | Labs open | Exit date / price | Labs open |
|----------|--------------------|-----------|-------------------|-----------|
| 722 (first overlap) | 2008-07-23 / 320.0 | 320.0 | 2008-07-24 / 337.0 | 337.0 |
| 2950 | 2026-08-11 / 1848.1 | 1848.1 | 2026-08-12 / 1844.4 | 1844.4 |
| 2954 | 2026-08-21 / 2175.0 | 2175.0 | 2026-08-24 / 2290.0 | 2290.0 |

Fill-vs-OHLC on 2231 overlap entries: **1321 exact `open`**, plus 120 `open+low`, 124 `open+high`; only **5 exact `close`**; 637 unmatched (likely pre-adjustment / gap days — not close-fills).

**INFERRED:** The tester script is an always-in long that `strategy.entry("TEST")` / `strategy.close("TEST")` each bar. With on-bar-close + one-tick delay, both legs fill at the **next session open**. Same-bar re-entry is blocked (next entry is the session *after* the previous exit). That is a **broker-emulator tape**, not a 252-week breakout with a 3×ATR trail.

---

## 2. What `strategy.pine` is

**OBSERVED** (`strategy.pine` lines 1–62):

```pine
indicator("STR-001 | 52W High Breakout Scanner", overlay=false)
float prior252High = ta.highest(high, LOOKBACK_52W)[1]
bool volumeOK = volume > volumeSMA20
bool marketOK = nifty500Close > nifty500SMA50
bool breakout = close >= prior252High
bool breakoutSignal = breakout and volumeOK and marketOK
```

- Declares `indicator()`, not `strategy()`
- No `strategy.entry` / `strategy.close` / `strategy.exit`
- ATR is computed and plotted but **not used in the signal**
- Outputs screener plots, not broker-emulator trades

This file **cannot** have produced `trades.csv`.

---

## 3. What Trading Labs ran

**OBSERVED** (`breakout52w`):

| Piece | Path | Behavior |
|-------|------|----------|
| Signal | `signal.py` `buy_signal` / `screener_pass` | close ≥ prior 252-high **and** vol > SMA20 **and** NIFTY500 > SMA50; blocked if held / sold today |
| Trail | `trail.py` | HWM close − 3× SMA ATR(14); no exit on entry bar |
| Fill KERNEL | `execution.py` `KERNEL_EXECUTION` | same-bar close |
| Fill TV_COMPAT | `TV_COMPAT_EXECUTION` | next-bar **open**, intrabar stop touch |
| Size | `portfolio.py` + `book_engine._open_holding` | 10% of marked equity (`ALLOC_PCT=0.10`), max 10 names |
| Costs | `costs.py` | NSE delivery (brokerage, STT, stamp, GST, DP) unless `apply_costs=False` |
| Capital default | `identity.py` | ₹100,000 (harness overrode to ₹1,000,000 to match YAML) |

Replay on WELCORP-EQ, 2008-07-22 → 2026-08-24, capital ₹1,000,000:

- KERNEL: **17** trades, first 2014-03-11 close-fill 71.85, NSE costs, ATR trail
- TV_COMPAT: **18** trades, first 2014-03-12 **open** 72.4 (= Labs O=72.4), ATR trail, ~1381 shares

---

## 4. Why Trade 1 diverges

1. **Strategy interpretation (primary).** TV Trade 1 is TEST always-in at 16.3 (2002). Labs Trade 1 is the first 52W *book* fill in 2014 after 252-session warmup + BuySignal. Different entry rule, different exit rule, different hold time.
2. **market/candle data.** Labs `daily_ohlcv` WELCORP-EQ starts **2008-07-22**. TV trading range starts **2002-08-22**. 723 TV entries have no Labs bar.
3. **position sizing.** TV qty=1. Labs ~10% of ₹10L → 1381 shares at 72.4.
4. **commission.** TV 0. Labs NSE delivery ~₹208 on that first round-trip.

**Order execution / fill price** is *not* the first-divergence cause for the overlapping recent tape: TV_COMPAT next-bar open already matches TV opens on 2026-08 bars.

---

## 5. What this is not

- Not a rounding bug (16.3 vs 72.4; 1 vs 1381 shares).
- Not timezone/session on daily NSE (dates align for 2026-08 fills).
- Not slippage (both 0).
- Not “close enough” aggregates: TV net **₹1,278.2** vs Labs TV_COMPAT net **₹156,622.81** on the same ₹1,000,000 nominal capital.

---

## 6. Taxonomy pick

| Rank | Class | Role |
|------|--------|------|
| 1 | **strategy interpretation** | TV TEST always-in 1-bar vs Labs 038 52W BuySignal+ATR trail |
| 2 | market/candle data | No Labs bars 2002–2008-07-21 |
| 3 | position sizing | qty 1 vs 10% equity |
| 4 | commission | 0 vs NSE delivery waterfall |
| 5 | order execution | TV one-tick → next open; TV_COMPAT already models this |

Changing `signal.py` / `trail.py` to emit 2954 1-bar TEST trades would **change 52W strategy intent**. That is forbidden by the operating rule. The engine surface that *is* a real TV-property gap (qty, costs, tester profile) is in the fix proposal.
