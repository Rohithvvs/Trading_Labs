# Indicator Scanner and Backtesting — Complete User Guide

This guide explains the **Indicator Scanner** and **Backtest** screens in Trading Labs, in plain language.

It is written around the screen you actually used:

- Indicator: **Momentum Pulse Finder**
- Universe: **750 stocks**
- Timeframe: **1 Day**
- Scan bar: **11 Sep 2026**
- Run ID: **IND-20260912-001**
- Result: **23 MATCHED**, **717 REJECTED**, **10 SKIPPED**

Read this once from top to bottom. After that you can jump to any section.

> For research and paper-trading only. Not investment advice. A MATCH is not a buy order. A high Return % on the scan is not a guaranteed profit.

---

## 1. The one idea you must not mix up

The app has **two different jobs** that sit next to each other.

| Job | What it answers | Does it buy or sell? | Your example |
|---|---|---|---|
| **Indicator Scanner** | *Which stocks match my rules **today** (last 1D bar)?* | **No.** Exit rule is **Scan only — no trade is opened**. Capital is **₹0**. | 23 names matched Close > EMA 20 **and** RSI 14 crossed above 50 on **11 Sep 2026**. |
| **Backtest (LEAN)** | *If I had **traded** this rule in the past, with real money, fees, and exits, what would have happened?* | **Yes, in simulation.** It opens and closes paper trades on history. | The TVSSCS Chart / Backtest tab with ₹1,00,000, 7 trades, Max drawdown, Profit factor. |

If you remember only one sentence:

**Scanning finds names. Backtesting tests whether those names would have made money if you had actually traded them.**

That is why the scan shows **Entry Price —** (blank) and **Capital ₹0**. The scanner is a **screener**, not a broker.

---

## 2. Why you are applying an indicator

You apply an indicator so the app knows **which rulebook** to use on every stock.

Without Apply:

- The Scan button has nothing to evaluate.
- The app does not know EMA 20, RSI 14, or any other condition.

With Apply:

- The indicator is saved in your library.
- It becomes the **active screener**.
- Strategy Conditions, columns, and MATCH logic all come from that code.
- Scan then runs that same rulebook on the whole universe.

**Apply = “Use this rulebook from now on.”**
**Scan = “Check every stock against that rulebook on the last daily bar.”**

You are not applying a stock. You are not applying a trade. You are applying a **definition of a setup**.

---

## 3. What you are applying — Momentum Pulse Finder

Your applied indicator is **Momentum Pulse Finder** on **1D**.

In words, it looks for a **short-term momentum pulse**:

1. Price is in a short uptrend: **Close is above the 20-day EMA**.
2. RSI just flipped from weak/neutral into strength: **RSI 14 crosses above 50**.
3. Both must be true **on the same last daily candle**.

The Pine-subset code (simplified) is:

```pine
//@version=6
indicator("Momentum Pulse Finder", overlay=true)
emaLength = input.int(20, "EMA Length")
rsiLength = input.int(14, "RSI Length")
ema20 = ta.ema(close, emaLength)
rsiValue = ta.rsi(close, rsiLength)
buySignal = close > ema20 and ta.crossover(rsiValue, 50)
plot(ema20, title="EMA 20")
plotshape(buySignal, title="Momentum Signal")
alertcondition(buySignal, title="Momentum Pulse")
```

### What each piece means

| Piece | Meaning | Why it is there |
|---|---|---|
| **EMA 20** | Exponential Moving Average of the last 20 daily closes. Recent prices weigh more than old ones. | A fast trend line. Close above it = short-term buyers are in control. |
| **Close > EMA 20** | Today’s close is higher than that trend line. | Avoids “RSI crossed 50” while price is still under the short trend. |
| **RSI 14** | Relative Strength Index over 14 days. Scale 0–100. Around 50 is the midpoint between bearish and bullish momentum. | Measures whether recent moves are up or down. |
| **RSI 14 crosses above 50** | Yesterday RSI was **at or below 50**, today it is **above 50**. | This is the **pulse**. It is a one-bar event, not “RSI is already 60”. |
| **AND** | Both must be true together. | A cross with price still below EMA 20 is ignored. Price above EMA 20 with no fresh RSI cross is ignored. |
| **LONG ONLY** | The scan only looks for long (buy-side) setups. | It does not look for short-sell pulses. |
| **1D** | One candle = one NSE cash session. | Daily swing research. Intraday is not used here. |

### The most important rule: `ta.crossover` is true on one bar only

`ta.crossover(RSI, 50)` is **true only on the day RSI moves from ≤50 to >50**.

- If RSI crossed 50 **yesterday**, today’s scan is **false**.
- If RSI is 55 today but was already 52 yesterday, that is **not** a cross. It is already above 50.
- TradingView Pine Screener works the same way.

That is why MATCH is rare. In your run, **RSI 14 crosses above 50** passed on only **27 of 740 evaluated names (3.6%)**. Close > EMA 20 is much easier: **246 names (33.2%)**. Both together: **23 MATCHED**.

---

## 4. How this is useful

Use the scanner as a **daily shortlist machine**.

Without it you would open 750 charts and check EMA 20 and RSI by hand.

