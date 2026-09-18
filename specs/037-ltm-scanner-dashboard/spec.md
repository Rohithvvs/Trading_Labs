# Feature Specification: Long-Term Buy & Hold Momentum Scanner

**Feature Branch**: `037-ltm-scanner-dashboard`  
**Created**: 2026-08-15  
**Status**: Clarified (session 2026-08-15)  
**Input**: User description: Add Long-Term Buy & Hold Momentum to the existing Scanner dashboard, with strategy-specific rejection breakdown, scan-time backtesting before recommendations, top-5 / least-5 return boards, strategy-owned Technicals, and matching Backtest / recommendation layouts. Canonical strategy id: `17_long_term_mom`.

**Business source of truth**: Long-Term Buy & Hold Momentum SPEC-SPECIFY (strategy identity `17_long_term_mom`).  
**Product surfaces**: Scanner dashboard, scan-results table, rejection breakdown, top/least return boards, stock-detail Technicals tab, stock-detail Backtest tab.  
**UI references** (layout and information density, not algorithm): `Rejection BreakDown.png`, `Top 5.png`, `techinicals.png`, `Backtest 1.png`, `backtest 2.png`, `UI Scanner .png`.

This specification locks both the product behaviour on the Scanner dashboard and the strategy rules that drive it. Later clarify / plan / tasks / implement work SHALL implement §§User Stories–Requirements without silently changing the selection math.

## Clarifications

### Session 2026-08-15

- Q: Who must finish a scan-time backtest before recommendations are shown? → A: Every name with valid 252-session history. Failed +50% and ranked-out names still get a backtest; insufficient-history / data-failure names do not.
- Q: What time window do the Top 5 and Least 5 boards use? → A: Last 1 year of completed sessions (fixed). Stock-detail Backtest tab may still offer 1Y / 3Y / 5Y / All.
- Q: How is each name’s 1-year board return calculated? → A: Only that name’s real book trades in the last 1 year (when it was in the selected 10). Never selected in the window → excluded from Top 5 / Least 5.
- Q: Do still-open holdings count in the 1-year board return? → A: Closed trades in the window, plus mark-to-market of any still-open book position as of the scan session.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See and Select Long-Term Buy & Hold Momentum on the Scanner (Priority: P1)

As a trader or research operator, I open the Scanner dashboard and can select **Long-Term Buy & Hold Momentum** as the active strategy. The strategy name is visible in the page chrome (engine/strategy switcher, badge, and subtitle) so I never confuse this book with Production, RE-001, RE-002, or Buy-and-Hold Top Momentum (the one-time, never-rebalanced cousin).

**Why this priority**: If the strategy is not selectable and named, none of the scan, backtest, or recommendation work is usable.

**Independent Test**: Open Scanner, switch to Long-Term Buy & Hold Momentum, confirm the displayed strategy name and that scan results, summary cards, and detail views are scoped to this strategy only.

**Acceptance Scenarios**:

1. **Given** an authenticated user with Scanner access, **When** they open the Scanner dashboard, **Then** Long-Term Buy & Hold Momentum is listed as a selectable strategy alongside existing engines, and selecting it updates the visible strategy name.
2. **Given** Long-Term Buy & Hold Momentum is selected, **When** the latest scan for that strategy exists, **Then** the page subtitle / badge shows the strategy display name (not a generic “Production” label) and scan counts belong to this strategy.
3. **Given** another engine is selected after viewing Long-Term Buy & Hold Momentum, **When** the user switches back, **Then** they again see this strategy’s name and its own latest scan — not another engine’s recommendations.

---

### User Story 2 - Scan Runs Backtest Before Recommendations Appear (Priority: P1)

As a trader, I run a Long-Term Buy & Hold Momentum scan and do **not** see a recommendation list until scan-time backtests have finished for **every name with valid 252-session history**, using **the same eligibility filters** as the scan. Names that failed the +50% gate or ranked outside the top 10 are still backtested. Names that lack history or failed data checks are excluded from backtest and are not treated as completed-return rows.

**Why this priority**: The user explicitly requires backtesting during the scan, before recommendations are shown, and filter parity between scan and backtest.

**Independent Test**: Start a Long-Term Buy & Hold Momentum scan; observe that recommendation rows stay hidden (or the results table remains in a “scanning / backtesting” state) until backtests complete for every name with valid 252-session history; then recommendations appear with backtest-linked ranking data.

**Acceptance Scenarios**:

1. **Given** the operator starts a Long-Term Buy & Hold Momentum scan, **When** evaluation is still running or any name with valid 252-session history has an unfinished backtest, **Then** the recommendations table is not presented as final (no premature BUY/WATCH list).
2. **Given** the scan finishes evaluation and those history-valid backtests, **When** results render, **Then** every recommended name (and every other history-valid name) has a completed backtest for the scan window.
3. **Given** a name fails for insufficient 252-session history, missing/invalid close, undefined momentum, or data-source failure, **When** backtesting runs, **Then** that name is **not** backtested, is excluded from Top 5 / Least 5, and keeps the same first-failure reason as the scan.
4. **Given** a name has valid 252-session history but failed the +50% gate or ranked outside the top 10, **When** backtesting runs, **Then** that name still receives a completed backtest under the same strategy rules. It appears on Top 5 / Least 5 only if it had at least one real book trade in the last 1 year (it was selected in a cohort during that window).
5. **Given** the operator compares scan filters to backtest filters for this strategy, **When** they inspect the run, **Then** universe, 252-session lookback, strict +50% gate, top-10 cap, and rebalance clock are identical — no extra moving-average, volume, sector, or earnings filter is introduced on either side.

