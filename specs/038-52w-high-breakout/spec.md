# Feature Specification: 52-Week High Breakout Scanner

**Feature Branch**: `038-52w-high-breakout`  
**Created**: 2026-08-16  
**Status**: Clarified (session 2026-08-16)  
**Input**: User description: Add a **52-Week High Breakout** button beside Long-Term Buy & Hold Momentum on the Scanner dashboard; open a dedicated 52-Week High Breakout view with its own Run control that starts only this strategy; show Rejection Breakdown, scan-time backtesting before recommendations, top-5 / least-5 return boards, strategy-owned Technicals, and matching Backtest / recommendation layouts. Canonical strategy id: `09_52w_breakout`.

**Business source of truth**: 52-Week High Breakout SPEC-SPECIFY (strategy identity `09_52w_breakout`).  
**Product surfaces**: Scanner dashboard strategy switcher, dedicated 52-Week High Breakout view, isolated Run control, scan-results table, today’s order list, holdings, rejection breakdown, top/least return boards, stock-detail Technicals tab, stock-detail Backtest tab.  
**UI references** (layout and information density, not algorithm): `Rejection BreakDown.png`, `Top 5.png`, `techinicals.png`, `Backtest 1.png`, `backtest 2.png`, `UI Scanner .png`.

This specification locks both the product behaviour on the Scanner dashboard and the strategy rules that drive it. Later clarify / plan / tasks / implement work SHALL implement §§User Stories–Requirements without silently changing the selection math, trail math, or isolated-run contract.

## Clarifications

### Session 2026-08-16

- Q: When a name is already held (not a new BUY today, not exiting), what should its Scan results row show? → A: Distinct **HOLD** signal in Scan results (not BUY, not REJECT). Holdings panel still shows trail state.
- Q: If the operator presses Run again while a 52-Week High Breakout scan is already in progress, what should happen? → A: Ignore / disable the second click; the current run finishes and publishes.
- Q: If some names with valid 252-session history fail their scan-time backtest while others finish, when may recommendations be shown? → A: Publish the scan. Failed names = data-source failure; they are not backtested rows and do not appear on Top 5 / Least 5.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See and Select 52-Week High Breakout Beside Long-Term Momentum (Priority: P1)

As a trader or research operator, I open the Scanner dashboard and see a **52-Week High Breakout** button immediately beside **Long-Term Buy & Hold Momentum**. Selecting it scopes the page to this strategy: the displayed name, subtitle, badge, latest scan, and detail views are 52-Week High Breakout only. I never confuse this book with Production, RE-001, RE-002, Long-Term Buy & Hold Momentum, Buy-and-Hold Top Momentum, Darvas, or an intraday “new 52-week high” scanner.

**Why this priority**: If the strategy is not selectable and named, none of the isolated run, scan, backtest, or recommendation work is usable.

**Independent Test**: Open Scanner, confirm the 52-Week High Breakout button sits beside Long-Term Buy & Hold Momentum, select it, and confirm the displayed strategy name and that scan results, summary cards, and detail views are scoped to this strategy only.

**Acceptance Scenarios**:

1. **Given** an authenticated user with Scanner access, **When** they open the Scanner dashboard, **Then** a button labelled **52-Week High Breakout** is visible beside **Long-Term Buy & Hold Momentum**, and selecting it updates the visible strategy name.
2. **Given** 52-Week High Breakout is selected, **When** the latest scan for that strategy exists, **Then** the page subtitle / badge shows **52-Week High Breakout** (not Production, not Long-Term Buy & Hold Momentum) and scan counts belong to this strategy.
3. **Given** another engine or strategy is selected after viewing 52-Week High Breakout, **When** the user switches back via the 52-Week High Breakout button, **Then** they again see this strategy’s name and its own latest scan — not another engine’s recommendations.

---

### User Story 2 - Isolated Run Starts Only 52-Week High Breakout (Priority: P1)

As a trader, I open the 52-Week High Breakout view and use **its own Run button**. That control starts **only** the 52-Week High Breakout evaluation. It does not start Long-Term Buy & Hold Momentum, Production, RE-001, RE-002, or any other strategy. Conversely, running those other strategies does not start this one.

**Why this priority**: The operator explicitly requires this book to be a separate strategy with a separate run. A shared “run everything” action would mix books and destroy trust.

**Independent Test**: From the 52-Week High Breakout view, press Run while other strategies have previous results; confirm only this strategy enters a running state and only this strategy’s results change when the run finishes.

**Acceptance Scenarios**:

1. **Given** 52-Week High Breakout is the active Scanner view, **When** the operator presses that view’s Run control, **Then** only `09_52w_breakout` starts; other strategies remain idle and their latest results are unchanged.
2. **Given** a Long-Term Buy & Hold Momentum (or Production / RE-001 / RE-002) run is started from that other view, **When** it completes, **Then** the 52-Week High Breakout latest scan, boards, and holdings are unchanged.
3. **Given** a 52-Week High Breakout run is in progress, **When** the operator stays on that view, **Then** progress copy refers to 52-Week High Breakout only (not a multi-strategy batch).
4. **Given** the operator is not on the 52-Week High Breakout view, **When** they look at that view later, **Then** they can still see this strategy’s last completed run without it having been overwritten by another strategy’s run.
5. **Given** a 52-Week High Breakout run is already in progress, **When** the operator presses that view’s Run control again, **Then** the second click is ignored or the control is disabled; the in-flight run is not cancelled, a second 52-Week High Breakout run does not start, and the current run still publishes when it finishes.

---

### User Story 3 - Scan Runs Backtest Before Recommendations Appear (Priority: P1)

As a trader, I run a 52-Week High Breakout scan and do **not** see a recommendation list until every name with valid 252-session history has a **terminal** scan-time backtest (completed successfully or failed), using **the same eligibility filters** as the scan. Names that failed today’s close/volume/market gates or missed a free slot are still backtested. Names that lack history or failed data checks up front are excluded from backtest. A backtest that errors or times out is a data-source failure for that name: it does not appear on Top 5 / Least 5, and it does **not** block publishing the rest of the scan.

**Why this priority**: The user explicitly requires backtesting during the scan, before recommendations are shown, and filter parity between scan and backtest.

**Independent Test**: Start a 52-Week High Breakout scan from this strategy’s Run control; observe that recommendation rows stay hidden (or the results table remains in a “scanning / backtesting” state) until backtests complete for every name with valid 252-session history; then recommendations appear with backtest-linked ranking data.

**Acceptance Scenarios**:

1. **Given** the operator starts a 52-Week High Breakout scan, **When** evaluation is still running or any name with valid 252-session history has an unfinished (not yet succeeded or failed) backtest, **Then** the recommendations table is not presented as final (no premature BUY list).
2. **Given** the scan finishes evaluation and every history-valid backtest has succeeded or failed, **When** results render, **Then** every name whose backtest succeeded has a completed backtest for the scan window, and the scan is published even if some backtests failed.
3. **Given** a name fails for insufficient 252-session high history, missing/invalid close, high, or volume, or data-source failure (including a backtest error or timeout), **When** the run publishes, **Then** that name is **not** a completed-return row, is excluded from Top 5 / Least 5, and is counted as a data-source failure when the failure is the backtest or an up-front data check.
4. **Given** a name has valid 252-session history but failed today’s close-versus-prior-high gate, volume gate, market filter, same-day-rebuy rule, or ranked outside the free slots, **When** backtesting runs and succeeds, **Then** that name still receives a completed backtest under the same strategy rules. It appears on Top 5 / Least 5 only if it had at least one real book trade in the last 1 year.
5. **Given** the operator compares scan filters to backtest filters for this strategy, **When** they inspect the run, **Then** universe, 252-session prior high, volume-versus-20-session-average, market-regime (benchmark above its 50-session average), 10-name / 10% slot book, 60-session rank key, and 3-average-true-range trailing stop are identical — no Darvas box, 2× volume, relative-strength, earnings, or sector filter is introduced on either side.
6. **Given** three history-valid names succeed their backtests and two fail, **When** the last of those five jobs terminates, **Then** recommendations, HOLD rows, today’s order list, and boards for the successful names are published; the two failed names increment data-failure, are omitted from Top 5 / Least 5, and do not keep the whole run incomplete.

---

### User Story 4 - Read Recommendations, Orders, and Holdings After the Scan (Priority: P1)

As a trader, after a completed 52-Week High Breakout scan I see: (1) a recommendation table in the existing Scanner results layout; (2) today’s order list with trailing-stop exits first, then ranked new entries into free 10% slots; (3) current holdings with trail state. Selected new names are BUY. Names that remain open after today’s trail evaluation (not a new BUY this session) are **HOLD**. Buy-signal names that did not get a slot, and market-off would-be names, are WATCH. Failed new-entry names are REJECT. HOLD is not a rejection.

**Why this priority**: Recommendations are the primary output of the Scanner.

**Independent Test**: Complete a scan with at least one new entry, one rejected name, and one held name; verify table columns, signals, empty-state copy, and that exits appear before new buys in the order list.

**Acceptance Scenarios**:

1. **Given** a completed scan on a session where the market filter is on and free slots exist, **When** the operator opens Scan results, **Then** names actually taken into free slots show signal BUY, ranked by 60-session return descending, ticker ascending on ties.
2. **Given** more buy-signal names than free slots, **When** results render, **Then** only the highest-ranked prefix equal to the number of free slots is BUY; the remainder of today’s buy-signal names show WATCH and are counted as “buy signal, no free slot”.
3. **Given** the market filter is off, **When** results render, **Then** there are zero new BUY rows, names that remain open show HOLD (and may also appear as EXIT in the order list if the trail was hit), and names that would have passed the stock-level gates show WATCH with a market-filter block.
4. **Given** a completed scan with zero new entries, **When** results render, **Then** an explicit empty or completed-without-buys banner states that the scan finished and no name received a new slot (no fake BUY list). Still-open names still show HOLD.
5. **Given** any completed scan, **When** the operator views the scan summary strip, **Then** they see totals for universe size, data-valid count, evaluated count, final candidates, BUY, HOLD, REJECT, and data failures, plus book status (warmup / market-off / active), free slots, and whether the market filter is on.
6. **Given** at least one open holding whose close is below the trailing stop and whose entry session is not today, **When** the order list renders, **Then** that name appears as an EXIT before any new BUY, with reason “trailing stop”, and its Scan results signal is **not** HOLD (the position is closed this session).
7. **Given** a name that remains open after today’s trail evaluation and was not a new BUY this session, **When** Scan results render, **Then** that row shows signal **HOLD**, appears in the same table as BUY / WATCH / REJECT, and is omitted from Rejection Breakdown.

---

### User Story 5 - Understand Why Names Were Rejected (Priority: P1)

As a trader, I expand a **Rejection Breakdown** section on the 52-Week High Breakout Scanner view and see first-failure counts for this strategy only. The layout matches the reference card grid (label, count, percent of evaluated, “First failure”), but the buckets are 52-Week High Breakout reasons — not Long-Term Momentum’s +50% gate and not another strategy’s relative-strength / consolidation / breakout gates.

**Why this priority**: Operators cannot trust a 10-name book unless they can see where the rest of the universe died.

**Independent Test**: Complete a scan that produces mixed failure reasons; confirm each rejected name increments exactly one first-failure bucket and percents sum consistently with the evaluated set.

**Acceptance Scenarios**:

1. **Given** a completed 52-Week High Breakout scan, **When** the operator expands Rejection Breakdown, **Then** they see first-failure cards for at least: not in investable universe; insufficient historical data (prior 252-session high undefined); missing or invalid close, high, or volume; close below the prior 252-session high; volume not above the 20-session average; market filter off; sold today (same-day rebuy blocked); buy signal but no free slot; data-source failure; and other.
2. **Given** a name fails both “insufficient history” and “volume not above average”, **When** counts are computed, **Then** it is counted only in the earliest first-failure bucket (not double-counted).
3. **Given** the operator compares this section to Long-Term Buy & Hold Momentum or another strategy’s breakdown, **When** 52-Week High Breakout is selected, **Then** they do **not** see that other strategy’s gates (252-session +50% momentum, relative-strength percentile, consolidation maturity, base width, Darvas box, sector rotation, 2× volume) as decision buckets.
4. **Given** a name remains open after today’s trail evaluation and is not a new BUY, **When** Rejection Breakdown is built, **Then** that name is **not** counted as a rejection (Scan results signal is HOLD, not a failed candidate).

---

### User Story 6 - Review Top 5 and Least 5 Backtest Returns (Priority: P2)

As a trader, after the scan I see two boards: the **top 5** names with the highest **positive** completed backtest returns, and the **least 5** names with the lowest completed backtest returns, both over the **last 1 year of completed sessions**. Boards use the reference table (rank, symbol, signal, return, trades, win rate, max drawdown, profit factor) and remain honest when fewer than five names qualify.

**Why this priority**: Post-scan ranking by realized backtest return is an explicit product request and helps operators challenge the live 10-name book.

**Independent Test**: Complete a scan whose 1-year backtests include at least six positive and six negative names with real book trades; verify the two boards, the 1-year period label, sort order, and exclusion of incomplete backtests.

**Acceptance Scenarios**:

1. **Given** a completed scan with more than five names that each had at least one real book trade in the last 1 year and a **positive** net return on those trades, **When** the Top 5 board renders, **Then** it shows exactly five rows sorted by that 1-year net return descending, including today’s REJECT names if those returns are the highest, and the period label is the last 1 year of completed sessions.
2. **Given** a completed scan with more than five names that each had at least one real book trade in the last 1 year, **When** the Least 5 board renders, **Then** it shows the five lowest 1-year net returns (most negative or smallest), same columns, independent of today’s BUY / HOLD / WATCH / REJECT.
3. **Given** fewer than five names have a positive 1-year book-trade return, **When** Top 5 renders, **Then** it shows only those names and does not pad with zero or negative returns.
4. **Given** a name was never selected in the last 1 year (zero real book trades in the window), **When** boards are built, **Then** that name is excluded even if its scan-time backtest job finished with an empty blotter.
5. **Given** the operator opens a name’s Backtest tab, **When** they change the chart window to 3Y / 5Y / All, **Then** the scan-level Top 5 / Least 5 boards stay on the fixed 1-year ranking and do not re-sort.
6. **Given** a name is still held, **When** boards are built, **Then** that open position’s mark-to-market at the scan session is included in the 1-year return and trade count; the system does not invent a live exit from that mark.

