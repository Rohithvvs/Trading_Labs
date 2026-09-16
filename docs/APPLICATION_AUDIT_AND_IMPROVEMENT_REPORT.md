# Trading Labs — Full Application Audit and Improvement Report

**Date:** 16 September 2026  
**Scope:** Entire product (frontend, backend, scanners, backtesting, paper trading, auth, admin, docs)  
**Method:** Code and route audit of the current repository, plus existing unit/API tests. This is **not** a live production run against FYERS. Claims below are from source, not from a full click-through of every screen.

**Bottom line:** The research workstation is real and usable for Indian-market scanning, paper practice, and two first-class strategies (LTM and 52-week breakout). It is **not** yet a clean “one backtest button” product. Several screens say “LEAN backtest” while running a last-bar scan. Several APIs are still unauthenticated. Docs and E2E tests lag the current UI.

Use this file as a work list: **P0 = fix first**, **P1 = next**, **P2 = polish**.

---

## 1. How the application actually works

Trading Labs is an **advisory research and practice-trading web app**. It does **not** place real broker orders. Income, when it comes, is meant to be software subscriptions — not brokerage.

Typical path for a logged-in user:

1. **Login** (email/password or Google) → lands on **Markets**.
2. **Markets** shows indices, movers, watchlist, last scan highlights, saved presets, price alerts.
3. **Scanner Dashboard** (Profile → Scanner, route `/scanner`) runs:
   - **Long-Term Momentum (LTM)** — default
   - **52-Week High Breakout**
4. Click a name → **stock research** (overview, chart, technicals, trade plan, news, backtest, research).
5. **Strategy Tester** builds or imports rules (visual builder or Pine) and **scans the 755-name universe** on the last daily bar. Window return is buy-and-hold from first to last close — not a full trade-by-trade portfolio sim.
6. **Indicator Scanner** (tab inside Strategy Tester) can launch a separate **LEAN-style** multi-asset backtest.
7. **Strategy Comparison** compares 2–4 **already completed** tester scans and/or LEAN jobs (radar + metrics). It does not re-run anything.
8. **Paper Desk** practises buy/sell with virtual money using live FYERS prices.
9. **Performance** summarises paper equity and daily analytics.

**Data:** PostgreSQL holds about **18 years of daily bars** (22 Jul 2008 → 17 Aug 2026) for ~747 of 755 Nifty 500 names. Live overlay from FYERS can stamp the latest session onto scans.

**Auth:** The UI is behind login. Feature flags (`advanced_scanner`, `portfolio_analytics`, `watchlist`, admin keys) hide some screens. Many backend routes are **not** gated the same way (see P0 security).

---

## 2. Feature status (whole product)

| Area | Status | What the user actually gets |
|---|---|---|
| Login / signup / Google / sessions | **Working** | JWT + HttpOnly cookies; traders vs admin |
| Markets home | **Working** (copy drift) | Overview, watchlist, alerts, scan highlights |
| LTM scanner | **Working** | Universe scan + book replay + boards |
| 52W breakout scanner | **Working** | Universe scan + book replay + TV tape tests |
| Production “swing” scanner | **Hidden leftover** | Code still in `App.tsx`; tabs no longer show it |
| Strategy Tester (builder / Pine scan) | **Working as a screener** | Last-bar universe scan + window return |
| Indicator Scanner + LEAN button | **Partial** | Scan works; LEAN jobs are in-memory and unauthenticated |
| Strategy Comparison + radar | **Working** (uncommitted on branch) | Side-by-side of existing runs only |
| Stock research tabs | **Working** | Backtest tab hydrates from strategy/LEAN/scan data |
| Paper trading | **Working** | Orders, positions, SL/target, gap replay |
| Performance | **Working** | Paper analytics; fetch errors swallowed |
| Profile | **Partial** | Core account works; several sections are stubs |
| Admin users + feature flags | **Working** | `/admin` is role-gated; `admin_panel` flag not on the route |
| Central Command | **Partial** | Close-position is a stub; BUY qty hardcoded to 10 |
| Diagnostics / logs | **Partial** | Logs gated; `/diagnostics` URL is not admin-gated |
| Walk-forward API | **Partial** | Mounted, **no auth**, weak UI |
| Event calendar API | **Partial** | Mock ingest, **no auth** |
| Live brokerage | **Intentionally absent** | Correct for this product |
| STR-005 strategy package | **Broken** | Tests remain; Python sources missing (only `__pycache__`) |
| AI Trading Coach | **Heuristic stub** | Hidden in retail sidebar; not an LLM coach |

---

## 3. Backtesting — read this section first