With it you get:

1. **Today’s pulse list** — the 23 names where the event actually fired on the scan bar.
2. **Why each name passed or failed** — condition-by-condition.
3. **How strict each filter is** — Filter Analytics and the Funnel.
4. **Context, not a trade result** — 252-session Return % so you can see if the name is already extended or still quiet.
5. **A door into backtesting** — open a MATCH, then ask “would trading this pulse have worked on this stock?”

What it is **not** useful for:

- It is **not** a buy recommendation.
- It is **not** a P&L report. Scan Return % is **1-year price change**, not the profit of a trade.
- It is **not** a live order. Nothing is bought when MATCH appears.
- A MATCH on a name that is already +80% over 252 sessions (BBOX in your run) can be a late, extended pulse — interesting, not automatically a good entry.

Typical research loop:

```text
Write / pick indicator
        → Apply
        → Scan universe
        → Read MATCH list
        → Open 1 stock (Overview + Chart)
        → Backtest that idea on history
        → Only then consider paper trade
```

---

## 5. The three tabs on Strategy Tester

Open **Strategy Tester**. You will see something like:

**Strategy Tester** | **Indicator Scanner** | **New Indicator** | **Scan** | **⚡ Backtest (LEAN)**

| Control | What it does |
|---|---|
| **Strategy Tester** | Visual Strategy Builder. Filter trees (SMA, RSI, volume, and so on) evaluated by the strategy engine. Different from the Pine indicator scanner. |
| **Indicator Scanner** | The Pine-compatible screener this guide is about. |
| **New Indicator** | Create or edit Pine-subset code. Observe → Apply. |
| **Scan** | Run the applied indicator on the universe. |
| **⚡ Backtest (LEAN)** | Replay the applied idea as a **portfolio simulation** over a date range, with capital, fees, and exits. |
| **750 / 755 Stocks** | The live NSE universe used for this scan. The product default is 755 tradable names; your run evaluated **750**. |
| **As of 11-09-2026** | The **scan bar** — the last 1D session being tested. Not “today’s calendar date” if you ran the scan on 12 Sep. |

There is also a **different** app Scanner (Nifty 500 swing / recommendation engine with BUY / WATCH / REJECT scores). That is **not** this Indicator Scanner. This guide is only about Strategy Tester → Indicator Scanner.

---

## 6. What you are applying, step by step (how to use it)

### 6.1 Create or open an indicator

1. Open **Strategy Tester**.
2. Click **Indicator Scanner** (or **New Indicator**).
3. Click **+ Add indicator** if you do not have one yet.
4. Give it a name, for example **Momentum Pulse Finder**.
5. Keep timeframe **1D** (the only fully supported timeframe).
6. Paste or keep the Pine-subset code.
7. Click **Observe**.
8. Review absorbed columns and entry conditions.
9. Click **Apply**.

**Observe** means: parse the code, check it is in the allowed Pine subset, and extract:

- Columns (EMA 20, Momentum Signal, Momentum Pulse, Close, …)
- Required entry conditions (`Close > EMA 20`, `RSI 14 crosses above 50`)

**Apply** means: save that indicator and make it the active screener.

If the code uses `strategy()` instead of `indicator()`, loops, user functions, or unsupported Pine, you get a **line-specific error**. This scanner is a **whitelist subset**, not full TradingView Pine. The server never executes arbitrary Python/`eval`.

### 6.2 Set strategy conditions (required vs extra filters)

On the scanner you will see:

```text
Close > EMA 20                 ✓ Required
RSI 14 crosses above 50        ✓ Required
+ Filter
```

- **Required** = must all be true on the scan bar (AND).
- **+ Filter** = extra column filters (for example Momentum Signal is true). These also must pass.
- **Clear Filters** = drop extra column filters. Required strategy conditions remain.

Do **not** set a filter like `EMA 20 = 1`. EMA 20 is a **price**. TradingView would also return an empty list. To screen the pulse, filter **Momentum Signal is true**.

### 6.3 Run the scan

1. Confirm universe (All Stocks / 750).
2. Confirm **As of** date (last completed session, or today after 09:15 IST).
3. Click **Scan**.
4. Wait. Your run took **1 minute 5 seconds** for 750 names.

You can run about **5 scans per minute**. One scan at a time per user.

### 6.4 Read results, then drill in

1. Look at MATCHED / REJECTED / SKIPPED first.
2. Use Filter Analytics to see **which rule is the bottleneck**.
3. Open **All Results**, search a symbol, filter MATCH only.
4. Click a row (example: TVSSCS).
5. Read **Overview / Trade Plan**, then **Chart**, then **Backtest**.
6. Export CSV if you want the full table in Excel.

### 6.5 Edit, Duplicate, Archive

| Action | Use when |
|---|---|
| **Edit** | Change Pine code, name, or inputs, then Apply again. |
| **Duplicate** | Clone an indicator so you can tweak RSI length without losing the original. |
| **Archive** | Hide an indicator you no longer want in the library. |

---

## 7. What happens during a scan (the process)

Think of the scan as a factory line.

