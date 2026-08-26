# First divergence — after ROUND_HALF_UP

**Run:** `20260824T135313Z`  
Trade count 2954=2954. Trade 1 MATCH. Trade 329 now MATCH (62.3). Last trade MATCH.

```
Trade 1..943: MATCH
Trade 944: EXIT PRICE + NET PNL DIFFERENCE
         TV:  2010-05-27 @ 222.7 → 2010-05-28 @ 239.9  net=+17.2
         TL:  2010-05-27 @ 222.7 → 2010-05-28 @ 240.0  net=+17.3
         bar: 2010-05-28 O=239.95
              ROUND_HALF_UP → 240.0 (current)
              Python round → 239.9 (TV list)
         suspected cause: rounding (the HALF_UP regression flagged before apply)
```

Exact MATCH at 0.01: **2772 / 2954** (was 2775 with `round(px,1)`). KERNEL still 17 trades.
