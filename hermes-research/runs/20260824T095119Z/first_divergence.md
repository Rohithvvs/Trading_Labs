# First divergence — WELCORP / Strategy_001

**Run:** `20260824T095119Z`  
**Golden:** `hermes-research/tradingview_reference/Strategy_001/`  
**Labs engine:** `backend/app/services/strategies/breakout52w/` profile `TV_COMPAT` (next-bar open)  
**Tolerances:** exact trade sequence; prices within 0.01; P&L within 0.01; identical trade count and direction.

Labs trades below are **chronological** (oldest first). Dashboard JSON originally listed newest first; that order is not used for this scan.

---

```
Trade 1: ENTRY DATE / ENTRY PRICE / EXIT DATE / EXIT PRICE / QTY / NET PNL DIFFERENCE
         TV:  LONG  entry 2002-08-22 @ 16.3 qty=1  exit 2002-09-03 @ 16.3 qty=1
              net_pnl=0  commission=0  duration=8 bars
              signal=TEST / Close entry(s) order TEST
         TL:  LONG  entry 2014-03-12 @ 72.4 qty=1381.2154696132595
              exit 2014-06-16 @ 87.42142857142858
              net_pnl=20539.744297059984  commission=208.08522148776638
              duration ~ months  exit_reason=atr_trail  signal=BuySignal
         bar: Labs daily_ohlcv WELCORP-EQ has no 2002-08-22 candle.
              Store span: 2008-07-22 → 2026-08-24 (4495 rows).
              2014-03-12 Labs OHLC: O=72.4 H=73.2 L=69.4 C=70.45
              (TL entry 72.4 matches that session OPEN — TV_COMPAT fill.)
         suspected cause: strategy interpretation (TV tape is always-in 1-share
              TEST round-trips at session open; Labs is 038 52W book with
              252-high + volume + market filter + 3×SMA-ATR trail, 10% equity).
              Contributing: market/candle data (no 2002–2008 Labs bars),
              position sizing, commission.
         evidence:
              - strategy.pine is indicator(), not strategy(); no strategy.entry
              - TV trades.csv: 2954/2954 entry_signal=TEST; 2953/2954 duration=1
              - TV overlap first trade after Labs data start: #722 2008-07-23
                entry 320.0 = Labs OPEN 320.0; exit 2008-07-24 337.0 = OPEN 337.0
              - Last 5 TV fills match Labs OPEN exactly (e.g. #2954 entry
                2026-08-21 2175.0 = O=2175.0; exit 2026-08-24 2290.0 = O=2290.0)
              - Labs first 52W fill is 2014-03-12 open 72.4, ~10% of ₹10L
```

Trade 2 and later at this index are not comparable: the sequence already diverged at Trade 1. Full remaining diffs are in `diff_trades.md`.

**Scan (index-aligned, chronological):**

```
Trade 1: ENTRY DATE + ENTRY PRICE + EXIT DATE + EXIT PRICE + QTY + NET PNL DIFFERENCE
Trade 2..2954: not scanned as MATCH candidates (sequence broken at Trade 1)
```

TV remaining after Trade 1: 2953 TEST 1-bar round-trips (qty=1, commission=0).  
TL remaining after Trade 1: 17 ATR-trail 52W book trades (fractional 10% equity, NSE delivery costs).