---

### User Story 3 - Read Recommendations After the Scan (Priority: P1)

As a trader, after a completed Long-Term Buy & Hold Momentum scan I see a recommendation table in the existing Scanner results layout: rank, symbol, signal, score/conviction context, and an action to open the stock. Selected names are BUY on a rebalance session and WATCH on a mid-cycle session. Everyone else is REJECT.

**Why this priority**: Recommendations are the primary output of the Scanner.

**Independent Test**: Complete a scan with at least one eligible name and one rejected name; verify table columns, signals, and empty-state copy.

**Acceptance Scenarios**:

1. **Given** a completed scan on a rebalance session with at least one eligible name, **When** the operator opens Scan results, **Then** selected names (up to 10) show signal BUY, ranked by 252-session momentum descending, ticker ascending on ties.
2. **Given** a completed scan on a non-rebalance session, **When** results render, **Then** current leaders (same selection rule) show WATCH, the page shows mid-cycle status and sessions remaining until the next rebalance, and no new BUY entries are emitted.
3. **Given** a completed scan with zero eligible names, **When** results render, **Then** an explicit empty banner states that the scan completed but no name passed the Long-Term Buy & Hold Momentum eligibility gates (no fake BUY list).
4. **Given** any completed scan, **When** the operator views the scan summary strip, **Then** they see totals for universe size, data-valid count, evaluated count, final candidates, BUY, REJECT, and data failures.

---

### User Story 4 - Understand Why Names Were Rejected (Priority: P1)

As a trader, I expand a **Rejection Breakdown** section on the Scanner dashboard and see first-failure counts for this strategy only. The layout matches the reference card grid (label, count, percent of evaluated, “First failure”), but the buckets are Long-Term Buy & Hold Momentum reasons — not another strategy’s RS / consolidation / breakout gates.

**Why this priority**: Operators cannot trust a 10-name book unless they can see where the rest of the universe died.

**Independent Test**: Complete a scan that produces mixed failure reasons; confirm each rejected name increments exactly one first-failure bucket and percents sum consistently with the evaluated set.

**Acceptance Scenarios**:

1. **Given** a completed Long-Term Buy & Hold Momentum scan, **When** the operator expands Rejection Breakdown, **Then** they see first-failure cards for at least: insufficient historical data, missing/invalid close, failed +50% momentum gate, eligible but ranked outside the top 10, not in investable universe, data-source failure, and other.
2. **Given** a name fails both “insufficient history” and “failed +50% gate”, **When** counts are computed, **Then** it is counted only in the earliest first-failure bucket (not double-counted).
3. **Given** the operator compares this section to a different strategy’s breakdown, **When** Long-Term Buy & Hold Momentum is selected, **Then** they do **not** see that other strategy’s gates (relative-strength percentile, consolidation maturity, base width, breakout, sector rotation, volume multiple) as decision buckets.

---

### User Story 5 - Review Top 5 and Least 5 Backtest Returns (Priority: P2)

As a trader, after the scan I see two boards: the **top 5** names with the highest **positive** completed backtest returns, and the **least 5** names with the lowest completed backtest returns, both over the **last 1 year of completed sessions**. Boards use the reference table (rank, symbol, signal, return, trades, win rate, max drawdown, profit factor) and remain honest when fewer than five names qualify.

**Why this priority**: Post-scan ranking by realized backtest return is an explicit product request and helps operators challenge the live 10-name book.

**Independent Test**: Complete a scan whose 1-year backtests include at least six positive and six negative names; verify the two boards, the 1-year period label, sort order, and exclusion of incomplete backtests.

**Acceptance Scenarios**:

1. **Given** a completed scan with more than five names that each had at least one real book trade in the last 1 year and a **positive** net return on those trades, **When** the Top 5 board renders, **Then** it shows exactly five rows sorted by that 1-year net return descending, including today’s REJECT names if those returns are the highest, and the period label is the last 1 year of completed sessions.
2. **Given** a completed scan with more than five names that each had at least one real book trade in the last 1 year, **When** the Least 5 board renders, **Then** it shows the five lowest 1-year net returns (most negative or smallest), same columns, independent of today’s BUY/WATCH/REJECT.
3. **Given** fewer than five names have a positive 1-year book-trade return, **When** Top 5 renders, **Then** it shows only those names and does not pad with zero or negative returns.
4. **Given** a name was never selected in the last 1 year (zero real book trades in the window), **When** boards are built, **Then** that name is excluded even if its scan-time backtest job finished with an empty blotter.
5. **Given** the operator opens a name’s Backtest tab, **When** they change the chart window to 3Y / 5Y / All, **Then** the scan-level Top 5 / Least 5 boards stay on the fixed 1-year ranking and do not re-sort.
6. **Given** a name is still held from the last rebalance, **When** boards are built, **Then** that open position’s mark-to-market at the scan session is included in the 1-year return and trade count; the system does not wait for the next rebalance and does not place a live exit from that mark.

