# Aggregate compare

| Metric | TV | TL TV_TESTER | KERNEL (FYERS, untouched) |
|--------|----|--------------|---------------------------|
| Trades | 2954 | **2954** | 17 |
| First trade | 2002-08-22 @ 16.3 → 09-03 | **same** | 2003-12-10 window |
| Last trade | 2026-08-21 @ 2175 → 08-24 @ 2290 +115 | **same** | |
| Qty / costs | 1 / 0 | 1 / 0 | 10% / NSE |
| Net vs ₹10L | +1278.2 | +1279.0 | +154007.90 |
| Win rate | 45.77% | 45.73% | 47.06% |
| Consecutive exact MATCH | | **328** then Trade 329 tick | |

ohlc_source for tester: `tv_ohlc_csv`. KERNEL period still 2003-12-10 → 2026-08-24.
