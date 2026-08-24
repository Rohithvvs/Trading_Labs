# 52-Week High Breakout — stored Strategy Tester metrics

Per-stock TradingView-style backtest statistics for the **755-name NIFTY 500 universe**, computed from **closed 52-Week High Breakout trades** over the stored **18-year daily history** and saved in PostgreSQL.

Opening a name on the Backtest tab reads these rows. Win/loss counts are not assumed from signals or open marks.

Strategy id: `09_52w_breakout`  
Source of truth: closed-trade ledger (`source = closed_trade_ledger`)  
Daily bars: `daily_ohlcv` (see [BACKTEST_DATA_AVAILABILITY.md](BACKTEST_DATA_AVAILABILITY.md))

---

## What is stored (TradingView Strategy Tester fields)

| Field | Column | Notes |
|---|---|---|
| Total P&L | `total_pnl` | Net rupee P&L of closed trades |
| Max Drawdown | `max_drawdown` | Percent |
| Max Drawdown (₹) | `max_drawdown_inr` | Rupee peak-to-trough |
| Total Trades | `total_trades` | Closed fills only |
| Profitable Trades | `profitable_trades` | Net P&L > 0 |
| Losing Trades | `losing_trades` | Net P&L < 0 |
| Breakeven | `breakeven` | Net P&L = 0 (within tolerance) |
| Profit Factor | `profit_factor` | Gross profit / abs(gross loss); `profit_factor_infinite` when no losses |
| Gross Profit | `gross_profit` | Sum of winning trade P&L |
| Gross Loss | `gross_loss` | Sum of losing trade P&L (negative) |
| Commission | `commission` | Total commission on closed trades |
| Expected Payoff | `expected_payoff` | Average trade return (%) |
| Expected Payoff (₹) | `expected_payoff_inr` | Average trade P&L |
| Largest Profit | `largest_profit` | Best winning trade (%) |
| Largest Loss | `largest_loss` | Worst losing trade (%) |
| Largest Profit (₹) | `largest_profit_inr` | |
| Largest Loss (₹) | `largest_loss_inr` | |
| Average Winning Trade | `average_winning_trade` | Mean winner return (%) |
| Average Losing Trade | `average_losing_trade` | Mean loser return (%) |
| Average Winning Trade (₹) | `average_winning_trade_inr` | |
| Average Losing Trade (₹) | `average_losing_trade_inr` | |
| Outlier P&L | `outlier_pnl` | P&L of trades beyond 3 population stdevs |
| Outlier trades | `outlier_trades` | Count of those outliers |

Also stored: `win_rate`, `total_return`, `cagr`, `initial_capital`, `ending_capital`, period dates, `data_hash`, closed-trade blotter (`trades` JSONB), and full `ledger` JSONB.

Open positions are **not** counted as profit or loss trades.

---

## Table

`w52_symbol_performance`

Unique key: `(strategy_id, symbol, window, execution_profile)`

Windows collected for every name:

`1Y` · `3Y` · `5Y` · `8Y` · `18Y` · `ALL`

`ALL` is the full stored history (from first available bar, typically 22 Jul 2008). `18Y` is the last 18 calendar years from the evaluation date.

---

## First collect (21 Aug 2026)

Replay used the 18-year daily store. One full-history replay per stock; the six windows were sliced from that blotter.

| | |
|---|---|
| Symbols processed | **755 / 755** |
| Failed | **0** |
| Skipped (already hashed) | **1** (`RELIANCE-EQ`, collected first as a smoke test) |
| Rows stored | **4,530** (755 × 6 windows) |
| Evaluation date | 2026-08-21 |
| Execution profile | `KERNEL` |

### ALL window

| | |
|---|---|
| Names with real closed trades | **662** (`status = ok`) |
| Never selected in 18 years | **85** (`status = never_selected`) |
| Insufficient history | **8** (`status = insufficient_history` — dummy / invalid FYERS names) |
| Closed trades | **7,581** |
| Profitable | **3,444** |
| Losing | **4,137** |
| Breakeven | **0** |

### Sample ALL-window rows