---

### User Story 6 - Inspect Strategy-Owned Technicals for a Name (Priority: P2)

As a trader, I open a scanned name and use the **Technicals** tab to see every technical input this strategy actually uses to decide eligibility, rank, and selection — not Production / RE-001 / RE-002 indicators that this strategy does not compute.

**Why this priority**: Showing another engine’s ATR, bands, or multi-timeframe tiles would mis-explain a 252-session momentum book.

**Independent Test**: Open a BUY, a failed-gate REJECT, and an insufficient-history REJECT; confirm the Technicals tab shows Long-Term Buy & Hold Momentum fields and the correct pass/fail state.

**Acceptance Scenarios**:

1. **Given** a selected name, **When** the operator opens Technicals, **Then** they see a technical-decision header (signal badge, eligibility / hard-filter result, strategy name) and tiles for 252-session momentum, close on the signal session, close 252 sessions earlier, rank among eligible names, gate result (strictly greater than +50%), and selection status.
2. **Given** a name that failed the +50% gate, **When** Technicals renders, **Then** momentum is shown as a number, the gate tile is failed, and the name is not marked selected.
3. **Given** a name with missing 252-session history, **When** Technicals renders, **Then** momentum is shown as unavailable (not zero) and the first-failure reason is insufficient history.
4. **Given** Long-Term Buy & Hold Momentum is the active strategy, **When** Technicals renders, **Then** RSI, moving-average stack, average true range, volume multiple, relative strength vs the index, and sector rotation are **not** presented as decision inputs.

---

### User Story 7 - Inspect Per-Name and Book Backtest on the Detail Tab (Priority: P2)

As a trader, I open the **Backtest** tab on a scanned name and see the reference backtest workspace: headline metrics, equity vs benchmark, drawdown, monthly returns, trade log, best/worst trade, and top winning / losing trades. The path uses the same filters and rebalance clock as the scan.

**Why this priority**: Backtest is the evidence layer that must exist before the operator acts on a recommendation.

**Independent Test**: Open Backtest for a name that appeared in at least one historical cohort and for a name that never qualified; verify metrics, empty states, and filter parity.

**Acceptance Scenarios**:

1. **Given** a name with at least one completed historical cohort trade, **When** Backtest opens, **Then** the operator sees total return, compounded annual growth, max drawdown, win rate, trade count, profit factor, equity curve, drawdown chart, monthly return grid, last trades, best trade, and worst trade.
2. **Given** the operator views the equity chart, **When** a benchmark series is available, **Then** they can compare strategy equity to NIFTY 500 buy-and-hold over the same window.
3. **Given** a name never qualified under the +50% gate, **When** Backtest opens, **Then** the tab shows zero strategy trades for this name (or an explicit “never selected” state) rather than inventing a different strategy’s trades.
4. **Given** the scan-level book backtest exists, **When** the operator reviews scan summary or detail, **Then** they can see that the book sold everything and bought the new equal-weight basket only on rebalance sessions.

---

### User Story 8 - Trust the Rebalance Clock, Warmup, and Disclosed Limits (Priority: P3)

As a trader, I can see whether the book is in warmup, mid-cycle, or rebalance, and I am shown the strategy’s known limits (no stop, concentration, survivorship, past performance is not a forecast) so I do not treat the Scanner as a guaranteed live edge.

**Why this priority**: Misreading a mid-cycle scan as an order day, or hiding a −40% historical drawdown, would be a product defect.

**Independent Test**: Load a warmup-only dataset, a mid-cycle snapshot, and a rebalance-day snapshot; confirm status labels and the limitations disclosure.

**Acceptance Scenarios**:

1. **Given** fewer than 252 shared trading sessions of history exist, **When** a scan runs, **Then** status is WARMUP, no BUY or WATCH entries are emitted, and the rejection/empty copy explains insufficient history.
2. **Given** a mid-cycle scan, **When** the dashboard renders, **Then** it shows estimated sessions (or date) until the next rebalance and does not instruct the operator to liquidate and rebuy today.
3. **Given** any Long-Term Buy & Hold Momentum result view, **When** the operator reads the strategy context, **Then** they can see that there is no stop-loss, no market-regime filter, and that published historical performance is not a live guarantee.

---

### Edge Cases

