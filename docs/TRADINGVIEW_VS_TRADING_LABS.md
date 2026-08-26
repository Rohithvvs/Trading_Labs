# TradingView vs Trading Labs — Complete Lifecycle and Comparison

This document explains, in plain language:

1. How **TradingView** works from open-chart to Strategy Tester.
2. How **Trading Labs** works from login to scan, backtest, and paper trade.
3. A **side-by-side comparison**.
4. Why WELCORP showed **17 trades in Labs** and **1600 / 2954 in TradingView**, and how a match is possible.

It describes the systems **as they work in this repository today**.

---

## 1. One-sentence difference

| | TradingView | Trading Labs |
|---|---|---|
| What it is | A **chart + Pine script** product. You pick **one symbol**, write or load a script, and the **Strategy Tester** simulates fills on that chart. | A **research workstation**. It loads **Nifty 500** from FYERS into **PostgreSQL**, **scans** with strategy rules, then you inspect **one name**, **backtest**, and optionally **paper-trade**. |
| Default 52W backtest | Script named **52W Breakout - Test**: always in, **1 share**, next-open fill. | **52W kernel**: 252-high + volume + Nifty filter + 3× ATR trail, **10% of equity**, max **10 names**. |
| WELCORP ~18Y | **2954** trades (full) / **1600** from 2013-09-11 | Kernel **17** trades. TradingView tester tab **2954 / 1600**. |

Same screen name (“52W”) does **not** mean the same engine.

---

## 2. TradingView — complete lifecycle

TradingView is built around **one chart**. Almost everything (Pine, tester, reports) is “what would this script do on **this** symbol’s candles?”

### 2.1 What you open

1. You log into TradingView.
2. You open a symbol, e.g. `NSE:WELCORP`.
3. You set timeframe, e.g. **1D** (one candle = one session).
4. TradingView’s **datafeed** draws Open, High, Low, Close, Volume from **its** NSE history (not FYERS, not Labs Postgres).

WELCORP on TV in this project: bars from **2000-11-28** to **2026-08-24** (`ohlc.csv`).

### 2.2 Two kinds of Pine scripts

| Kind | Declaration | What it does |
|---|---|---|
| **Indicator / screener** | `indicator(...)` | Plots columns (signal 1/0, prior high, ATR). **No orders. No Strategy Tester trade list.** |
| **Strategy** | `strategy(...)` | Calls `strategy.entry` / `strategy.close`. The **broker emulator** turns those into fills and a trade list. |

In this repo:

- `strategy.pine` is an **`indicator()`** named `STR-001 | 52W High Breakout Scanner`. It cannot emit the 1600-trade list.
- The 1600 / 2954 list came from a **strategy** named **52W Breakout - Test**, signal id **TEST**.

### 2.3 Strategy Tester lifecycle (how a TV backtest actually runs)

```text
You add a strategy() script to the chart
        │
        ▼
TradingView loads chart candles (OHLC)
        │
        ▼
For each bar, in order:
        1. Update indicators on this bar
        2. Run your Pine (often on bar close)
        3. If Pine says buy/sell → create an ORDER
        4. Broker emulator FILLS the order (not always at the signal price)
        5. Update position, cash, equity, drawdown
        │
        ▼
Strategy Tester report
  Overview · Performance · Trades analysis · List of trades · Properties
```

That is **one symbol, one script, one date range**. There is no Nifty 500 book and no 10-slot portfolio inside the tester.

### 2.4 Broker emulator (the “how fills happen” layer)

From `test_config.yaml` for **52W Breakout - Test** on WELCORP:

| Setting | Value | Plain meaning |
|---|---|---|
| Mode | Deep backtesting | Uses the full requested history, not only bars on screen |
| Range | 2000-06-23 → 2026-08-24 | Tester window |
| Capital | ₹10,00,000 | Starting cash |
| Order size | **1 quantity** | Always 1 share |
| Pyramiding | 1 | At most one add; this tape stays flat or 1 long |
| Script execution | **on_bar_close** | Decision uses the **closed** daily bar |
| Order delay | **one_tick** | Fill is **not** the signal close; it is the **next session open** |
| Commission | 0% | No fees |
| Slippage | 0 ticks | No extra slippage |
| Tick size | 0.10 | Prices printed to 10 paise |