There are **four different “backtests”**. Mixing them up is the main product confusion.

### 3.1 What is working properly

| Engine | Where you see it | What it does | Verdict |
|---|---|---|---|
| **52W book replay** | Scanner → 52W → stock Backtest | 252-session high + volume + Nifty 500 gate + 3× ATR trail, 10% of equity, max 10 names, NSE costs | **Working and well tested** |
| **LTM book replay** | Scanner → LTM | Buy-and-hold momentum book on stored daily bars | **Working**; survivorship (current list only) |
| **Strategy Tester scan** | Strategy Tester → Run | Filters on **last daily bar**; return = first-close → last-close | **Working as a screener**, not a strategy tester in the TradingView sense |
| **Legacy analysis backtest** | `POST /analysis/backtest` | Single-name EMA/RSI/MACD `iterrows()` sim | **Working but old**; fills gaps with ffill/bfill; unauthenticated |
| **LEAN-style engine** | Indicator Scanner → Backtest (LEAN), `/backtests` | In-process QuantConnect-**like** event engine (next-bar open, NSE fees, multi-name) | **Partial** — see 3.3 |

Daily history in Postgres is enough for 1Y / 3Y / 5Y / All windows on names that existed that long. Newer IPOs start at listing, not 2008.

### 3.2 What is *not* a TradingView Strategy Tester

TradingView Strategy Tester = **one symbol, one `strategy()` script, broker emulator, list of trades**.

Trading Labs Strategy Tester = **755 names, last bar, BUY/WATCH/REJECT, window return**.

Same words, different machines. A 52W Pine on TradingView can print hundreds of 1-share round-trips. Labs 52W kernel prints a handful of ATR-trail holds. That is **not a bug in the kernel** if the rules differ (see `docs/TRADINGVIEW_VS_TRADING_LABS.md` and `docs/PINE_52W_BREAKOUT_SCAN_TV_VS_LABS.md`).

### 3.3 Backtest issues you must fix

**P0 — Engine dropdown does not run LEAN**

- UI: Strategy Tester → Engine = “QuantConnect LEAN” or “Trading Labs Standard” (`StrategyConfigurationPanel.tsx`).
- Run path: `handleRunStrategy` never sends `engine`. `POST /strategy-tests` accepts `engine` on `CreateRunBody` and **ignores it** (`strategy_tester.py` `create_run` → `start_test_background`).
- Effect: User thinks they ran a professional portfolio backtest. They ran a last-bar scan.

**Fix:** Either (a) wire Engine = LEAN to `LeanBacktestService`, or (b) remove the dropdown from the scan panel and label the button **Scan universe**. Keep LEAN only on the Indicator Scanner backtest button.

**P0 — “QuantConnect LEAN” is not QuantConnect**

- Code: `backend/app/lean/` is a **clone of QC types**, not the official LEAN binary.
- Jobs live in process memory (`lean_service.py` `_JOBS`, `_ACTIVE_TASKS`). Restart = all jobs gone. Strategy Comparison cannot recover those runs after a reboot.
- HTTP `/backtests` has **no login**. Docs say `/api/v1/backtests` — wrong path (`LEAN_INTEGRATION.md`).

**Fix:** Persist jobs/results in Postgres; require `advanced_scanner` (or admin) on `/backtests`; correct the docs; rename UI to “Labs event engine” unless you actually embed QuantConnect LEAN.

**P0 — “TradingView validation” does not compare to TradingView**

- `validation_service.py` recomputes the entry rule from **LEAN’s own debug trace**, then counts matches. TV CSV helpers are imported and unused.
- This cannot fail for a real TV mismatch.

**Fix:** Compare bar-by-bar to a stored TradingView tape/CSV (the 52W kernel already has `tv_tester_tape.py` / `tv_ohlc_csv.py`).

**P0 — Dual engine “EXISTING” is misleading**

- `existing_engine.py` hard-codes `quantity: 100`, `gross_pnl: 0`, `commission: 0`, `net_pnl = pnl% × capital`, equity curve from **first symbol only**.
- Not a fair LEAN vs Standard comparison.

**Fix:** Hide EXISTING in the UI until portfolio, fees, and equity are real — or delete the adapter.

**P0 — Indicator LEAN maps unknown Pine to 52W**

- `indicator_scanner.py` ~309–319: if the name is not pulse/LTM/52, it still uses `09_52w_breakout`.
- A custom RSI script can run the 52W algorithm.

**Fix:** Compile the indicator’s own filters into `dynamic_rule_algorithm`, or refuse backtest until a strategy id is chosen.

**P1 — Live overlay on historical windows**