```text
1. You click Scan
2. Server takes a snapshot of the applied indicator + conditions + filters
3. Run ID is created  (yours: IND-20260912-001)
4. Universe list is loaded  (NSE cash names, ~755, 750 in your run)
5. Daily OHLCV is loaded / repaired for the As-of session
6. Each stock is evaluated on the LAST 1D bar only
7. Required conditions are checked (AND)
8. Extra column filters are checked
9. Status is set: MATCH / REJECT / SKIPPED
10. 252-session Return % is attached as context
11. Analytics are built (top returns, funnel, pass rates)
12. UI shows the completed run
```

### 7.1 Which bar is tested?

The scanner evaluates **the last 1D bar TradingView Pine Screener would use**.

| When you scan | Scan bar |
|---|---|
| After 09:15 IST on a trading day | **Today’s** forming / current 1D candle |
| Before 09:15 IST, weekend, or holiday | **Last completed** NSE cash session |
| You pick an older As-of date | That historical session |

Your run:

- Started **12 Sep 2026, 9:46 AM**
- Scan bar **2026-09-11**

So the question asked of every stock was:

> On the **11 Sep 2026** daily candle, was Close above EMA 20 **and** did RSI 14 cross above 50 **on that same candle**?

Yesterday’s cross does not count. Next week’s cross does not count.

### 7.2 What is computed per stock?

For each symbol the engine:

1. Loads enough daily bars (buffer is large; EMA 20 + RSI 14 need a bit more than 20 bars; 252-day return needs 253 closes).
2. Computes EMA 20 on Close.
3. Computes RSI 14 on Close.
4. Tests `close > ema20` on the last bar.
5. Tests `ta.crossover(rsi, 50)` on the last bar (yesterday ≤ 50 and today > 50).
6. AND them together.
7. Applies any extra filters.
8. Stores plots (EMA 20, Momentum Signal, Momentum Pulse).
9. Stores Return % = `(Close / Close 252 trading sessions ago − 1) × 100`.

No look-ahead: bar `t` cannot see bar `t+1`.

### 7.3 MATCH / REJECT / SKIPPED

| Signal | Meaning | Your run |
|---|---|---|
| **MATCH** | Every **required** entry condition passed on that last 1D bar, **and** every extra column filter passed, **and** the boolean pulse (Momentum Signal) was true on that bar. | **23** (3.1%) |
| **REJECT** | At least one required condition or extra filter failed. The stock was evaluated; it simply did not qualify. | **717** (95.6%) |
| **SKIPPED** | Not enough history, missing daily bars, or the latest stored bar is older than the scan date. The engine did **not** fail the rule; it could not judge. | **10** (1.3%) |

CUPID and ATHERENERG in your table are REJECT because **RSI 14 crosses above 50** failed (even if Close > EMA 20 passed).

TVSSCS is MATCH because **both** required conditions passed on 11 Sep 2026.

### 7.4 Independent filters vs sequential funnel

**Filter Analytics (Independent)** asks: *If I only used this one rule, how many would pass?*

Your numbers:

| Filter | Passed | Failed | Pass % |
|---|---|---|---|
| Close > EMA 20 | 246 | 494 | 33.2% |
| RSI 14 crosses above 50 | 27 | 713 | 3.6% |

These are **not** sequential. A stock can pass EMA and fail RSI, or pass RSI and fail EMA.

**Filter Funnel (Sequential)** asks: *Start with 750, apply condition 1, then condition 2, how many remain?*

Approximate funnel for your AND logic:

```text
750 total
  → skip 10 with no history
  → 740 evaluated
      → Close > EMA 20           ~246 remain
          → RSI crosses above 50  ~23 remain  ← MATCHED
```

The RSI cross is the **bottleneck**. If MATCH is “too few”, loosen RSI (for example `RSI > 50` instead of `crosses above 50`). If MATCH is “too many”, add volume or a longer trend filter.

### 7.5 Return % on the scan is not trade P&L

On the scan, Return % is:

```text
Return % = (Close / Close t-252 − 1) × 100
```

`t-252` means **252 trading sessions ago**, not 252 calendar days. Weekends and holidays are skipped.

| What it measures | What it does **not** measure |
|---|---|
| How much the **stock price** moved over about 1 year | Whether **you** would have made money |
| Context: is this name already extended? | Entry fill, stop, target, or holding period |
| Ranking of strong vs weak 1-year tapes | The pulse trade itself |

That is why:

- Entry is **—**
- Exit is the **current close** (TVSSCS ₹130.49)
- Exit rule is **Scan only — no trade is opened**
- Capital is **₹0**
- Position mode is **EOD (End of Day)** — daily close, not tick data

**BBOX +79.96%** means: BBOX’s close on the scan bar is about 80% higher than its close 252 sessions earlier. It does **not** mean a Momentum Pulse trade on BBOX made +80%.

### 7.6 Positive / Negative / Avg Return in Run Summary

Your summary:

| Number | Value | How to read it |
|---|---|---|
| Positive Returns | 322 (42.9%) | Among stocks that **could** compute a 252-day return, 322 are up over that year |
| Negative Returns | 388 (51.7%) | 388 are down over that year |
| Flat Returns | 0 | None exactly unchanged |
| Avg Return | **+7.49%** | Average of those 252-day returns |