**Always-in TEST tape (what produced 1600 / 2954):**

1. On bar close, strategy is long (signal `TEST`).
2. Fill buy at **next bar’s open**.
3. Next session, close that long at **that open**, then arm the next entry.
4. Same-bar re-entry is blocked, so you get roughly **one round-trip every other session**.
5. Almost every trade lasts **1 bar**. Trade 1 is an **8-bar** hold (2002-08-22 → 2002-09-03) because of TV’s session calendar.

So TV is **not** “buy a 52-week high and trail 3× ATR”. It is “stay long 1 share, flatten next open, repeat.”

### 2.5 What you see in TradingView reports

| Tab | What it is |
|---|---|
| Overview | Net profit, drawdown, percent profitable, profit factor |
| Performance analysis | Gross profit/loss, CAGR, Sharpe, vs buy-and-hold, margin, run-up/drawdown |
| Trades analysis | Winners / losers / breakeven donut, return histogram, streaks |
| List of trades | Every entry and exit (export = `trades.csv`) |
| Properties | Symbol, range, capital, commission, tick size |

WELCORP full tester (golden files):

- **2954** longs, qty **1**, commission **0**
- Net ≈ **₹1,278** on ₹10L (~0.13%)
- First fill **2002-08-22 @ 16.3**, last **2026-08-21 → 2026-08-24**
- From **2013-09-11**: **1600** trades, **788 / 778 / 34** (win / loss / BE)

### 2.6 TradingView daily loop (as a user)

```text
Open TV → pick NSE:WELCORP → 1D
    → add Pine strategy
    → set Properties (capital, 1 share, dates, commission)
    → Strategy Tester runs on TV candles
    → read Overview / Trades / List
    → optionally export trades.csv and chart OHLC
```

New days appear when **TradingView’s datafeed** adds a new daily bar. There is no Labs Postgres in this loop.

### 2.7 TradingView does **not** do (in this comparison)

- Scan 755 names into one 10-slot book
- Size 10% of equity with NSE delivery costs
- Paper-trade from a scanner table into a simulated broker
- Store 18 years in **your** PostgreSQL

It is a **chart tester**, not a portfolio scanner.

---

## 3. Trading Labs — complete lifecycle

Trading Labs is a **workstation**: many stocks, several strategies, Postgres history, paper trading. Advisory only — **no live broker orders**.

### 3.1 The factory line

```text
You (browser)
    → Login (cookies)
    → FYERS token (NSE key)
    → Prices saved in PostgreSQL (~18 years from ~2008-07-22)
    → Run a scanner (swing / 52W / LTM)
    → Candidate table
    → Open one stock (overview, technicals, plan, news, chart, backtest)
    → Optional paper trade on live ticks
```

Three loops:

1. **You click** — scan, detail, backtest, paper order.
2. **Scheduler** — IST jobs (engine hours, heartbeats, cleanup).
3. **Market engine** — live FYERS ticks so paper orders can fill.

### 3.2 Stage 1 — Enter the app

1. Sign in (email/password or Google). HttpOnly cookies.
2. Save a **FYERS access token** so Labs can fetch NSE data.
3. Home: market overview, saved scans, history, alerts, admin.

Without FYERS, scanners cannot refresh real candles into Postgres.

### 3.3 Stage 2 — Data (the fuel)

| Store | Source | Used for |
|---|---|---|
| `daily_ohlcv` (Postgres) | FYERS EOD | 52W **kernel**, LTM, swing scanner, charts |
| Intraday candles | FYERS | finer fills, paper gap-replay |
| Live websocket | FYERS LTP | paper fills |
| `ohlc.csv` | TradingView export | WELCORP **TradingView tester** only |

New session: **FYERS → Postgres**.  
`ohlc.csv` does **not** auto-update. WELCORP TV tester keeps the last export until you replace the file.

WELCORP in Postgres starts about **2008-07-22**. TradingView’s first fill is **2002-08-22**. That gap alone blocks a TV match on Postgres.

### 3.4 Stage 3 — Scanners (find names)

**A. Nifty 500 swing scanner**