- **Exactly +50.000…% 252-session return**: ineligible. The gate is strict (`>` +50%), not `>=`.
- **Fewer than 10 names above +50%**: take all eligible names; size equally across those names; residual cash is none in the canonical book.
- **Zero eligible names**: 100% cash until the next rebalance; no BUY; rejection breakdown still populated.
- **Momentum undefined (missing close, not-a-number, infinite)**: ineligible; first-failure is missing/invalid data, not a failed gate.
- **Missing print on a non-rebalance day for a held name**: carry last mark for reporting; still attempt exit on the next rebalance if a print exists.
- **Name delisted between rebalances**: exit at last available print immediately; do not wait for the annual clock.
- **Selected name cannot be bought (halt, ban, no auction)**: skip it; redistribute that slot across remaining selected names in the canonical book.
- **Name remains in the top 10 next year**: still treated as a full sell-and-rebuy on the rebalance (no “hold if still selected” netting in this version).
- **Last session of a historical test**: force-close remaining names at that session’s close for reporting only. Live trading does not invent an extra liquidation day.
- **Process restart mid-cycle**: persisted sessions-since-rebalance and last rebalance date survive; the clock must not reset to zero.
- **Scan still running**: recommendations, top/least boards, and rejection percents are not shown as final.
- **Insufficient-history or data-failure name**: not backtested; not a Top 5 / Least 5 candidate; first-failure remains the data reason.
- **History-valid but rejected today** (failed +50% gate or ranked outside top 10): still backtested. Appears on Top 5 / Least 5 only if it had at least one real book trade in the last 1 year.
- **Never selected in the last 1 year**: scan-time backtest may finish with zero strategy trades; excluded from Top 5 / Least 5 (not treated as 0% return).
- **Still-open current-cohort holding**: counts toward that name’s 1-year board return via mark-to-market at the scan session’s adjusted close (or last available mark if that session has no print). It is not left out until the next rebalance.
- **Buy-and-hold or isolated single-name replay**: MUST NOT be used as the board return. Boards use only this name’s fills from the true top-10 book.
- **Fewer than five names with a positive 1-year book-trade return**: Top 5 shows the smaller set; does not fabricate rows.
- **Survivorship-only universe (current list applied to all history)**: results MUST be labelled survivorship-biased and MUST NOT be claimed as a production live book.
- **Corporate-action-unadjusted prices**: forbidden for the 252-session return; splits would dominate rank.
- **Confusion with Buy-and-Hold Top Momentum**: that other system buys top 10 once and never rebalances. This system rebalances every 252 sessions.

---

## Requirements *(mandatory)*

### Functional Requirements

#### Strategy identity and scanner presence

- **FR-001**: System MUST register Long-Term Buy & Hold Momentum as a distinct Scanner strategy with display name **Long-Term Buy & Hold Momentum**, short name **LTM**, and stable id `17_long_term_mom`.
- **FR-002**: Users MUST be able to select this strategy on the Scanner dashboard and see its display name in the strategy switcher, page subtitle, and stock-detail badge.
- **FR-003**: System MUST NOT confuse this strategy with Buy-and-Hold Top Momentum (one-time purchase, never rebalanced) or with Production / RE-001 / RE-002 decision engines.
- **FR-004**: This strategy MUST be long-only Indian cash equities, benchmarked to NIFTY 500 for reporting only. The benchmark MUST NOT change selection.

#### Universe, calendar, and prices

- **FR-005**: Investable universe MUST be NIFTY 500 cash-equity constituents on the evaluation session.
- **FR-006**: The master calendar MUST be NIFTY 500 index trading sessions (or NSE cash-equity sessions if the index print is missing). Momentum lookback counts **sessions on this calendar**, not calendar days.
- **FR-007**: A name is a candidate on session T only if all of the following hold: it is a NIFTY 500 constituent as of T; it has a valid corporate-action-adjusted close on T; it has a valid adjusted close 252 sessions earlier; 252-session momentum is finite.
- **FR-008**: 252-session momentum, ranking, marks, and backtest fills MUST use corporate-action-adjusted close. Unadjusted close MUST NOT be used.
- **FR-009**: Stock series MUST align to the master calendar. A missing stock print is treated as missing for that name that day and MUST NOT be invented solely to force eligibility.

#### Core selection rules

- **FR-010**: System MUST compute `Momentum_252 = (adjusted close on T ÷ adjusted close 252 sessions earlier) − 1`. Units are decimal (`0.50` = +50%).
- **FR-011**: A name is eligible if and only if momentum is defined **and** strictly greater than `0.50`. A name at exactly +50% is not eligible.
- **FR-012**: Eligible names MUST be ranked by momentum descending, then ticker symbol ascending (deterministic tie-break). Sort MUST NOT depend on hash or insertion order.
- **FR-013**: Selected set MUST be the first `min(10, number of eligible names)` in that ranked list. If none are eligible, the book is 100% cash until the next rebalance.
- **FR-014**: This strategy MUST NOT require RSI, simple/exponential moving averages, average true range, volume multiple, relative strength versus Nifty, sector rotation scores, or earnings calendars as selection inputs.

#### Rebalance clock