These figures are **universe context**, not “the 23 MATCHES averaged +7.49%”. They describe the **whole evaluated tape**, MATCH and REJECT together.

So:

- 42.9% of names are up over ~1 year.
- The average name is modestly positive (+7.49%).
- That does **not** prove Momentum Pulse Finder is a +7.49% strategy.

Look at the MATCH list itself to see what **qualified names** did over 1 year. In your MATCH list, results range from **BBOX +79.96%** down to **AWFIS −49.49%**. Same pulse rule, wildly different 1-year tapes.

### 7.7 Top 5 Positive / Negative

Those tables rank by **252-day Return %**, then show whether the row was MATCH.

Your Top 5 Positive (all MATCH in this run):

1. BBOX +79.96%
2. SOUTHBANK +61.07%
3. TORNTPHARM +37.96%
4. ABDL +28.04%
5. INDUSTOWER +19.73%

Use this as **“who is already extended?”** not as a league table of trading skill.

---

## 8. How to read one stock — TVSSCS worked example

You opened **TVSSCS — TVS Supply Chain Solutions Ltd.** from run **IND-20260912-001**.

### Overview / Trade Plan

| Field | Your screen | Meaning |
|---|---|---|
| Signal | MATCH | Both required conditions passed on 11 Sep 2026 |
| Position | LONG | Scan is long-only |
| Entry Price | — | No order was placed |
| Exit Price | ₹130.49 | Last daily close (scan bar) |
| Strategy | Momentum Pulse Finder | The applied rulebook |
| Stop / Target / R:R | — | Scanner does not invent a stop or target |
| Exit Rule | Scan only — no trade is opened | Confirms this is a screen, not a fill |
| Timeframe | 1D | Daily |
| Close > EMA 20 | Passed | Price above short trend |
| RSI 14 crosses above 50 | Passed | Pulse fired **on that bar** |
| RSI (14) | 52.2 | Just above 50 — consistent with a fresh cross |
| SMA 20 | ₹127.57 | Close 130.49 is above SMA 20 |
| SMA 50 | ₹132.13 | Close is **below** SMA 50 |
| SMA 200 | ₹117.51 | Close is **above** SMA 200 |
| Primary Trend | Bullish (Above SMA 200) | Long-term trend still up |
| Medium Trend | Bearish (Below SMA 50) | Intermediate trend is not confirmed |
| RSI Zone | Neutral (30–70) | Not overbought, not oversold |
| Volume | 2.9M | Participation that session |

How to use this:

- MATCH means **the pulse happened**.
- Medium trend below SMA 50 is a caution: this is a short-term pulse, not a clean all-timeframe uptrend.
- RSI 52.2 is a **fresh** cross, not an RSI-80 blow-off. That is the point of the pulse definition.

The table showed TVSSCS Return **−1.82%** (252-day). The detail card may show Return **0.00%** with Calculation **—** when Close t-252 is missing on that panel. Trust the **formula** and the **results table**. The 252-day change is the intended scan return, not a trade P&L.

---

## 9. What backtesting is

**Backtesting** means:

> Replay the past, bar by bar, as if your rule had been allowed to **enter and exit trades**, with a cash account, and then measure how that account behaved.

A scan asks: *Did the signal fire on this bar?*

A backtest asks: *If I bought when it fired, and sold when the exit rule fired, over months or years, with ₹1,00,000, fees, and position limits, what happened to my money?*

That is why backtesting exists:

- A scan can look brilliant because 23 names “matched today”.
- Those names might have been terrible **trades** after you include exits, losers, and drawdowns.
- Backtest is the honesty check **before** paper trading.

### Scan vs backtest vs paper trade vs live

| Stage | Reality | Money | Time |
|---|---|---|---|
| **Scan** | Last bar only | ₹0 | Seconds to a minute |
| **Backtest** | Many years of bars, simulated fills | Simulated capital (e.g. ₹1,00,000) | Minutes |
| **Paper trade** | Live market, fake orders | Fake money, real prices | Days to months |
| **Live** | Real broker | Real money | After you trust the above |

Do not skip from MATCH → live buy.

---

## 10. Two backtest buttons you will see

### A. ⚡ Backtest (LEAN) on the Indicator Scanner page

This is the **professional portfolio engine** (QuantConnect LEAN, running inside Trading Labs).

You choose:

- Start date (default 2020-01-01)
- End date (today)
- Initial capital (default **₹1,00,000**)
- Universe (all ~755, or a symbol list)
- Max positions (default **10**)

It then simulates a **book of trades**, not one screenshot.

For Momentum Pulse Finder, the LEAN algorithm is:

| Rule | What LEAN does |
|---|---|
| **Entry** | Same as the scanner: Close > EMA 20 **and** RSI 14 crosses above 50 |
| **Exit** | Close **falls below** EMA 20, **or** RSI 14 **crosses below** 50 |
| **Side** | Long only |
| **Sizing** | About **10% of equity** per name (`allocation_pct = 0.10`) |
| **Max names** | 10 at once |
| **Fill** | Signal on bar **t close** → fill at bar **t+1 open** (next session open), plus slippage |
| **Costs** | Indian NSE delivery-style fees (STT, exchange, SEBI, GST, stamp, DP on sell) |
| **Slippage** | Small percentage (default around 0.05%) |