---

### User Story 7 - Inspect Strategy-Owned Technicals for a Name (Priority: P2)

As a trader, I open a scanned name and use the **Technicals** tab to see every technical input this strategy actually uses to decide eligibility, rank, trail, and selection — not Production / RE-001 / RE-002 / Long-Term Momentum indicators that this strategy does not use as decision inputs.

**Why this priority**: Showing another engine’s bands, multi-timeframe tiles, or 252-session +50% gate would mis-explain a close-based 52-week breakout with a 3-average-true-range trail.

**Independent Test**: Open a BUY, a volume-failed REJECT, a market-off WATCH, a current HOLD, and an insufficient-history REJECT; confirm the Technicals tab shows 52-Week High Breakout fields and the correct pass/fail state.

**Acceptance Scenarios**:

1. **Given** a selected or evaluated name, **When** the operator opens Technicals, **Then** they see a technical-decision header (signal badge, eligibility / hard-filter result, strategy name **52-Week High Breakout**) and tiles for: close on the signal session, prior 252-session high, close-versus-prior-high result, session volume, 20-session volume average, volume-versus-average result, 14-session average true range (simple average of true range, not Wilder), 60-session rank key, rank among today’s buy-signal names, market-filter result (benchmark close versus its 50-session average), and slot status (taken / no slot / held / sold today).
2. **Given** the name is currently held, **When** Technicals renders, **Then** they also see high-water mark (highest close since entry), current trailing stop, and whether today’s close would exit.
3. **Given** a name that failed the volume gate, **When** Technicals renders, **Then** volume and the 20-session average are shown as numbers, the volume tile is failed, and the name is not marked selected.
4. **Given** a name with missing 252-session high history, **When** Technicals renders, **Then** the prior-high tile is unavailable (not zero) and the first-failure reason is insufficient history.
5. **Given** 52-Week High Breakout is the active strategy, **When** Technicals renders, **Then** RSI, stock moving-average stack, Bollinger bands, Darvas box, Mansfield / sector relative strength, earnings blackout, and a 252-session +50% momentum gate are **not** presented as decision inputs.

---

### User Story 8 - Inspect Per-Name and Book Backtest on the Detail Tab (Priority: P2)

As a trader, I open the **Backtest** tab on a scanned name and see the reference backtest workspace: headline metrics, equity vs benchmark, drawdown, monthly returns, trade log, best/worst trade, and top winning / losing trades. The path uses the same filters, slot book, and trailing-stop rules as the scan.

**Why this priority**: Backtest is the evidence layer that must exist before the operator acts on a recommendation.

**Independent Test**: Open Backtest for a name that appeared in at least one historical book trade and for a name that never qualified; verify metrics, empty states, and filter parity.

**Acceptance Scenarios**:

1. **Given** a name with at least one completed historical book trade, **When** Backtest opens, **Then** the operator sees total return, compounded annual growth, max drawdown, win rate, trade count, profit factor, equity curve, drawdown chart, monthly return grid, last trades, best trade, and worst trade.
2. **Given** the operator views the equity chart, **When** a benchmark series is available, **Then** they can compare strategy equity to NIFTY 500 buy-and-hold over the same window.
3. **Given** a name never received a 10% slot under this strategy, **When** Backtest opens, **Then** the tab shows zero strategy trades for this name (or an explicit “never selected” state) rather than inventing another strategy’s trades.
4. **Given** the scan-level book backtest exists, **When** the operator reviews scan summary or detail, **Then** they can see that exits fire only on the trailing stop (or historical end-of-sample liquidation), that the market filter blocks new buys without flattening, and that new entries fill only free 10% slots.

---

### User Story 9 - Trust Warmup, Market-Off, Trail State, and Disclosed Limits (Priority: P3)

As a trader, I can see whether the book is in warmup, market-off, or active; I can see persisted trail-stop state; and I am shown the strategy’s known limits (gap-through risk, state-not-cross entries, survivorship, past performance is not a forecast) so I do not treat the Scanner as a guaranteed live edge.

**Why this priority**: Misreading a market-off day as an order day, flattening because the index dipped, or hiding a name that gapped through the trail would be a product defect.

**Independent Test**: Load a warmup-only dataset, a market-off snapshot with open holdings, and an active breakout day; confirm status labels, zero new buys when market-off, continued trail exits, and the limitations disclosure.

**Acceptance Scenarios**:

1. **Given** fewer than 252 shared trading sessions of history exist, **When** a scan runs, **Then** status is WARMUP, no BUY entries are emitted, and the rejection/empty copy explains insufficient history.
2. **Given** the benchmark close is not strictly above its 50-session average, **When** the dashboard renders, **Then** status is MARKET_OFF, new BUY count is zero, existing holdings still update high-water mark / trailing stop and may EXIT, and the book is **not** flattened solely because the market filter turned off.
3. **Given** the app restarts with open holdings, **When** the operator opens 52-Week High Breakout, **Then** each holding’s high-water mark and trailing stop match the last persisted values (the stop is not silently lowered).
4. **Given** any 52-Week High Breakout result view, **When** the operator reads the strategy context, **Then** they can see that entry is close-based (not an intraday high print), that the trail can be gapped through, that win rate is historically below 50% with payoff carrying the edge, and that published historical performance is not a live guarantee.

---

### Edge Cases

