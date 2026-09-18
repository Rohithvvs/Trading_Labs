# Reference Strategy Identity Investigation

**Date:** 2026-08-24  
**Golden reference integrity before investigation:** `STATUS MATCH`  
**Golden reference files modified:** none

Evidence classes: `OBSERVED`, `DOCUMENTED`, `INFERRED`, `UNKNOWN`.

---

## TradingView Tester Strategy

**Name:** `52W Breakout - Test`

**DOCUMENTED** from `test_config.yaml` (unmodified):

- Symbol: `NSE:WELCORP`
- Timeframe: `1D`
- Mode: `deep_backtesting`
- Backtesting range: `2000-06-23` → `2026-08-24`
- Initial capital: `1000000` INR
- Order size: `1` quantity
- Pyramiding: `1`
- Commission: `0` percent
- Slippage: `0` ticks
- Script execution: `on_bar_close`
- Order execution delay: `one_tick`

**DOCUMENTED** from `strategy_report.xlsx` Properties / Performance / Trades analysis:

- Symbol `NSE:WELCORP`, timeframe `1 day`
- Trading range Aug 22, 2002 — Aug 24, 2026
- Net profit `1278.2`, commission paid `0`, total trades `2954`, all long
- Profit factor `1.186`, percent profitable `45.77`, average bars in trades `2`

**OBSERVED** from `trades.csv`:

- Signal id on entries: `TEST`
- Signal id on exits: `Close entry(s) order TEST`
- 2954 completed long round-trips as 5908 list rows (exit row then entry row per trade number)

---

## Current strategy.pine

Path: `hermes-research/tradingview_reference/Strategy_001/strategy.pine`  
SHA256 (unchanged): `6b715e65ad06bcf6aa5c7346f7bd735c3e571c261cbff218cfbb57275f452128`

**OBSERVED:**

| Item | Value |
|------|--------|
| Pine version | `//@version=6` |
| Declaration | `indicator("STR-001 \| 52W High Breakout Scanner", overlay=false)` |
| `strategy()` | absent |
| `strategy.entry` / `strategy.exit` / `strategy.order` / `strategy.close` | absent |
| Inputs | hardcoded constants, not `input.*` |
| Lookback | `LOOKBACK_52W = 252` via `ta.highest(high, 252)[1]` |
| Volume | `volume > ta.sma(volume, 20)` |
| ATR | SMA of True Range (comment: not `ta.atr(14)`), unused in the signal |
| Market filter | `NSE:CNX500` close > SMA50 |
| Signal | `breakout and volumeOK and marketOK` |
| Outputs | `plot(...)` screener columns only |
| Alerts | none |

It is a Pine **screener/indicator**. It cannot emit Strategy Tester trades.

---

## Is it the tester strategy?

**NO**

---

## Evidence

1. **OBSERVED:** Pine declares `indicator()`, not `strategy()`. TradingView Strategy Tester requires a `strategy()` script to produce a trade list.
2. **OBSERVED:** No `strategy.entry` / `strategy.close` / `strategy.exit` exist in this file or in any other `.pine` file on disk.
3. **OBSERVED:** Title is `STR-001 | 52W High Breakout Scanner`, not `52W Breakout - Test`.
4. **OBSERVED:** Tester CSV signal names are `TEST` / `Close entry(s) order TEST`, which do not appear in `strategy.pine`.
5. **OBSERVED:** Tester holds are 1 bar for 2953 of 2954 trades (`Duration (bars)` = `1` on 5906 rows; one trade duration `8`). A 252-session breakout + ATR trail cannot be this script.
6. **DOCUMENTED (prior spec):** `specs/038-52w-high-breakout/parity-audit-glaxo.md` and `execution-parity.md` already state that Pine for `52W Breakout - Test` was not in the workspace.

---

## Repository Candidates

Every Pine/script-like source found:

### Candidate 1 — current golden `strategy.pine`

- **path:** `hermes-research/tradingview_reference/Strategy_001/strategy.pine`
- **type:** Pine v6 indicator / screener
- **title:** `STR-001 | 52W High Breakout Scanner`
- **Pine version:** 6
- **strategy()/indicator():** `indicator()`
- **evidence:** file contents (OBSERVED)
- **confidence:** certain it is **not** the tester strategy
- **classification:** NOT the source of `52W Breakout - Test`

No other `.pine` file exists under `D:\Trading_Labs` (filesystem search). No `.pinescript` files found.

Python implementations of a *different* 52W book (`backend/app/services/strategies/breakout52w/`) are Labs engines, not Pine, and are not tester-source candidates.

Google Drive library docs name **STR-007** as “52-Week High Breakout” in prose. That is a strategy-library blurb, not Pine, and not titled `52W Breakout - Test`. **CANDIDATE — NOT YET VERIFIED** as even a Track A spec; **not** a tester-source candidate.

Drive library **STR-001** is “Trend Pullback Continuation”, which **conflicts** with the golden Pine title `STR-001 | 52W High Breakout Scanner`. That naming collision is recorded; it does not supply tester Pine.

---

## Git Candidates

Read-only search:

- `git ls-files '*.pine'` — empty (no tracked Pine)
- `git log --all --diff-filter=A -- '*.pine'` — empty (Pine never committed)
- `git log -S "strategy.entry"` — no commits
- `git log -S "52W Breakout - Test"` — only spec markdown:
  - `e27daa22` `52 week high breakout`
  - `195dadc8` untracked-files snapshot
  - files: `specs/038-52w-high-breakout/parity-audit-glaxo.md`, `execution-parity.md`
- `git grep "52W Breakout - Test" HEAD` — those two spec files only
- tags: none

**No historical Pine strategy source exists in Git.**

---

## XLSX Evidence

**Proves (DOCUMENTED from cells, file not converted):**

- Tester properties: WELCORP, 1 day, ₹10,00,000, qty 1, commission 0, slippage 0 ticks, on-bar-close, one-tick delay, pyramiding 1
- Performance: net profit 1278.2, 2954 long trades, PF 1.186, Sharpe -40.6, Sortino -1
- Application metadata: SheetJS export

**Does not prove:**

- Pine source code (none in the workbook)
- Strategy title `52W Breakout - Test` as an XLSX string (XML search for `Breakout` did not hit Properties)
- Entry/exit formulas
- Whether ATR, 252-high, or volume gates were used

---

## CSV Evidence

**Proves:**

- 5908 data rows = 2954 `Exit long` + 2954 `Entry long`
- Each trade number has exactly the pair `(Exit long, Entry long)` in file order (TradingView list style: exit listed above entry)
- 0 open trades
- Direction: long only
- Size always `1`; commission always `0`
- Cumulative PnL on last rows: `1278.2` (matches XLSX net profit)
- Entry dates 2002-08-22 → 2026-08-21; exit dates 2002-09-03 → 2026-08-24
- Order comment/signal: `TEST`

**Does not prove:** the Pine that created `TEST`.

Correct representation: **not** “5908 trades”. It is **2954 completed round-trips**, each serialized as two rows.

---

## Final Determination

**EXACT_STRATEGY_NOT_FOUND**

State: **REFERENCE_INCOMPLETE**

Comparison against Labs backtesters is **not allowed** until the user supplies the `strategy()` Pine (or an approved substitute) that produced `52W Breakout - Test`.
