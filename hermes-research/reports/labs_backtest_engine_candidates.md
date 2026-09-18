# Labs Backtest Engine Candidates

**Question:** which Trading Labs engine, if any, should reproduce TradingView `52W Breakout - Test`?

**Answer as of this investigation:** none is verified. Track B Pine is missing, so no engine is authorized for comparison.

Do not modify any engine.

---

## 1. `BacktestService` (advisory analysis backtest)

| Field | Value |
|-------|--------|
| Path | `backend/app/services/backtest_service.py` |
| Entry point | `BacktestService.run` via `BacktestAgent` / `POST /analysis/backtest` |
| Strategy input | Hardcoded `sma_rsi_macd` (swing) or `ema_rsi_volume` (intraday) — EMA/RSI/MACD/volume rules |
| Data source | Caller-supplied OHLCV; swing agent may load ~3Y `daily_ohlcv` |
| Timeframe | Analysis mode (intraday vs swing), not locked to 1D WELCORP tester |
| Execution model | FEAT-008 `REALISTIC` / `LEGACY` |
| Order model | Implicit long flat/entry/exit in a candle loop; not TV broker emulator |
| Position model | `PercentEquityPositionSizer`; default 20% of ₹100,000 |
| Commission | `COST_SCENARIOS` NSE-like waterfall |
| Slippage | scenario `slippage_rate` (e.g. BASE_COST 0.05%) |
| Sizing | percent equity, not qty=1 |
| Output | `BacktestResult` trades/metrics JSON |
| Can reproduce a 52W strategy? | No — different entry/exit family |
| Class | **NOT_CANDIDATE** for `52W Breakout - Test` |

---

## 2. 52W book replay (`breakout52w`)

| Field | Value |
|-------|--------|
| Path | `backend/app/services/strategies/breakout52w/` |
| Entry points | `book_engine.replay_book`; `window_backtest.run_symbol_window_backtest`; `GET /scanner/w52/symbols/{symbol}`; `POST /scanner/w52/runs`; `python -m app.cli.w52_performance_cli` |
| Strategy input | `09_52w_breakout` kernel: 252-high, vol SMA20, market SMA50, 3×SMA-ATR trail, Mode B 10%×10 |
| Data source | `daily_ohlcv` + `index_ohlcv` (FYERS EOD load) |
| Timeframe | `1D` |
| Execution model | `KERNEL` (same-bar close) or `TV_COMPAT` (next-bar open / intrabar stop) |
| Order model | in-replay `FLAT → ENTRY_PENDING → LONG`; pyramiding 0; no same-session rebuy |
| Position model | up to 10 names, 10% of equity (default capital ₹100,000) |
| Commission | NSE delivery `costs.py` (unless `apply_costs=False`) |
| Slippage | `ExecutionConfig.slippage_rate` default 0.0 |
| Sizing | not 1-share TV tester |
| Output | blotter / ledger / dashboard JSON; optional `w52_symbol_performance` |
| Can reproduce a 52W strategy? | Can reproduce **Labs 038 / Track A book**, not the unknown tester formula |
| Class | **CANDIDATE** for Track A Labs product only. **NOT_CANDIDATE** for Track B until Pine is known and shown to be this kernel (current CSV duration/count evidence says it is not). |

---

## 3. LTM book (`ltm`)

| Field | Value |
|-------|--------|
| Path | `backend/app/services/strategies/ltm/` |
| Entry point | LTM scan / book replay |
| Strategy input | 252-session momentum, 10-name hold, rebalance every 252 |
| Data source | `daily_ohlcv` / `index_ohlcv` |
| Timeframe | daily |
| Can reproduce a 52W strategy? | No |
| Class | **NOT_CANDIDATE** |

---

## 4. Walk-forward service

| Field | Value |
|-------|--------|
| Path | `backend/app/services/walk_forward_service.py` |
| Entry point | walk-forward routes/service |
| Strategy input | Uses `COST_SCENARIOS` and similar EMA-style loop (sibling of advisory backtest) |
| Class | **NOT_CANDIDATE** for the TV tester |

---

## 5. Paper trading

| Field | Value |
|-------|--------|
| Path | `backend/app/services/paper_trading_service.py` |
| Entry point | `place_order` / market-hours executor |
| Purpose | live-session paper orders, not historical Strategy Tester replay |
| Class | **NOT_CANDIDATE** |

---

## 6. Compiled-only / source-missing modules

These listings showed `__pycache__` only at inspection (no `.py` in tree):

- `backend/app/services/daily_swing/` (position_engine, cost_waterfall, …)
- `backend/app/services/strategies/str005/`
- `backend/app/services/re001/`, `re002/`
- `recommendation_backtest.cpython-*.pyc` without `recommendation_backtest.py`
- `strategies/__pycache__/universe_backtest.cpython-*.pyc` without `.py`

| Class | **UNKNOWN** as implementations; **not usable as verified tester counterparts** |

---

## 7. Backtrader dependency

`backtrader==1.9.78.123` is in `backend/requirements.txt`. No production import path was found in the files inspected.

| Class | **UNKNOWN** (likely unused) |

---

## Designation rule

HERMES will not pick an engine for Track B comparison until:

1. Exact tester Pine is verified, **and**
2. The user names the Labs engine (or explicitly authorizes a new research harness).