- **Close exactly equal to the prior 252-session high**: the price leg passes (`>=`).
- **Intraday high above the prior 252-session high, close below it**: not an entry.
- **Volume exactly equal to the 20-session average**: the volume leg fails (must be strictly greater).
- **Benchmark close exactly equal to its 50-session average**: market filter is off; no new buys; existing names still trail.
- **Buy signal is a state, not a first-print event**: if a name stays at or above the rolling prior high with confirming volume for 10 sessions, it is a candidate on each of those 10 sessions until a free slot takes it.
- **No exit on the entry session**, even if a synthetic trail would be pierced.
- **Close equal to the trailing stop**: not an exit (exit is strictly below).
- **Intraday low pierces the trail and the close recovers to at or above the trail**: not an exit.
- **Trail never decreases**: a new closing high with an expanded average true range cannot lower the stop.
- **No new closing high**: the trail is unchanged even if average true range shrinks.
- **Average true range missing on the entry bar**: initial stop is 10% below entry; later updates use live average true range only on a new closing high.
- **Name sold today**: cannot be rebought the same session even if the close is still at or above the prior high.
- **Book already has 10 names**: zero new buys, even if 20 names signal; those names are WATCH, not queued for a later slot unless they still signal tomorrow.
- **Fewer than 10 buy-signal names**: buy all of them at 10% of equity each; leftover cash remains cash.
- **Zero buy-signal names**: no new buys; holdings continue; rejection breakdown still populated.
- **Market filter turns off**: do **not** flatten; only the trail (or a later delisting) exits.
- **Held name missing today’s print**: do not update high-water mark or trail; do not exit; carry last mark; retry on the next print.
- **Name delisted while held**: exit at last available print immediately.
- **Selected name cannot be bought (halt, ban, no auction)**: skip it; take the next-ranked still-valid name into that 10% slot.
- **Last session of a historical test**: force-close remaining names at that session’s close for reporting only (reason end-of-sample liquidation). Live trading does not invent an extra liquidation day.
- **Process restart**: persisted cash, holdings, high-water marks, trailing stops, fill model, pending orders, and last processed session survive. Recalculating the stop from only today’s close is a defect.
- **Scan still running**: recommendations, top/least boards, and rejection percents are not shown as final.
- **Insufficient-history or data-failure name**: not backtested (or backtest did not complete); not a Top 5 / Least 5 candidate; first-failure remains the data reason.
- **Scan-time backtest error or timeout** on a history-valid name: treat as data-source failure for that name; exclude from Top 5 / Least 5; do **not** block publishing the rest of the scan. Today’s BUY / HOLD / WATCH / EXIT from the evaluation step is not cancelled solely because that name’s historical replay failed.
- **History-valid but rejected or skipped today**: still backtested. Appears on Top 5 / Least 5 only if it had at least one real book trade in the last 1 year.
- **Never selected in the last 1 year**: scan-time backtest may finish with zero strategy trades; excluded from Top 5 / Least 5 (not treated as 0% return).
- **Still-open holding**: Scan results signal is **HOLD** (not BUY, not REJECT). Counts toward that name’s 1-year board return via mark-to-market at the scan session’s adjusted close (or last available mark if that session has no print). HOLD names are omitted from Rejection Breakdown.
- **Holding that exits today**: order-list signal is EXIT; Scan results signal is **not** HOLD. If the name would otherwise buy-signal, first-failure is sold today (same-day rebuy blocked).
- **Buy-and-hold or isolated single-name replay**: MUST NOT be used as the board return. Boards use only this name’s fills from the true 10-slot book.
- **Fewer than five names with a positive 1-year book-trade return**: Top 5 shows the smaller set; does not fabricate rows.
- **Survivorship-only universe (current list applied to all history)**: results MUST be labelled survivorship-biased and MUST NOT be claimed as a production live book.
- **Corporate-action-unadjusted prices**: forbidden. Splits would fabricate or destroy 52-week highs.
- **Confusion with other books**: this is not Darvas (no box), not Mansfield tight-base, not Long-Term Buy & Hold Momentum (no 252-session return gate, no annual rebalance), and not an intraday 52-week-high scanner (close, not high).
- **Another strategy’s Run control**: MUST NOT start this strategy; this view’s Run control MUST NOT start any other strategy.
- **Second Run while this strategy is already scanning**: ignore or disable the second click. Do not cancel the in-flight run. Do not start a second 52-Week High Breakout evaluation. Do not queue a follow-on run. The in-flight run publishes when it finishes.

---

## Requirements *(mandatory)*

### Functional Requirements

#### Strategy identity and scanner presence

- **FR-001**: System MUST register 52-Week High Breakout as a distinct Scanner strategy with display name **52-Week High Breakout**, short name **52W**, and stable id `09_52w_breakout`.
- **FR-002**: Users MUST be able to select this strategy from a button labelled **52-Week High Breakout** placed immediately beside the **Long-Term Buy & Hold Momentum** control on the Scanner dashboard, and MUST see the display name in that button, the page subtitle, and the stock-detail badge.
- **FR-003**: System MUST NOT confuse this strategy with Long-Term Buy & Hold Momentum, Buy-and-Hold Top Momentum, Darvas box books, Mansfield tight-base, Production, RE-001, RE-002, or an intraday “printed a new 52-week high” scanner.
- **FR-004**: This strategy MUST be long-only Indian cash equities. The default market-filter and reporting benchmark MUST be NIFTY 500. The benchmark MUST change only the market-regime entry gate and reporting, never ranking, stops, or universe membership. A NIFTY 50 research switch MAY exist; it MUST NOT be the default.

#### Isolated run contract

- **FR-005**: The 52-Week High Breakout view MUST provide its own Run control.
- **FR-006**: Activating that Run control MUST start evaluation, scan-time backtests, and result publication for `09_52w_breakout` only.
- **FR-007**: Activating that Run control MUST NOT start Long-Term Buy & Hold Momentum, Production, RE-001, RE-002, or any other strategy.
- **FR-008**: Starting any other strategy’s run MUST NOT start, cancel, or overwrite 52-Week High Breakout results.
- **FR-066**: While a 52-Week High Breakout run is in progress, a further activation of this strategy’s Run control MUST be ignored or the control MUST be disabled. The system MUST NOT cancel the in-flight run, MUST NOT start a second 52-Week High Breakout evaluation, and MUST NOT queue another run. The in-flight run MUST continue and MUST publish when it finishes.

#### Universe, calendar, and prices

- **FR-009**: Investable universe MUST be NIFTY 500 cash-equity constituents on the evaluation session.
- **FR-010**: The master calendar MUST be NIFTY 500 index trading sessions (or NSE cash-equity sessions if the index print is missing). All lookbacks (252, 50, 20, 14, 60) count **sessions on this calendar**, not calendar days. “52-week” in this product means 252 trading sessions, not 365 calendar days.
- **FR-011**: A name is in the candidate set on session T only if all of the following hold: it is treated as a NIFTY 500 constituent as of T; it has a valid adjusted close, high, and volume on T; the prior 252-session high is defined (252 valid highs ending on T−1); the 20-session volume average is defined and finite; average true range is defined and finite **or** the published missing-average-true-range fallback in FR-029 is applied; the name is not already held; the name was not sold on session T.
- **FR-012**: The 52-week level MUST use corporate-action-adjusted high. Breakout test, marks, trail close-reference, ranking, and historical replay fills MUST use corporate-action-adjusted close. Volume is session share volume. Average true range uses adjusted high, low, and previous adjusted close. Unadjusted prices MUST NOT be used. Mixing adjusted close with unadjusted high is a defect.
- **FR-013**: Stock series MUST align to the master calendar. A missing stock print is treated as missing for that name that day and MUST NOT be invented solely to force a breakout.

#### Core formulas and entry

- **FR-014**: Prior 252-session high on T MUST be the maximum adjusted high over the 252 sessions ending on T−1 (today’s high is excluded). A window with fewer than 252 valid highs is undefined.
- **FR-015**: 20-session volume average on T MUST be the mean of volume over the 20 sessions ending on T (today is included). The volume gate is **today’s volume strictly greater than** that average.
- **FR-016**: 14-session average true range MUST be the simple average of true range over the 14 sessions ending on T (today included). True range is the maximum of (high − low), absolute(high − previous close), and absolute(low − previous close). Wilder / smoothed average true range MUST NOT be used.
- **FR-017**: Market filter is on if and only if the benchmark close is **strictly greater** than its 50-session simple average (today included). Equal-to-average is off.
- **FR-018**: 60-session rank key MUST be (close on T ÷ close 60 sessions earlier) − 1. It ranks candidates when free slots are fewer than buy signals. It is **not** an entry gate. A missing rank key is treated as last in line.
- **FR-019**: A buy signal on T is true if and only if the market filter is on **and** adjusted close ≥ prior 252-session high **and** volume > 20-session volume average **and** close is finite and greater than zero **and** the prior high and volume average are defined.
- **FR-020**: The buy signal is a **level / state**, not a first-print cross. A name that remains at or above the rolling prior high with confirming volume remains a candidate every such session until a free slot takes it (subject to FR-011).
- **FR-021**: This strategy MUST NOT require RSI, stock moving averages, exponential moving averages, Bollinger bands, Darvas box top/bottom, Mansfield or sector relative strength, earnings calendars, a 2× or 5× volume multiple, or a 252-session +50% return gate in order to fire.

