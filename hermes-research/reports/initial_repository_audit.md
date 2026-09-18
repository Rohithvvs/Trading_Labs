# Initial Repository Audit — HERMES PART 1

**Repository:** Trading_Labs  
**Audit date:** 2026-08-24  
**Git HEAD at inspection:** `e27daa226d4a046f855d4b57f6c3f083aea72a0f`  
**Branch:** `038-52w-high-breakout`  
**Evidence classes used below:** `OBSERVED`, `INFERRED`, `UNKNOWN`

This audit is read-only with respect to production code, database schema, golden
reference files, and live-trading logic. No production file was modified to
produce it.

---

# 1 Repository Overview

**OBSERVED:** The workspace root contains a FastAPI backend (`backend/`), a
React/Vite frontend (`frontend/`), specs (`specs/`), docs, governance files,
scripts, Docker Compose, Alembic at both repo root and `backend/alembic/`,
and `hermes-research/tradingview_reference/` (golden data present before PART 1
foundation files were added).

**OBSERVED:** Package management:

- Python: `backend/requirements.txt` and a root `requirements.txt`. No
  `pyproject.toml` at repo root or `backend/`.
- Frontend: `frontend/package.json` (npm, Vite 5, React 18, Vitest, Playwright).
- Virtualenv present at `backend/venv/` (bytecode tag `cpython-311`).

**OBSERVED:** Git remote `origin` points at GitHub `Rohithvvs/Trading_Labs.git`.
Current branch is up to date with `origin/038-52w-high-breakout`. Latest commit
subject: `52 week high breakout`.

**OBSERVED:** `git status` at the start of PART 1 inspection:

```text
On branch 038-52w-high-breakout
Your branch is up to date with 'origin/038-52w-high-breakout'.

Untracked files:
  hermes-research/

nothing added to commit but untracked files present
```

**OBSERVED:** Docker Compose defines a PostgreSQL 15 service named
`trading_system_db` on host port 5433. **Credential detected — value
intentionally hidden.**

**OBSERVED:** `.env` exists at repo root. It was not opened. `.env.template`
exists and lists credential *names* with empty values (FYERS_*, SCHEDULER_SECRET).

**OBSERVED:** Root `README.md` still describes an earlier Phase 1 SQLite advisory
system. The running architecture in `backend/` is PostgreSQL + FastAPI +
scanners + paper/live models. **INFERRED:** root README is stale relative to
current backend.

**UNKNOWN:** Production deployment topology (which host, which database
instance) beyond files in this repo.

---

# 2 Application Architecture

**OBSERVED:** Backend entry: `backend/app/main.py` (FastAPI). Settings via
`pydantic-settings` in `backend/app/config/settings.py`, loading `.env` from
repo root and `backend/.env`.

**OBSERVED:** Layering:

- `routes/` HTTP API (`/analysis`, `/scanner`, paper trading, auth, admin, …)
- `agents/` orchestrator, backtest, technical, news, ranking, router
- `services/` scanners, market data, paper trading, strategies, research, shadow
- `models/` SQLAlchemy
- `schemas/` Pydantic
- `db/` async SQLAlchemy session (`postgresql+asyncpg`) plus sync engine
- `cli/` market-data and 52W performance
- `governance/` experiment CLI

**OBSERVED:** API router assembly in `backend/app/routes/__init__.py` includes
health, stocks, analysis, paper trading, tokens, broker tokens, workstation,
scanner, system, auth, admin, features, diagnostics, governance, analytics.

**OBSERVED:** Frontend is a React SPA (`frontend/src/App.tsx`) with AppShell
navigation, scanner dashboards (including W52 and LTM), paper order page,
markets page, performance page.

**OBSERVED:** Async is used: `AsyncSession`, `asyncpg`, FastAPI async routes,
asyncio scanners/CLIs.

**INFERRED:** The product is an advisory + paper-trading workstation with
strategy scanners, not a fully autonomous live execution desk. Live order
tables exist (see §6).

