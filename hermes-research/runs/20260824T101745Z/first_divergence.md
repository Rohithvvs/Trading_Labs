# First divergence — after tick rounding, session filter, FYERS backfill

**Run:** `20260824T101745Z`  
**Profile:** `TV_TESTER` + golden session calendar + tick 0.10  
**Labs OHLC span (after backfill):** 2003-12-10 → 2026-08-24 (5628 rows)

```
Trade 1: ENTRY DATE + ENTRY PRICE + EXIT DATE + EXIT PRICE + NET PNL DIFFERENCE
         TV: LONG 2002-08-22 @ 16.3 qty=1 → 2002-09-03 @ 16.3 net=0 dur=8 TEST
         TL: LONG 2003-12-11 @ 49.8 qty=1 → 2003-12-12 @ 48.5 net=-1.3
         bar: Labs/FYERS has no WELCORP-EQ candle on 2002-08-22.
              Fetch 2000-06-23 → 2003-12-09 returned EMPTY.
              First stored bar: 2003-12-10 O=50.15.
              First tape fill: 2003-12-11 O=49.8 (next session after 2003-12-10 signal).
         suspected cause: market/candle data (FYERS listing/history starts 2003-12-10)
         evidence: FyersEodProvider.fetch_daily_range WELCORP-EQ 2002-08-22..2008-07-21
                   → min 2003-12-10; pre-2003-12-10 query empty. 1133 bars upserted
                   for 2003-12-10..2008-07-21.
```

## Overlap from first Labs fill (2003-12-11)

Dates match TV #160 (2003-12-11 → 2003-12-12) but prices do not:

| | Entry | Exit |
|--|-------|------|
| TV | 101.6 | 99.0 |
| Labs open | 49.8 | 48.5 |

Ratio ≈ 2.04× — different adjusted series, not a tick.

## 2008-07-23+ (previous matching window)

13 consecutive MATCH then:

```
Overlap-from-2008 trade 14: EXIT PRICE DIFFERENCE
TV: 2008-08-29 @ 313.0 → 2008-09-01 @ 315.3  net=+2.3
TL: 2008-08-29 @ 313.0 → 2008-09-01 @ 315.2  net=+2.2
bar: 2008-09-01 Labs O=315.25 → round(x,1)=315.2
     TV print 315.3
```

`round(356.65,1)=356.6` matches TV; `round(315.25,1)=315.2` does not (TV 315.3). One rounding mode cannot fix both — vendor OHLC, not engine.
