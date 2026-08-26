# ohlc.csv validation

**File:** `hermes-research/tradingview_reference/Strategy_001/ohlc.csv`  
**Engine consumer:** `TV_TESTER` only (`resolve_tv_tester_ohlc_csv("KERNEL")` is None)

## Schema

Header (15 columns):

`time,open,high,low,close,Volume,STR-001 Signal,Breakout,Volume OK,Market OK,Close,Prior 252 High,Volume,Volume SMA20,ATR14`

| Check | Result |
|-------|--------|
| Date column | `time` → ISO `YYYY-MM-DD`; parser alias already maps `time` → date |
| OHLC | `open,high,low,close` present; extra `Close` ignored (first `close` wins) |
| Volume | duplicate header `Volume`; first column used |
| Extra screener plots | ignored |
| Parsed rows | **6105 / 6105** (0 dropped) |
| Range | **2000-11-28 → 2026-08-24** |
| Chronology | sorted ascending |
| Duplicate dates | **0** |
| KERNEL uses file | **no** |

## Gaps > 14 calendar days

2000-12-08→2001-02-15 (69d), 2001-02-20→2001-07-18 (148d), 2001-07-18→2001-10-17 (91d), 2001-11-07→2001-11-26 (19d), 2005-04-19→2005-05-24 (35d). Sparse pre-listing / halt, not parse errors.

## Alignment with trades.csv (2954 round-trips)

| Check | Result |
|-------|--------|
| Entry date has a bar | 2954 / 2954 |
| Exit date has a bar | 2954 / 2954 |
| Entry px = raw open ±0.01 | 1954 |
| Entry px = `round(open, 1)` ±0.01 | +905 (total 2859) |
| Entry still unmatched after tick | 95 |
| Exit unmatched after tick | 87 |
| First unmatched after tick | TV exit 2005-05-24 **62.3** vs CSV open **62.25** (`round` → 62.2) |

### 2002-08-22 (TV Trade 1)

CSV bar present: O=H=L=C=**16.32653**. `round(..., 1) = 16.3` = TV entry/exit print. Prior session **2002-08-21** O=16.32653. Hold sessions through **2002-09-03** exist (8 bars 08-22…09-02, exit 09-03).

### 2026 last five TV trades

All five entry and exit prices equal CSV **open** exactly (1848.1, 1844.4, …, 2175 → 2290).
