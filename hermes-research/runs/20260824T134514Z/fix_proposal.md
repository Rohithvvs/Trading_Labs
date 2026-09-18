# Fix proposal (NOT applied)

CSV is valid. KERNEL/scanner stay off this file. Two small changes, neither touches `signal.py` / `trail.py` / scan.

## First real tape divergence

TV Trade 1 enters **2002-08-22** open; TL signals that day and enters **2002-09-03**. Prices 16.3 match.

## 1. Harness window (comparator)

`hermes-research/harness/export_and_compare.py` currently:

```python
ohlc = await load_ohlc("WELCORP-EQ")  # FYERS
start = max(start, ohlc[0]["date"])   # 2003-12-10
```

For `TV_TESTER`, set start/end from `ohlc.csv` (2000-11-28…2026-08-24) and use that series for fill_stats. KERNEL/TV_COMPAT keep FYERS.

## 2. Session calendar — signal bar before first fill

`tv_session_calendar()` is only TV entry/exit dates, so **2002-08-21** is omitted.

Add the last `ohlc.csv` session **strictly before** the first TV entry (2002-08-21). Do **not** add every intra-hold bar: skipping 08-23…09-02 is what makes duration=8 (entry 08-22, next allowed session 09-03).

Optional: when building the set, for every TV entry date `E`, include the previous CSV session if it exists. That covers Trade 1 without flattening 8-bar holds.

## 3. Out of scope this patch

- KERNEL / `scan_service` / FYERS store
- Changing `round_to_tick` (95 later 0.05 quote diffs stay data until this date bug is gone)
- Inventing bars

## Tests after APPROVE

- Existing tape + w52 tests
- New: calendar with {08-21, 08-22, 09-03} fills entry 08-22 and exit 09-03
- Harness uses CSV span; Trade 1 dates 2002-08-22 → 2002-09-03

## Risk

Only TV_TESTER + research harness. Scanner book replay unchanged.