So LEAN answers:

> If I had run this pulse as a **portfolio** on many stocks, with realistic Indian costs and next-day fills, would the account have grown?

### B. Chart / Backtest tab on one stock (TVSSCS)

This is **one symbol**, one period (your screenshot: **11 Sep 2025 – 11 Sep 2026**), capital **₹1,00,000**.

It is a TradingView-style report:

- Key stats
- Cumulative PnL chart
- Buy and hold comparison
- Trades analysis
- Returns distribution

Use it to study **this name**. Do not treat one stock’s 7 trades as the strategy’s overall edge.

Important: the scanner script is an **`indicator()`**, not a **`strategy()`**. An indicator does not place broker orders by itself. The Chart/Backtest tab **reconstructs** a simulated trade list from history so you can research. That is why you can see:

- **Exit Rule: Scan only — no trade is opened**
- **All signals 0.00 INR / Primary Strategy 0.00 INR**
- **Total PnL 0.00 INR** on the headline

…while **Trades analysis** still shows 7 reconstructed trades, gross profit, gross loss, and profit factor.

Read it as: **“If pulses on TVSSCS over this year were treated as trades, here is the scoreboard.”** It is **not** money the scanner booked, and it is **not** the 750-stock LEAN portfolio.

---

## 11. Process of a LEAN backtest (what the engine does)

```text
1. You click ⚡ Backtest (LEAN) and set dates + capital
2. Job is queued (status QUEUED → RUNNING)
3. Daily bars are loaded in calendar order (oldest → newest)
4. For each trading day, for each symbol:
      a. Update EMA 20 and RSI 14 using only bars up to today
      b. If not in a position, and pulse is true, and slots remain
            → send BUY (filled next bar’s open)
      c. If in a position, and exit is true
            → send SELL (filled next bar’s open)
5. Fees and slippage are deducted
6. Equity = cash + market value of holdings (marked to close)
7. When the last date is reached, open trades are closed for reporting
8. Metrics are computed from the equity curve and the closed-trade list
9. You get: Total PnL, Max drawdown, Win rate, Profit factor, trade list, equity chart
```

### Why next-bar open?

If the signal is known only **after** today’s close, you cannot honestly fill at today’s close. The honest fill is **tomorrow’s open**. That avoids look-ahead fantasy profits.

### Why 252 trading sessions, not 252 calendar days?

NSE is closed on weekends and holidays. “One year of trading” is about **252 sessions**, not 365 calendar days. LEAN and the scan return formula both use **session bars**.

---

## 12. Every important backtest number

All examples below use **your TVSSCS Chart/Backtest screenshot** (₹1,00,000, 11 Sep 2025 – 11 Sep 2026, 7 trades).

### 12.1 Total PnL (Total Profit and Loss)

**What it is:** Ending account value minus starting capital.

```text
Total PnL (₹)  = Final equity − Initial capital
Total PnL (%)  = Total PnL / Initial capital × 100
```

**How to use it:** The first “did I make money?” number for that simulation.

| Reading | Meaning |
|---|---|
| Positive | The simulated account grew |
| Zero | No net change, **or** no strategy fills were booked |
| Negative | The simulated account shrank |

On your TVSSCS Chart tab, **Total PnL = 0.00 INR (0.00%)** sits next to **All signals 0.00 / Primary Strategy 0.00**. That headline is the **indicator / scan-only** book: the scanner did not run a broker emulator on that tab.

The **trade list** underneath is the reconstructed pulse history (7 trades). Use **Gross profit / Gross loss** there, not the 0.00 headline, to judge those reconstructed trades.

On a real **⚡ Backtest (LEAN)** result, Total PnL is the number that matters for the whole portfolio.

### 12.2 Max drawdown

**What it is:** The worst peak-to-trough drop in the equity curve.

Imagine the account climbs to ₹1,10,000, then falls to ₹99,860 before recovering. Drawdown from that peak is ₹10,140 = **10.14%**.

```text
At each day:
  peak     = highest equity seen so far
  drawdown = peak − today’s equity
Max drawdown = the largest of those drawdowns
Max drawdown % = that drop / that peak × 100
```

Your screen: **Max drawdown 10,140.00 INR / 10.14%** on ₹1,00,000.

**How to use it:** This is the pain number. It answers:

> How much would I have had to watch the account fall, even if it later recovered?

A strategy can have a positive Total PnL and still be unusable if max drawdown is 40% and you would have quit at −15%.

Rules of thumb (research, not advice):

- Under ~10%: often tolerable for a swing system
- 15–25%: uncomfortable; size down
- Over 30%: many people cannot sit through it

Drawdown is measured on **equity** (cash + open positions), not only on closed trades. A big open loser counts.

### 12.3 Profitable trades (win rate)

**What it is:** Of all **closed** trades, how many made money.

```text
Profitable trades % = Winning trades / Total trades × 100
```

