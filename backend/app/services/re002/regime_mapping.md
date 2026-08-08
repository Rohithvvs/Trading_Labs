# RE-002 Regime Mapping

Maps platform market permission / regime signals → Bull | Sideways | Bear | UNKNOWN.

| Platform signals | Bucket |
| ---------------- | ------ |
| FAVORABLE / BULL / BULLISH trend, entry allowed | Bull |
| CAUTIOUS / NEUTRAL / MIXED / SIDEWAYS | Sideways |
| DEFENSIVE / HIGH_RISK / BEAR / entry not allowed / ABS/DEF | Bear |
| Missing / unusable | UNKNOWN → Decision REJECT (`missing_market_context`) |

Implementation: `regime.py` (`map_market_regime`, `is_regime_usable`).
