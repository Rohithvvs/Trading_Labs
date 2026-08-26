# Golden Reference Audit

**Audit timestamp (UTC):** 2026-08-24T06:44:30.205632+00:00  
**Root:** `hermes-research/tradingview_reference/`  
**Integrity manifest:** `hermes-research/state/reference_manifest.json`  
**Files modified during this audit:** none (read-only)

Evidence classes: `DOCUMENTED` (from the golden files themselves), `OBSERVED` (file metadata), `INFERRED`, `UNKNOWN`.

---

## Strategy directories found

One directory:

- `Strategy_001`

---

## Strategy_001 — file presence

| Expected file | Present | Size (bytes) | SHA256 |
|---------------|---------|--------------|--------|
| `strategy.pine` | yes | 2825 | `6b715e65ad06bcf6aa5c7346f7bd735c3e571c261cbff218cfbb57275f452128` |
| `strategy_report.xlsx` | yes | 1294346 | `21d5fbad0e6da329f9160a166d3c7003525cce55fea1654a7e7c2690a1f8f7ea` |
| `trades.csv` | yes | 582713 | `069153b3ce3fe0287730892794d5558122004fdbda6d9738ba48fc69d103f1b7` |
| `test_config.yaml` | yes | 986 | `e4c18fd33d717b7c31fbc58c1c41aaac741bf2d4fefe47b75b1439b2ee5be9c2` |

**OBSERVED:** All four expected files exist. No extra files were listed in this directory.

The XLSX was **not converted**. Sheet names and cell values were read in memory from the Open XML zip for audit metadata only. The file on disk was not rewritten.

---

## strategy.pine

**OBSERVED:**

- First line: `//@version=6`
- 129 lines
- Declares `indicator("STR-001 | 52W High Breakout Scanner", overlay=false)`
- Does **not** declare `strategy(`
- Parameters in source: `LOOKBACK_52W = 252`, `VOLUME_LENGTH = 20`, `ATR_LENGTH = 14`, `MARKET_SMA_LENGTH = 50`, `ATR_MULTIPLIER = 3.0`
- Breakout reference: `ta.highest(high, LOOKBACK_52W)[1]`
- Volume: `volume > ta.sma(volume, 20)`
- ATR: SMA of True Range, with a comment that this is not `ta.atr(14)`
- Market filter: `request.security("NSE:CNX500", "1D", ...)`
- Plots screener flags (signal / breakout / volume / market) and series

**INFERRED:** This file is a Pine *screener/indicator*, not the Strategy Tester script that produced `trades.csv` / `strategy_report.xlsx`.

**UNKNOWN:** Whether a separate `strategy()` Pine for "52W Breakout - Test" exists outside this tree.

---

## test_config.yaml

**DOCUMENTED** (file contents, unmodified):

| Field | Value |
|-------|--------|
| strategy_name | `52W Breakout - Test` |
| symbol | `NSE:WELCORP` |
| timeframe | `1D` |
| backtest.mode | `deep_backtesting` |
| start_date | `2000-06-23` |
| end_date | `2026-08-24` |
| initial_capital | `1000000` INR |
| default_order_size | `1` quantity |
| pyramiding | `1` |
| bar_detailization | `default` |
| ticks_per_bar | `4` |
| script_execution | `on_bar_close` |
| order_execution_delay | `one_tick` |
| commission | `0` percent |
| slippage | `0` ticks |
| limit_order_execution | `requested_price` |
| process_orders_on_close | `null` (explicitly not guessed) |
| calc_on_order_fills | `null` |
| calc_on_every_tick | `null` |
| bar_magnifier | `null` |

---

## trades.csv

**OBSERVED:**

- Encoding: UTF-8 with BOM
- Header + 5908 data rows (5909 lines including header)
- 2954 `Entry long` rows and 2954 `Exit long` rows
- Trade numbers `1` through `2954`
- Columns: `Trade number`, `Type`, `Date and time`, `Signal`, `Price INR`, `Size (qty)`, `Size (value)`, `Net PnL INR`, `Return %`, `Commission INR`, `Favorable excursion INR`, `Favorable excursion %`, `Adverse excursion INR`, `Adverse excursion %`, `Cumulative PnL INR`, `Cumulative PnL %`, `Duration (bars)`
- Date values present: min `2002-08-22`, max `2026-08-24`
- First row datetime in file order: `2002-09-03` (an Exit long)
- Last row datetime in file order: `2026-08-21`
- Unique Signal values: `TEST`, `Close entry(s) order TEST`

**INFERRED:** CSV is a long-only Strategy Tester trade list for a script whose order comment/signal name is `TEST`, with quantity 1 visible on the first rows.

**UNKNOWN:** Whether every price/qty/PnL in later rows remains 1-share / 0 commission without a full scan. First rows show commission `0` and size `1`; this was not exhaustively re-aggregated here.

---

## strategy_report.xlsx

**OBSERVED** (Open XML, read-only):

- Produced by application metadata `SheetJS`
- Sheets: `Performance`, `Trades analysis`, `Risk-adjusted performance`, `Trades`, `Properties`

**Properties sheet (DOCUMENTED from cells):**

| Property | Value |
|----------|--------|
| Trading range | Aug 22, 2002 — Aug 24, 2026 |
| Backtesting range | Jun 23, 2000 — Aug 24, 2026 |
| Symbol | NSE:WELCORP |
| Timeframe | 1 day |
| Currency | INR |
| Tick size | 0.10 |
| Initial capital | 1000000 |
| Default order size | 1 contracts |
| Pyramiding | 1 orders |
| Bar detalization | Default (4 ticks per bar) |
| Script execution | On bar close |
| Commission | 0 |
| Slippage | 0 ticks |
| Order execution delay | One tick |
| Limit order execution | Requested price |
| Long/short leverage | 1x / 1x |

**Performance sheet (DOCUMENTED from cells, All / Long):**

| Metric | Value |
|--------|--------|
| Initial capital | 1000000 |
| Open PnL | 0 |
| Net profit | 1278.2 (0.13%) |
| Gross profit | 8147 (0.81%) |
| Gross loss | 6868.8 (0.69%) |
| Commission paid | 0 |
| Buy and hold PnL | 144955417.2 |
| Max contracts held | 1 |
| Annualized return (CAGR) | 0 (as stored in the % cell) |
| Max drawdown (close-to-close) | 627 (0.06%) |
| Max drawdown (intrabar) | 627.4 (0.06%) |

**Trades analysis sheet:**

| Metric | Value |
|--------|--------|
| Total open trades | 0 |
| Total trades | 2954 |
| Total winners | 1352 |
| Total losers | 1449 |
| Even trades | 153 |
| Percent profitable | 45.77 |
| Average PnL | 0.43 |
| Average bars in trades | 2 |

**Risk-adjusted performance sheet:**

| Metric | Value |
|--------|--------|
| Sharpe ratio | -40.6 |
| Sortino ratio | -1 |
| Profit factor | 1.186 |

**INFERRED:** Total trades 2954 matches 2954 entry/exit pairs in `trades.csv`. Properties match `test_config.yaml` on symbol, timeframe, capital, commission 0, slippage 0, one-tick delay.

**UNKNOWN:** Exact TradingView build/export pipeline beyond SheetJS metadata. Whether Sharpe/Sortino here use TradingView's current published formulas.

---

## Integrity policy

Future hash mismatch against `state/reference_manifest.json`:

1. Status `REFERENCE_CHANGED`
2. Do not auto-replace
3. User confirmation required before comparisons that depend on the file
