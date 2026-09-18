# Fix proposal (NOT applied)

HALF_UP did what we said: Trade 329 passes; Trade 944 fails on 239.95. **A third rounding mode will not produce 2954/2954 at 0.01.**

| Mode | Consecutive first break | Exact trades |
|------|-------------------------|--------------|
| `round(px, 1)` | Trade 329 (62.25→62.2 vs TV 62.3) | **2775** |
| `ROUND_HALF_UP` (now) | Trade 944 (239.95→240.0 vs TV 239.9) | 2772 |

TV prints both directions on `*.*5` opens. Remaining mismatches are 0.1 (one tick) on those bars, dates/qty/direction already equal.

## Recommended (no KERNEL/scanner change)

**Do not change `round_to_tick` again.** Treat the leftover ~182 legs as a proven TradingView list vs chart-open half-tick limitation.

Optional if you still want a code change:

1. **Revert** TV_TESTER to Python `round(px, 1)` (more exact trades, first fail 329), or
2. **Widen compare tolerance** to 0.10 for price/P&L (one tick) in the harness only — would PASS the sequence without claiming the printed tenths are identical.

Neither changes 52W BuySignal or the scanner.