- Tester/LEAN load `daily_ohlcv` then overlay live FYERS (`overlay_live=True` by default).
- A “backtest to 2024” can include **today’s incomplete bar**.

**Fix:** `overlay_live=False` when `end_date < today`.

**P1 — Cost models disagree**

| Place | DP charge (approx.) |
|---|---|
| 52W `costs.py` | ₹15.93 |
| LEAN `fee_models.py` | ₹13.50 |
| Legacy `BacktestService` BASE | ₹13.50 |

**Fix:** One NSE delivery table, used by all engines.

**P1 — Warmup is calendar, not sessions**

- LEAN data adapter uses `warmup_sessions * 1.6` calendar days, not exact NSE session count.

**Fix:** Use `nse_session_dates` (already in the repo).

**P1 — Delivery % not backfilled** for the 18-year window (only recent bars). Volume/delivery filters on deep history are weaker.

**P1 — Survivorship:** scans use today’s Nifty 500 list. Names that later left the index are missing from old windows.

**P2 — Legacy backtest** truncates equity curve to last 50 points; `ffill().bfill()` invents prices across holidays.

### 3.4 Backtest — recommended product wording

| Screen | Button / title should say |
|---|---|
| Strategy Tester run | **Scan universe** (last completed session) |
| Indicator Scanner LEAN | **Portfolio backtest (event engine)** |
| Stock → Backtest (52W/LTM) | **Book replay for this name** |
| Strategy Comparison | **Compare completed runs** (no ranking) |

Do not use “best strategy” or a single Sharpe as a winner. Comparison radar is a **display scale**, not a ranking (already noted in the UI).

---

## 4. Issues to fix (all areas)

### P0 — Security (do these before any public deploy)

| # | Issue | Where |
|---|---|---|
| S1 | Save/delete FYERS token without login | `routes/fyers.py`, `routes/token.py` `POST /api/token/save-access-token`, `POST /settings/token` |
| S2 | Anyone can start/stop the **process-wide** market engine | `POST /paper-trading/engine/start\|stop`, `GET .../engine/status` |
| S3 | LEAN create/list/results/cancel with no auth | `lean/routes/lean_router.py` `/backtests` |
| S4 | Analysis / stocks / workstation / walk-forward / events / shadow-run mostly open | `analysis.py`, `stocks.py`, `workstation.py`, `routers/walk_forward.py`, `event_calendar.py`, `system.py` |
| S5 | `/diagnostics` in the UI is not admin-gated (URL only) | `App.tsx` |
| S6 | Governance/analytics/diagnostics APIs are open if `API_KEY` is empty | `core/security.py` `verify_api_key` |
| S7 | `/admin` is role-gated but **not** `FeatureGuard admin_panel` | `App.tsx` |

Saving a token can auto-start a scanner. An open token endpoint is a real incident waiting to happen.

### P0 — Correctness / honesty

| # | Issue | Where |
|---|---|---|
| C1 | Engine dropdown ignored | `StrategyTesterPage.tsx`, `strategy_tester.py` |
| C2 | LEAN jobs not persisted | `lean/services/lean_service.py` |
| C3 | TV validator compares LEAN to itself | `lean/services/validation_service.py` |
| C4 | EXISTING engine fake qty/fees | `lean/engine/existing_engine.py` |
| C5 | Unknown Pine → 52W LEAN | `routes/indicator_scanner.py` |
| C6 | STR-005 sources deleted, tests still collected | `services/strategies/str005/` (pyc only), `tests/unit/str005_tests/` |
| C7 | `backend/main.py` does not export `app` | Start with `backend.app.main:app` only |

### P1 — Product / UX

| # | Issue | Where |
|---|---|---|
| U1 | Production scanner still in App; E2E still clicks `run-scanner-button` | `App.tsx`, `e2e/app.spec.ts` |
| U2 | Save-scan handler never used; Markets “saved scans” cannot be created from scanner | `App.tsx` `handleSaveCurrentScan` |
| U3 | LTM has no Favorites / Scan-results tabs (52W does) | `App.tsx` |
| U4 | Markets hero still says “swing decision dashboard”; `SwingDecisionDashboard` unused | `MarketsPage.tsx` |
| U5 | Watchlist full page unused; `/watchlist` redirects to Paper | `WatchlistPage.tsx` |
| U6 | Profile: other brokers “Coming soon”, 2FA planned, privacy actions are text, Support → github.com | `UserProfilePage.tsx` |
| U7 | AI coach is a win-rate heuristic; retail hides the nav item but overview can still open it | `UserProfilePage.tsx` |
| U8 | Central Command close-position stub; BUY qty = 10 | `CentralCommand.tsx` |
| U9 | Admin “forbidden” CTA goes to `/scanner` | `AdminRoute.tsx` |
| U10 | Mobile bottom nav ignores feature flags; Strategy Tester always shown; Comparison not on mobile | `AppShell.tsx` |
| U11 | Hardcoded “755 Stocks” and demo identity in shell | `AppShell.tsx` |
| U12 | Stock details fallback run id `STR-20260826-001` | `StockDetailsPage.tsx` |
| U13 | Performance page swallows API errors | `PerformancePage.tsx` |
| U14 | Paper E2E looks for `paper-order-ticket` / `paper-symbol-select` on `/paper`; ticket is `/paper-order` | `e2e/app.spec.ts` |
| U15 | Scanner prefs in Profile (NIFTY50, 4h, etc.) not wired to the scanner | `UserProfilePage.tsx` vs `App.tsx` |
| U16 | Universe locked to `ALL_755` in Strategy Tester | `StrategyTesterPage.tsx` |

