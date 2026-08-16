# Contract: LTM Scanner UI

**Feature**: `037-ltm-scanner-dashboard`  
**References (layout only):** `UI Scanner .png`, `Rejection BreakDown.png`, `Top 5.png`, `techinicals.png`, `Backtest 1.png`, `backtest 2.png`  
**Audience:** Authenticated users with `advanced_scanner`

---

## S0 — Strategy switcher (P1)

On the Scanner page, next to Favorites / Scan results (or immediately below the header), show a strategy control.

| Item | Rule |
|------|------|
| Visible name | **Long-Term Buy & Hold Momentum** (never only an opaque id) |
| Other options | Production (existing). Do not invent RE-001/RE-002 unless those engines are actually registered in this build |
| Selecting LTM | Loads `/scanner/ltm/latest`; does **not** replace Production data in memory for the Production tab |
| Badge on detail | `LTM` / full name |
| Run | Explicit **Run LTM scan** (do not reuse Production “Run from Markets” as the only start) |

---

## S1 — Scan lifecycle (P1)

| State | UI |
|-------|-----|
| No LTM scan | Empty: “No Long-Term Buy & Hold Momentum scan yet” + Run |
| evaluating / backtesting | Progress. **Hide** final recommendation table, Top 5, Least 5, and rejection percents-as-final |
| blocked_stale | Operator-visible freshness reason + remediation (033 contract) |
| completed + warmup | STATUS=WARMUP; zero BUY/WATCH |
| completed + zero selected | Banner: scan completed; no name passed LTM eligibility gates |
| completed | Summary + breakdown + boards + table |

Copy must name **Long-Term Buy & Hold Momentum**, not “STR-500”.

---

## S2 — Scan summary strip (P1)

Cards: Total, Data valid, Evaluated, Final candidates, BUY, REJECT, Data failures.  
Also show WATCH when mid-cycle leaders exist.  
Show `clock_status` and sessions (or date) to next rebalance.  
If `survivorship_biased`, show a visible **Survivorship-biased** label.

---

## S3 — Rejection Breakdown (P1)

Collapsible card grid matching the reference density: **label, count, percent of evaluated, “First failure”**.

Required buckets (only these families):  
`not_in_universe`, `insufficient_history`, `missing_close_t`, `momentum_undefined`, `failed_momentum_gate`, `ranked_outside_top_10`, `data_source_failure`, `other`.

**Forbidden bucket labels:** RS percentile, consolidation maturity, base width, breakout, RS leading high, volume multiple, sector MRS, corporate event (unless mapped into `other` with LTM wording).

Each rejected name increments exactly one bucket.

---

## S4 — Recommendations table (P1)

Reuse CandidateTable layout: rank, symbol, signal, score/conviction slot (momentum % is the LTM “score” stand-in), action to open detail.

| Clock | Selected rows | Others |
|-------|---------------|--------|
| REBALANCE | BUY | REJECT |
| MID_CYCLE | WATCH | REJECT |
| WARMUP | none | REJECT / empty |

Do not show a final table before `recommendations_final`.

---

## S5 — Top 5 / Least 5 (P2)

Two tables after a completed scan.

| Board | Inclusion | Sort |
|-------|-----------|------|
| Top 5 Positive Backtest Returns | 1Y book-trade net return **> 0** | return desc |
| Least 5 Backtest Returns | ≥1 real book trade in 1Y | return asc |

Columns: rank, symbol, signal (today), return, trades, win rate, max DD, profit factor.  
Period label: last 1 year of completed sessions (`start → end`).  
Footnote: only completed 1-year **book** backtests; never-selected names omitted.  
Today’s REJECT may appear.  
Do not pad to five rows.  
Detail-tab window toggles do **not** re-sort these boards.

---

## S6 — Technicals tab (P2)

When `strategy_id = 17_long_term_mom`:

**Header:** signal badge, eligibility / hard-filter result, strategy name, clock chip.

**Tiles (required):** Momentum 252, Close T, Close T−252, Rank among eligible, Gate (> +50%), Selected, Sessions to rebalance.

Missing momentum ⇒ “unavailable”, never `0.00`.

**Must not show as decision tiles:** RSI, EMA/SMA structure, ATR, Bollinger, volume multiple, RS vs Nifty, sector rotation.

---

## S7 — Backtest tab (P2)

Headline: total return, CAGR, max DD, win rate, trades, profit factor (Sharpe optional if computed).  
Equity vs NIFTY 500 when index series exists.  
Drawdown, monthly grid, trade log, best / worst, top winning / losing.  
Windows 1Y / 3Y / 5Y / All on this tab only.  
Never-selected name: explicit empty / “never selected” — do not invent another strategy’s trades.

---

## S8 — Limitations (P3)

Always reachable from LTM results: no stop, concentration, survivorship, look-ahead of signal-close replay, past CAGR is not a forecast.

---

## Accessibility / empty / error

- Unauthenticated: existing login wall.
- Missing permission: existing feature-guard.
- Failed scan: error panel + retry.
- Keyboard: switcher and tabs stay in the existing Scanner tab pattern.
