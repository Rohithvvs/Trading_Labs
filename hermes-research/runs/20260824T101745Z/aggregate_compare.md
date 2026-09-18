# Aggregate compare

FAIL on full sequence (Trade 1).

| Metric | TV | TL TV_TESTER |
|--------|----|----------------|
| Trades | 2954 | 2793 |
| Net vs ₹10L | +1278.2 | +381.1 |
| PF | 1.186 | 1.056 |
| Win rate | 45.77% | 46.87% |
| Qty / costs | 1 / 0 | 1 / 0 |
| First entry | 2002-08-22 @ 16.3 | 2003-12-11 @ 49.8 |
| Last TL | | 2026-08-20 @ 1990 → 2026-08-21 @ 2175 +185 |

TV last trade was 2026-08-21 @ 2175 → 2026-08-24 @ 2290. Session calendar ended the tape one session earlier (no 2026-08-24 in the fill pair as last entry). Worth checking if 2026-08-24 is in the session set as an exit-only date — last TL exits 2026-08-21, so 2026-08-24 may have been skipped as a trailing session without a following bar.

Labs OHLC: 2003-12-10 → 2026-08-24, 5628 rows (was 4495 from 2008-07-22).
