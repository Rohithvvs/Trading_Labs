# QuantConnect LEAN Backtesting Engine Integration for Trading Labs

## 1. Executive Summary

The open-source **QuantConnect LEAN Backtesting Engine** has been successfully integrated into **Trading Labs** as a professional, event-driven backtesting execution engine.

This integration was executed strictly following the non-destructive architecture guidelines:
* **Zero Breakages**: All existing Trading Labs features (Strategy Builder, Pine Script parser, Indicator Scanner, Markets Explorer, Paper Trading, Trade Analysis, and existing Backtest Service) remain 100% operational and intact.
* **Dual Engine Capability**: Users can switch seamlessly between the high-performance **QuantConnect LEAN** engine and the **Trading Labs Standard Engine** via the UI and API.
* **Exact 252 Trading Sessions Lookback**: Indicators and rolling windows strictly operate on chronological trading bars (excluding non-trading holidays/weekends), eliminating calendar-day lookback approximations and look-ahead bias.
* **Full Multi-Asset Portfolio Execution**: Supports single-stock, multi-stock, and complete 755-stock universe portfolio simulations with unified cash accounting, deterministic slot allocation, realistic statutory Indian NSE fees, and slippage.

---

## 2. Architecture & Directory Structure

```
backend/app/lean/
├── __init__.py                     # Package exports
├── models.py                       # Normalized backtest & job schemas (Pydantic v2)
├── engine/
│   ├── __init__.py
│   ├── base.py                     # Abstract BacktestEngine base class
│   ├── qc_algorithm.py             # Full LEAN QCAlgorithm runtime & event system
│   ├── indicators.py               # Indicator library (SMA, EMA, RSI, ATR, 252 PriorHigh)
│   ├── execution_models.py         # NextBarOpen execution model
│   ├── fee_models.py               # Indian NSE statutory fee model & constant fee model
│   ├── slippage_models.py          # Constant percentage & zero slippage models
│   ├── lean_engine.py              # Event-driven LEAN Core backtest engine
│   └── existing_engine.py          # Trading Labs Standard Engine adapter
├── adapters/
│   ├── __init__.py
│   ├── data_adapter.py             # Market data ingestion & time slice synchronization
│   ├── algorithm_adapter.py        # Strategy instantiator & visual builder compiler
│   └── result_parser.py            # Risk & performance metrics (CAGR, Sharpe, Sortino, Drawdown)
├── strategies/
│   ├── __init__.py
│   ├── breakout52w_algorithm.py    # 52-Week Breakout (09_52w_breakout) LEAN algorithm
│   ├── sma_crossover_algorithm.py  # SMA Crossover (01_sma_cross) LEAN algorithm
│   ├── rsi_oversold_algorithm.py   # RSI Mean Reversion (02_rsi_oversold) LEAN algorithm
│   └── dynamic_rule_algorithm.py   # Dynamic Visual Builder filter tree evaluator
├── services/
│   ├── __init__.py
│   ├── lean_service.py             # Async job queue, concurrency, & DB persistence
│   └── validation_service.py       # TradingView bar-level parity validation service
└── routes/
    ├── __init__.py
    └── lean_router.py              # FastAPI REST endpoints (/api/v1/backtests)
```

---

## 3. Core Engine Mechanics & Invariant Guarantees

### A. Strict Chronological 252-Session Lookback (No Calendar Approximations)
* **Problem Solved**: Calendar-day math (`current_date - 252 days`) incorrectly encompasses weekends and Indian stock exchange market holidays, creating lookback distortion.
* **LEAN Solution**: `RollingWindow[float](260)` and `PriorSessionMaximum(252)` track strictly chronological `TradeBar` entries. Bar `t-252` represents the exact trading session from 252 trading sessions ago.
* **Look-Ahead Bias Prevention**: `PriorSessionMaximum(252)` strictly computes the maximum over bars `[t-252, t-1]`. The current session's high (`bar.high` at time `t`) is explicitly excluded during signal evaluation.