---

# 3 Backtesting Architecture

**OBSERVED:** At least two distinct backtest implementations exist.

## 3.1 Production advisory `BacktestService`

Path: `backend/app/services/backtest_service.py`

- Invoked by `BacktestAgent` and `POST /analysis/backtest`.
- Depends on `ta` RSI/EMA/MACD indicators over supplied OHLCV.
- Cost scenarios `LOW_COST`, `BASE_COST`, `STRESS_COST`.
- Execution models `REALISTIC` and `LEGACY` (FEAT-008). REALISTIC applies
  slippage and next-bar style fills; LEGACY reports gross metrics as primary.
- Position sizer: `PercentEquityPositionSizer`.
- Metrics include total return, CAGR (`calculate_cagr`), max drawdown, win
  rate, profit factor, Sharpe, costs, slippage.

**OBSERVED:** `BacktestAgent.run_async` for swing mode may replace candles with
up to 3 years of `daily_ohlcv` via `fetch_equity_history`.

## 3.2 Strategy book replay (52-Week High Breakout)

Path: `backend/app/services/strategies/breakout52w/`

- `book_engine.replay_book` is the portfolio/session kernel.
- `window_backtest.py` runs on-demand per-symbol windows for the UI.
- Default execution profile `KERNEL`: fill at signal close, close-cross trail.
- Alternate profile `TV_COMPAT`: next-bar open, optional intrabar stop touch.
- Does not call `BacktestService` for the 10-slot book.

**OBSERVED:** Spec `specs/038-52w-high-breakout/execution-parity.md` states the
52W scanner must remain a 10-slot book and must not be replaced by
`BacktestService`.

## 3.3 Other

**OBSERVED:** `walk_forward_service.py` has its own cost/slippage fill loop.

**OBSERVED:** `backtrader==1.9.78.123` is listed in `backend/requirements.txt`.
**UNKNOWN:** Whether any production path currently instantiates Backtrader. No
import was inspected exhaustively.

**OBSERVED:** `recommendation_backtest` module exists under services.

**OBSERVED:** Compiled-only packages visible at inspection:

- `backend/app/services/daily_swing/` listing showed `__pycache__` only
  (position_engine, equity, cost_waterfall, …) and no `.py` sources.
- `backend/app/services/strategies/str005/` listing showed `__pycache__` only.

**UNKNOWN:** Whether those `.py` sources exist elsewhere, are gitignored, or
were omitted from this working tree.

---

# 4 Strategy Architecture

**OBSERVED:** Strategy packages under `backend/app/services/strategies/`:

| Package | Identity (from source) | Role |
|---------|------------------------|------|
| `breakout52w/` | `STRATEGY_ID = "09_52w_breakout"` | 52-week high breakout scanner + book |
| `ltm/` | Long-term momentum (037) | Buy-and-hold momentum scanner + book |

**OBSERVED:** 52W signal (`signal.py` / `identity.py`):

- Universe id `nifty500`, timeframe `1D`
- Buy when market OK, `close >= prior 252-session high` (today excluded),
  `volume > SMA20` (today included), not held, not sold today
- Trail: 3× SMA ATR14, close-cross in KERNEL
- Mode B: 10% of equity, max 10 positions, default capital ₹100,000
- Warmup 252 sessions

**OBSERVED:** Pine golden reference `strategy.pine` is an *indicator* named
`STR-001 | 52W High Breakout Scanner` with the same 252 / volume SMA20 /
NIFTY500 SMA50 / SMA-ATR ideas, but it does not place Strategy Tester orders.

**OBSERVED:** TradingView tester export is labeled `52W Breakout - Test` on
`NSE:WELCORP` with 2954 trades and average 2 bars in trade
(`reports/golden_reference_audit.md`).

**INFERRED:** The golden Strategy Tester export and the Labs 038 kernel are not
the same algorithm. This is also the conclusion already written in
`specs/038-52w-high-breakout/parity-audit-glaxo.md` (prior work; not re-verified
numerically in PART 1).

