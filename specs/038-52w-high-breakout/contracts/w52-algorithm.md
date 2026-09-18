# Contract: 52-Week High Breakout Algorithm Kernel

**Feature**: `038-52w-high-breakout`  
**Strategy id**: `09_52w_breakout`  
**Normative source**: spec.md §§FR-009–FR-036, Acceptance Fixtures, Clarifications Q1–Q3

This is the compute contract. Implementations MUST share these functions between **live evaluate** and **book replay**. Adding a filter on only one path is a defect.

---

## Inputs

- Aligned matrices on the NIFTY 500 master calendar: adjusted `H`, `L`, `C`, `V` per symbol; benchmark close `B`
- Active constituent set as of evaluation session T (or current list + `survivorship_biased`)
- Book state: cash, holdings (`shares`, `entry_date`, `entry_price`, `hwm`, `tsl`), last session processed
- Initial capital default: 100_000 INR
- Mode default: **B** (10% of current equity, max 10)

Windows count **sessions**, not calendar days. “52-week” = 252 sessions.

---

## Indicators

```
High_252_prior(s, t) = max(H(s, t-252) … H(s, t-1))     # today’s high excluded
Vol_SMA20(s, t)      = mean(V(s, t-19) … V(s, t))         # today included
TR(s, t)             = max(H-L, |H-C_prev|, |L-C_prev|)
ATR14(s, t)          = mean(TR(s, t-13) … TR(s, t))       # SMA, NOT Wilder
Nifty_SMA50(t)       = mean(B(t-49) … B(t))
MarketOK(t)          ⇔ B(t) > Nifty_SMA50(t)              # strict
Momentum_60(s, t)    = C(s, t) / C(s, t-60) − 1           # rank only
```

A window with fewer than the required valid points is undefined (not 0).

Wilder / RMA ATR **fails** the trail fixtures.

---

## Buy signal (state, not a cross)

```
BuySignal(s, t) ⇔
    MarketOK(t)
    AND C(s, t) ≥ High_252_prior(s, t)
    AND V(s, t) > Vol_SMA20(s, t)
    AND C finite and > 0
    AND High_252_prior and Vol_SMA20 defined
    AND s not held
    AND s not sold on t
```

Close equal to the prior high **passes**. Volume equal to the average **fails**. Intraday high above the level with close below it **fails**.

If the three stock+market legs stay true for 10 sessions, the name is a candidate on each of those 10 sessions until a free slot takes it.

---

## Session order (must be preserved)

On every session `t` with `t` index ≥ 252:

1. For each holding with `entry_date < t` and a valid close:
   - If `C > hwm` and ATR defined: `hwm = C`; `tsl = max(tsl, C − 3×ATR)`
   - If `C < tsl`: queue EXIT reason `atr_trail`
2. Execute exits → credit cash; record symbols in `sold_today`
3. Mark equity = cash + remaining holdings at `C(*, t)`
4. If MarketOK and `free = 10 − |holdings| > 0`:
   - candidates = BuySignal and not held and not sold today
   - sort Momentum_60 desc, undefined last, then symbol asc
   - take first `free` names
   - each buy: `alloc = equity × 0.10`, clipped to cash after fees
   - `hwm = fill`; `tsl = fill − 3×ATR` or `0.90 × fill` if ATR is NaN
5. Persist state

No exit on the entry session. No same-session rebuy. No pyramid. Newly freed slots MAY be filled by **other** names the same session.

When MarketOK is false: skip step 4 entirely. Do **not** flatten.

Warmup (`i < 252`): zero entries. Status `WARMUP`.

Last historical session: force-close leftovers at last available close, reason `eod_liquidation`. Live MUST NOT invent that day.

---

## Trail properties

- HWM is the highest **close** since entry, not the highest high.
- TSL never decreases.
- Close equal to TSL is **not** an exit.
- Intraday pierce that closes ≥ TSL is **not** an exit.
- ATR expansion on a new high cannot lower the stop.
- No new HWM ⇒ TSL unchanged even if ATR shrinks.

Worked path (MarketOK true) is in spec.md Acceptance Fixtures (entry 100 / ATR 2 → TSL 94 → ratchet to 101 → exit 100.99).

---

## Rank / sizing (Mode B default)

- 15 buy-signal names, 10 free slots → buy the 10 highest Momentum_60 only.
- 3 buy-signal names → buy 3 at 10% equity each, ~70% cash.
- Book already has 10 names → zero new buys.
- Unbuyable ranked name (halt / ban): skip and take the next-ranked still-valid name.

Mode A (uncapped per-symbol research loop) is **not** the Scanner default.

---

## Fills and costs

| Context | Fill |
|---------|------|
| Replay / boards | Adjusted close of session T; exits before entries |
| Live recommended | Next session open / auction (label only in scan MVP) |
| Open MTM for 1Y boards | Scan session close or last mark; **not** an order |

Replay cost: NSE delivery breakdown (brokerage cap 20, exchange, SEBI, stamp on buy, GST on brokerage+exchange, STT on sell, DP on sell). Selection MUST NOT depend on capital-gains tax.

---

## Scan-time backtest

1. Replay the **same** book across history (same filters — FR-049).
2. Every name with valid 252-session high history gets a result object.
3. Names failing history / missing bar / up-front data checks are **not** backtested.
4. Attribution error / timeout for one name → `data_source_failure` for that name; boards omit it; **scan still publishes** (clarify Q3). Today’s BUY/HOLD/EXIT is not cancelled by that failure.
5. Shared replay throw → entire run `failed` (not a per-name case).
6. Per-name 1Y return = real 10-slot book trades in the last 1 year of completed sessions **plus** MTM of a still-open book position.

---

## Published fixtures (frozen calendar 2019-08-19 → 2026-08-14)

| Check | Expected |
|-------|----------|
| First entry date | 2020-08-27 |
| First-day set | SJVN, DIXON, ATUL, JUBLFOOD, TATAELXSI, CDSL, SAREGAMA |
| Closed trades | 294 |
| Unique names | 207 |
| Exit mix | 284 `atr_trail` + 10 `eod_liquidation` |
| Best / worst | SAREGAMA +464.24% / VEDL −64.55% |

Rupee tolerances (only after the cost model is applied) are in spec.md Acceptance Fixtures.

---

## Forbidden in this kernel

Darvas box, 2×/5× volume, Wilder ATR, calendar 365-day highs, enter on high without close, market-off flatten, RSI / stock MA / Bollinger / RS / earnings / sector cap, 252-session +50% gate, shorts, leverage.
