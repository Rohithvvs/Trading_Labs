# Contract: 52-Week High Breakout Scanner UI

**Feature**: `038-52w-high-breakout`  
**References (layout only):** `UI Scanner .png`, `Rejection BreakDown.png`, `Top 5.png`, `techinicals.png`, `Backtest 1.png`, `backtest 2.png`  
**Audience:** Authenticated users with `advanced_scanner`

---

## S0 — Strategy switcher and isolated Run (P1)

On the Scanner page, in the existing strategy tablist, place a button labelled **52-Week High Breakout** immediately **beside** **Long-Term Buy & Hold Momentum**.

| Item | Rule |
|------|------|
| Visible name | **52-Week High Breakout** (never only `09_52w_breakout`) |
| Position | Immediately after the LTM button |
| Selecting 52W | Loads `/scanner/w52/latest`; does **not** replace LTM or Production data in memory |
| Subtitle / badge | Full display name + `52W` |
| Run | Explicit Run on **this** view calls **only** `POST /scanner/w52/runs` |
| Second click | Disabled or ignored while status is queued / evaluating / backtesting / publishing (clarify Q2) |

This Run MUST NOT start LTM or Production. LTM Run and Production “Run from Markets” MUST NOT start 52W.

---

## S1 — Scan lifecycle (P1)

| State | UI |
|-------|-----|
| No 52W scan | Empty: “No 52-Week High Breakout scan yet” + Run |
| evaluating / backtesting | Progress copy names **52-Week High Breakout** only. **Hide** final recommendation table, Top 5, Least 5, and rejection percents-as-final |
| blocked_stale | Operator-visible freshness reason + remediation (033 contract) |
| completed + warmup | STATUS=WARMUP; zero BUY |
| completed + market-off | STATUS=MARKET_OFF; zero new BUY; HOLD rows still shown; EXIT may appear |
| completed + zero new buys | Banner: scan completed; no name received a new slot (no fake BUY list). HOLD rows still shown |
| completed | Summary + breakdown + boards + table + order list |
| 409 in progress | Keep showing in-flight progress; do not start a second spinner |

Copy must name **52-Week High Breakout**, not “STR-500” and not Long-Term Buy & Hold Momentum.

---

## S2 — Scan summary strip (P1)

Cards: Total, Data valid, Evaluated, Final candidates, BUY, **HOLD**, REJECT, Data failures.  
Also show WATCH count when skipped buy-signals exist.  
Show `book_status`, `market_ok`, free slots, cash / equity, holdings count.  
If `survivorship_biased`, show a visible **Survivorship-biased** label.

---

## S3 — Rejection Breakdown (P1)

Collapsible card grid matching the reference density: **label, count, percent of evaluated, “First failure”**.

Required buckets (only these families):  
`not_in_universe`, `insufficient_history`, `missing_bar`, `close_below_prior_high`, `volume_not_above_average`, `market_filter_off`, `sold_today`, `no_free_slot`, `data_source_failure`, `other`.

**Forbidden bucket labels:** LTM +50% gate, RS percentile, consolidation maturity, base width, Darvas box, sector MRS, 2× volume, corporate event (unless mapped into `other` with 52W wording).

Each rejected name increments exactly one bucket. **HOLD names are omitted.**

---

## S4 — Recommendations table and order list (P1)

Reuse CandidateTable layout: rank, symbol, signal, context slot (close vs prior high / volume vs average as the “score” stand-in), action to open detail.

| Signal | When |
|--------|------|
| BUY | New 10% slot taken today |
| HOLD | Still open after trail; not a new BUY this session (clarify Q1) |
| WATCH | Buy signal, no slot; or market-off would-be |
| REJECT | Failed a new-entry gate |

Do not show a final table before `recommendations_final`.

**Order list** (separate strip or stacked above the table): EXIT rows first (reason trailing stop), then BUY rows. A same-session EXIT is **not** labelled HOLD in the table.

---

## S5 — Top 5 / Least 5 (P2)

Two tables after a completed scan. Layout matches `Top 5.png`.

| Board | Inclusion | Sort |
|-------|-----------|------|
| Top 5 Positive Backtest Returns | 1Y book-trade net return **> 0** | return desc |
| Least 5 Backtest Returns | lowest 1Y book-trade net return | return asc |

Columns: rank, symbol, today’s signal (may be HOLD or REJECT), return, trades, win rate, max drawdown, profit factor. Period label = last 1 year of completed sessions (start → end).

Omit: never selected in the window, insufficient history, data-source failure (including failed attribution). Do not pad Top 5 with non-positive names. Detail 3Y/5Y/All MUST NOT re-rank these boards.

---

## S6 — Technicals tab (P2)

When `strategy_id == 09_52w_breakout`, the Technicals tab shows a decision header (signal, eligibility, **52-Week High Breakout**) and tiles:

- Close on T, prior 252-session high, close-versus-prior-high pass/fail
- Volume on T, 20-session volume average, volume-versus-average pass/fail
- 14-session **simple** average true range
- 60-session rank key and rank among today’s buy-signal names
- Market filter: benchmark close vs 50-session average, pass/fail
- Slot status: taken / no slot / held / sold today
- When HOLD: high-water mark, current trailing stop, would-exit today

Missing values render as unavailable, never as zero.

**Forbidden decision tiles:** RSI, stock MA stack, Bollinger, Darvas box, Mansfield/sector RS, earnings, 2× volume, LTM 252-session +50% gate.

---

## S7 — Backtest tab (P2)

Layout matches `Backtest 1.png` / `backtest 2.png`: headline metrics, equity vs NIFTY 500, drawdown, monthly grid, trade log, best/worst, top winning / losing trades. Window toggle 1Y / 3Y / 5Y / All is detail-only.

Never-selected name: explicit empty / “never selected”, not another strategy’s trades.  
Failed attribution: explicit data-source failure, not a fake 0% curve.

---

## S8 — Disclosures (P3)

Always visible on 52W Scanner / Backtest surfaces (spec Known Limitations): survivorship, signal-close look-ahead, SMA/ATR include today, state-not-cross late entries, gap-through trail (VEDL example), win rate < 50% with payoff carrying the edge, 10-name concentration, open 2026 drawdown on the published sample, past CAGR is not a forecast.
