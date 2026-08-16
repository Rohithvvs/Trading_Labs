# Contract: LTM Algorithm Kernel

**Feature**: `037-ltm-scanner-dashboard`  
**Strategy id**: `17_long_term_mom`  
**Normative source**: spec.md §§FR-005–FR-028, Acceptance Fixtures, Clarifications Q1–Q4

This is the compute contract. Implementations MUST share these functions between **live evaluate** and **book replay**. Adding a filter on only one path is a defect.

---

## Inputs

- Aligned adjusted-close matrix `C[symbol, session]` on the NIFTY 500 master calendar
- Active constituent set as of evaluation session T (or current list + `survivorship_biased`)
- Book state: cash, holdings, `session_index`, `sessions_since_rebalance`, mode (`A` default)
- Initial capital default: 100_000 INR

## Momentum

```
Momentum_252(s, t) = C(s, t) / C(s, t-252) − 1
```

Missing either close ⇒ undefined (not 0). Non-finite ⇒ undefined.

## Eligibility

```
Eligible(s, t) ⇔ Momentum_252 defined AND Momentum_252 > 0.50
```

Exact `0.50` is **not** eligible.

## Rank / selection

1. Momentum descending  
2. Symbol ascending (ASCII / NSE ticker)  
3. `Selected = first min(10, |Eligible|)`  
4. Zero eligible ⇒ 100% cash; clock still resets on a rebalance fire

## Clock

- Session index `i = 0` is the first date in the aligned matrix used for this run.
- No selection while `i < 252` (WARMUP).
- First rebalance: first session with `i >= 252`.
- After a fire, counter resets to 0; next fire when counter reaches 252 again.
- Not calendar year-end. Not 365 calendar days.
- Historical last session: force-liquidate at that close (reporting only). Live MUST NOT invent that day.

Published calendar (frozen `data_mrs`-equivalent) MUST emit buys on:

`2020-08-27`, `2021-09-03`, `2022-09-09`, `2023-09-15`, `2024-10-01`, `2025-10-09`

Membership sets are listed in spec.md Acceptance Fixtures.

## Sizing

**Mode A (default):** after selling the entire book, `target_notional(s) = cash_after_sells / N`. Full round-trip even if the name remains selected.

**Mode B (optional research):** 10% of equity per name, max 10, residual cash.

No shorts, no leverage, no stops.

## Fills

| Context | Fill |
|---------|------|
| Replay / boards | Adjusted close of session T; sells before buys |
| Live recommended | Next session open / auction (label only in scan MVP) |
| Open MTM for 1Y boards | Scan session close or last mark; **not** an order |

Research replay cost (Mode A): 25 bps each side.  
`buy_price = close * 1.0025`, `sell_price = close * 0.9975`.

## Scan-time backtest (Q1–Q4)

1. Replay the book across history (same filters).
2. Every name with valid 252-session history gets a result object.
3. Names failing history / missing close / data-source are **not** backtested.
4. Per-name 1Y return = real book trades in the last 1 year of completed sessions **plus** MTM of a still-open book position.
5. Never selected in that year ⇒ exclude from Top 5 / Least 5 (not 0%).
6. Isolated single-name replay and buy-and-hold are forbidden as board returns.

## Signals for session T (after replay)

| Clock | Selected | Signal |
|-------|----------|--------|
| WARMUP | — | no BUY/WATCH |
| REBALANCE | yes | BUY |
| MID_CYCLE | yes | WATCH |
| any | no | REJECT |

## Determinism

Same matrix + same state ⇒ same Selected set, same first-failure codes, same board order. No hash-order sorts.