**OBSERVED:** Recommendation engines `re001/` and `re002/` exist as separate
service packages.

---

# 5 Order Architecture

**OBSERVED:** Paper orders: SQLAlchemy model `PaperOrder` table
`paper_trading_orders` (`backend/app/models/paper_trading.py`). Fields include
side, order_type, qty, order_price, stop_price, stop_loss, target, status,
lifecycle_state, filled_price, filled_at, idempotency_key, scheduled_execution.

Statuses documented in the model comments: PENDING, WAITING_FOR_MARKET,
READY_TO_EXECUTE, FAILED, OPEN, FILLED/EXECUTED, PARTIALLY_EXECUTED,
CANCELLED, REJECTED.

**OBSERVED:** Placement API: `backend/app/routes/paper_trading.py` →
`PaperTradingService.place_order`.

**OBSERVED:** Live orders: `LiveOrder` table `live_orders`
(`backend/app/models/live_trading.py`) with execution_id, requested/filled qty,
order_price, stop_price, idempotency_key, product_type default `CNC`.

**OBSERVED:** 52W book uses in-replay order lifecycle in `execution.py`:
`FLAT → ENTRY_PENDING → LONG → EXIT_PENDING`, not the paper `PaperOrder` table.

**UNKNOWN:** Whether live_orders is wired to a broker send path in the current
branch; tables exist.

---

# 6 Execution Architecture

**OBSERVED:** Three execution domains:

1. **Advisory backtest (FEAT-008)** — `BacktestService` REALISTIC vs LEGACY;
   slippage_rate inside cost scenarios; skip-on-missing-next-bar flag.
2. **52W historical replay** — `ExecutionConfig` with profiles KERNEL /
   TV_COMPAT; fill delays `SAME_BAR_CLOSE` / `NEXT_BAR_OPEN`; trail
   `CLOSE_CROSS` / `INTRABAR_TOUCH`; optional `LOWER_TIMEFRAME` using stored
   lower-TF bars, falling back to daily OHLC without fabricating ticks
   (`execution.py` docstring).
3. **Paper trading** — market-hours gated execution via
   `PaperTradingService` and `trading_hours_service`; pending market-open
   orders.

**OBSERVED:** Settings `w52_execution_profile` default `KERNEL`,
`w52_historical_fill_mode` default `DEFAULT_OHLC`.

**OBSERVED:** Shadow executor interfaces exist (`shadow_executor.py`) behind
feature flags.

**OBSERVED:** FYERS broker client `fyers_apiv3` is a dependency;
`FyersService` is used for market data and paper quotes.

---

# 7 Position Architecture

**OBSERVED:**

- Paper: `PaperPosition` (`paper_trading_positions`) — qty, avg_entry_price,
  realized/unrealized PnL, stop_loss, target, lifecycle_state.
- Live: `LivePosition` (`live_positions`) — unique open position per
  (account, symbol).
- 52W replay: holdings inside `replay_book` / persisted `W52BookState.holdings`
  JSON. No pyramiding in the 52W kernel (`pyramiding: int = 0` on
  `ExecutionConfig`).
- LTM: analogous book state under `ltm_strategy` models.

**OBSERVED:** Settings `portfolio_allow_fractional_shares` default False
(NSE/BSE whole shares). 52W `shares_from_notional` can return fractional
shares unless `whole_shares=True`. **INFERRED:** 52W replay may size with
fractional shares depending on call sites — not fully traced in PART 1.

---

# 8 Portfolio Architecture

**OBSERVED:** Paper account default starting balance ₹1,000,000
(`DEFAULT_PAPER_STARTING_BALANCE`).

**OBSERVED:** 52W book: cash + equity, `DEFAULT_CAPITAL = 100_000.0`,
`ALLOC_PCT = 0.10`, `MAX_POSITIONS = 10`, Mode B substitute-next-ranked
(`portfolio.py`).

