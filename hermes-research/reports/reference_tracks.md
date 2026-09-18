# Reference Tracks

Do not merge these tracks. They are different objects.

---

## TRACK A — STR-001 indicator / screener

| Field | Content | Class |
|-------|---------|--------|
| Name | `STR-001 \| 52W High Breakout Scanner` | OBSERVED |
| Source | `hermes-research/tradingview_reference/Strategy_001/strategy.pine` | OBSERVED |
| Type | Pine v6 `indicator()` | OBSERVED |
| Purpose | Pine Screener flags: signal, breakout, volume OK, market OK, plus series plots | OBSERVED |
| Signals | `close >= prior252High` AND `volume > SMA20` AND NIFTY500 (`NSE:CNX500`) close > SMA50 | OBSERVED |
| Execution | none (no orders) | OBSERVED |
| Available evidence | Pine source; Labs `screener_pass` / `buy_signal` in `breakout52w/signal.py`; unit test citing a TV STR-001 print | OBSERVED |
| Related Labs engine | `09_52w_breakout` book (`breakout52w`) — **additional** trail, 10-slot sizing, NSE costs, not in this Pine | OBSERVED |
| Naming collision | Drive strategy library STR-001 = “Trend Pullback Continuation”; library STR-007 = “52-Week High Breakout”. Golden Pine uses STR-001 for 52W scanner. | OBSERVED |
| Status | **identified** as an indicator. Not a Strategy Tester source. |

---

## TRACK B — 52W Breakout - Test strategy / tester

| Field | Content | Class |
|-------|---------|--------|
| Name | `52W Breakout - Test` | DOCUMENTED in `test_config.yaml` |
| Source | **missing** (`strategy()` Pine not found) | OBSERVED |
| Type | TradingView Strategy Tester `strategy()` (inferred from existence of tester export) | INFERRED |
| Purpose | Produce the exported trade list / performance report | INFERRED |
| Signals | Order comment `TEST`; long only; almost all 1-bar duration | OBSERVED from CSV |
| Execution | on_bar_close, one_tick delay, qty 1, commission 0, slippage 0, capital ₹10,00,000, WELCORP 1D, deep backtesting | DOCUMENTED |
| Available evidence | `trades.csv`, `strategy_report.xlsx`, `test_config.yaml` | OBSERVED |
| Related Labs engine | **none designated**. Do not assume `replay_book` or `BacktestService`. | OBSERVED |
| Status | **source_unverified** |

---

## Separation rules

- Track A research may compare screener flags to Labs `screener_pass`. That is **not** a tester-trade comparison.
- Track B comparison is **blocked** until exact Pine is verified.
- Matching Track B Net Profit (₹1,278.20) by changing Track A / 038 code is forbidden.