#### Position lifecycle and trailing stop

- **FR-022**: No new entries before session index 252 (WARMUP). Until then the Scanner MUST show STATUS=WARMUP and MUST NOT emit BUY entries.
- **FR-023**: On every session after warmup, the book MUST process in this order: (1) update high-water mark / trailing stop and queue trail exits for holdings whose entry session is not today; (2) execute exits and credit cash; (3) mark equity; (4) if the market filter is on and free slots exist, rank remaining buy-signal names and fill free slots; (5) persist state.
- **FR-024**: Opening a position sets high-water mark to the fill and trailing stop to fill minus three times that session’s average true range. High-water mark is the highest **close** since entry, not the highest high.
- **FR-025**: On later sessions with a valid close, if close is strictly above the high-water mark and average true range is defined, the high-water mark becomes that close and the trailing stop becomes the greater of the previous stop and (close − 3 × average true range). The stop MUST never decrease.
- **FR-026**: Exit when close is **strictly below** the trailing stop. Reason is trailing stop. An intraday pierce that closes at or above the stop does not exit. Close equal to the stop does not exit.
- **FR-027**: The system MUST NOT exit a name on its entry session. It MUST NOT rebuy a name sold on the same session. It MUST NOT add to an existing name. Newly freed slots MAY be filled the same session by **other** names.
- **FR-028**: Live positions MUST NOT be exited by take-profit, time stop, market filter turning off, stock moving-average cross, index-crash flatten, or earnings. Historical tests MUST force-liquidate remaining names on the last sample session at that session’s last available adjusted close (reason end-of-sample liquidation). Live trading MUST NOT invent an extra liquidation day.
- **FR-029**: If average true range is missing on the entry bar, the initial stop MUST be 90% of the entry price. Once average true range exists, the trail updates only on a new closing high.
- **FR-030**: A held name with no close today MUST NOT update high-water mark or trailing stop and MUST NOT exit that session; last mark is carried. A delisted held name MUST be exited at the last available print immediately.

#### Portfolio construction and execution

- **FR-031**: Default live / Scanner book (canonical published book): each new buy is 10% of **current equity** (cash plus marked holdings), maximum 10 names, one name per slot. If fewer than 10 names qualify, residual cash stays cash. If more buy-signal names exist than free slots, only the highest 60-session-return names (ticker ascending on ties) get the slots. Unused cash earns 0 on the published historical path.
- **FR-032**: Gross exposure MUST NOT exceed 100% of equity except microscopic rounding. Shorts, leverage, pyramiding, and futures/options substitutes are forbidden.
- **FR-033**: Live India cash equity MUST use whole shares only; leftover rupees stay cash. Research replay MAY allow fractional shares.
- **FR-034**: Historical replay fills MUST use the signal session’s adjusted close, exits before entries. Live recommended fill is the next session’s open / auction after the official close is known.
- **FR-035**: If a ranked name cannot be bought, skip it and take the next-ranked still-valid name into that slot. Do not silently leave the slot empty when a valid substitute exists.
- **FR-036**: A valid buy signal that misses a slot is not queued as a stale “enter later” memory. Because the signal is a state, the name may fire again tomorrow if the three legs are still true.

#### Scanner run contract

- **FR-037**: A 52-Week High Breakout scan MUST evaluate the investable universe with FR-009–FR-021, then run a scan-time backtest for **every name that has valid 252-session history** using those **same** filters (FR-049), and only then publish the recommendation list. Names that failed today’s close, volume, or market gates, or that missed a free slot, MUST still be backtested. Names that lack 252-session high history or failed data checks up front MUST NOT be backtested.
- **FR-038**: On an active session the Scanner MUST emit BUY for each name actually taken into a free slot, with rank, close, prior 252-session high, volume versus average, 60-session rank key, target weight (10% of equity), target notional, initial trailing stop, and average true range, plus EXIT orders for every holding whose close is strictly below its trailing stop.
- **FR-039**: When the market filter is off, the Scanner MUST NOT emit new BUY entries. Existing holdings MUST still be marked, MUST show HOLD if they remain open, and MAY emit EXIT. Names that pass the stock-level close and volume legs MAY appear as WATCH with a market-filter block. The book MUST NOT be flattened solely because the market filter turned off.
- **FR-040**: Scan summary MUST report total names, data-valid count, evaluated count, final candidates, BUY count, HOLD count, REJECT count, data-failure count, book status (WARMUP / MARKET_OFF / ACTIVE), market-filter state, number of holdings, cash, equity, and free slots.
- **FR-065**: Scan results MUST show signal **HOLD** for every name that remains open after today’s trail evaluation and was not a new BUY this session. HOLD rows stay in the same Scan results table as BUY / WATCH / REJECT. A name that EXITs this session MUST NOT show HOLD. A new BUY this session stays BUY (not HOLD) even though the position is now open. HOLD MUST NOT be treated as a rejection.
- **FR-041**: If zero names receive a new slot, the Scanner MUST show an explicit completed-without-new-buys state rather than a blank table presented as success-with-buys.
- **FR-042**: The persisted evening snapshot for this strategy MUST include session date, status, market-filter state, benchmark close and 50-session average, holdings with shares, entry date, entry price, high-water mark, trailing stop, and unrealized percent, today’s exits, all buy-signal candidates (even if no slot), actual entries, and buy-signal names skipped because the book was full.

#### Rejection breakdown

- **FR-043**: Scanner MUST present a collapsible Rejection Breakdown section in the reference card-grid layout (bucket name, count, percent of evaluated, first-failure caption).
- **FR-044**: First-failure buckets for this strategy MUST include at least: not in investable universe; insufficient historical data (prior 252-session high undefined); missing or invalid close, high, or volume on T; close below the prior 252-session high; volume not strictly above the 20-session average; market filter off; sold today (same-day rebuy blocked); buy signal but no free slot; data-source failure; other.
- **FR-045**: Each rejected name MUST increment exactly one first-failure bucket (earliest failing rule). Percents are of the evaluated set. HOLD names (still open, not a new BUY) MUST NOT be counted as rejections.
- **FR-046**: Rejection Breakdown MUST NOT reuse another strategy’s gate names (including Long-Term Momentum’s +50% gate, Darvas box, relative-strength percentile, consolidation maturity, base width, sector rotation, or 2× volume) as if they were this strategy’s rules.

#### Top 5 / least 5

