# Trade-level diff

Index-aligned chronological comparison. Tolerances: price 0.01, P&L 0.01, exact dates/qty/direction/count.

## Sequence scan

```
Trade 1: ENTRY DATE + ENTRY PRICE + EXIT DATE + EXIT PRICE + QTY + NET PNL DIFFERENCE
         TV:  LONG 2002-08-22 @ 16.3 qty=1 → 2002-09-03 @ 16.3  net=0  TEST  dur=8
         TL:  LONG 2014-03-12 @ 72.4 qty=1381.2154696132595 → 2014-06-16 @ 87.42142857142858
              net=20539.744297059984  commission=208.09  atr_trail  BuySignal
Trade 2: NOT COMPARED (sequence already broken)
…
Trade 2954: NOT COMPARED (sequence already broken)
```

**MATCH count:** 0 / 2954  
**First break:** Trade 1  
**TL extra trades after TV exhausted:** n/a (TV list is longer)

## Full-set facts (still computed)

| | TV | TL TV_COMPAT |
|--|----|----------------|
| Round-trips | 2954 | 18 |
| Signals | TEST | BuySignal |
| Exit reasons | Close entry(s) order TEST (2954) | atr_trail (17) + BACKTEST_END_LIQUIDATION (1) |
| Duration | 1 bar × 2953; 8 bars × 1 | multi-week / multi-month holds |
| Qty | 1 | 10% equity (72–1381 shares) |
| Commission | 0 | NSE delivery per fill |

## Date-aligned overlay (not the required index scan; extra evidence)

Labs data starts 2008-07-22. First TV trade on/after that date:

```
TV #722: 2008-07-23 @ 320.0 → 2008-07-24 @ 337.0  qty=1  net=+17  dur=1
         Labs bar 2008-07-23: O=320.0 H=352.0 L=320.0 C=335.9
         Labs bar 2008-07-24: O=337.0 H=341.4 L=322.1 C=327.35
         Fill: both legs = OPEN
TL: no 52W position open on 2008-07-23 (first 52W fill is 2014-03-12)
```

Last TV trade vs last Labs bar:

```
TV #2954: 2026-08-21 @ 2175.0 → 2026-08-24 @ 2290.0  qty=1  net=+115
          Labs 2026-08-21 O=2175.0 C=2311.9
          Labs 2026-08-24 O=2290.0 C=2374.0
TL last (open, liquidated): 2026-04-16 @ 1065.0 → 2026-08-24 @ 2374.0
          qty=96.74  net=+126313.96  reason=BACKTEST_END_LIQUIDATION
          1065.0 = Labs 2026-04-16 OPEN; 2374.0 = Labs 2026-08-24 CLOSE
```

So even the last calendar day disagrees: TV exits at **open** 2290 as a 1-share TEST round-trip; Labs marks a 4-month 52W position at **close** 2374.

## Files

- `tv_trades_normalized.csv` — 2954 TV round-trips
- `tl_trades_normalized.csv` — 18 Labs TV_COMPAT closed trades, chronological
- `tl_trades_kernel_normalized.csv` — 17 Labs KERNEL closed trades, chronological
