# Root cause (iteration 3)

**Primary (index Trade 1):** `market/candle data`  
**Contributing on overlap:** `market/candle data` (adjustment / vendor OHLC)  
**Not:** strategy interpretation of the TEST tape (that layer is in)

---

## Applied this iteration (approved)

- `tick_size=0.10` on `TV_TESTER` only; `round_to_tick` = Python `round(px, 1)`
- `session_dates` skips Labs-only days
- FYERS backfill WELCORP-EQ 2003-12-10 → 2008-07-21 (1133 rows). **2002-08-22 → 2003-12-09: empty.**

KERNEL / scanner unchanged. Unit tests: 28 tape+execution, 166 w52.

---

## Why Trade 1 still diverges

**OBSERVED:** `FyersEodProvider.fetch_daily_range("WELCORP-EQ", 2000-06-23, 2003-12-09)` returned no candles.  
**OBSERVED:** First FYERS bar 2003-12-10. TV Trade 1 is 2002-08-22.  
Cannot emit that fill without inventing OHLC (forbidden).

159 TV trades occur before 2003-12-11.

---

## 2003-12-11 same dates, different prices

TV 101.6 / 99.0 vs Labs 49.8 / 48.5. Engine fills Labs **open** correctly. The series are not the same (adjustment or listing). Changing 52W signals will not fix this.

---

## 2008-09-01 315.25 vs 315.3

Labs open 315.25. Half-even tick → 315.2. Half-up → 315.3. TV used 315.3 here but 356.6 for 356.65 (half-even). **INFERRED:** TV’s printed open is not a single rounding of the FYERS open; the raw quotes differ by 0.05.

---

## Progress

| Run | TL trades | First TL fill | Notes |
|-----|-----------|---------------|--------|
| 095119Z | 18 52W book | 2014-03-12 @ 72.4 ×1381 | pre-tape |
| 100920Z | 2247 tape | 2008-07-23 @ 320 qty=1 | tape works |
| 101745Z | 2793 tape | 2003-12-11 @ 49.8 qty=1 | backfill + tick + sessions |
