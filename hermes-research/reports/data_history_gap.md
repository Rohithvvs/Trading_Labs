# Data History Gap

**TV reference trading range:** 2002-08-22 → 2026-08-24 (Properties / CSV)  
**TV backtesting range (config):** 2000-06-23 → 2026-08-24  
**Classification:** **UNRESOLVED**

No data was imported, downloaded, or modified.

---

## Where Labs daily data begins

**OBSERVED (read-only SQL, 2026-08-24):**

| Store | Symbol | Min date | Max date | Rows |
|-------|--------|----------|----------|------|
| `daily_ohlcv` | `WELCORP-EQ` | 2008-07-22 | 2026-08-24 | 4495 |
| `daily_ohlcv` | all symbols | 2008-07-22 | 2026-08-24 | 2,234,307 |
| `index_ohlcv` | `NIFTY500` | 2008-07-22 | 2026-08-24 | 4478 |
| `historical_candles` | `WELCORP` | 2025-06-20 | 2026-06-19 | 262 |
| `historical_candles` | `WELCORP-EQ` | 2025-06-24 | 2026-08-24 | 308 |

No `daily_ohlcv` row exists for `WELCORP` without `-EQ`. No pre-2008 equity bars in this store.

Document `docs/BACKTEST_DATA_AVAILABILITY.md` described an 18-year load dated 18 Aug 2026 ending **2026-08-17**. Live store now ends **2026-08-24**. The **start remains 2008-07-22**.

---

## Why it begins there

**OBSERVED:** Strategy-grade load is FYERS EOD via:

```text
python -m app.cli.market_data_cli full-load --years 18 --skip-delivery
python scripts/backfill_equity_history.py --years 18
```

`full_load.run_full_load` sets `start = end - timedelta(days=years*365 + 30)`. An 18-year window from mid-2026 lands near July 2008. That is an **operator-chosen lookback**, not proof that FYERS lacks earlier WELCORP bars.

`FyersEodProvider` chunks requests to 365 calendar days (`code=-50` on longer ranges). It does not itself cap history at 2008.

WELCORP is listed in `ind_nifty500list.csv` (Welspun Corp Ltd.).

---

## Older WELCORP data elsewhere?

| Location | Pre-2008 WELCORP? |
|----------|-------------------|
| `daily_ohlcv` | No (OBSERVED) |
| `historical_candles` | No; series starts 2025 (OBSERVED) |
| TradingView export | Yes, first trade date 2002-08-22 (OBSERVED) |
| Local CSV/parquet besides golden trades | Not found (OBSERVED search) |
| FYERS API beyond 18Y | **UNKNOWN** (not queried; download forbidden this task) |

---

## Different vendors / corporate actions

**UNKNOWN.** TV uses NSE:WELCORP. Labs uses FYERS `WELCORP-EQ` adjusted daily bars. Split/bonus alignment was not compared. Prices in the first CSV rows (e.g. 16.3 in 2002) have no Labs bar to match.

Index identity also differs: Pine Track A requests `NSE:CNX500`; Labs store symbol is `NIFTY500`. Whether those series are identical is **UNKNOWN**.

---

## Implication for comparison

Even after tester Pine is supplied, a full 2002–2026 WELCORP compare cannot use the current `daily_ohlcv` series without an explicit data decision (extend FYERS lookback, accept a 2008 start, or import another vendor). That decision is **not** made here.

**RESOLVED:** Labs WELCORP-EQ span is known: 2008-07-22 → 2026-08-24.  
**UNRESOLVED:** 2002–2008 TV history, vendor/corporate-action parity, and whether FYERS can supply the missing years.
