"""First-failure assignment. Earliest failing rule wins."""

from __future__ import annotations

from .identity import FAILURE_CODES, FAILURE_LABELS, MAX_SELECTED
from .momentum import is_eligible, momentum_252


def first_failure(
    *,
    in_universe: bool,
    close_t: float | None,
    close_t_minus_252: float | None,
    data_source_failed: bool = False,
    eligible_rank: int | None = None,
) -> str | None:
    """Return a failure code or None if the name is selected (rank <= 10)."""
    if data_source_failed:
        return "data_source_failure"
    if not in_universe:
        return "not_in_universe"
    if close_t_minus_252 is None:
        return "insufficient_history"
    if close_t is None:
        return "missing_close_t"
    mom = momentum_252(close_t, close_t_minus_252)
    if mom is None:
        return "momentum_undefined"
    if not is_eligible(mom):
        return "failed_momentum_gate"
    if eligible_rank is None or eligible_rank > MAX_SELECTED:
        return "ranked_outside_top_10"
    return None


def breakdown(codes: list[str], evaluated: int) -> list[dict]:
    counts = {code: 0 for code in FAILURE_CODES}
    for code in codes:
        key = code if code in counts else "other"
        counts[key] += 1
    denom = evaluated if evaluated > 0 else 1
    rows = []
    for code in FAILURE_CODES:
        n = counts[code]
        rows.append(
            {
                "code": code,
                "label": FAILURE_LABELS[code],
                "count": n,
                "pct": round(100.0 * n / denom, 1),
                "caption": "First failure",
            }
        )
    return rows
