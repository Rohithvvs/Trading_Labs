# First divergence — after CSV window + signal-bar calendar

**Run:** `20260824T134919Z`  
**OHLC:** `ohlc.csv` 6105 rows, 2000-11-28 → 2026-08-24  
**Counts:** TV 2954 = TL 2954. KERNEL still 17 (FYERS, unchanged).

Trade 1 **MATCH** (2002-08-22 @ 16.3 → 2002-09-03 @ 16.3, qty=1, net=0).  
Last trade **MATCH** (2026-08-21 @ 2175 → 2026-08-24 @ 2290, net=+115).

```
Trade 1..328: MATCH
Trade 329: EXIT PRICE + NET PNL DIFFERENCE
         TV:  LONG 2005-04-19 @ 77.1 → 2005-05-24 @ 62.3  qty=1  net=-14.8  dur=1
         TL:  LONG 2005-04-19 @ 77.1 → 2005-05-24 @ 62.2  qty=1  net=-14.9
         bar: 2005-04-19 O=77.14285714 → tick 77.1 (entry MATCH)
              2005-05-24 O=62.25 → Python round(...,1)=62.2  TV list=62.3
         suspected cause: rounding (half-tick 62.25)
         evidence: dates/qty/direction match; 35-day CSV gap 2005-04-19→05-24
                   is the same span TV stored as duration=1
```

Index MATCH count: **328 / 2954** consecutive, then price.  
Full-file at 0.01: **2775 MATCH**, 179 remaining (92 entry, 84 exit, 3 both) — all |TV−TL|=0.1 on a CSV open of `*.*5`.
