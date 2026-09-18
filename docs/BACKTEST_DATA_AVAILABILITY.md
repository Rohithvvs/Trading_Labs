# Backtest data currently available

**Short answer: local Postgres now holds about 18 years of daily history (22 Jul 2008 → 17 Aug 2026).**

Loaded on 18 August 2026 into `trading_data` from FYERS daily bars for the 755-name NIFTY 500 universe.

| What | How much is loaded now |
|---|---|
| **Equity daily bars** (`daily_ohlcv`) | **18.07 years** |
| Date range | **2008-07-22 → 2026-08-17** |
| Trading sessions on the calendar | **4,495** |
| Rows | **2,230,588** |
| Symbols with any bars | **747 of 755** |
| Names with data from 2008 | **347** |
| Names with ≥ 10 years | **444** |
| Names with ≥ 5 years | **561** |
| Names with ≥ 4,000 sessions | **372** |
| NIFTY 500 index | **2008-07-22 → 2026-08-17** · **4,473** bars |

A 1Y / 3Y / 5Y / All backtest window can now be served from stored history. Names listed after 2008 only have data since listing — FYERS returns empty candles before IPO.

---

## Equity store (`daily_ohlcv`)

| Year | Rows | Symbols | Sessions |
|---|---:|---:|---:|
| 2008 | 37,111 | 347 | 108 |
| 2009 | 84,073 | 357 | 243 |
| 2010 | 93,841 | 387 | 252 |
| 2011 | 96,417 | 399 | 247 |
| 2012 | 100,966 | 409 | 251 |
| 2013 | 101,889 | 414 | 250 |
| 2014 | 101,001 | 417 | 244 |
| 2015 | 104,559 | 429 | 248 |
| 2016 | 108,483 | 453 | 247 |
| 2017 | 114,601 | 476 | 248 |
| 2018 | 119,772 | 499 | 246 |
| 2019 | 124,961 | 521 | 245 |
| 2020 | 133,351 | 542 | 252 |
| 2021 | 138,158 | 582 | 248 |
| 2022 | 148,090 | 612 | 249 |
| 2023 | 153,762 | 649 | 246 |
| 2024 | 165,065 | 689 | 249 |
| 2025 | 180,942 | 747 | 255 |
| 2026 | 123,546 | 747 | 167 |

Sessions per symbol: min **165**, average **2,986**, max **4,493**.

This is the series used by LTM and 52-Week High Breakout book replays, Top 5 / Least 5 boards, and the stock-detail Backtest tab.

---

## Index store (`index_ohlcv`)

| Field | Value |
|---|---|
| Symbol | `NIFTY500` |
| First bar | 22 July 2008 |
| Last bar | 17 August 2026 |
| Rows | 4,473 |

Benchmark overlays can now use the same 18-year window as equities.

---

## UI windows vs stored history

| Window | What you get now |
|---|---|
| **1Y** | Fully available |
| **3Y** | Fully available for names listed ≥ 3 years |
| **5Y** | Fully available for names listed ≥ 5 years (561 names) |
| **All** | Entire stored history: **2008-07-22 → 2026-08-17** |

Newer listings (Jio Financial, recent IPOs, etc.) still start at their first FYERS print, not 2008.

---

## Names that could not be loaded from FYERS

12 universe tickers failed with `FyersInvalidSymbolError` (renamed, delisted, or dummy):

`CIGNITITEC-EQ`, `DIACABS-EQ`, `DUMMYALCAR-EQ`, `DUMMYVEDL1-EQ`, `DUMMYVEDL2-EQ`, `DUMMYVEDL3-EQ`, `DUMMYVEDL4-EQ`, `GSPL-EQ`, `JBCHEPHARM-EQ`, `MTARTECH-EQ`, `LOTUSDEV-EQ`, `STLTECH-EQ`

Those 8 dummy / invalid names explain most of the **755 − 747 = 8** symbols with no `daily_ohlcv` rows. They cannot be filled from FYERS.

NSE delivery % was **not** backfilled for the 18-year window (session-by-session archives would be ~4,500 HTTP files). Existing delivery on 2025–2026 bars was preserved.

---

## How this was loaded

```text
python -m app.cli.market_data_cli full-load --years 18 --skip-delivery
python scripts/backfill_equity_history.py --years 18
```

The serial script resumes missing date ranges per symbol and backs off on FYERS rate limits. Re-run it any time to fill new gaps.

Database size after the load: **672 MB**.
