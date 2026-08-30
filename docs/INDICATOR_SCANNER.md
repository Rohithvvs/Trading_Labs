# TradingLabs Pine-compatible Indicator Scanner

For research and paper-trading only. Not investment advice. A technical scan is not a guarantee of returns. Verify signals and account for liquidity, corporate actions, split-adjusted data, data delays, and risk management.

## What it is

The **Indicator** tab on Strategy Tester is a **Pine-compatible subset scanner**, not a full Pine Script runtime.

| Surface | Purpose |
|---|---|
| Strategy Builder | Visual filter rules that the Strategy Tester engine evaluates. |
| Pine Script tab | Translates a strategy script into Builder filters. It does **not** execute Pine. |
| Indicator tab | Validates a **whitelist Pine subset**, saves an indicator, and **scans the 755-stock universe server-side**. |

TradingLabs does **not** claim full Pine Script compatibility. Arbitrary Pine is never executed (`eval` / `exec` / dynamic code execution are forbidden). The engine tokenizes, parses, and evaluates a constrained AST.

## How to use

1. Open **Strategy Tester**.
2. Switch to **Indicator Scanner**, or open **New Strategy** and choose the **Indicator** tab.
3. Universe defaults to **755 Stocks**.
4. Click **Add Indicator**.
5. Name the indicator (default template: **52-Week High Breakout [SCAN]**).
6. Timeframe defaults to **1D** (the only fully supported timeframe).
7. Paste or keep the template Pine-subset code.
8. Click **Observe** to absorb plot columns and screen rules from the code.
9. Review absorbed columns (for example Close, Prior 252 High) and rules (for example `52W Breakout Signal = 1`).
10. Click **Apply**.
11. Click **Run Scan**.
12. Review stocks that satisfied every absorbed rule, open a stock for details, or **Export CSV**.

## Data requirements

- Daily OHLCV from the existing TradingLabs store (`daily_ohlcv` + live overlay).
- Minimum history: the compiler reports **required bars**. The 52-week template needs **at least 253** daily bars (`ta.highest(high, 252)[1]`). Scans fetch a buffer of about **400** bars.
- Benchmark **NSE:CNX500** maps to the strategy index store (typically `NIFTY500`). It is loaded **once per scan** and aligned to each stock by trading date with **no look-ahead**.
- **As of** is the last completed daily bar date used for each symbol.
- Missing or short history marks the symbol `insufficient_history` instead of crashing the scan.

Universe (755 tradable names) is **not** the same as the NIFTY 500 benchmark. The scan set is the configured live universe; the market gate uses CNX500/NIFTY500.

## Supported Pine-compatible subset (v1)

- `//@version=6` and `indicator(title, overlay=...)`
- `input.int/float/bool/string/symbol`
- `open high low close volume`, `timeframe.period`, `close[1]`-style integer indexes
- Arithmetic, comparisons, `and` / `or` / `not`, ternary `?:`, `na`
- `math.max/min/abs/round/floor/ceil`
- `ta.sma ema rma highest lowest atr rsi crossover crossunder`
- `na()`, `nz()`
- `request.security(symbol, timeframe.period, close or ta.sma(close, n))` — same-timeframe daily only, no nested security, no look-ahead
- `plot`, `plotshape`, `alertcondition` (visual args parsed and ignored)

Rejected with a line-specific error: `strategy()`, loops, user functions, `var`/`varip`, arrays/maps, drawing APIs, `request.security_lower_tf` / financial / earnings / dividends, dynamic indexes, unsupported functions.

## Performance

Scans run **on the server**, not in the browser. Market data is loaded in bulk, the benchmark is reused, symbols are evaluated with bounded concurrency, and results are paginated. Rate-limit: 5 scan starts per user per minute.

## Intentional limitations

- Daily (1D) only. 1W/1M are reserved in the UI.
- Input overrides are accepted by the API but the UI uses source defaults.
- `scan_date` is accepted by the API for a later historical mode; the UI scans the latest completed bar.
- Overlay/style/colors are not rendered on a chart.
- This is a subset, not TradingView Pine.

## API

- `POST /indicators/validate`
- `POST /indicators` · `GET /indicators` · `GET/PUT /indicators/{id}` · `POST /indicators/{id}/duplicate` · `DELETE /indicators/{id}`
- `POST /indicators/{id}/scans`
- `GET /indicator-scans/{scanId}` · `.../results` · `.../results/export` · `.../diagnostics` · `POST .../cancel`