- **FR-015**: No selection or new entry is allowed before 252 sessions of shared history (WARMUP).
- **FR-016**: After warmup, a rebalance fires on the first session with session index ≥ 252, then every 252 further sessions. The rebalance session resets the counter to 0. This is **not** calendar year-end and **not** every 365 calendar days.
- **FR-017**: On non-rebalance sessions the live book MUST NOT trade, MUST NOT trail stops, MUST NOT rebalance early, and MUST NOT add names. The Scanner MAY still evaluate and display current leaders as WATCH (FR-031).
- **FR-018**: Historical tests MUST force-liquidate remaining names on the last session of the sample at that session’s close. Live trading MUST NOT invent an extra liquidation day.
- **FR-019**: System MUST persist cash, holdings, sessions since rebalance, last rebalance date, sizing mode, fill model, and pending orders. Restarting MUST NOT reset the 252-session clock.

#### Portfolio construction and execution

- **FR-020**: Default live / Scanner book (Mode A): after selling the entire book on a rebalance, each selected name receives an equal share of remaining cash (`cash ÷ N`). If `N = 0`, hold 100% cash. The book is fully invested whenever `N ≥ 1`.
- **FR-021**: System SHOULD also support Mode B as a research/comparison switch only: each new buy is 10% of current equity, maximum 10 names, leftover cash if fewer than 10 qualify. Mode B MUST NOT be the default live book.
- **FR-022**: Names that remain selected MUST still be sold and rebought on the rebalance (full round-trip). Netting “hold if still selected” is out of scope for this version.
- **FR-023**: Live India cash equity MUST use whole shares only; leftover rupees stay cash. Research replay MAY allow fractional shares.
- **FR-024**: Gross exposure MUST NOT exceed 100% of equity except microscopic rounding. Shorts, leverage, and futures/options substitutes are forbidden.
- **FR-025**: There is no stop-loss, trailing stop, take-profit, time stop other than the 252-session rebalance, index/moving-average market filter, sector cap, or volatility targeting. A name that falls sharply inside the year is held until the next rebalance.
- **FR-026**: Historical replay fills MUST use the rebalance session’s adjusted close, sells before buys. Live recommended fill is the next session’s open / auction after the signal close is known.
- **FR-027**: If a selected name cannot be bought, skip it and redistribute its slot across remaining selected names (Mode A) or leave that slot in cash (Mode B).
- **FR-028**: Unused cash earns 0 in the published historical path unless a later clarification adds a sweep rate.

#### Scanner run contract

- **FR-029**: A Long-Term Buy & Hold Momentum scan MUST evaluate the investable universe with FR-005–FR-014, then run a scan-time backtest for **every name that has valid 252-session history** using those **same** filters (FR-041), and only then publish the recommendation list. Names that failed the +50% gate or ranked outside the top 10 MUST still be backtested. Names that lack 252-session history or failed data checks MUST NOT be backtested.
- **FR-030**: On a rebalance session the Scanner MUST emit BUY for each selected name with rank, 252-session momentum, target weight, and target notional, plus exits for every current holding (reason = rebalance) and unfilled cash.
- **FR-031**: On a non-rebalance session the Scanner MUST NOT emit new BUY entries. Current leaders MAY appear as WATCH. The page MUST show next-rebalance estimate, current holdings with mark-to-market and unrealized percent when holdings exist, and sessions remaining.
- **FR-032**: Until 252 sessions of history exist, the Scanner MUST show STATUS=WARMUP and MUST NOT emit BUY or WATCH entries.
- **FR-033**: Scan summary MUST report total names, data-valid count, evaluated count, final candidates, BUY count, REJECT count, and data-failure count.
- **FR-034**: If zero names pass the gates, the Scanner MUST show an explicit completed-but-empty state rather than a blank table.

#### Rejection breakdown

- **FR-035**: Scanner MUST present a collapsible Rejection Breakdown section in the reference card-grid layout (bucket name, count, percent of evaluated, first-failure caption).
- **FR-036**: First-failure buckets for this strategy MUST include at least: not in investable universe; insufficient historical data (no close 252 sessions earlier); missing or invalid close on T; undefined momentum; failed +50% gate; eligible but ranked outside top 10; data-source failure; other.
- **FR-037**: Each rejected name MUST increment exactly one first-failure bucket (earliest failing rule). Percents are of the evaluated set.
- **FR-038**: Rejection Breakdown MUST NOT reuse another strategy’s gate names as if they were this strategy’s rules.

#### Top 5 / least 5

- **FR-039**: After a completed scan, Scanner MUST show Top 5 Positive Backtest Returns over the **last 1 year of completed sessions** (fixed window): up to five names whose **real book trades** in that window have a **positive** net return, sorted by that return descending. A “real book trade” is an entry created because the name was in the selected top 10 on a rebalance (not an isolated single-name signal and not buy-and-hold). The 1-year net return MUST include (1) closed book trades whose hold overlaps the window and (2) mark-to-market of any still-open book position as of the scan session. Columns: rank, symbol, signal, return, trades, win rate, max drawdown, profit factor. The period (start date → end date) MUST be visible.
- **FR-040**: After a completed scan, Scanner MUST show Least 5 Backtest Returns over the **same fixed last-1-year window**: up to five names with at least one real book trade in that window and the lowest net returns on those trades, same columns. Names with zero book trades in the window, insufficient history, or data failure are excluded (not ranked as 0%). Isolated single-name replays and plain buy-and-hold MUST NOT be used. Changing the stock-detail Backtest window MUST NOT re-rank these boards.
- **FR-055**: For board metrics, an open book position is marked at the scan session’s adjusted close (carry last mark if that session has no print). Trade count includes that open position as one trade. Win rate treats the marked-open position as one outcome (win if marked return > 0). Live trading MUST NOT invent an exit order from this mark.

