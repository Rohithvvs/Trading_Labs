# First divergence — after approved TV_TESTER patch

**Run:** `20260824T100920Z`  
**Profile:** `TV_TESTER` (qty=1, costs=0, next-open tape)  
**Tolerances:** exact sequence; price 0.01; P&L 0.01.

Index-aligned scan (required):

```
Trade 1: ENTRY DATE + ENTRY PRICE + EXIT DATE + EXIT PRICE + NET PNL DIFFERENCE
         TV:  LONG 2002-08-22 @ 16.3 qty=1 → 2002-09-03 @ 16.3  net=0  TEST  dur=8
         TL:  LONG 2008-07-23 @ 320.0 qty=1 → 2008-07-24 @ 337.0  net=+17
              reason=Close entry(s) order TEST
         bar: Labs daily_ohlcv WELCORP-EQ has no 2002-08-22 candle.
              Store span: 2008-07-22 → 2026-08-24 (4495 rows).
              2008-07-23 Labs O=320.0 (TL entry matches OPEN).
              2008-07-24 Labs O=337.0 (TL exit matches OPEN).
         suspected cause: market/candle data (no 2002–2008-07-21 Labs bars).
                          TV_TESTER tape is now correct on the first Labs session.
         evidence: Layer 1 qty/costs/open-fill match TV #722 exactly
                   (same dates, 320→337, qty=1, net=+17).
```

Trade 2..2954 not MATCH-scanned after the sequence break at Trade 1.

## Overlap-aligned scan (from 2008-07-23; not a substitute for Trade 1)

TV trades with entry ≥ 2008-07-23: 2233. TL TV_TESTER: 2247.

```
Overlap 1: MATCH   TV #722 2008-07-23 320.0 → 2008-07-24 337.0
Overlap 2: MATCH   2008-07-25 323.0 → 2008-07-28 337.0
Overlap 3: MATCH   2008-07-29 337.0 → 2008-07-30 332.5
Overlap 4: MATCH   2008-07-31 329.7 → 2008-08-01 322.0
Overlap 5: MATCH   2008-08-04 335.0 → 2008-08-05 353.0
Overlap 6: EXIT PRICE DIFFERENCE
           TV: 2008-08-06 @ 372.0 → 2008-08-07 @ 356.6  net=-15.4
           TL: 2008-08-06 @ 372.0 → 2008-08-07 @ 356.65 net=-15.35
           bar: 2008-08-07 Labs O=356.65 H=359.7 L=345.0 C=351.85
           suspected cause: rounding (TV tick 0.10; round(356.65, 1)=356.6)
```

First overlap **date** break is later: overlap trade 33, TV exit 2008-10-29 @ 104.8 vs TL exit 2008-10-28 @ 95.0. Labs has a 2008-10-28 bar (O=95); TV jumps 10-27 → 10-29 (10-29 O=104.8 = TV exit). Extra Labs session.
