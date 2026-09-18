# Root cause (post TV_TESTER)

**Primary class (index Trade 1):** `market/candle data`  
**Next overlap issues:** `rounding`, then `session`

Layer 1 (`TV_TESTER` always-in qty=1 next-open tape) is **verified** on the first five overlapping round-trips.

---

## 1. Index Trade 1 — still no 2002 bars

**DOCUMENTED:** TV trading range Aug 22, 2002 — Aug 24, 2026.  
**OBSERVED:** Labs `daily_ohlcv` WELCORP-EQ min date 2008-07-22 (4495 rows).  
TV Trade 1 cannot be emitted. 721 TV trades occur before the first Labs fill (2008-07-23).

This is not a signal bug. `TV_TESTER` does not use `buy_signal`.

---

## 2. What Layer 1 fixed (evidence)

| Item | Before (TV_COMPAT 52W book) | After (TV_TESTER) |
|------|-----------------------------|-------------------|
| Trade count | 18 | 2247 |
| First fill | 2014-03-12 @ 72.4, 1381 shares, ATR trail | 2008-07-23 @ 320.0 qty=1, 1-bar |
| Last fill | 2026-08-24 close 2374, 96 shares | 2026-08-21 @ 2175 → 2026-08-24 @ 2290 qty=1 net=+115 |
| TV last trade | #2954 2175 → 2290 +115 | **identical** |
| Commission | NSE delivery | 0 |
| Net vs ₹10L | +156,622 | +995.05 (TV full sample +1,278.2) |

Overlap trades 1–5: exact date, open fill, qty, P&L match.

---

## 3. Overlap trade 6 — rounding

Labs 2008-08-07 **open = 356.65**. TV exit **356.6**. Δ=0.05 > 0.01.

XLSX Properties: tick size **0.10**.  
`round(356.65, 1) == 356.6` (Python / TV display). Same pattern: 366.75→366.8, 342.85→342.9.

**Class:** `rounding`

---

## 4. Overlap trade 33 — extra Labs session

TV: 2008-10-27 @ 93.0 → **2008-10-29** @ 104.8  
TL: 2008-10-27 @ 93.0 → **2008-10-28** @ 95.0  

Labs has 2008-10-28 O=95.0. TV next session after 10-27 is 10-29 (O=104.8). After this extra bar the date sequence desyncs (2165 later index mismatches).

**Class:** `session` (Labs-only daily bar vs TV session calendar)

---

## 5. Not the cause

- 52W BuySignal / ATR trail (isolated tape; scanner unchanged)
- Qty / commission on TV_TESTER
- Next-open fill model (opens match when the session exists)