Your screen: **28.57% (2 / 7)**

- 7 closed trades
- 2 winners
- 5 losers
- 0 breakevens

**How to use it:** Win rate alone is almost useless.

A system can win 80% of the time and still lose money if the 20% losers are huge. Your TVSSCS reconstruction is the opposite shape: **few wins, many losses**. That can still work **only if** winners are much larger than losers. Here they are not (see Profit factor).

### 12.4 Profit factor

**What it is:** How many rupees of gross profit you made for each rupee of gross loss.

```text
Profit factor = Gross profit / Gross loss
```

(LEAN uses the sum of winning trades’ net P&L divided by the absolute sum of losing trades’ net P&L. Same idea.)

| Profit factor | Reading |
|---|---|
| **Below 1.0** | Losses exceed profits. The system lost money on trades. |
| **= 1.0** | Breakeven before hoping for more. |
| **1.3 – 1.5** | Modest edge; easy to erase with costs or bad fills. |
| **Above 1.5 – 2.0** | Historically useful edge, still verify drawdown. |
| **Very high on tiny samples** | Often luck. 2 or 7 trades is not enough. |
| **∞ (infinite)** | No losing trades in the sample. Do not trust a tiny sample. |

Your screen:

- Gross profit **₹3,610** (3.61%)
- Gross loss **₹37,010** (37.01%)
- Displayed profit factor **0.170**

A profit factor **below 1** means: **for every ₹1 lost, you only made about ₹0.17 back.** That is a losing reconstructed series on TVSSCS for that year.

So even though the scan said **MATCH**, the 1-year pulse **trades** on this name were not a good money machine.

That is exactly why scan and backtest must stay separate in your head.

### 12.5 The rest of the scoreboard (same screen)

| Metric | Your number | Meaning |
|---|---|---|
| **Gross profit** | ₹3,610 | Sum of winning trades only |
| **Gross loss** | ₹37,010 | Sum of losing trades only (as a positive size) |
| **Commission load** | 0.14% | Fees as a % of capital — small here, but always subtracts from edge |
| **Expected payoff** | 0.00 | Average P&L per trade in that report (headline book) |
| **Largest profit** | ₹3,320 | Best single winner (almost all of the ₹3,610 came from one trade) |
| **Largest loss** | ₹13,830 | Worst single loser — much bigger than the best win |
| **Winners** | 2 trades (28.57%) | |
| **Losers** | 5 trades (71.43%) | |
| **Average profit** | ~₹1,805 | Mean of the 2 winners (the “+1805%” label on that chart is the rupee average, not +1805 percent) |
| **Average loss** | ~₹7,402 | Mean of the 5 losers — about **4×** the average win |
| **Buy and hold** | Chart overlay | What you would have made just holding the stock. Compare strategy vs doing nothing. |

The shape of this name: **small, rare wins; larger, more frequent losses.** Profit factor 0.17 is the summary of that shape.

### 12.6 Other LEAN metrics you will see on a full ⚡ Backtest

| Metric | Meaning | Use |
|---|---|---|
| **CAGR** | Annualised growth rate of the account | Compare strategies of different lengths |
| **Sharpe ratio** | Return per unit of day-to-day volatility | Higher is more “smooth” growth |
| **Sortino ratio** | Like Sharpe, but only penalises downside volatility | Useful if you care about drops more than chop |
| **Calmar ratio** | CAGR / Max drawdown % | Return you got per unit of pain |
| **Expectancy** | Average rupee (or %) you expect per trade | (Win% × Avg win) − (Loss% × \|Avg loss\|) |
| **Average trade** | Mean return of all closed trades | |
| **Total commission / slippage** | Friction | If profit factor is 1.1 before costs, costs can kill it |
| **Win rate** | Same as profitable trades % | |
| **Holding period** | Bars/days in the trade | Pulse trades should be relatively short |

---

## 13. How to use backtesting in practice

### Step-by-step (LEAN, recommended for “does this strategy work?”)

1. Apply Momentum Pulse Finder.
2. Optionally Scan first, so you understand today’s MATCH rate.
3. Click **⚡ Backtest (LEAN)**.
4. Set:
   - Start: at least several years (2020-01-01 is a reasonable default)
   - End: today
   - Capital: ₹1,00,000 (or the size you actually think in)
   - Universe: all stocks to test the **portfolio**, or one symbol to test **that name**
   - Max positions: 10
5. Wait until status is Completed.
6. Read in this order:
   1. **Total PnL** — did the account grow?
   2. **Max drawdown** — could you have lived through it?
   3. **Profit factor** — is gross profit bigger than gross loss?
   4. **Profitable trades** — is it a high-win or low-win system?
   5. **Number of trades** — 7 trades is anecdotal; hundreds is more informative.
   6. **Equity curve** — smooth up, or one lucky spike then collapse?
   7. **List of trades** — are losers clustered? Is one stock carrying everything?

### Step-by-step (one stock Chart / Backtest tab)

1. From the MATCH list, click a name.
2. Open **Chart**, then **Backtest**.
3. Note the range (1Y / 3Y / 5Y / ALL).
4. Treat it as **stock-level research**.
5. If **many** MATCH names show profit factor well below 1 and ugly drawdowns, the rule is probably not tradable as-is.