- **FR-047**: After a completed scan, Scanner MUST show Top 5 Positive Backtest Returns over the **last 1 year of completed sessions** (fixed window): up to five names whose **real book trades** in that window have a **positive** net return, sorted by that return descending. A “real book trade” is an entry created because the name received a 10% slot in this strategy’s book (not an isolated single-name signal and not buy-and-hold). The 1-year net return MUST include (1) closed book trades whose hold overlaps the window and (2) mark-to-market of any still-open book position as of the scan session. Columns: rank, symbol, signal, return, trades, win rate, max drawdown, profit factor. The period (start date → end date) MUST be visible.
- **FR-048**: After a completed scan, Scanner MUST show Least 5 Backtest Returns over the **same fixed last-1-year window**: up to five names with at least one real book trade in that window and the lowest net returns on those trades, same columns. Names with zero book trades in the window, insufficient history, or data failure are excluded (not ranked as 0%). Isolated single-name replays and plain buy-and-hold MUST NOT be used. Changing the stock-detail Backtest window MUST NOT re-rank these boards.
- **FR-061**: For board metrics, an open book position is marked at the scan session’s adjusted close (carry last mark if that session has no print). Trade count includes that open position as one trade. Win rate treats the marked-open position as one outcome (win if marked return > 0). Live trading MUST NOT invent an exit order from this mark.

#### Filter parity for backtesting

- **FR-049**: Backtests run during the scan MUST use the same universe, adjusted high/close/volume fields, prior 252-session high, volume-versus-20-session-average, simple 14-session average true range, NIFTY 500 50-session market filter, 10% × 10 slot book, 60-session rank key with ticker tie-break, 3-average-true-range trailing stop, no-same-day-rebuy, no-exit-on-entry-bar, and no-market-off-flatten rules as the scan. Adding or removing a filter on only one side is a defect.
- **FR-050**: Recommendations MUST NOT be shown as final until every name with valid 252-session history has a **terminal** scan-time backtest (success or failure). Insufficient-history names and names that failed data checks up front are omitted from backtest by rule. A backtest that errors or times out MUST be recorded as a data-source failure for that name, MUST exclude that name from Top 5 / Least 5, and MUST NOT leave a “backtest unavailable” gap. The rest of the scan MUST still publish. A failed backtest MUST NOT by itself cancel that name’s today’s BUY / HOLD / WATCH / EXIT from the evaluation step.
- **FR-067**: Partial backtest failure MUST NOT keep the entire run in an incomplete state. Once every history-valid backtest has succeeded or failed, the run is complete.

#### Technicals tab

- **FR-051**: Stock-detail Technicals, when this strategy is active, MUST show a technical-decision header (signal, eligibility result, strategy name **52-Week High Breakout**) and all strategy-owned technicals: close on T, prior 252-session high, close-versus-prior-high pass/fail, volume on T, 20-session volume average, volume-versus-average pass/fail, 14-session simple average true range, 60-session rank key, rank among today’s buy-signal names, market-filter pass/fail with benchmark close and 50-session average, slot status, and — when held — high-water mark, current trailing stop, and whether close would exit.
- **FR-052**: Technicals MUST NOT present RSI, stock moving-average structure, Bollinger bands, Darvas box, Mansfield or sector relative strength, earnings, a 2× volume multiple, or a 252-session +50% momentum gate as decision inputs for this strategy.
- **FR-053**: Missing prior high, volume average, average true range, or rank key MUST render as unavailable, never as zero.

#### Backtest tab and reporting metrics

- **FR-054**: Stock-detail Backtest MUST present headline metrics (total return, compounded annual growth, max drawdown, win rate, trade count, profit factor, and average trade when available), equity curve, optional benchmark overlay, drawdown chart, monthly return grid, trade log, best trade, worst trade, and top winning / losing trades. The detail tab MAY offer 1Y / 3Y / 5Y / All chart windows; those toggles do not change the scan-level 1-year Top 5 / Least 5 ranking.
- **FR-055**: A “trade” is one symbol from entry fill to exit fill. Re-entering the same name later is a new trade. For the 1-year boards only, a still-open book position is included as one marked trade (FR-061) and is not omitted until it actually exits.
- **FR-056**: Required book-level metrics on the marked equity curve: total return, compounded annual growth using calendar days and 365.25, max drawdown, Calmar (growth ÷ |max drawdown|), win rate, average trade, profit factor, exposure (fraction of sessions with at least one holding), hold days, and excess versus NIFTY 500 over the same window.
- **FR-057**: Default historical cost model for the canonical book is the published NSE delivery fee breakdown (brokerage, exchange, regulator fee, stamp, tax on brokerage+exchange, securities transaction tax on sells, and depository charge on sells). Selection MUST NOT depend on capital-gains tax. The product SHOULD report both pre-tax and after-tax equity when tax view is enabled.
- **FR-058**: Live recommended starting capital is configurable, default 1,00,000 Indian rupees.

#### Data quality, safety, persistence, and disclosure

- **FR-059**: If only a current (not point-in-time) NIFTY 500 list is available historically, results MUST be labelled survivorship-biased.
- **FR-060**: Known limitations MUST be disclosed on the strategy’s Scanner / Backtest surfaces: survivorship of the published path, look-ahead if replay fills at the same close used to test the breakout, volume average and average true range including the signal bar, state-not-cross late entries, gap-through trail risk, historically below-50% win rate with payoff carrying the edge, 10-name concentration with no sector cap, open 2026 drawdown on the published sample, and that past compounded growth is not a forecast.
- **FR-062**: System MUST persist cash, holdings (shares, entry date, entry price, high-water mark, trailing stop), fill model, pending orders, and last session processed. Restarting MUST NOT lose high-water mark or trailing stop. If trail state is lost, reconstruct from last known high-water mark minus three times average true range and MUST NOT set a stop lower than the last known stop.
- **FR-063**: System MUST never open a short, never buy a name whose buy signal is false, never place live entries during WARMUP, and never flatten solely because the market filter turned off.
- **FR-064**: Access to Scanner and this strategy’s results MUST follow the existing authentication and feature-permission model. Unauthenticated access is forbidden.

### Key Entities

