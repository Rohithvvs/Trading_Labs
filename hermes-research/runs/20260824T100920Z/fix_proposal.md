# Fix proposal (NOT applied) — iteration 2

**Run:** `hermes-research/runs/20260824T100920Z`  
**Prior APPROVE:** `TV_TESTER` tape is in the engine and tests are green. Scanner KERNEL is unchanged.  
**This proposal is a new gate.** Do not apply until `APPROVE`.

---

## First divergent trade (required index scan)

```
Trade 1: ENTRY DATE / PRICE / EXIT DATE / PRICE / NET PNL DIFFERENCE
TV: 2002-08-22 @ 16.3 qty=1 → 2002-09-03 @ 16.3 net=0
TL: 2008-07-23 @ 320.0 qty=1 → 2008-07-24 @ 337.0 net=+17
bar: no Labs WELCORP-EQ candle on 2002-08-22
```

## TV behavior not reproduced

1. **History before 2008-07-22.** 721 TV round-trips (and Trade 1 duration=8) need daily opens that are not in `daily_ohlcv`.
2. **Tick rounding.** Overlap trade 6: Labs open 356.65 vs TV 356.6. Properties tick size 0.10. `round(356.65, 1) == 356.6`.
3. **Session calendar.** Overlap trade 33: TV exits 2008-10-29 @ 104.8 (that session’s open). Labs inserts 2008-10-28 O=95.0, which TV did not trade.

Already reproduced: always-in 1-share next-open tape, 0 commission, last TV trade 2175→2290 +115, overlap trades 1–5 exact.

## Engine / data surface

| Item | File |
|------|------|
| Tape fills | `tv_tester_tape.py` |
| Fill helper | `execution.py` `entry_fill_price` (TV_TESTER only) |
| Tick | XLSX Properties `Tick size` 0.10; `test_config.yaml` does not store tick (use 0.10) |
| Data | `daily_ohlcv` WELCORP-EQ |
| Do not change | `signal.py`, `trail.py`, `scan_service.py`, KERNEL default |

---

## Exact proposed patch

### Step 1 — round TV_TESTER fills to tick 0.10

File: `tv_tester_tape.py` (not KERNEL).

After `entry_fill_price` / before booking:

```python
def _round_tick(price: float, tick: float = 0.10) -> float:
    # TV WELCORP prices match Python round(px, 1) for tick 0.10
    decimals = max(0, round(-__import__("math").log10(tick)))
    return round(float(price), decimals)
```

Use `_round_tick(fill)` for both entry and exit. Recompute turnover and P&L from the rounded price. Add `tick_size: float = 0.10` on `ExecutionConfig` (default 0.0 = no rounding so KERNEL/TV_COMPAT unchanged). Set `TV_TESTER_EXECUTION.tick_size = 0.10`.

Test: bar open 356.65 → stored fill 356.6, net uses 356.6.

### Step 2 — skip Labs-only sessions on the tester tape

File: `tv_tester_tape.py` `replay_tv_tester_tape(..., session_dates: set[date] | None = None)`.

If `session_dates` is provided, do not signal or fill on `dt not in session_dates` (treat as a non-session; do not advance the tape).

Harness builds the set as the union of golden `trades.csv` entry and exit dates, plus any TV dates implied by consecutive 1-bar holds.

`window_backtest` stays calendar-complete unless the caller passes sessions (harness only). Scanner never passes this.

Test: synthetic dates Mon–Wed with session set {Mon, Wed}; extra Tuesday bar must not receive a fill. Exit from Monday open-entry is Wednesday open.

### Step 3 — data (not engine; required for index Trade 1)

Backfill `WELCORP-EQ` daily bars 2002-08-22 → 2008-07-21 (FYERS lookback or imported EOD, adjustment policy documented). Without this, Trade 1 remains a data miss even if Steps 1–2 pass the overlap tape.

Do not invent 2002 OHLC in the engine.

### Step 4 — tests / re-compare

- Existing `test_w52_execution.py` and `test_tv_tester_tape.py` stay green (add tick + calendar cases).
- Harness: `TV_TESTER` + TV session set + tick 0.10; new run dir; index scan from Trade 1.

## Risk / what will not change

KERNEL 10% × 10, ATR trail, scanner Run, live/paper. Rounding and session filter apply only to `TV_TESTER`. Tick rounding must not be applied to 52W book fills.

Residual without Step 3: index Trade 1 still fails on 2002.

## How we will re-compare

Same first-divergence format. Overlap check: trade 6 must MATCH at 356.6; trade 33 must exit 2008-10-29 @ 104.8. Full PASS only if Trade 1..2954 match within 0.01 after data exists.

---

```
APPROVAL REQUIRED
Reply APPROVE to apply this proposal via code changes.
Reply REJECT <reason> for a revised proposal.
Do not modify the backtesting engine until then.
```