| Symbol | Trades | Profitable | Losing | Breakeven | Total P&L |
|---|---:|---:|---:|---:|---:|
| RELIANCE-EQ | 21 | 7 | 14 | 0 | ₹456.73 |
| TCS-EQ | 20 | 9 | 11 | 0 | ₹1,418.50 |
| IIFL-EQ | 13 | 7 | 6 | 0 | ₹13,799.26 |
| GLAXO-EQ | 13 | 5 | 8 | 0 | ₹−359.44 |

RELIANCE-EQ ALL detail (18 years, 4,497 candles, 2008-07-22 → 2026-08-21):

- Max drawdown −3.78% (₹−3,837.65)
- Profit factor 1.20
- Gross profit ₹7,338.87 · Gross loss ₹−6,882.15
- Commission ₹743.87
- Expected payoff +0.26% (₹21.75)
- Largest profit +27.91% · Largest loss −9.82%
- Average winning trade +10.58% · Average losing trade −4.90%
- Outlier P&L ₹2,776.51 (1 trade)

---

## Look up a stock

### SQL

```sql
SELECT
  symbol,
  window,
  period_start,
  period_end,
  total_pnl,
  max_drawdown,
  total_trades,
  profitable_trades,
  losing_trades,
  breakeven,
  profit_factor,
  gross_profit,
  gross_loss,
  commission,
  expected_payoff,
  largest_profit,
  largest_loss,
  average_winning_trade,
  average_losing_trade,
  outlier_pnl
FROM w52_symbol_performance
WHERE symbol = 'RELIANCE-EQ'
  AND window = 'ALL';
```

All windows for one name:

```sql
SELECT window, total_trades, profitable_trades, losing_trades, breakeven, total_pnl
FROM w52_symbol_performance
WHERE symbol = 'RELIANCE-EQ'
ORDER BY window;
```

### API

Requires Scanner access.

```http
GET /scanner/w52/performance/RELIANCE-EQ
GET /scanner/w52/performance/RELIANCE-EQ?window=ALL
GET /scanner/w52/symbols/RELIANCE-EQ?window=ALL
```

`GET /scanner/w52/symbols/{symbol}` serves the Backtest tab. If a stored row exists for that window, it is returned without replaying 18 years. Pass `refresh=true` to recompute and overwrite.

Response includes `strategy_tester` with the fields above.

### CLI

From `backend/`:

```bash
python -m app.cli.w52_performance_cli show RELIANCE-EQ
python -m app.cli.w52_performance_cli show RELIANCE-EQ --window ALL
python -m app.cli.w52_performance_cli show RELIANCE-EQ --window ALL --with-trades
```

---

## Collect / refresh

After new daily bars are loaded, re-run collect. Matching `data_hash` skips a name; `--force` recomputes everything.

```bash
# Full universe (active NIFTY 500)
python -m app.cli.w52_performance_cli collect --concurrency 4

# Force recompute
python -m app.cli.w52_performance_cli collect --force

# One or more names
python -m app.cli.w52_performance_cli collect --symbols RELIANCE-EQ,TCS-EQ --force

# Subset of windows
python -m app.cli.w52_performance_cli collect --windows ALL,18Y

# Cap for a trial run
python -m app.cli.w52_performance_cli collect --limit 10
```

Same entry point: `python backend/scripts/collect_w52_symbol_performance.py collect`

Alembic revision: `20260821_w52_symbol_performance`  
Model: `app.models.w52_strategy.W52SymbolPerformance`  
Collector: `app.services.strategies.breakout52w.performance_store`

---

## Rules

1. Statistics are computed only from **simulated fills** (closed trades), never from scan signals.
2. An open mark-to-market lot is not a winner, loser, or breakeven.
3. `profitable_trades + losing_trades + breakeven = total_trades`.
4. Custom date ranges on the Backtest tab are **not** written to this table (they would overwrite `CUSTOM`).
5. Names with no 52W book trades in the window are stored as `never_selected` with zero trades — not invented P&L.
6. Dummy / invalid FYERS symbols (no `daily_ohlcv`) are stored as `insufficient_history`.