- **52-Week High Breakout Strategy**: Event-driven, long-only, close-based 252-session high breakout with a 3-average-true-range trail, identified as `09_52w_breakout`.
- **Shared Trading Session**: One NSE cash-equity / NIFTY 500 session date on the master calendar.
- **Adjusted High / Close / Volume**: Corporate-action-adjusted official session fields used for the 52-week level, breakout test, trail, rank, and replay fills.
- **Prior 252-Session High**: Maximum adjusted high over the 252 sessions ending yesterday; the breakout level.
- **Volume Average (20)**: Simple average of session volume including today; today’s volume must be strictly above it.
- **Average True Range (14)**: Simple average of true range including today; used only to place and ratchet the trail, not as an entry gate.
- **Market Filter**: Benchmark close strictly above its 50-session average; blocks new buys only.
- **Momentum (60)**: 60-session total return used only to rank candidates into free slots.
- **Buy Signal**: State condition: market filter on, close at or above prior high, volume above average, data complete.
- **High-Water Mark**: Highest close since entry.
- **Trailing Stop**: Ratcheting close − 3 × average true range (or 90% of entry if average true range was missing at entry); never decreases.
- **Slot Book**: Up to 10 names, 10% of current equity each, one lot per symbol.
- **Scan Run**: One isolated evaluation of the universe for this strategy, including filter outcomes and backtests, started only from this strategy’s Run control.
- **Recommendation Row**: Rank, symbol, signal (BUY / HOLD / WATCH / REJECT), close, prior high, volume context, rank key, weight/notional when selected, trail state when HOLD, and link to detail.
- **Order List**: Today’s EXIT rows (trail) followed by today’s BUY rows (ranked into free slots).
- **First-Failure Rejection**: Single earliest reason a name left the new-entry path.
- **Scan-Time Backtest**: Historical replay using the same filters as the scan, produced before recommendations are shown, for every name with valid 252-session history. Each job ends in success or data-source failure; failure does not block publishing the rest of the scan.
- **Top/Least Return Board**: Up to five names ranked by net return of that name’s real 10-slot book trades over the last 1 year of completed sessions. Zero-trade names are omitted.
- **Real Book Trade**: A fill that exists because the name received a 10% slot. Not a hypothetical single-name signal and not buy-and-hold. For 1-year boards, a still-open book position is marked to the scan session and counted as one trade.
- **Technicals Snapshot**: Strategy-owned indicator values for one symbol on the evaluation session, including trail state when held.
- **Backtest Report**: Equity curve, drawdown, monthly returns, blotter, and headline metrics for a name or the book.
- **Limitations Disclosure**: Operator-visible caveats that MUST accompany results.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After this strategy is available, an authorized user can find the 52-Week High Breakout button beside Long-Term Buy & Hold Momentum and see the strategy name without consulting documentation, in under 30 seconds from opening Scanner.
- **SC-002**: In 100% of acceptance runs, pressing Run on the 52-Week High Breakout view starts only this strategy; other strategies’ latest scans, boards, and holdings do not change during that run.
- **SC-016**: In 100% of acceptance runs, a second press of this strategy’s Run control while a run is in progress neither starts another 52-Week High Breakout evaluation nor cancels the first; the first run still publishes a completed result.
- **SC-003**: On a completed scan, 100% of recommendation rows are withheld until every name with valid 252-session history has a terminal backtest (success or failure). Insufficient-history names and names whose backtest failed are not completed-return rows and never appear on Top 5 / Least 5. A mix of successful and failed backtests still publishes one completed scan.
- **SC-004**: 100% of rejected names in a completed scan appear in exactly one Rejection Breakdown first-failure bucket; displayed percents match those counts against the evaluated set within rounding of one tenth of a percent.
- **SC-005**: Given a frozen historical calendar and prices, a replay’s first entries fall on 2020-08-27 and the first-day membership set matches Acceptance Fixtures (order inside the day need not match).
- **SC-006**: On that same frozen path, a name whose close equals the prior 252-session high is eligible on the price leg, a name whose close is one tick below is not, a name whose volume equals the 20-session average is not eligible, and a Wilder-smoothed average true range implementation fails the trail fixtures.
- **SC-007**: After a scan with at least five names that have a positive 1-year **book-trade** return and five that have a non-positive 1-year book-trade return, operators can identify the top 5 winners and least 5 names from the boards without exporting data. Names never selected in that year do not appear. The boards’ period label is the last 1 year of completed sessions.
- **SC-008**: On a Technicals tab for this strategy, every displayed decision tile is a 52-Week High Breakout input; a review checklist finds zero decision tiles for RSI, stock moving averages, Bollinger bands, Darvas box, sector rotation, or a 252-session +50% gate.
- **SC-009**: On an active session with 15 buy-signal names and 10 free slots, operators see exactly 10 BUY rows (the 10 highest 60-session returns) and the remaining buy-signal names counted as “buy signal but no free slot”.
- **SC-010**: On a market-off session with open holdings, operators see zero new BUY rows, each still-open name as HOLD in Scan results, trail updates and any EXIT rows, and can read that the book was not flattened because the market filter turned off.
- **SC-015**: On a completed scan with at least one still-open prior holding, 100% of those names show HOLD in Scan results, zero of them appear in Rejection Breakdown, and a name that EXITs the same session is not labelled HOLD.
- **SC-011**: During warmup, operators see STATUS=WARMUP and zero BUY recommendations on 100% of warmup scans.
- **SC-012**: Nine out of ten operators in an acceptance walkthrough can explain, from the Rejection Breakdown and Technicals tab alone, why a given REJECT name was not bought.
- **SC-013**: Backtest and scan eligibility answers never disagree for the same name, session, and dataset (same pass/fail and same first-failure reason).
- **SC-014**: After a process restart with open holdings whose price did not print a new high-water mark, 100% of those holdings show a trailing stop greater than or equal to the stop persisted before the restart.

---

## Assumptions

- Point-in-time NIFTY 500 membership is used when the host can supply it; otherwise the current list may be applied historically and results are labelled survivorship-biased.
- Live fills use the next session’s open / auction; historical replay uses the signal session’s adjusted close, exits before entries.
- The canonical book is 10% of current equity per name, maximum 10 names (the published comparison book). The original uncapped per-symbol research loop is out of scope for the live / Scanner default.
- Whole shares only in live cash equity; fractional shares allowed only in research replay.
- If a ranked name cannot be bought, take the next-ranked still-valid name into that slot.
- Any consistent adjusted open-high-low-close vendor is acceptable; mixing adjusted and unadjusted series is not.
- Market filter turning off does **not** flatten the book. That would be a different strategy.
- Entry is close at or above the prior 252-session high, not an intraday high print.
- Average true range is a 14-session simple average of true range, not Wilder / smoothed.
- Volume average includes today, matching the published engine. A “prior-only” rewrite would not match published P&L.
- Default research capital is 1,00,000 Indian rupees and is configurable.
- Tax does not change selection. When a tax view is shown, report both pre-tax and after-tax equity using then-current Indian cash-equity rules. Most published holds are short-term.
- Paper versus live brokerage adapters are out of scope of the algorithm; the host already owns order routing.
- An optional intraday preview MAY show the current print versus yesterday’s prior high. Official signals fire only on the official close. Provisional data MUST NOT send live orders.
- If trail state is lost, reconstruct from last known high-water mark minus three times average true range and never lower the stop below the last known stop.
- Ranking tie-break is 60-session return descending, then ticker symbol ascending. The published engine sorted by the rank key only; this product adds the ticker tie-break so two operators never see a different 10th name.
- 52-Week High Breakout appears as its own selectable Scanner strategy with its own Run control, not as a silent scoring tweak inside Production or Long-Term Buy & Hold Momentum.
- Top 5 / Least 5 rank each name by the net return of **that name’s real book trades** over the last 1 year of completed sessions (bought only when it received a 10% slot; sold on the trailing stop), **including mark-to-market of any still-open book position** as of the scan session. Today’s REJECT names may appear if they were selected in that window. Names never selected in the window, and names without valid 252-session history, do not appear. The mark is for ranking and display only — it is not a live exit. Stock-detail Backtest may show other windows; the boards stay on 1 year.
- Scan-time backtests run for every name with valid 252-session history, including names that failed today’s close, volume, or market gates or missed a slot. Insufficient-history and data-failure names are not backtested.
- Reference images define layout, hierarchy, and density. Bucket names, indicator tiles, and metrics MUST follow this strategy’s rules rather than copying another strategy’s labels.
- Existing Scanner authentication, feature permissions, paper-trade handoff, and navigation are reused.
- Unused cash earns 0 unless a later clarification adds a sweep rate.
- A NIFTY 50 market-filter switch is research-only and is not the Scanner default.

