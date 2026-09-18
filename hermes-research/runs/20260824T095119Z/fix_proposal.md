# Fix proposal (NOT applied)

**Run:** `hermes-research/runs/20260824T095119Z`  
**Status:** waiting for explicit `APPROVE` / `REJECT <reason>`  
**Hermes MUST NOT and did not modify the backtesting engine.**  
**Grok has not modified the engine.**

---

## First divergent trade

```
Trade 1: ENTRY DATE / ENTRY PRICE / EXIT DATE / EXIT PRICE / QTY / NET PNL DIFFERENCE
TV: LONG 2002-08-22 @ 16.3 qty=1 → 2002-09-03 @ 16.3  net=0  signal=TEST  dur=8
TL: LONG 2014-03-12 @ 72.4 qty=1381.22 → 2014-06-16 @ 87.42
    net=+20539.74  commission=208.09  BuySignal / atr_trail
bar: no Labs WELCORP-EQ candle on 2002-08-22
     Labs store 2008-07-22 → 2026-08-24
```

## TV behavior not reproduced

1. **Always-in 1-share TEST tape.** 2954 longs, 2953 of them 1-bar, entry `TEST`, exit `Close entry(s) order TEST`, flatten at next session **open**, re-enter the following session **open**. Verified: TV #2954 entry 2175 = Labs 2026-08-21 open; exit 2290 = 2026-08-24 open.
2. **Qty = 1**, commission 0, slippage 0, capital ₹1,000,000 (`test_config.yaml` / XLSX Properties).
3. **Trading range from 2002-08-22.** Labs EOD for WELCORP-EQ begins 2008-07-22 (18Y FYERS load). 723 TV entries have no Labs bar.
4. **Not reproduced (and must not be faked inside 038):** 252-high + volume + CNX500 SMA50 + 3×SMA-ATR trail as the thing that produced this CSV. `strategy.pine` is an `indicator()` screener; it has no `strategy.entry`. The CSV is a different script.

`TV_COMPAT` already fills 52W *entries* at next open. That is why TL Trade 1 is 2014-03-12 **72.4 = that day’s open**. The missing TV behavior is the **TEST order policy**, not the open-fill helper.

## Engine component / files / functions

| Area | File | Functions |
|------|------|-----------|
| Execution profile | `backend/app/services/strategies/breakout52w/execution.py` | `ExecutionConfig`, `KERNEL_EXECUTION`, `TV_COMPAT_EXECUTION`, `parse_execution_profile` |
| Share calc / costs | `book_engine.py` `_open_holding`, `_account_exit` | 10% equity + `costs.py` NSE waterfall |
| Sizing helper | `portfolio.py` | `shares_from_notional`, `target_notional` |
| Signal / trail (DO NOT CHANGE on this proposal) | `signal.py`, `trail.py`, `indicators.py` | `buy_signal`, `update_trail`, `prior_high_252` |
| Window replay | `window_backtest.py` | `run_symbol_window_backtest` |
| Data | `daily_ohlcv` WELCORP-EQ | FYERS EOD from 2008-07-22 |

Primary taxonomy: **strategy interpretation**. Contributing: **market/candle data**, **position sizing**, **commission**.

---

## Exact proposed patch (numbered)

This is one approval package with two layers. Layer 0 is data (not code). Layer 1 is engine. Layer 2 is explicitly **out of scope** so 038 intent stays frozen.

### Layer 0 — data (required for Trade 1; not an engine diff)

Without WELCORP daily bars from **2002-08-22**, no engine patch can emit TV Trade 1.

Operator choice (this proposal does not download):