### What “good” looks like (research checklist, not a promise)

A setup worth paper-trading usually shows **together**:

- Profit factor **above ~1.3** after fees
- Max drawdown you personally can tolerate
- Enough trades (dozens to hundreds, not 2)
- Equity curve that does not depend on one outlier
- Scan MATCH rate that is rare enough to be selective, not so rare you never get a sample

Your TVSSCS 1-year reconstruction **fails** that checklist: 7 trades, PF ~0.17, losers much larger than winners.

That does **not** mean the scan is broken. It means **this name, this year, this exit rule** was a poor trade series. Other MATCH names (or a full-universe LEAN run) may look different. That is the point of testing.

---

## 14. How the two tools work together (recommended daily workflow)

```text
Morning (or after close)
  1. Open Strategy Tester → Indicator Scanner
  2. Confirm Momentum Pulse Finder is Applied
  3. Confirm As-of date is the session you care about
  4. Click Scan
  5. Wait for 100%

When completed
  6. Ignore Avg Return +7.49% as a “strategy return”
  7. Open MATCHED (23)
  8. Sort / eyeball 252-day Return %
       - Very large positive → already extended; be careful
       - Modest / negative 252-day with a fresh pulse → different kind of setup
  9. Click 3–5 names
 10. On each: Overview (did both conditions pass?) → Chart (does the cross look real?) → Backtest (did pulses pay on this name?)

Weekly / when you change the rule
 11. ⚡ Backtest (LEAN) on the full universe
 12. Only if LEAN looks acceptable, paper-trade new MATCHES
```

### Adding or changing conditions

| You want | Change |
|---|---|
| More MATCHES | Replace `crosses above 50` with `RSI > 50` (state, not event). Expect many more names, weaker timing. |
| Fewer, stricter MATCHES | Add volume (e.g. volume > 1.5 × SMA 20 of volume) or Close > SMA 200. |
| Same pulse, different speed | Change EMA 20 → 10, or RSI 14 → 7. Then **re-Apply** and re-Scan. Always re-backtest after changing. |

---

## 15. Worked reading of your full run (IND-20260912-001)

**Question the scan answered**

> Among ~750 NSE names, on **11 Sep 2026**, which ones closed above EMA 20 **and** had RSI 14 cross above 50 **that day**?

**Answer:** 23 names.

**What the 23 are:** a **same-day pulse list**, not a ranked “best stocks to own for a year”.

**Why only 23?** Because a crossover is rare. Independent pass rate 3.6%. AND with trend filter → 23.

**Why 10 skipped?** Those names did not have enough clean daily history for the engine to judge. They are not rejects. Do not treat SKIPPED as “bad stocks”.

**Why BBOX is #1 on Top Positive:** it MATCHED **and** its 252-day price change is +79.96%. That is a **hot tape**, which can also mean late entry risk.

**Why AWFIS is at the bottom of MATCH:** it still had the pulse, but its 252-day change is −49.49%. A pulse in a damaged 1-year tape is a different animal from a pulse in BBOX.

**Why CUPID is REJECT:** it failed `RSI 14 crosses above 50` on that bar. Maybe RSI was already above 50. Maybe it was still below. Either way, **no pulse today**.

**Why scan Capital is ₹0:** no trade is opened. Do not look for Total PnL on the scan page. It is not a trading account.

**Why TVSSCS backtest can show Total PnL 0.00 and also 7 trades:** the scan/indicator book did not place strategy orders; the trade analysis reconstructed 7 historical pulses. Those reconstructed trades lost more than they made (gross loss ₹37,010 vs gross profit ₹3,610).

---

## 16. Pine subset — what the scanner can and cannot do

Supported (v1):

- `//@version=6` and `indicator(title, overlay=...)`
- `input.int / float / bool / string / symbol`
- `open high low close volume`, `close[1]` style offsets
- Arithmetic, comparisons, `and` / `or` / `not`, ternary `?:`, `na`, `nz`
- `ta.sma ema rma highest lowest atr rsi crossover crossunder`
- `math.max min abs round floor ceil`
- Same-timeframe `request.security` for index close / SMA (no nested security)
- `plot`, `plotshape`, `alertcondition` (visual style is ignored)

Rejected with a line error:

- `strategy()` (this is an indicator scanner)
- Loops, user functions, `var` / `varip`
- Arrays, maps, drawing APIs
- Lower-timeframe security, financials, earnings
- Dynamic indexes, unknown functions

Daily **1D** only. Weekly / monthly are reserved in the UI but not fully supported.

---

## 17. Common misunderstandings

