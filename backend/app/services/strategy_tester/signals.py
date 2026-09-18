"""Deterministic BUY / WATCH / REJECT classification.

BUY, WATCH, and REJECT are mutually exclusive. Incomplete indicator data is
not a signal — callers must record DATA_UNAVAILABLE separately.
"""

from __future__ import annotations

from .filter_engine import FilterEvaluation, LeafEvaluation
from .schema import SignalRules

BUY = "BUY"
WATCH = "WATCH"
REJECT = "REJECT"


def classify_signal(evaluation: FilterEvaluation, rules: SignalRules) -> tuple[str, str | None]:
    """Return (signal, primary_failure_reason)."""
    leaves = evaluation.leaves
    if evaluation.unevaluable or evaluation.passed is None:
        return REJECT, "insufficient_indicator_data"
    scored = [leaf for leaf in leaves if leaf.passed is not None]
    if not scored:
        return REJECT, "no_evaluable_filters"
    passed_n = sum(1 for leaf in scored if leaf.passed)
    failed = [leaf for leaf in scored if not leaf.passed]
    total = len(scored)
    ratio = passed_n / total if total else 0.0
    if evaluation.passed and (not rules.buy_requires_all or passed_n == total):
        return BUY, None
    if passed_n >= rules.watch_min_passed and ratio >= rules.watch_min_pass_ratio:
        return WATCH, _primary_failure(failed)
    return REJECT, _primary_failure(failed)


def _primary_failure(failed: list[LeafEvaluation]) -> str | None:
    if not failed:
        return None
    return failed[0].label