#### Filter parity for backtesting

- **FR-041**: Backtests run during the scan MUST use the same universe, adjusted-close field, 252-session lookback, strict +50% gate, deterministic rank, top-10 cap, and 252-session rebalance clock as the scan. Adding or removing a filter on only one side is a defect.
- **FR-042**: Recommendations MUST NOT be shown as final until scan-time backtests have finished for every name with valid 252-session history. Insufficient-history and data-failure names are omitted from backtest by rule (not “backtest unavailable” gaps).

#### Technicals tab

- **FR-043**: Stock-detail Technicals, when this strategy is active, MUST show a technical-decision header (signal, eligibility result, strategy name) and all strategy-owned technicals: 252-session momentum, close on T, close on T−252, rank among eligible, gate pass/fail, selection flag, and rebalance-clock context (warmup / mid-cycle / rebalance, sessions remaining).
- **FR-044**: Technicals MUST NOT present RSI, moving-average structure, average true range, volume multiple, relative strength, or sector rotation as decision inputs for this strategy.
- **FR-045**: Missing momentum MUST render as unavailable, never as zero.

#### Backtest tab and reporting metrics

- **FR-046**: Stock-detail Backtest MUST present headline metrics (total return, compounded annual growth, max drawdown, win rate, trade count, profit factor, and average trade when available), equity curve, optional benchmark overlay, drawdown chart, monthly return grid, trade log, best trade, worst trade, and top winning / losing trades. The detail tab MAY offer 1Y / 3Y / 5Y / All chart windows; those toggles do not change the scan-level 1-year Top 5 / Least 5 ranking.
- **FR-047**: A “trade” is one symbol from entry fill to exit fill. A name sold and rebought in a later cohort is two trades. For the 1-year boards only, a still-open book position is included as one marked trade (FR-055) and is not omitted until the next rebalance.
- **FR-048**: Required book-level metrics on the marked equity curve: total return, compounded annual growth using calendar days and 365.25, max drawdown, Calmar (growth ÷ |max drawdown|), win rate, average trade, profit factor, exposure (fraction of sessions with at least one holding), hold days, and excess versus NIFTY 500 over the same window.
- **FR-049**: Default historical cost model for the canonical book is 25 basis points per side. Mode B comparison SHOULD use the published NSE delivery fee breakdown. Selection MUST NOT depend on tax. The product SHOULD report both pre-tax and after-tax equity when tax view is enabled.
- **FR-050**: Live recommended starting capital is configurable, default 1,00,000 Indian rupees.

#### Data quality, safety, and disclosure

- **FR-051**: If only a current (not point-in-time) NIFTY 500 list is available historically, results MUST be labelled survivorship-biased.
- **FR-052**: Known limitations MUST be disclosed on the strategy’s Scanner / Backtest surfaces: survivorship of the published path, look-ahead if replay fills at the same close used to rank, no stop (a name can lose most of its value inside the year), historically deeper drawdown than NIFTY 500, 10-name concentration, full annual turnover even when a leader remains a leader, and that past compounded growth is not a forecast.
- **FR-053**: System MUST never open a short, never buy a name with undefined momentum, and never place live entries during WARMUP.
- **FR-054**: Access to Scanner and this strategy’s results MUST follow the existing authentication and feature-permission model. Unauthenticated access is forbidden.

### Key Entities

