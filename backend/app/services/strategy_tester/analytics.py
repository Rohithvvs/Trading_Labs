"""Independent filter stats vs sequential funnel. Do not mix the two."""

from __future__ import annotations

from typing import Any

from .engine import STATUS_OK, StrategyEvaluationResult
from .schema import FilterNode, StrategyDefinitionConfig
from .signals import BUY, REJECT, WATCH


def summarize_results(
    results: list[StrategyEvaluationResult],
    strategy: StrategyDefinitionConfig,
    *,
    universe_size: int,
) -> dict[str, Any]:
    ok = [r for r in results if r.status == STATUS_OK]
    insufficient = sum(1 for r in results if r.status == "insufficient_data")
    validation_failed = sum(1 for r in results if r.status == "validation_failed")
    errors = sum(1 for r in results if r.status == "error")
    buy = sum(1 for r in ok if r.signal == BUY)
    watch = sum(1 for r in ok if r.signal == WATCH)
    reject = sum(1 for r in ok if r.signal == REJECT)
    with_ret = [r for r in results if r.return_pct is not None]
    positive = sum(1 for r in with_ret if (r.return_pct or 0) > 0)
    negative = sum(1 for r in with_ret if (r.return_pct or 0) < 0)
    flat = sum(1 for r in with_ret if (r.return_pct or 0) == 0)
    ranked_pos = sorted(
        [r for r in with_ret if (r.return_pct or 0) > 0],
        key=lambda r: float(r.return_pct or 0),
        reverse=True,
    )[:5]
    ranked_neg = sorted(
        [r for r in with_ret if (r.return_pct or 0) < 0],
        key=lambda r: float(r.return_pct or 0),
    )[:5]
    returns = [float(r.return_pct) for r in with_ret if r.return_pct is not None]
    return {
        "universe_size": universe_size,
        "stocks_scanned": len(results),
        "evaluated": len(ok),
        "insufficient_data": insufficient,
        "failed_validation": validation_failed,
        "errors": errors,
        "buy": buy,
        "watch": watch,
        "reject": reject,
        "positive_returns": positive,
        "negative_returns": negative,
        "flat_returns": flat,
        "top_return": max(returns) if returns else None,
        "worst_return": min(returns) if returns else None,
        "average_return": (sum(returns) / len(returns)) if returns else None,
        "median_return": _median(returns) if returns else None,
        "win_rate": (positive / len(returns) * 100.0) if returns else None,
        "top_positive": [_rank_row(r, i + 1, key_filters=True) for i, r in enumerate(ranked_pos)],
        "top_negative": [_rank_row(r, i + 1, key_filters=False) for i, r in enumerate(ranked_neg)],
        "filter_analytics": independent_filter_stats(ok, strategy.root),
        "filter_funnel": sequential_funnel(ok, strategy.root, universe_size=len(ok) or universe_size),
    }


def independent_filter_stats(evaluated: list[StrategyEvaluationResult], root: FilterNode) -> list[dict[str, Any]]:
    """How many stocks independently passed/failed each leaf filter."""
    leaves = root.leaf_nodes()
    stats: list[dict[str, Any]] = []
    for leaf in leaves:
        passed = 0
        failed = 0
        skipped = 0
        for row in evaluated:
            match = next((d for d in row.filter_details if d.get("filter_id") == leaf.id), None)
            if match is None:
                skipped += 1
                continue
            if match.get("passed") is True:
                passed += 1
            elif match.get("passed") is False:
                failed += 1
            else:
                skipped += 1
        total = passed + failed
        stats.append(
            {
                "filter_id": leaf.id,
                "label": leaf.display_label(),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "evaluated": total,
                "pass_pct": (passed / total * 100.0) if total else None,
                "fail_pct": (failed / total * 100.0) if total else None,
            }
        )
    return stats


def sequential_funnel(
    evaluated: list[StrategyEvaluationResult],
    root: FilterNode,
    *,
    universe_size: int,
) -> list[dict[str, Any]]:
    """Stocks remaining after applying leaf filters in definition order (AND)."""
    leaves = root.leaf_nodes()
    remaining_ids = {row.symbol for row in evaluated}
    steps = [
        {
            "step": 0,
            "filter_id": None,
            "label": "Universe evaluated",
            "remaining": universe_size,
        }
    ]
    for i, leaf in enumerate(leaves, start=1):
        still: set[str] = set()
        for row in evaluated:
            if row.symbol not in remaining_ids:
                continue
            match = next((d for d in row.filter_details if d.get("filter_id") == leaf.id), None)
            if match and match.get("passed") is True:
                still.add(row.symbol)
        remaining_ids = still
        steps.append(
            {
                "step": i,
                "filter_id": leaf.id,
                "label": leaf.display_label(),
                "remaining": len(remaining_ids),
            }
        )
    buy_n = sum(1 for row in evaluated if row.signal == BUY)
    steps.append(
        {
            "step": len(leaves) + 1,
            "filter_id": None,
            "label": "Final BUY signals",
            "remaining": buy_n,
        }
    )
    return steps


def _rank_row(row: StrategyEvaluationResult, rank: int, *, key_filters: bool) -> dict[str, Any]:
    return {
        "rank": rank,
        "symbol": row.symbol,
        "company": row.company,
        "entry_price": row.entry_price,
        "exit_price": row.exit_price,
        "return_pct": row.return_pct,
        "signal": row.signal,
        "key_filters": row.passed_filters if key_filters else row.failed_filters,
        "failed_filters": row.failed_filters,
        "passed_filters": row.passed_filters,
    }


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0
