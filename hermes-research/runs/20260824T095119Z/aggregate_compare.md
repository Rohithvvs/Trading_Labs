# Aggregate compare — TV golden vs Labs WELCORP 52W

Tolerances: prices 0.01, P&L 0.01, identical trade count and direction. **FAIL.**

## TradingView (golden)

Source: `strategy_report.xlsx` + `trades.csv` (cross-checked).

| Metric | TV |
|--------|----|
| Symbol / TF | NSE:WELCORP / 1D |
| Trading range | 2002-08-22 → 2026-08-24 |
| Initial capital | 1,000,000 INR |
| Total trades | 2954 (all long) |
| Open trades | 0 |
| Winners / losers / even | 1352 / 1449 / 153 |
| Percent profitable | 45.77% |
| Net profit | 1278.2 (0.13%) |
| Gross profit | 8147 |
| Gross loss | 6868.8 |
| Profit factor | 1.186 |
| Commission paid | 0 |
| Avg trade | 0.43 |
| Average bars in trades | 2 (CSV: 2953 trades duration=1, one duration=8) |
| Max DD (close-to-close) | 627 (0.06%) |
| Max DD (intrabar) | 627.4 |
| Max contracts held | 1 |
| Sharpe / Sortino | -40.6 / -1 |
| Buy and hold PnL | 144,955,417.2 |
| Order size | 1 contract |
| Slippage | 0 ticks |

## Trading Labs (this run)

Symbol store: `WELCORP-EQ`. Data: 2008-07-22 → 2026-08-24. Capital passed: ₹1,000,000. Engine: `09_52w_breakout`.

| Metric | KERNEL | TV_COMPAT (comparison export) |
|--------|--------|-------------------------------|
| Period | 2008-07-22 → 2026-08-24 | same |
| Trade count | 17 | 18 |
| Win rate | 47.0588% | 44.4444% |
| Total return | 15.4008% | 15.6623% |
| Ending capital | 1,154,007.90 | 1,156,622.81 |
| Implied net vs 1,000,000 | +154,007.90 | +156,622.81 |
| Profit factor | 2.9296 | 2.7466 |
| Max drawdown | -6.3351% | -5.5237% |
| CAGR | 0.5478 | 0.5565 |
| Typical qty | ~10% equity | ~10% equity |
| Commission | NSE delivery | NSE delivery |
| First trade | 2014-03-11 @ 71.85 (close) | 2014-03-12 @ 72.4 (open) |
| Exit family | atr_trail + end liquidation | atr_trail + BACKTEST_END_LIQUIDATION |

## Side-by-side (comparison profile = TV_COMPAT)

| Metric | TV | TL | Match? |
|--------|----|----|--------|
| Trade count | 2954 | 18 | **NO** |
| Direction | long | long | yes (family) |
| Net profit | 1278.2 | 156622.81 | **NO** (Δ 155344.61) |
| Gross profit | 8147 | (book, costs on) | **NO** |
| Gross loss | 6868.8 | | **NO** |
| Profit factor | 1.186 | 2.7466 | **NO** |
| Max DD | 627 INR | 5.52% of 1e6 ≈ 55k | **NO** |
| Avg trade | 0.43 | ~8700 | **NO** |
| Win rate | 45.77% | 44.44% | close as a rate, not a match |
| Position size | 1 | ~100–1381 shares | **NO** |
| Commission | 0 | NSE delivery | **NO** |
| First entry | 2002-08-22 | 2014-03-12 | **NO** |

## Data coverage

| Store | Span | Rows |
|-------|------|------|
| TV trades | 2002-08-22 → 2026-08-24 | 2954 round-trips |
| Labs `daily_ohlcv` WELCORP-EQ | 2008-07-22 → 2026-08-24 | 4495 |
| TV entries with a Labs bar | | 2231 |
| TV entries with no Labs bar | | 723 |

## Fill diagnostic (not an aggregate pass)

On overlapping dates, TV entry/exit prices match Labs **open** (not close). That confirms TV Properties “on bar close + one tick” against FYERS EOD opens. It does **not** make trade counts or P&L match.
