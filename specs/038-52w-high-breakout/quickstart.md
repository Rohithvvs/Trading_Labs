# Quickstart: Validate 52-Week High Breakout Scanner

**Feature**: `038-52w-high-breakout`  
**Audience**: Implementer / reviewer after `/speckit-implement`  
**Do not** treat this file as a task list. Tasks live in `tasks.md` (not created by `/speckit-plan`).

Normative details: [w52-algorithm.md](./contracts/w52-algorithm.md), [w52-scan-api.md](./contracts/w52-scan-api.md), [data-model.md](./data-model.md).

---

## Prerequisites

- Backend Python 3.11+ venv with existing `backend/requirements.txt`
- PostgreSQL with strategy-grade tables from spec 033 (`daily_ohlcv` including **high / low / volume**, `index_ohlcv`)
- NIFTY 500 universe seeded (`UniverseService.get_active_nifty500_symbols` non-empty)
- Latest completed NSE session present (or freshness gate will block)
- Authenticated user with feature `advanced_scanner`
- Frontend dev server as in the existing README
- 037 LTM tables already migrated (`strategy_scan_latest`, `strategy_scan_runs`)

---

## 1. Algorithm kernel (no server)

From `backend/`:

```text
pytest tests/unit/test_w52_indicators.py tests/unit/test_w52_signal.py tests/unit/test_w52_trail.py tests/unit/test_w52_book.py -q
```

**Expect:**

| Case | Result |
|------|--------|
| Prior 252-high on bar 252 excludes today’s high | pass |
| Close == prior high | price leg true |
| Close one tick below; high above | price leg false |
| Volume == 20-session average | volume leg false |
| Benchmark close == SMA50 | MarketOK false |
| ATR is SMA of TR, not Wilder | Wilder fixture fails |
| Session 251 | no entries |
| Entry 100, ATR 2 | TSL 94, HWM 100 |
| Next close 99 | TSL stays 94 |
| Close 110, ATR 3 | HWM 110, TSL 101 |
| Close 112, ATR 6 | TSL stays 101 |
| Close 101.00 | still held |
| Close 100.99 | EXIT `atr_trail` |
| Entry session | no exit |
| ATR NaN at entry | TSL = 0.90 × entry |
| 15 signals, 10 free | buy 10 highest Momentum_60 |
| 3 signals | buy 3 at 10% each |
| Book full | zero new buys |
| Sold today | no rebuy |
| MarketOK false | zero new buys; trail still runs |

If a frozen published calendar is available, also assert first entry date **2020-08-27** and first-day membership {SJVN, DIXON, ATUL, JUBLFOOD, TATAELXSI, CDSL, SAREGAMA}.

---

## 2. Attribution / boards

```text
pytest tests/unit/test_w52_attribution.py -q
```

**Expect:**

- History-valid name never selected in last 1Y → backtest object exists, **absent** from Top 5 / Least 5
- Insufficient history → no backtest object
- Failed volume gate today but held a slot last year → may appear on boards
- Open holding → 1Y return includes MTM; no exit order emitted from the mark
- Attribution error for one name → `data_source_failure`; boards omit it; other names still published
- Board window is last 1Y even if detail asks for 3Y

---

## 3. Freshness block and isolation

With latest session withheld (or gate forced stale):

```text
POST /scanner/w52/runs
```

**Expect:** `MARKET_DATA_STALE`; `GET /scanner/latest` and `GET /scanner/ltm/latest` unchanged.

With a 52W run already `evaluating`:

```text
POST /scanner/w52/runs
```

**Expect:** `409` `W52_SCAN_IN_PROGRESS` with the in-flight `scan_id`; that run is not cancelled.

Starting LTM (`POST /scanner/ltm/runs`) while 52W is idle MUST leave 52W latest unchanged, and the reverse.

---

## 4. End-to-end scan (warm data)

1. Open Scanner, confirm **52-Week High Breakout** sits beside **Long-Term Buy & Hold Momentum**
2. Select it; press this view’s Run
3. Poll `GET /scanner/w52/runs/{scan_id}` until `completed` (`evaluating` → `backtesting` → `publishing`)
4. `GET /scanner/w52/latest`

**Expect:**

- `strategy_id` is `09_52w_breakout`
- `recommendations_final` is true only on `completed`
- Summary includes `hold`
- Still-open prior names are **HOLD**, not in Rejection Breakdown
- Order list lists EXIT before BUY
- `book_status` is WARMUP / MARKET_OFF / ACTIVE
- Top 5 / Least 5 period is last 1 year; never-selected names absent
- LTM latest and Production latest unchanged

---

## 5. Detail surfaces

Open a BUY, a HOLD, a volume-failed REJECT, and an insufficient-history REJECT.

**Technicals:** prior high, volume vs average, SMA ATR, market filter, and (on HOLD) HWM/TSL. No RSI / EMA / LTM +50% tiles.

**Backtest:** headline metrics + equity vs NIFTY 500 when trades exist; “never selected” or data-failure empty state otherwise. Changing 3Y does not re-rank the scan-level boards.

---

## 6. Restart persistence

1. Complete a scan that leaves at least one HOLD with a ratcheted TSL  
2. Restart the backend  
3. `GET /scanner/w52/latest` (or start a new evaluate)

**Expect:** that name’s TSL ≥ TSL before restart if price did not print a new HWM.