### P1 — Data / ops

| # | Issue | Notes |
|---|---|---|
| D1 | 12 universe tickers have no FYERS history | Dummy/renamed names in `BACKTEST_DATA_AVAILABILITY.md` |
| D2 | Delivery % not backfilled for 18y | Volume/delivery studies on deep history |
| D3 | Pre-market 09:00 auto-scan is **commented out** | `main.py` — bootstrap token→scanner still runs once/day |
| D4 | `nightly_candle_sync()` defined, not scheduled | `main.py` |
| D5 | Dual pytest trees | `backend/tests` vs `backend/app/tests` vs `backend/app/tests_pg` |
| D6 | Docs inventory is stale | `docs/architecture/APIInventory.md` (~117 endpoints, no tester/LEAN/comparison); `FEATURE_INVENTORY.md` still says SQLite; `USER_MANUAL.md` still says Scanner is top nav; `FINAL_DEPLOYMENT_DECISION.md` says scheduler is commented — **scheduler.start() is live** |

### P2 — Polish

- Radar/comparison is new; keep the “not a ranking” note.
- Dead files: `Dashboard.tsx`, `WorkstationPage.tsx`, `OrderDrawer.tsx` (ticket is `/paper-order`).
- Density hook unused in AppShell.
- NotificationBell only on unused Dashboard header.
- Walk-forward and event calendar have no first-class UI.
- Intraday scanner timeframes in Profile are not backed by an intraday store (daily is the strategy-grade tape).

---

## 5. Improvements (what to build next, in order)

### Must do (makes the product honest and shippable)

1. **Rename Scan vs Backtest everywhere** so users are not comparing Labs to TradingView incorrectly.
2. **Persist LEAN jobs** and gate `/backtests`.
3. **Lock down token, engine, analysis, workstation, diagnostics.**
4. **One NSE cost table.**
5. **Stop defaulting unknown Pine to 52W.**
6. **Delete or restore STR-005.**
7. **Fix E2E** to LTM/52W buttons and `/paper-order`.
8. **Update USER_MANUAL** to current nav (Markets, Strategy Tester, Comparison, Paper, Performance, Profile).

### Should do (product quality)

9. Wire **save scan** from Scanner, or remove Markets presets.
10. Give LTM the same result-board pattern as 52W, or say why not.
11. Finish or hide Profile stubs (privacy, 2FA, other brokers, AI coach).
12. Gate mobile nav with the same feature flags as desktop.
13. Disable live overlay on historical backtests.
14. Session-count warmup for LEAN.
15. Strategy Comparison: persist LEAN runs so comparison survives restart.
16. Single pytest entry documented in `docs/TESTING.md`.

### Nice to have

17. Real QuantConnect LEAN **or** stop using the QuantConnect name.
18. Intraday store if you want 1h/4h scans (today the serious engines are **daily**).
19. Walk-forward UI with auth.
20. Delivery % backfill for names that need it.
21. Watchlist as its own page again, or keep it only on Paper and change Markets “View all”.
22. Central Command: implement close, or remove the button.

---

## 6. What is working well (do not rip this out)

- **Auth + roles + feature catalog** as a foundation (JWT fail-closed in prod on default secrets).
- **LTM and 52W** as first-class strategies: scan, persistence, orphan cleanup, book replay, attribution, large unit suites (including 52W TV tape).
- **~18 years of daily OHLCV** in Postgres for the universe; EOD update path exists.
- **Paper trading** with user isolation, market hours, pending fills, SL/target, gap replay after restart.
- **Strategy Tester** as a Pine/builder **screener** with funnel, filter analytics, save/import.
- **Strategy Comparison** (including the hexagonal radar) as a read-only overlay of completed runs — no fake ranking.
- **Indicator parser/evaluator** with tests.
- **Operational pieces:** Alembic gate, singleton worker lease, correlation IDs, bounded health probes, FYERS token automation + once-per-day bootstrap scan.
- **Advisory-only design** (no live orders) matches the company overview.

