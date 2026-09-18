"""Deterministic filter evaluation. AND / OR / NOT groups and comparison operators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .indicators import BarSeries
from .schema import FilterNode, Operand, is_benchmark_leaf


@dataclass
class LeafEvaluation:
    filter_id: str
    label: str
    passed: bool | None
    left_value: float | None
    right_value: float | None
    right_high_value: float | None
    operator: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "filter_id": self.filter_id,
            "label": self.label,
            "passed": self.passed,
            "left_value": self.left_value,
            "right_value": self.right_value,
            "right_high_value": self.right_high_value,
            "operator": self.operator,
            "reason": self.reason,
        }


@dataclass
class FilterEvaluation:
    passed: bool | None
    leaves: list[LeafEvaluation]
    unevaluable: bool = False


def _compare(op: str, left: float | None, right: float | None, high: float | None, prev_left: float | None, prev_right: float | None) -> tuple[bool | None, str | None]:
    if op in {"between", "outside"}:
        if left is None or right is None or high is None:
            return None, "missing_operand"
        lo, hi = (right, high) if right <= high else (high, right)
        inside = lo <= left <= hi
        if op == "between":
            return inside, None
        return (not inside), None
    if left is None or right is None:
        return None, "missing_operand"
    if op == ">":
        return left > right, None
    if op == "<":
        return left < right, None
    if op == ">=":
        return left >= right, None
    if op == "<=":
        return left <= right, None
    if op == "==":
        return math_close(left, right), None
    if op == "!=":
        return not math_close(left, right), None
    if op == "cross_above":
        if prev_left is None or prev_right is None:
            return None, "missing_prior_bar"
        return prev_left <= prev_right and left > right, None
    if op == "cross_below":
        if prev_left is None or prev_right is None:
            return None, "missing_prior_bar"
        return prev_left >= prev_right and left < right, None
    return None, f"unsupported_operator:{op}"


def math_close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def evaluate_tree(node: FilterNode, series: BarSeries, t: int, benchmark: BarSeries | None = None) -> FilterEvaluation:
    leaves: list[LeafEvaluation] = []
    passed = _eval_node(node, series, t, leaves, benchmark)
    unevaluable = passed is None or any(leaf.passed is None for leaf in leaves)
    return FilterEvaluation(passed=passed, leaves=leaves, unevaluable=unevaluable)


def _eval_node(node: FilterNode, series: BarSeries, t: int, leaves: list[LeafEvaluation], benchmark: BarSeries | None = None) -> bool | None:
    if node.kind == "leaf":
        return _eval_leaf(node, series, t, leaves, benchmark)
    op = (node.op or "AND").upper()
    if op == "NOT":
        if len(node.children) != 1:
            return None
        child = _eval_node(node.children[0], series, t, leaves, benchmark)
        if child is None:
            return None
        return not child
    results: list[bool | None] = [_eval_node(child, series, t, leaves, benchmark) for child in node.children]
    if not results:
        return True
    if any(r is None for r in results):
        return None
    bools = [bool(r) for r in results]
    if op == "OR":
        return any(bools)
    return all(bools)


def _eval_leaf(node: FilterNode, series: BarSeries, t: int, leaves: list[LeafEvaluation], benchmark: BarSeries | None = None) -> bool | None:
    if is_benchmark_leaf(node):
        return _eval_benchmark_leaf(node, series, t, leaves, benchmark)
    left = node.left or Operand(kind="series", name="CLOSE")
    right = node.right
    left_v = series.value_at(left, t)
    right_v = series.value_at(right, t) if right else None
    high_v = series.value_at(node.right_high, t) if node.right_high else None
    prev_left = series.value_at(left, t - 1) if t > 0 else None
    prev_right = series.value_at(right, t - 1) if right and t > 0 else None
    passed, reason = _compare(node.op or ">", left_v, right_v, high_v, prev_left, prev_right)
    leaves.append(
        LeafEvaluation(
            filter_id=node.id,
            label=node.display_label(),
            passed=passed,
            left_value=left_v,
            right_value=right_v,
            right_high_value=high_v,
            operator=node.op or ">",
            reason=reason,
        )
    )
    return passed


def _eval_benchmark_leaf(node: FilterNode, series: BarSeries, t: int, leaves: list[LeafEvaluation], benchmark: BarSeries | None) -> bool | None:
    """Market-gate leaf: every series operand is evaluated on the benchmark index bars.

    The benchmark bar is aligned to the stock bar by date (last index bar on/before
    the stock's date), so no future index data is read.
    """
    left = node.left or Operand(kind="series", name="BENCHMARK_CLOSE")
    op = node.op or ">"
    day = series.dates[t] if 0 <= t < len(series.dates) else None
    bt = benchmark.index_on_or_before(day) if benchmark is not None and day is not None and len(benchmark) > 0 else None
    if bt is None:
        leaves.append(
            LeafEvaluation(
                filter_id=node.id,
                label=node.display_label(),
                passed=None,
                left_value=None,
                right_value=None,
                right_high_value=None,
                operator=op,
                reason="benchmark_data_unavailable",
            )
        )
        return None
    left_v = benchmark.value_at(left, bt)
    right_v = benchmark.value_at(node.right, bt) if node.right else None
    high_v = benchmark.value_at(node.right_high, bt) if node.right_high else None
    prev_left = benchmark.value_at(left, bt - 1) if bt > 0 else None
    prev_right = benchmark.value_at(node.right, bt - 1) if node.right and bt > 0 else None
    passed, reason = _compare(op, left_v, right_v, high_v, prev_left, prev_right)
    leaves.append(
        LeafEvaluation(
            filter_id=node.id,
            label=node.display_label(),
            passed=passed,
            left_value=left_v,
            right_value=right_v,
            right_high_value=high_v,
            operator=op,
            reason=reason,
        )
    )
    return passed
