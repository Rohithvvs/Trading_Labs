# Fix proposal (NOT applied)

Approved CSV window + 2002-08-21 signal bar are in. Trade 1 and trade count match. **Do not patch KERNEL/scanner.**

## First remaining divergence

Trade 329 exit: CSV open **62.25**, TL `round(62.25, 1)=62.2`, TV list **62.3**. Dates already match.

## Evidence against a global mode switch

| Policy | TV trades matching CSV fills at 0.01 |
|--------|--------------------------------------|
| Python `round(px, 1)` (current) | **2775 / 2954** |
| Decimal `ROUND_HALF_UP` | 2772 / 2954 (fixes 62.25→62.3, **breaks** 239.95→240.0 vs TV 239.9) |

TV is not a single IEEE mode: 62.25 prints 62.3 (up) and 239.95 prints 239.9 (down). Switching to half-up would fail later trades that currently MATCH.

## Proposed patch (TV_TESTER only) if you still want 329 to pass first

**Not recommended as a net win.** If you APPROVE anyway:

In `execution.py` `round_to_tick`, for `tick==0.10` use:

```python
from decimal import Decimal, ROUND_HALF_UP
return float(Decimal(str(price)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
```

Tests: 62.25→62.3; add a regression that 239.95 currently 239.9 will become 240.0.

**Preferred alternative:** leave rounding; treat the 179 remaining 0.05/0.1 list-vs-open ties as a proven TradingView print vs chart-open limitation. No engine change.

## Out of scope

KERNEL, scanner, inventing OHLC, changing 52W BuySignal.
