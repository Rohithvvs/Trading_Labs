# RE-002 RS Defaults (versioned under engine_version)

Conservative defaults for MVP (engine_version 1.0). Tighten later without architecture change.

| Parameter | Default | Notes |
| --------- | ------- | ----- |
| Weak RS sector threshold | sector_rs_20 < 0 | early REJECT `weak_relative_strength` |
| Strong RS threshold | sector_rs_20 >= 5 | leadership support |
| Exceptional RS (bear) | sector_rs_20 >= 8 and tech_score >= 78 | survivors only |
| Tech floor for BUY | >= 72 with support | else WATCH/REJECT |
| Tech floor for WATCH | >= 55 | |
| Insufficient history | < 50 bars | REJECT `insufficient_history` |

Exact RS formulas come from existing sector RS / TA services — RE-002 does not re-implement market data.