---

## 7. Suggested 30 / 60 / 90 day plan

### Days 1–30 — Trust and safety

- Auth on token save/delete, paper engine, LEAN, analysis, workstation, diagnostics.
- Persist LEAN jobs; fail comparison gracefully if a job is gone.
- Relabel Strategy Tester Run as Scan; disconnect unused Engine dropdown.
- Stop Pine→52W default.
- Align E2E with LTM/52W and paper-order.
- One cost table.

### Days 31–60 — One backtest story

- Indicator/LEAN backtest uses the **same filters** the user scanned (dynamic rule algorithm).
- Historical windows: no live overlay.
- TV validator uses a real tape.
- Hide EXISTING engine until it is a real adapter.
- Save-scan from Scanner; clean Markets copy.
- Profile: hide unfinished sections in retail.

### Days 61–90 — Product polish

- Mobile nav + feature flags.
- Docs: USER_MANUAL, API inventory, FEATURE_INVENTORY, LEAN_INTEGRATION paths.
- Delete dead Dashboard/Workstation/OrderDrawer or wire them.
- Decide: official LEAN vs keep in-process engine under an honest name.
- Optional: intraday data product, walk-forward UI.

---

## 8. How to verify after you fix

| Check | How |
|---|---|
| Strategy Tester scan | Run a saved 52W-style filter on ALL_755; BUY list should match last **completed** NSE session, not a mixed date |
| 52W book backtest | Open one BUY name → Backtest tab; trade count should match kernel (not TV 1-share tester) |
| LEAN button | Start job, restart backend, confirm job still listed (after persist fix) |
| Comparison | Two completed tester runs → radar + metrics; no “best strategy” copy |
| Paper | Place limit/market on `/paper-order`, reload, position survives |
| Auth | Logged-out `POST /api/token/save-access-token` must be 401 (after S1) |
| Flags | Trader without `advanced_scanner` must not open `/strategy-tester` |

Useful existing tests (not a substitute for a live FYERS day):

```text
pytest backend/tests/unit/test_strategy_comparison_service.py backend/tests/unit/test_strategy_comparison_api.py
pytest backend/tests/unit/test_lean_integration.py backend/tests/unit/test_w52_window_backtest.py
cd frontend ; npx vitest run src/pages/__tests__/StrategyComparisonPage.test.tsx src/pages/__tests__/StrategyTesterPage.test.tsx
```

---

## 9. File map (for the next engineer)

| Topic | Paths |
|---|---|
| App routes / scanner dashboards | `frontend/src/App.tsx` |
| Nav | `frontend/src/layout/navConfig.tsx`, `AppShell.tsx` |
| Strategy Tester | `frontend/src/pages/StrategyTesterPage.tsx`, `backend/app/routes/strategy_tester.py`, `backend/app/services/strategy_tester/` |
| Comparison + radar | `frontend/src/pages/StrategyComparisonPage.tsx`, `frontend/src/components/strategy_comparison/` |
| LEAN | `backend/app/lean/` |
| 52W | `backend/app/services/strategies/breakout52w/` |
| LTM | `backend/app/services/strategies/ltm/` |
| Paper | `backend/app/routes/paper_trading.py`, `backend/app/services/paper_trading_service.py` |
| Auth / features | `backend/app/routes/auth.py`, `admin.py`, `features.py` |
| Market data | `docs/BACKTEST_DATA_AVAILABILITY.md`, `backend/app/services/` market-data CLI |

---

## 10. Verdict

**Is the application working?**  
Yes, as a **research + paper-trading workstation** for daily NSE names: login, Markets, LTM/52W scans, stock research, strategy scans, paper book, and comparison of completed runs.

**Is backtesting working properly?**  
**The 52W and LTM book replays are.**  
**The Strategy Tester “LEAN” control is not a backtest.**  
**The Indicator Scanner LEAN path is a real event engine but jobs die on restart, are unauthenticated, and may run the wrong strategy.**  
**Do not treat Labs vs TradingView trade counts as a bug until both sides use the same script, same bars, and same sizing.**

**Can you improve and ship?**  
Yes — if you treat P0 security and P0 backtest honesty as the next sprint, then product polish. Do not expand into more engines until Scan vs Backtest is one story in the UI.

---

*Generated from repository state on 16 September 2026. Re-run a live FYERS session after P0 fixes before calling production ready.*
