# First divergence — TV_TESTER OHLC CSV hook live, golden CSV absent

**Run:** `20260824T102451Z`  
**ohlc.csv:** not present at `hermes-research/tradingview_reference/Strategy_001/ohlc.csv`  
**OHLC used:** FYERS `daily_ohlcv` WELCORP-EQ 2003-12-10 → 2026-08-24

```
Trade 1: ENTRY DATE + ENTRY PRICE + EXIT DATE + EXIT PRICE + NET PNL DIFFERENCE
         TV: 2002-08-22 @ 16.3 qty=1 → 2002-09-03 @ 16.3 net=0
         TL: 2003-12-11 @ 49.8 qty=1 → 2003-12-12 @ 48.5 net=-1.3
         bar: no Labs/FYERS candle on 2002-08-22; TV OHLC CSV not supplied
         suspected cause: market/candle data
```

KERNEL still 17 trades (unchanged). TV_TESTER 2793 vs TV 2954.