1. Load candles; backfill FYERS if gaps.
2. Drop bad history / dead volume.
3. Keep uptrends (`close > SMA50 > SMA200`).
4. Score EMA, Supertrend, MACD, RSI, structure, volume.
5. Shortlist (score ≥ 52).
6. Full analysis on the shortlist (technicals, news, generic backtest, LLM text).
7. **BUY / WATCH / REJECT**.
8. Save snapshot.

**B. 52-Week High Breakout (`09_52w_breakout`) — the published kernel**

One **10-slot book** across the universe, not 755 independent TV testers.

Buy only if:

- close ≥ prior **252-session** high (today excluded)
- volume > 20-day average
- Nifty 500 > SMA50
- not held, not sold today

Hold until close &lt; high-water mark − **3 × SMA ATR**.  
Fill = **signal close**. Size = **10% of ₹1,00,000 book**, NSE costs. No pyramid, no same-day rebuy.

On WELCORP that produces **17** swing trades in ~18 years (first **2014-03-11**). Those are **17 trades of one stock**, not 17 stocks.

**C. Long-Term Momentum** — separate tab, separate rules.

### 3.5 Stage 4 — Open one stock

Tabs: Overview, Technicals, Trade plan, News, Chart, **Backtest**.

Backtest **re-runs that symbol** for 1Y / 3Y / 5Y / 8Y / All / custom dates. It does not paste the 755-name book equity onto every name.

### 3.6 Stage 5 — Backtest tab (two engines)

```text
GET /scanner/w52/symbols/WELCORP-EQ
        ?window=...&start_date=...&end_date=...
        &execution_profile=TV_TESTER | KERNEL
```

| Toggle | Data | Rules | WELCORP result |
|---|---|---|---|
| **TradingView tester** (WELCORP default) | `ohlc.csv` + `trades.csv` sessions | Always-in, 1 share, next open, ₹10L, 0 commission | **2954** full / **1600** from 2013-09-11 |
| **52W kernel** | Postgres FYERS | 252-high + ATR trail, 10% book | **17** trades, 8 win / 9 loss |

### 3.7 Stage 6 — Recommendation

Technicals + news + overlays → LLM wording → **BUY / WATCH / REJECT** + plan. Advisory only.

### 3.8 Stage 7 — Paper trading

Fake cash. Place order → pending / filled / cancelled. Position opens, then close realizes P&L. Market engine uses live ticks. **No real FYERS order.**

### 3.9 Labs daily loop (without clicking)

Singleton backend (IST): token refresh, optional daily scan, start/stop live engine around market hours, paper heartbeats, log cleanup.

---

## 4. Side-by-side comparison

### 4.1 Purpose

| Topic | TradingView | Trading Labs |
|---|---|---|
| Job | Chart, Pine, **one-symbol** tester | Scan universe, research, **paper** desk |
| Live brokerage | You trade in TV/broker yourself | **Does not** place live orders |
| Universe | Whatever is on the chart | Nifty 500 (and other lists) in **one book** for 52W |

### 4.2 Data

| Topic | TradingView | Trading Labs |
|---|---|---|
| Vendor | TradingView NSE datafeed | FYERS → PostgreSQL |
| WELCORP start | 2000-11-28 (CSV) | ~2008-07-22 |
| New bar | TV datafeed updates the chart | FYERS ingest updates Postgres |
| Frozen TV copy | You export OHLC / trades | `Strategy_001/ohlc.csv` used only for WELCORP TV tester |

### 4.3 “52W” strategy

| Topic | TradingView “52W Breakout - Test” | Labs **52W kernel** |
|---|---|---|
| Script | `strategy()` TEST tape | Spec 038 BuySignal + ATR |
| Entry | Always in / every other session | Close ≥ 252-high + volume + market |
| Exit | Next session open | Close &lt; HWM − 3× ATR |
| Hold | ~1 bar (Trade 1 = 8 bars) | Weeks to months |
| Size | **1 share** | **10% of equity**, max 10 names |
| Capital | ₹10,00,000 | ₹1,00,000 (kernel) |
| Costs | 0% | NSE delivery |
| Fill | Signal close → **next open** | **Same-bar close** |
| WELCORP 18Y | 2954 / 1600 | **17** |

### 4.4 Backtest UI