- **Long-Term Buy & Hold Momentum Strategy**: Calendar-rebalance, long-only, cross-sectional momentum book identified as `17_long_term_mom`.
- **Shared Trading Session**: One NSE cash-equity / NIFTY 500 session date on the master calendar.
- **Adjusted Close**: Corporate-action-adjusted official close used for momentum, rank, marks, and replay fills.
- **Momentum_252**: Total return over 252 shared sessions.
- **Eligibility Result**: Pass/fail of the defined-and-strictly-greater-than-+50% gate plus data completeness.
- **Selection Set**: Up to 10 eligible names after deterministic rank.
- **Rebalance Clock**: Warmup of 252 sessions, then fire every 252 sessions; persisted `sessions_since_rebalance` and `last_rebalance_date`.
- **Holdings Book**: Map of symbol to shares, average cost, entry date, and entry session; fully liquidated on each rebalance.
- **Scan Run**: One evaluation of the universe for this strategy, including filter outcomes and backtests.
- **Recommendation Row**: Rank, symbol, signal (BUY / WATCH / REJECT), momentum, weight/notional when selected, and link to detail.
- **First-Failure Rejection**: Single earliest reason a name left the candidate path.
- **Scan-Time Backtest**: Historical replay using the same filters as the scan, produced before recommendations are shown, for every name with valid 252-session history (including failed-gate and ranked-out names).
- **Top/Least Return Board**: Up to five names ranked by net return of that name’s real top-10 book trades over the last 1 year of completed sessions. Zero-trade names are omitted.
- **Real Book Trade**: A fill that exists because the name was in the selected set on a rebalance. Not a hypothetical single-name signal and not buy-and-hold. For 1-year boards, a still-open book position is marked to the scan session and counted as one trade.
- **Technicals Snapshot**: Strategy-owned indicator values for one symbol on the evaluation session.
- **Backtest Report**: Equity curve, drawdown, monthly returns, blotter, and headline metrics for a name or the book.
- **Limitations Disclosure**: Operator-visible caveats that MUST accompany results.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After this strategy is available, an authorized user can select Long-Term Buy & Hold Momentum on the Scanner and see the strategy name without consulting documentation, in under 30 seconds from opening Scanner.
- **SC-002**: On a completed scan, 100% of recommendation rows are withheld until scan-time backtests finish for every name with valid 252-session history. Insufficient-history and data-failure names are not backtested and never appear on Top 5 / Least 5.
- **SC-003**: 100% of rejected names in a completed scan appear in exactly one Rejection Breakdown first-failure bucket; displayed percents match those counts against the evaluated set within rounding of one tenth of a percent.
- **SC-004**: Given a frozen historical calendar and prices, a replay produces the same six rebalance membership sets listed in Acceptance Fixtures (order inside a cohort need not match).
- **SC-005**: On that same frozen path, a name with momentum of exactly +50% is never selected, and a name with momentum just above +50% is eligible if it ranks in the top 10.
- **SC-006**: After a scan with at least five names that have a positive 1-year **book-trade** return and five that have a non-positive 1-year book-trade return, operators can identify the top 5 winners and least 5 names from the boards without exporting data. Names never selected in that year do not appear. The boards’ period label is the last 1 year of completed sessions.
- **SC-007**: On a Technicals tab for this strategy, every displayed decision tile is a Long-Term Buy & Hold Momentum input; a review checklist finds zero decision tiles for RSI, moving averages, average true range, volume multiple, or sector rotation.
- **SC-008**: On a rebalance-day scan with 15 eligible names, operators see exactly 10 BUY rows (the 10 largest momentums) and the remaining eligible names counted as “ranked outside top 10”.
- **SC-009**: On a mid-cycle scan, operators see zero new BUY rows and can read the sessions remaining until the next rebalance without leaving the Scanner.
- **SC-010**: During warmup, operators see STATUS=WARMUP and zero BUY/WATCH recommendations on 100% of warmup scans.
- **SC-011**: Nine out of ten operators in an acceptance walkthrough can explain, from the Rejection Breakdown and Technicals tab alone, why a given REJECT name was not bought.
- **SC-012**: Backtest and scan eligibility answers never disagree for the same name, session, and dataset (same pass/fail and same first-failure reason).

---

## Assumptions

- Point-in-time NIFTY 500 membership is used when the host can supply it; otherwise the current list may be applied historically and results are labelled survivorship-biased.
- Live fills use the next session’s open / auction; historical replay uses the signal session’s adjusted close, sells before buys.
- Mode A (full cash split across selected names) is the default live and Scanner book. Mode B (10% × 10) is an optional research switch so published comparison numbers can be reproduced.
- Whole shares only in live cash equity; fractional shares allowed only in research replay.
- Full sell-and-rebuy on every rebalance, including names that remain selected. Netting is a future version.
- Tax does not change selection. When a tax view is shown, report both pre-tax and after-tax equity using then-current Indian cash-equity rules.
- Unbuyable selected names are skipped and redistributed in Mode A, left as cash in Mode B.
- Any consistent adjusted-close vendor is acceptable; mixing adjusted and unadjusted series is not.
- A 2026-style intra-year crash does **not** trigger an extra flatten. That would be a different strategy.
- Default research capital is 1,00,000 Indian rupees and is configurable.
- If the app starts mid-cycle without a persisted last rebalance date, it waits until 252 sessions of this run have passed or an operator supplies an override date.
- Paper versus live brokerage adapters are out of scope of the algorithm; the host already owns order routing.
- Long-Term Buy & Hold Momentum appears as its own selectable Scanner strategy (same family of switcher as Production / RE-001 / RE-002 / other strategy badges), not as a silent scoring tweak inside Production.
- Mid-cycle current leaders are shown as WATCH so operators can see the would-be book without treating the day as an execution day.
- Top 5 / Least 5 rank each name by the net return of **that name’s real book trades** over the last 1 year of completed sessions (bought only when selected in the top 10; sold on the next rebalance), **including mark-to-market of any still-open book position** as of the scan session. Today’s REJECT names may appear if they were selected in that window. Names never selected in the window, and names without valid 252-session history, do not appear. The mark is for ranking and display only — it is not a live exit. Stock-detail Backtest may show other windows; the boards stay on 1 year.
- Reference images define layout, hierarchy, and density. Bucket names, indicator tiles, and metrics MUST follow this strategy’s rules rather than copying another strategy’s labels.
- Existing Scanner authentication, feature permissions, paper-trade handoff, and navigation are reused.
- Unused cash earns 0 unless a later clarification adds a sweep rate.