**OBSERVED:** Settings FEAT-024B portfolio_* flags are documented in
`settings.py` as a **configuration contract only / NON-BINDING** until later
specs wire consumers. Dual source of truth is called out: `BacktestService`
hardcoded equity 100000.0 remains authoritative for single-asset advisory
backtests.

**OBSERVED:** `W52BookState` persists cash, equity, holdings, pending_orders,
sold_today.

---

# 9 Commission and Slippage

**OBSERVED:** Multiple independent cost models:

| Location | Commission / costs | Slippage |
|----------|--------------------|----------|
| `backtest_service.COST_SCENARIOS` | NSE-like brokerage cap, STT, exchange, SEBI, stamp, GST, DP | `slippage_rate` 0.02% / 0.05% / 0.15% |
| `breakout52w/costs.py` | Published NSE delivery buy/sell waterfall (brokerage min 0.03%/₹20, STT on sell, DP 15.93 on sell, …) | `ExecutionConfig.slippage_rate` default 0.0 |
| Settings FEAT-024A | `commission_fixed` 0.50, `commission_percent` 0.001, `slippage_bps` 5.0 | Documented NON-BINDING until wired |
| Golden TV config | commission 0 percent | 0 ticks |

**OBSERVED:** TradingView Properties sheet: Commission paid 0, slippage 0 ticks.

**INFERRED:** Matching TV rupee PnL on WELCORP 1-share / 0-commission cannot use
the 52W NSE delivery waterfall or BacktestService BASE_COST without an explicit
zero-cost experiment profile.

---

# 10 Historical Data

**OBSERVED:** Strategy-grade store:

- `daily_ohlcv` (equity OHLCV + optional delivery)
- `index_ohlcv` (NIFTY500)
- `historical_candles` (symbol, resolution, timestamp — FYERS default source)
- load tracking `data_load_log`

**OBSERVED:** Ingestion CLI: `python -m app.cli.market_data_cli` with
`full-load`, `daily-update`, `status`, `verify`. Provider `fyers_eod.py`.

**OBSERVED:** Document `docs/BACKTEST_DATA_AVAILABILITY.md` (not re-queried
against the live DB in PART 1) claims local Postgres holds ~18 years
(2008-07-22 → 2026-08-17) for the NIFTY 500 universe.

**OBSERVED:** Golden TV trading range for WELCORP starts 2002-08-22. Labs
documented store starts 2008-07-22. **INFERRED:** A full-history TV vs Labs
compare on WELCORP will be truncated or unmatched before 2008 unless another
source exists.

**UNKNOWN:** Whether WELCORP is in the current NIFTY 500 universe CSV and
whether its `daily_ohlcv` rows were actually loaded in this environment.
PART 1 did not query the database.

**OBSERVED:** Authoritative candle store exists behind feature flags
(`authoritative_candle_store_enabled`, dual-write, fallback).

---

# 11 Performance Metrics

**OBSERVED:** Advisory `BacktestResult` (schemas/analysis) includes total
return, CAGR, max drawdown, win rate, profit factor, Sharpe, trade list,
costs, slippage, FEAT-008 metadata.

**OBSERVED:** 52W ledger (`ledger.py`) classifies winners/losers/breakeven from
**net PnL**, not rounded display percent. Aggregates: total trades, profit
factor, gross profit/loss, commission, payoff, win rate, CAGR via
`calculate_cagr`.

**OBSERVED:** Persisted tester-like columns on `W52SymbolPerformance`
(total_pnl, max_drawdown, profit_factor, win_rate, cagr, commission, …).

**OBSERVED:** TradingView report metrics for Strategy_001 are listed in
`reports/golden_reference_audit.md` (net profit 1278.2, PF 1.186, 2954 trades,
Sharpe -40.6, Sortino -1).

**UNKNOWN:** Formula parity (TradingView Sharpe/Sortino/CAGR vs Labs). Not
computed in PART 1.

---

