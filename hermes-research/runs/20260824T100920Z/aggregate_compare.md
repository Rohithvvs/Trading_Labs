# Aggregate compare — after TV_TESTER

FAIL on full golden sequence (Trade 1 date).

| Metric | TV golden | TL TV_TESTER | TL KERNEL (unchanged) |
|--------|-----------|--------------|------------------------|
| Trades | 2954 | 2247 | 17 |
| Net profit | 1278.2 | ~995.05 | +154,007.90 |
| Profit factor | 1.186 | 1.0186 | 2.9296 |
| Win rate | 45.77% | 47.31% | 47.06% |
| Qty | 1 | 1 | ~10% equity |
| Commission | 0 | 0 | NSE delivery |
| First entry | 2002-08-22 | 2008-07-23 | 2014-03-11 |
| Last round-trip | 2026-08-21 @ 2175 → 2026-08-24 @ 2290 +115 | **same** | 2026-04-16 @ 1065 → 2374 |

Data: Labs WELCORP-EQ 2008-07-22 → 2026-08-24. 723 TV entries have no Labs bar.