---

## Out of Scope

- Adding a Nifty moving-average or “risk-off” flatten.
- Adding a stop-loss or trailing stop.
- Skipping the annual sale of names that remain in the top 10 (netting).
- Trading derivatives, basket futures, or leveraged funds as a substitute.
- Using 60-day or 20-day momentum (those belong to other strategies).
- A 50% gate on a first-year-only buy-and-hold that never rebalances (that is the other momentum system).
- Optimizing the 0.50 threshold or the 10-name cap as part of implementing this feature.
- Replacing Production, RE-001, or RE-002, or changing their scoring.
- Redesigning the entire Scanner chrome beyond what is required to host this strategy’s switcher, summary, breakdown, boards, recommendations, Technicals, and Backtest.

---

## Acceptance Fixtures

These fixtures are product acceptance tests on a frozen historical calendar (published research window 2019-08-19 through 2026-08-14). They are not live-trading guarantees.

### Formula and clock

- Close 150 vs close-252 of 100 → momentum = 0.50 → **ineligible**.
- Close 150.01 vs close-252 of 100 → **eligible**.
- Missing close 252 sessions earlier → **ineligible**.
- Session 251 of a fresh series → no orders (warmup).
- Session 252 with 15 eligible names → exactly 10 buys, the 10 largest momentums.
- Session 252 with 3 eligible names → Mode A buys 3 at one-third cash each; Mode B buys 3 at 10% equity each and holds 70% cash.
- Session 252 with 0 eligible → no buys, 100% cash, clock still resets.
- Next rebalance is 252 sessions later, not 1 January.
- Mid-cycle → zero live orders.
- Last historical session force-closes leftovers with reason end-of-sample liquidation.

### Published rebalance sessions (membership MUST match)

| Cohort | Rebalance session | Action |
|--------|-------------------|--------|
| 1 | 2020-08-27 | First buy (10 names) |
| 2 | 2021-09-03 | Full liquidate + new 10 |
| 3 | 2022-09-09 | Full liquidate + new 10 |
| 4 | 2023-09-15 | Full liquidate + new 10 |
| 5 | 2024-10-01 | Full liquidate + new 10 |
| 6 | 2025-10-09 | Full liquidate + new 10 |
| End | 2026-08-14 | Historical force-liquidate only |

**2020-08-27**: ADANIGREEN, AFFLE, BSOFT, DEEPAKNTR, DIXON, GRANULES, INDIAMART, LAURUSLABS, NAVINFLUOR, TATACOMM  

**2021-09-03**: ADANIENSOL, ADANIENT, ATGL, CGPOWER, ELECON, JSWENERGY, PGEL, SAREGAMA, TEJASNET, TTML  

**2022-09-09**: ADANIPOWER, ATGL, CGPOWER, CHENNPETRO, ELGIEQUIP, GMDCLTD, JWL, PGEL, SCHAEFFLER, TTML  

**2023-09-15**: APARINDS, FACT, IRFC, JINDALSAW, JSL, JWL, MAZDOCK, RVNL, TARIL, TITAGARH  

**2024-10-01**: GALLANTT, GVT&D, IFCI, INOXWIND, NEULANDLAB, PCBL, PGEL, TARIL, TRENT, WOCKPHARMA  

**2025-10-09**: AIIL, BSE, CARTRADE, FORCEMOT, GABRIEL, GALLANTT, GVT&D, LAURUSLABS, PARADEEP, SYRMA  

Order inside a cohort is not required to match; membership is.

### Published Mode B path (optional comparison switch only)

On the frozen published dataset, Mode B with NSE delivery costs and signal-close fills produced about +1,224.54% total return, +44.74% compounded annual growth, max drawdown about −43.69%, 60 closed trades, 50 unique names, 78.33% win rate, best trade JWL, worst trade ATGL. If only Mode A is implemented, do not compare rupee figures to this path; compare only cohort membership.

---

## Known Limitations (MUST be disclosed in the product)

- Published historical numbers used a 2026 NIFTY 500 list for all history. Dead names are missing; recent listings have short samples.
- Signal-close replay assumes you trade the close just used to rank — look-ahead versus a live trader.
- No stop: a single name can lose most of its value inside the year (example: ATGL about −82%).
- Published max drawdown (about −43.69%) was worse than NIFTY 500 (about −38.30%) and was still open at the end of the sample.
- Ten names, often the same theme. No sector cap.
- Full annual turnover costs even when a name remains a leader.
- Momentum can fail in a factor rotation (sample’s last year was deeply negative while the index was only slightly down).
- Past compounded growth is not a forecast.