# 12 Database Dependencies

**OBSERVED:** SQLAlchemy 2.x + Alembic. Primary URL scheme
`postgresql+asyncpg`. Sync engine also created in `db/session.py`.
`backend/alembic/` contains 53 Python version files.

**OBSERVED:** Settings default `database_url` is a PostgreSQL DSN.
**Credential detected — value intentionally hidden.**

**OBSERVED:** Redis URL setting exists (`redis_url`). Mongo URL settings exist
(optional).

**OBSERVED:** 52W tables: `w52_book_state`, `w52_symbol_performance`. LTM
tables in `ltm_strategy.py`. Scan snapshots, latest scan results, paper and
live account/order/position tables.

**OBSERVED:** README Phase 1 mentions SQLite; current settings default is
PostgreSQL. Tests include `test_sqlite_pg_migration.py`.

PART 1 did not run migrations and did not alter data.

---

# 13 Existing Tests

**OBSERVED:** Pytest config: `backend/pytest.ini` (`asyncio_mode = auto`,
`pythonpath = .`). Frontend Vitest + Playwright.

**OBSERVED:** Substantial unit coverage for 52W, including:

`test_w52_alignment.py`, `test_w52_analytics.py`, `test_w52_attribution.py`,
`test_w52_book.py`, `test_w52_book_state.py`, `test_w52_execution.py`,
`test_w52_glaxo_parity.py`, `test_w52_indicators.py`, `test_w52_signal.py`,
`test_w52_trail.py`, `test_w52_window_backtest.py`, `test_w52_scan_*`,
`test_w52_symbol_performance.py`, and others.

**OBSERVED:** `backend/app/tests/test_backtest_realism.py` covers
`BacktestService` costs/execution. `test_w52_execution.py` locks KERNEL vs
TV_COMPAT. `test_w52_glaxo_parity.py` states it locks what the engine actually
does and must not leak TradingView report totals into Labs metrics.

**OBSERVED:** Paper/live/order tests: `test_order_lifecycle.py`,
`test_trading_execution.py`, `test_market_hours_order_lifecycle.py`,
Postgres order execution event tests.

PART 1 did **not** run the production pytest suite (many tests are not
guaranteed read-only against a database).

---

# 14 Existing Backtest Commands

**OBSERVED:**

| Command / endpoint | What it does |
|--------------------|--------------|
| `POST /analysis/backtest` | Advisory `BacktestService` via RouterAgent |
| `GET /api/v1/scanner/w52/symbols/{symbol}?window=&execution_profile=` | Per-name 52W window replay |
| `POST /scanner/w52/runs` | Universe 52W scan / book replay |
| `python -m app.cli.w52_performance_cli collect\|show` | Persist/inspect per-symbol tester metrics |
| `python -m app.cli.market_data_cli full-load\|daily-update\|status\|verify` | Strategy market data |
| `python -m app.governance.experiment_cli …` | Governance experiments (not TV compare) |

**UNKNOWN:** Whether a CLI exists that emits a TradingView-shaped trades.csv
from Labs. None was found in the paths inspected.

---

# 15 Existing Compatibility Features

**OBSERVED:**

- `TV_COMPAT` execution profile (next-bar open + intrabar trail touch)
- Pine screener-shaped signal (`screener_pass`) with a unit test citing a
  TradingView STR-001 print (`test_w52_session_overlay.py`)
- SMA-of-TR ATR (not Wilder) matching the golden `strategy.pine` comment
- Prior-high excludes today (`[1]` / `highs[t-252:t]`)
- Ledger-first tester-like stats and `w52_symbol_performance`
- Specs: `execution-parity.md`, `parity-audit-glaxo.md`
- Frontend W52 boards / order list / backtest dashboard

**OBSERVED:** `execution-parity.md` states TV_COMPAT aligns **broker timing**,
not the unknown TV entry/exit formula, and warns not to force 242/490/860
trade counts onto the 038 kernel.

---