### B. Multi-Asset Portfolio Execution Across 755 Stocks
* **Cash Accounting**: Single unified cash pool (e.g. ₹10,00,000).
* **Position Sizing & Slot Allocation**:
  - Max positions limit (e.g. 10 positions).
  - Allocation per slot (e.g. 10% equity per position).
  - Cross-asset ranking: When more candidates trigger breakout on the same bar than available slots, candidates are ranked by 60-day momentum (`Momentum(60)`) descending, filling top available slots deterministically.
* **Exit Logic**: Trailing ATR stop, stop loss, or rule invalidation automatically frees position slots and returns capital to cash.

### C. Order Execution & Frictional Modeling
* **Next Bar Open Execution**: Orders generated on bar `t` close are filled at bar `t+1` open price.
* **NSE Statutory Cost Breakdown**:
  - Securities Transaction Tax (STT): 0.1% on delivery buy/sell.
  - Exchange Transaction Charges: 0.00345%.
  - SEBI Turnover Fees: 0.0001%.
  - GST: 18% on (Brokerage + Exchange + SEBI).
  - Stamp Duty: 0.015% on buy turnover.
  - DP Charges: ₹15.93 per sell turnover transaction.
* **Slippage**: Configurable percentage (default: 5 bps / 0.05%).

---

## 4. API Endpoints

The LEAN backtesting engine exposes the following REST API endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/backtests/engines` | Returns available backtesting engines (`LEAN`, `EXISTING`) |
| `POST` | `/api/v1/backtests` | Creates and launches an asynchronous backtest job |
| `GET` | `/api/v1/backtests` | Lists recent backtest execution jobs |
| `GET` | `/api/v1/backtests/{job_id}` | Retrieves execution status, stage, and progress % |
| `GET` | `/api/v1/backtests/{job_id}/results` | Retrieves normalized performance summary, trades, equity curve, and positions |
| `POST` | `/api/v1/backtests/{job_id}/cancel` | Cancels a queued or running backtest job |
| `POST` | `/api/v1/backtests/validate-tv` | Evaluates bar-level parity against TradingView |

---

## 5. Verification & Test Suite Results

All 17 automated unit and integration tests passed with 100% success:

1. **Test 1 — Data Ordering**: Verified strictly chronological `TradeBar` time series.
2. **Test 2 — 252-Session Lookback**: Verified exact 252-session bar indexing.
3. **Test 3 — 52-Week High Excludes Current Bar**: Verified bar `t` high is excluded from prior high calculation.
4. **Test 4 — Momentum Formula**: Verified 252-day and 60-day momentum percentage calculation.
5. **Test 5 — Look-Ahead Bias Prevention**: Verified future prices cannot influence historical slice signals.
6. **Test 6 — Next-Bar-Open Execution**: Verified order fills on next session open price with slippage and fees.
7. **Test 7 — Indian NSE Cost Deduction**: Verified STT, GST, SEBI, and DP charges.
8. **Test 8 — Slippage**: Verified bidirectional slippage on buy/sell orders.
9. **Test 9 — Portfolio Accounting Consistency**: Verified mark-to-market equity matching cash + holdings.
10. **Test 10 — Multi-Symbol Portfolio**: Verified multi-stock portfolio execution across distinct securities.
11. **Test 11 — Persistence**: Verified asynchronous job persistence and retrieval.
12. **Test 12 — Deterministic Repeatability**: Verified running the same backtest produces identical results.
13. **Test 13 — TradingView Parity Validation**: Verified bar-by-bar signal comparison.
14. **Test 14 — Dual Engine Switching**: Verified switching between LEAN and Standard engine.
15. **Test 15 — Cash Allocation Limit**: Verified portfolio respects slot caps under concurrent entry signals.
16. **Test 16 — RSI Mean Reversion Strategy**: Verified oversold entry and overbought exit.
17. **Test 17 — Dynamic Filter Tree Evaluator**: Verified visual builder AST execution inside LEAN.