---

## Out of Scope

- Adding a Darvas box (3-day unbreached top and 3-day bottom).
- Using a 2× or 5× volume multiple.
- Flattening the book when the benchmark drops below its 50-session average.
- Using Wilder / smoothed average true range.
- Using calendar 365-day highs instead of 252-session highs.
- Entering on an intraday high through the prior 252-session high without the close also clearing the level.
- Adding RSI, relative-strength rating, earnings blackout, or sector caps as part of implementing this strategy.
- Optimizing the 3× trail multiple, the 252 window, or the 10-name cap as part of the first build.
- Replacing the 10% × 10 slot book with an uncapped per-symbol research loop as the live default.
- Trading derivatives, basket futures, or leveraged funds as a substitute.
- Replacing Production, RE-001, RE-002, or Long-Term Buy & Hold Momentum, or changing their scoring.
- A shared “run all strategies” action from the 52-Week High Breakout Run control.
- Redesigning the entire Scanner chrome beyond what is required to host this strategy’s button (beside Long-Term Buy & Hold Momentum), isolated Run control, summary, breakdown, boards, recommendations, Technicals, and Backtest.

---

## Acceptance Fixtures

These fixtures are product acceptance tests on a frozen historical calendar (published research window 2019-08-19 through 2026-08-14). They are not live-trading guarantees.

### Formula, trail, and book

- Session 251 of a fresh series → no orders (warmup).
- Prior 252-session high on bar 252 equals the maximum high of the previous 252 sessions and **excludes** bar 252’s high.
- Close equal to that prior high → price leg true.
- Close one tick below the prior high, even if that session’s high is above it → price leg false.
- Volume equal to the 20-session average → volume leg false.
- Benchmark close equal to its 50-session average → market filter off.
- Average true range is the 14-session simple average of true range. A Wilder implementation fails.
- Entry 100, average true range 2 → trailing stop 94, high-water mark 100.
- Next close 99, average true range 2 → stop stays 94, still held.
- Later close 110, average true range 3 → high-water mark 110, stop 101.
- Later close 112, average true range 6 → stop stays 101 (does not drop).
- Close 101.00 → still held.
- Close 100.99 → exit, reason trailing stop.
- Entry session does not exit even if a synthetic stop would be breached.
- Missing average true range at entry → stop = 90% of entry.
- 15 buy-signal names and 10 free slots → buy the 10 highest 60-session returns only.
- 3 buy-signal names → buy 3 at 10% equity each, hold about 70% cash.
- Book already has 10 names → zero new buys.
- A name sold today is not rebought today.
- Market filter off → zero new buys; existing names still trail and can exit.
- No short is ever opened.
- Last historical session force-closes leftovers with reason end-of-sample liquidation.

### Worked single-name path (market filter on throughout)

| Session | High | Close | Volume | Prior 252-high | Vol average | ATR | Action |
|---------|------|-------|--------|----------------|-------------|-----|--------|
| 251 | 99 | 98 | 1.0m | n/a | 1.0m | 2.0 | Warmup, no buy |
| 252 | 101 | 100 | 1.6m | 99 | 1.1m | 2.0 | BUY at 100, stop 94, high-water 100 |
| 253 | 102 | 99 | 1.2m | 101 | 1.1m | 2.0 | Hold; no ratchet (99 < 100) |
| 254 | 112 | 110 | 2.0m | 102 | 1.2m | 3.0 | High-water 110, stop max(94, 101) = 101 |
| 255 | 111 | 102 | 1.0m | 112 | 1.2m | 3.0 | Hold (102 > 101) |
| 256 | 108 | 100 | 1.4m | 112 | 1.2m | 2.8 | SELL at 100, reason trailing stop; cannot rebuy today |

### Published first-cohort fixture (membership MUST match)

On the frozen published dataset, first entries print on **2020-08-27** (7 names; book not yet full):

| Symbol | Entry | Exit | Return | Reason | Hold days |
|--------|-------|------|--------|--------|-----------|
| SJVN | 20.1501 | 2020-08-31 18.2366 | −9.50% | trailing stop | 4 |
| DIXON | 1719.0934 | 2020-09-22 1706.8004 | −0.72% | trailing stop | 26 |
| ATUL | 6130.8076 | 2020-09-23 5855.2656 | −4.49% | trailing stop | 27 |
| JUBLFOOD | 428.0413 | 2020-10-22 431.8321 | +0.89% | trailing stop | 56 |
| TATAELXSI | 1081.7810 | 2020-11-10 1373.2408 | +26.94% | trailing stop | 75 |
| CDSL | 195.7957 | 2021-01-28 228.5507 | +16.73% | trailing stop | 154 |
| SAREGAMA | 50.6307 | 2021-08-23 285.6780 | +464.24% | trailing stop | 361 |

First-day membership set: **SJVN, DIXON, ATUL, JUBLFOOD, TATAELXSI, CDSL, SAREGAMA**.

Next fills: 2020-08-28 SUNPHARMA, WELSPUNLIV; 2020-08-31 CGPOWER as slots allow.

### Published book-level checks (canonical 10% × 10 book, published delivery costs, signal-close fills)

| Check | Expected |
|-------|----------|
| First entry date | 2020-08-27 |
| Closed trade count | 294 |
| Unique names | 207 |
| Exit mix | 284 trailing stop + 10 end-of-sample liquidation |
| Best trade | SAREGAMA +464.24% (2020-08-27 → 2021-08-23, 361 days) |
| Worst trade | VEDL −64.55% (2026-04-15 → 2026-04-30, 15 days) |
| Final equity | within 2% of 6,85,622.99 on 1,00,000 start |
| Compounded annual growth | within 0.3 percentage points of +31.72% |
| Max drawdown | within 1 percentage point of −25.81% |
| Win rate | within 1 percentage point of 45.92% |

If only membership and trail fixtures are implemented first, do not claim rupee figures until the cost model is applied.

---

## Known Limitations (MUST be disclosed in the product)

- Published historical numbers used a 2026 NIFTY 500 list for all history. Dead names are missing; recent listings have short samples.
- Signal-close replay assumes you trade the close just used to test the breakout — look-ahead versus a live trader.
- Volume average and average true range include the signal bar. That matches the published engine; a “prior-only” rewrite would not match P&L.
- The buy signal is a state, not a first print. A name riding the 52-week high keeps firing every day until a slot opens. Late entries can be late in the move.
- No hard stop / gap risk: a close can print far below the trail (published example: VEDL about −64.55% in 15 days). The fill is the close, not the stop price.
- Win rate is historically below 50%. The edge is payoff (published average win about +32.6% versus average loss about −9.0%). Median trade is negative (about −1.82%).
- The published sample ended in an open about −25.81% drawdown; 2026 calendar return about −19.64% versus NIFTY 500 about −2.09%.
- Ten names, no sector cap. Theme clusters can appear in the winners.
- Published path allowed fractional shares; live India cash is whole shares.
- Past compounded growth (published about +31.72%) is not a forecast.
