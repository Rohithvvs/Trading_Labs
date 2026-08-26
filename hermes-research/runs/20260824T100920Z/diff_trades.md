# Trade-level diff (TV_TESTER)

```
Trade 1: ENTRY DATE + ENTRY PRICE + EXIT DATE + EXIT PRICE + NET PNL DIFFERENCE
         TV 2002-08-22 @ 16.3 → 2002-09-03 @ 16.3
         TL 2008-07-23 @ 320.0 → 2008-07-24 @ 337.0
Trade 2..2954: sequence broken
```

MATCH count (index-aligned): **0 / 2954**

Overlap-aligned from 2008-07-23 (extra diagnostic):

- 2233 TV trades vs 2247 TL
- First 5 overlap trades MATCH
- Overlap 6: exit 356.6 vs 356.65 (tick rounding)
- Dates stay paired through overlap 32; overlap 33 TV skips Labs 2008-10-28
- 14 TL extra trades (2247 − 2233)

Files: `tv_trades_normalized.csv`, `tl_trades_normalized.csv` (TV_TESTER chronological).
