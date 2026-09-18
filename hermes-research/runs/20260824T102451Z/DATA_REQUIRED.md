# Data required — no further engine patch

The approved TV_TESTER OHLC override is implemented and tested. It is **dormant** until this file exists:

```
hermes-research/tradingview_reference/Strategy_001/ohlc.csv
```

Required columns (header row, UTF-8): `date,open,high,low,close,volume`  
Source: TradingView NSE:WELCORP 1D export from the **same chart** as `trades.csv` / `strategy_report.xlsx`, range covering 2000-06-23 → 2026-08-24.

Without it:

- FYERS has no WELCORP-EQ bars before 2003-12-10 (verified empty fetch)
- Trade 1 (2002-08-22 @ 16.3) cannot be reproduced
- 2003-12-11 TV 101.6 vs Labs 49.8 remains a vendor/adjustment mismatch

KERNEL / scanner are unchanged. Drop the CSV in that path and say **continue** (or APPROVE again) to re-run the harness. Do not invent those bars in the engine.