# 16 Potential TradingView Compatibility Gaps

These are **not** PART 1 discrepancy tickets. They are hypotheses for PART 2+.

| Gap | Class | Notes |
|-----|-------|-------|
| Golden `strategy.pine` is `indicator()`, while `trades.csv` / xlsx are Strategy Tester output | OBSERVED | Different Pine kinds in the same folder |
| Tester script name `52W Breakout - Test` / signal `TEST` vs Labs `09_52w_breakout` | OBSERVED | Naming mismatch |
| 2954 trades, average 2 bars vs 252-high hold-until-ATR | OBSERVED from TV report + Labs identity | Incompatible trade frequency if both claim the same rules |
| Capital ₹1,000,000 qty 1 vs Labs ₹100,000 × 10% × 10 | OBSERVED | Sizing |
| Commission 0 / slippage 0 ticks vs NSE delivery costs | OBSERVED | Costs |
| Fill: TV order delay one tick / on_bar_close vs KERNEL same-bar close | OBSERVED | Timing |
| `process_orders_on_close`, `calc_on_order_fills`, `calc_on_every_tick`, `bar_magnifier` are null in test_config | DOCUMENTED | Must not be guessed |
| Data vendor: TV NSE vs FYERS `daily_ohlcv` | OBSERVED as architecture | Bar-for-bar unknown |
| History start 2002 (TV WELCORP) vs documented Labs 2008 | OBSERVED vs documented file | Coverage |
| ATR: Pine file uses SMA TR; TV `ta.atr` elsewhere is Wilder | OBSERVED in Pine + Labs comments | Tester script ATR unknown because tester Pine is not this indicator |
| Two Labs engines (`BacktestService` vs `replay_book`) | OBSERVED | Which one HERMES should compare must be chosen explicitly |
| Fractional vs whole shares in 52W sizing | INFERRED | Needs call-site verification |
| Sharpe/Sortino definitions | UNKNOWN | TV Sharpe -40.6 is extreme; formula not researched |

---

# 17 Risks

**OBSERVED / INFERRED:**

1. Treating the indicator Pine as the strategy that produced 2954 trades will
   send research in the wrong direction.
2. Optimizing Net Profit (TV 1278.2 on ₹10L) without trade identity will overfit.
3. Changing KERNEL to match TV would break 038 fixtures (`test_w52_*`).
4. Live order tables + FYERS tokens make accidental live sends a real hazard;
   HERMES blocks live broker orders.
5. Multiple cost models; silent mixing will create false discrepancies.
6. Database credentials exist in compose/settings/env; Hermes must not copy them.
7. Unrelated dirty work: at PART 1 start, `git status` showed only untracked
   `hermes-research/`. Do not revert or stash other user work in later parts.
8. Compiled-only `daily_swing` / `str005` trees may hide execution behavior
   that is not reviewable as source in this listing.

---

# 18 Recommended Next Steps

For **PART 2 — TRADINGVIEW RESEARCH ENGINE** (do not start until authorized):

1. Document TradingView Strategy Tester and broker-emulator behavior from
   **official** docs only, classified as DOCUMENTED vs UNKNOWN.
2. Separate two research tracks:
   - Track A: STR-001 **indicator/screener** vs Labs `screener_pass`.
   - Track B: Strategy Tester export `52W Breakout - Test` vs a Labs engine
     still to be designated (do not assume `replay_book` is the counterpart).
3. Confirm whether a `strategy()` Pine for `TEST` exists anywhere; if not,
   mark entry/exit formula UNKNOWN and stop guessing.
4. Design (not implement unless PART 2 asks) a read-only parser for
   `trades.csv` and a first-divergence comparator per `config/comparison.yaml`.
5. Do not modify production engines. Do not run live trades. Do not migrate.

---

## PART 1 explicit non-actions

- Production backtesting code was not modified.
- TradingView golden reference files were not modified.
- Live trading code was not modified.
- Database schema was not modified.
- Comparison engine was not implemented.