| Topic | TradingView | Trading Labs |
|---|---|---|
| Where | Strategy Tester on the chart | Stock detail → Backtest |
| Scope | One symbol, one script, one range | Per-symbol window; scan is a separate 10-slot replay |
| Date tools | Chart / deep-backtest range | 1Y, 3Y, 5Y, 8Y, All, From/To |
| Match path | Native tester | Toggle **TradingView tester** (WELCORP CSV) |

### 4.5 Lifecycle compared

```text
TRADINGVIEW                         TRADING LABS
───────────                         ────────────
Login to TV                         Login to Labs + FYERS token
Open NSE:WELCORP 1D                 Load Nifty 500 into Postgres
Add Pine strategy                   Run scanner (kernel book)
Set Properties (1 share, ₹10L)      Open WELCORP in the table
Tester walks TV bars                Backtest tab:
  order on close                      • TV tester → ohlc.csv → 2954/1600
  fill next open                      • Kernel    → Postgres → 17
Report + export CSV                 Paper trade (optional, fake money)
```

### 4.6 Can they match?

| Goal | Possible? | How |
|---|---|---|
| WELCORP tester blotter (2954 / 1600) | **Yes — already wired** | Backtest → **TradingView tester** + `ohlc.csv` |
| Same for other stocks | **Yes, per stock** | That name’s TV OHLC (and `trades.csv` for exact sessions), then per-symbol CSV loader |
| Kernel 17 = TV 1600 | **No** | Different rules |
| Postgres 18Y = TV chart | **No** | Different vendor, Labs starts ~2008 |
| 755-stock scan = 755 TV charts | **No** | TV = 1 name 1 share; Labs scan = 10-slot book |
| Auto-update TV results from FYERS | **No** | Must re-export and replace `ohlc.csv` |

Known leftover on a good match: ~₹0.10 on some `*.*5` opens (WELCORP slice **786 / 778 / 36** vs TV **788 / 778 / 34**). Count and dates still match.

---

## 5. WELCORP numbers (same stock, two lifecycles)

| | TradingView tester | Labs kernel | Labs TV tester tab |
|---|---|---|---|
| Trades | 2954 full / 1600 from 2013-09-11 | **17** | **2954 / 1600** |
| Win / loss / BE (2013-09-11) | 788 / 778 / 34 | 8 / 9 | 786 / 778 / 36 |
| First entry | 2002-08-22 | 2014-03-11 | 2002-08-22 |
| Data | TV OHLC | FYERS Postgres | `ohlc.csv` |
| Why that count | Always-in 1-share tape | Real 52-week swings | Copy of TV tape |

---

## 6. How to use this without mixing the two

1. Open WELCORP → Backtest.
2. **TradingView tester** — same family as TV Strategy Tester (needs current `ohlc.csv`).
3. **52W kernel** — published 52-week book on Postgres (the **17** trades).
4. To refresh TV numbers: export new OHLC (and trades) from TradingView and **overwrite**  
   `hermes-research/tradingview_reference/Strategy_001/ohlc.csv`.  
   Postgres will not do that for you.

---

## 7. Files that define each side

**TradingView golden reference**

- `hermes-research/tradingview_reference/Strategy_001/strategy.pine` — screener **indicator**, not the tester
- `hermes-research/tradingview_reference/Strategy_001/test_config.yaml` — tester properties
- `hermes-research/tradingview_reference/Strategy_001/ohlc.csv` — TV daily bars
- `hermes-research/tradingview_reference/Strategy_001/trades.csv` — tester list
- `hermes-research/tradingview_reference/Strategy_001/strategy_report.xlsx` — TV report

**Trading Labs 52W**

- `backend/app/services/strategies/breakout52w/` — kernel, book, TV tester tape
- `specs/038-52w-high-breakout/contracts/w52-algorithm.md` — kernel rules
- `frontend/src/components/StockDetailPanel.tsx` — Backtest toggle and dates

---

## 8. Short memory aid

| If you ask… | You are in… |
|---|---|
| “How did 1 share always-in do on this TV chart?” | **TradingView** (or Labs **TradingView tester**) |
| “How did the 52-week high + ATR book do on FYERS history?” | **Labs kernel** |
| “Which names look buyable today across Nifty 500?” | **Labs scanner** |
| “Can I practise the fill with fake money?” | **Labs paper trading** |

TradingView = **one chart, one script, broker emulator**.  
Trading Labs = **universe scan + Postgres history + optional TV-copy tester + paper desk**.