1. Extend FYERS `full-load` / `backfill_equity_history` lookback past 18 years for `WELCORP-EQ`, **or**
2. Import a vendor EOD series for NSE:WELCORP 2000-06-23 → 2008-07-21 into `daily_ohlcv` with documented adjustment policy, **or**
3. Temporarily compare only `2008-07-22 → 2026-08-24` (then TV Trade 1 is still a documented data miss; overlap first TV row is #722).

Recommend (1) or (2). (3) cannot satisfy the golden Trade 1 date.

### Layer 1 — engine (this is what `APPROVE` applies)

**Goal:** reproduce the *observed TV tester tape* as an isolated replay, and honor `test_config.yaml` sizing/costs on that replay. Do **not** change `09_52w_breakout` scan/BuySignal/trail.

#### Step 1 — `ExecutionConfig` TV tester fields

File: `backend/app/services/strategies/breakout52w/execution.py`

Add:

```python
OrderSizeType = Literal["percent_equity", "quantity"]

@dataclass(frozen=True)
class ExecutionConfig:
    # existing fields …
    order_size_type: OrderSizeType = "percent_equity"
    default_order_size: float = 0.0  # qty when order_size_type=="quantity"
```

Add profile (does not replace KERNEL default):

```python
TV_TESTER_EXECUTION = ExecutionConfig(
    profile="TV_COMPAT",
    order_fill_delay="NEXT_BAR_OPEN",
    historical_fill_mode="DEFAULT_OHLC",
    trail_touch="INTRABAR_TOUCH",
    allow_entry_bar_exit=True,
    allow_same_bar_reentry=False,
    skip_on_missing_next_bar=True,
    slippage_rate=0.0,
    apply_costs=False,
    pyramiding=1,
    max_positions=1,
    alloc_pct=1.0,
    order_size_type="quantity",
    default_order_size=1.0,
)
```

Extend `parse_execution_profile` so `TV_TESTER` / `TEST_TAPE` maps to `TV_TESTER_EXECUTION`.

Update `ExecutionConfig.hash()` payload (already dumps `asdict`).

#### Step 2 — quantity sizing in `_open_holding`

File: `backend/app/services/strategies/breakout52w/book_engine.py` (`_open_holding`, ~L662–684)

Today:

```python
alloc = min(target_notional(equity, alloc_pct=cfg.alloc_pct), max(state.cash, 0.0))
sh = shares_from_notional(investable, exec_px, whole_shares=whole_shares)
```

Replace share selection with:

```python
if cfg.order_size_type == "quantity" and cfg.default_order_size > 0:
    sh = float(cfg.default_order_size)
else:
    alloc = min(target_notional(equity, alloc_pct=cfg.alloc_pct), max(state.cash, 0.0))
    fee_est = alloc * 0.002 if cfg.apply_costs else 0.0
    investable = max(0.0, min(state.cash - fee_est, alloc))
    sh = shares_from_notional(investable, exec_px, whole_shares=whole_shares)
```

Keep `apply_costs` gate as-is (already 0 fees when False).

Optional one-liner in `portfolio.py`:

```python
def shares_from_config(cfg, equity, cash, fill, *, whole_shares=False) -> float:
    ...
```

#### Step 3 — isolated TEST tape (new file; not the scanner)

New: `backend/app/services/strategies/breakout52w/tv_tester_tape.py`

Behavior matching the **observed** CSV (not invented 52W rules):

1. Walk daily bars in session order (WELCORP only).
2. `FLAT` → place long market qty=`default_order_size` at bar close (signal).
3. Fill at **next session open** (`entry_fill_price` / `NEXT_BAR_OPEN`).
4. Place `strategy.close` equivalent at that entry bar’s close; fill flatten at **following session open**.
5. `allow_same_bar_reentry=False` so next entry is the session after the exit (matches TV: exit 2026-08-20 open, next entry 2026-08-21 open).
6. Commission 0, slippage 0, pyramiding 1, long only.
7. Emit `Trade` rows with `entry_signal="TEST"`, `exit_reason_canonical="Close entry(s) order TEST"`.

Wire **only**:

- `window_backtest.run_symbol_window_backtest(..., execution_profile="TV_TESTER")` when profile is TV_TESTER: call `replay_tv_tester_tape` instead of `replay_book`.
- Do **not** call this from `scan_service.run_scan`.

First-bar duration=8 on TV Trade 1: treat as UNKNOWN until 2002 bars exist; do not hard-code an 8-bar special case without those candles.

#### Step 4 — tests (new, plus existing)

- `backend/tests/unit/test_w52_execution.py` — existing TV_COMPAT tests must still pass (KERNEL default unchanged).
- New `backend/tests/unit/test_tv_tester_tape.py`:
  - Synthetic 5 daily bars: opens `[10,11,12,13,14]`.
  - Expect round-trips: entry bar2 open 11 → exit bar3 open 12; entry bar4 open 13 → exit bar5 open 14; qty=1; net = +1 and +1; commission 0.
  - Assert no same-session re-entry.
  - Assert `buy_signal` / `prior_high_252` are **not** imported by `tv_tester_tape.py`.
- Existing 038 scan/book fixtures must remain KERNEL 10% × 10.

#### Step 5 — re-export harness

`hermes-research/harness/export_and_compare.py` already exists (read-only). Point comparison profile at `TV_TESTER` after the patch.

### Layer 2 — explicitly not in this patch

- No edits to `signal.py`, `trail.py`, `indicators.py`, `scan_service.py`.
- No change to default `W52_EXECUTION_PROFILE=KERNEL`.
- No conversion of `strategy.pine` into a fake `strategy()`.
- No “force 2954 trades” by loosening 252-high / ATR.

---

## Risk / what will not change

| Will change | Will not change |
|-------------|-----------------|
| New `TV_TESTER` profile + `tv_tester_tape.py` | 038 BuySignal, ATR trail, 10-name book |
| Qty=1 and `apply_costs=False` on that profile | Scanner Run button / recommendations |
| Comparison export path when profile=TV_TESTER | KERNEL / TV_COMPAT 52W fills |
| | Live trading, paper broker, `BacktestService` |

**Residual even after Layer 1:**

- Trade 1 date 2002-08-22 still fails until Layer 0 data exists.
- 637 overlap fills that did not match open/high/low/close may be corporate-action / vendor differences; they stay as a **data** investigation, not a signal rewrite.
- First TV trade duration=8 remains UNKNOWN without 2002 OHLC.

## Tests that will be run after APPROVE

1. `pytest backend/tests/unit/test_w52_execution.py backend/tests/unit/test_tv_tester_tape.py -q`
2. Broader `pytest backend/tests/unit -k w52 -q` if the first set is green
3. Harness: `backend/venv/Scripts/python.exe hermes-research/harness/export_and_compare.py` with `TV_TESTER`

## How we will re-compare

1. Re-export `tl_trades_normalized.csv` from `TV_TESTER` on WELCORP-EQ.
2. Index-scan vs `tv_trades_normalized.csv` with the required format (`Trade N: MATCH` until first break).
3. If Layer 0 data is still 2008-start: first divergence will still be Trade 1 (2002 vs 2008). Then overlap-only scan from TV #722 vs TL #1 on 2008-07-23 @ 320.0.
4. FAIL → new `fix_proposal.md` → wait again. PASS → `FINAL_REPORT.md`.

Victory condition is not “net profit close”. It is exact sequence within 0.01 price / 0.01 P&L / identical count and direction.

---

## Why this patch vs changing 52W

TV last five fills equal Labs **opens**. The broker emulator’s next-open fill is already right. The 52W kernel is a different strategy (18 trades, ATR trail, 10% equity). Matching `trades.csv` by rewriting `buy_signal` would violate “do not change strategy intent.”

Isolated `TV_TESTER` tape is the engine change that can actually converge on this golden file **without** destroying `09_52w_breakout`.