| If you think… | The truth is… |
|---|---|
| MATCH = buy now | MATCH = rules were true on the last 1D bar. Still need chart, risk, liquidity, backtest. |
| Return % = my profit | Return % = 252-session price change of the stock. No position was opened. |
| Avg Return +7.49% = strategy CAGR | That is the average 1-year tape of evaluated names, MATCH and REJECT together. |
| RSI is above 50, so it should MATCH | Need a **cross on this bar**, not “already above 50”. |
| It matched last week, so it should still match | Crossover is one bar. Next day it is usually REJECT. |
| SKIPPED means the stock failed | SKIPPED means not enough data to judge. |
| 23 MATCHES will all behave like BBOX | MATCH list includes +80% and −49% 1-year tapes. |
| Chart Total PnL 0.00 means the code is broken | Scan-only indicator does not book strategy P&L. Read reconstructed trades / run LEAN. |
| High win rate is enough | Profit factor and max drawdown decide survival. 28% wins with PF 0.17 is a losing sample. |
| LEAN and the scan must show the same names every day | Scan = last bar. LEAN = many bars with **exits**, **next-open fills**, **10 slots**, **fees**. Different question. |
| This is full TradingView Pine | It is a **compatible subset** aimed at screening, not a Pine runtime. |

---

## 18. Glossary

| Term | Simple meaning |
|---|---|
| **Universe** | The list of stocks being checked (about 755 NSE names; 750 in your run). |
| **Scan bar / As of** | The one daily candle the screener evaluates. |
| **Apply** | Save and activate an indicator as the current rulebook. |
| **Observe** | Parse Pine-subset code and absorb columns + conditions without scanning yet. |
| **MATCH** | All required conditions (and extra filters) true on the scan bar. |
| **REJECT** | Evaluated, but at least one required condition failed. |
| **SKIPPED** | Could not evaluate (history too short or bar missing). |
| **Required condition** | A leaf of the strategy’s AND tree (Close > EMA 20, RSI cross, …). |
| **Column filter** | Extra screener constraint on a plotted column. |
| **EMA** | Exponential moving average — a smoothed price that follows recent closes more closely. |
| **RSI** | Relative Strength Index — momentum oscillator 0–100. |
| **Crossover** | Series A was ≤ series B yesterday and is > series B today. True for one bar. |
| **OHLCV** | Open, High, Low, Close, Volume for a candle. |
| **EOD** | End of day — uses daily closes, not live ticks. |
| **Return % (scan)** | `(Close / Close t-252 − 1) × 100`. 1-year price change. |
| **t-252** | The close from 252 **trading sessions** earlier. |
| **LEAN** | Event-driven backtest engine used for portfolio simulation. |
| **Next-bar open** | Buy/sell the session **after** the signal, at the open. |
| **Equity** | Cash + current value of open positions. |
| **Total PnL** | Final equity − starting capital. |
| **Drawdown** | Drop from a previous equity peak. |
| **Max drawdown** | Worst such drop in the test. |
| **Gross profit** | Sum of winning trades. |
| **Gross loss** | Sum of losing trades (size). |
| **Profit factor** | Gross profit ÷ Gross loss. |
| **Profitable trades / win rate** | Winners ÷ all closed trades. |
| **Expectancy** | Average amount you expect to make (or lose) per trade. |
| **Slippage** | Difference between intended price and fill price. |
| **Commission / fees** | Brokerage-style and statutory NSE costs in the simulator. |
| **Buy and hold** | P&L if you just held the stock instead of trading pulses. |
| **Paper trading** | Fake orders on live (or delayed) prices. Still not a scan. |

---

## 19. Quick reference — what to click

| I want to… | Do this |
|---|---|
| Define a setup | New Indicator → paste Pine subset → Observe → Apply |
| See who qualifies **today** | Indicator Scanner → Scan |
| See why a name failed | Click the row → Scan Filters (Passed / Failed) |
| See how strict a rule is | Filter Analytics + Filter Funnel |
| Download the table | Export CSV |
| Study one MATCH | Click name → Overview → Chart → Backtest |
| Test if the **idea** makes money | ⚡ Backtest (LEAN) on the universe |
| Change the idea | Edit → Observe → Apply → Scan again → Backtest again |

---

## 20. How this run should change what you do next

From **IND-20260912-001** you already know:

1. The pulse is **rare** (3.1% MATCH). That is expected for a crossover.
2. The bottleneck is **RSI 14 crosses above 50**, not Close > EMA 20.
3. MATCH names are a mixed bag on 1-year return (about +80% to −49%).
4. TVSSCS can MATCH and still be a **poor reconstructed trade series** (low profit factor, large average loss).

So the healthy next step is **not** “buy the 23”. It is:

1. Open a few MATCH charts and confirm the RSI cross is real.
2. Run **⚡ Backtest (LEAN)** for Momentum Pulse Finder across the universe.
3. Judge **Total PnL, Max drawdown, Profit factor, number of trades**.
4. If that fails, change the rule (exit, trend filter, volume) and test again.
5. If that passes, paper-trade new MATCHES with a stop you choose. The scanner will not choose it for you.

---

## Related docs in this repo

- `docs/INDICATOR_SCANNER.md` — shorter technical notes (API, Pine subset, limits).
- `LEAN_INTEGRATION.md` — how the LEAN engine fills orders, fees, and 252-session lookback.
- `docs/TRADINGVIEW_VS_TRADING_LABS.md` — why TradingView Strategy Tester and Labs scans/backtests are different products.
- `docs/USER_MANUAL.md` — full app journey including the other (Nifty 500 recommendation) scanner and paper trading.
