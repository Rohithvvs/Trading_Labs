# First divergence

## Official harness (this run)

Harness still clamps the TV_TESTER window to FYERS `daily_ohlcv` min **2003-12-10**, so it never replayed 2002 even though `ohlc.csv` is loaded later inside `window_backtest`. Reported:

```
Trade 1: ENTRY DATE + PRICE + EXIT DATE + PRICE + NET PNL DIFFERENCE
         TV: 2002-08-22 @ 16.3 → 2002-09-03 @ 16.3
         TL: 2003-12-11 @ 101.6 → 2003-12-12 @ 99.0
```

That first line is a **comparator window bug**, not a CSV parse failure. KERNEL period also 2003-12-10 (unchanged, 17 trades).

## TV_TESTER on full `ohlc.csv` (read-only diagnostic, no code change)

`run_symbol_window_backtest(..., start=2000-06-23, end=2026-08-24, execution_profile=TV_TESTER, session_dates=TV trade dates)`  
`ohlc_source=tv_ohlc_csv`, **2953** closed trades.

```
Trade 1: ENTRY DATE + EXIT DATE DIFFERENCE
         TV:  LONG entry 2002-08-22 @ 16.3 qty=1 → exit 2002-09-03 @ 16.3
              net=0  duration=8  TEST
         TL:  LONG entry 2002-09-03 @ 16.3 qty=1 → exit 2002-09-04 @ 16.3
              net=0  signal_time=2002-08-22
         bar: 2002-08-21 O=16.32653  (not in session_dates)
              2002-08-22 O=16.32653 → tick 16.3
              2002-09-03 O=16.32653 → tick 16.3
         suspected cause: session calendar
              Tape signals on first *allowed* session (08-22) and fills next
              allowed session (09-03). TV filled the entry *on* 08-22 open,
              which requires a prior session (08-21) as the signal bar.
         evidence: prices already match tick 16.3; only dates are wrong.
```

MATCH count (full CSV diagnostic): **0 / 2954** (broken at Trade 1 dates).
