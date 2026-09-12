"""Filter evaluation against parsed indicator outputs. No raw SQL."""

from __future__ import annotations

from typing import Any

from .compiler import CompiledIndicator
from .errors import PineCompileError
from .evaluator import Scalar, _is_num, _truthy

NUMERIC_OPS = {"=", "==", "!=", ">", ">=", "<", "<=", "between", "is_null", "is_not_null"}
BOOL_OPS = {"is_true", "is_false", "=", "==", "!=", "is_null", "is_not_null"}
STRING_OPS = {"equals", "contains", "=", "==", "!=", "is_null", "is_not_null"}


def validate_filters(compiled: CompiledIndicator, filters: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    allowed = {out.name for out in compiled.outputs}
    cleaned: list[dict[str, Any]] = []
    for item in filters or []:
        field = str(item.get("field") or "").strip()
        if field not in allowed:
            raise PineCompileError(
                f"Filter field '{field}' is not an output of this indicator.",
                line=1,
                column=1,
                code="INVALID_FILTER_FIELD",
            )
        op = str(item.get("operator") or "=").strip()
        cleaned.append(
            {
                "field": field,
                "operator": op,
                "value": item.get("value"),
                "low": item.get("low"),
                "high": item.get("high"),
            }
        )
    return cleaned


def row_matches(outputs: dict[str, Scalar], filters: list[dict[str, Any]]) -> bool:
    for item in filters:
        if not _match(outputs.get(item["field"]), item):
            return False
    return True


def _match(value: Scalar, item: dict[str, Any]) -> bool:
    op = str(item.get("operator") or "=")
    if op in {"is_null", "is none"}:
        return value is None
    if op in {"is_not_null", "is not null"}:
        return value is not None
    if op in {"is_true"}:
        return _truthy(value)
    if op in {"is_false"}:
        return not _truthy(value)
    if op == "between":
        num = _num(value)
        low = _num(item.get("low"))
        high = _num(item.get("high"))
        if num is None or low is None or high is None:
            return False
        return low <= num <= high
    if op == "contains":
        return str(item.get("value") or "").lower() in str(value or "").lower()
    if op == "equals":
        return str(value) == str(item.get("value"))
    target = item.get("value")
    if op in {"=", "=="}:
        return _equals(value, target)
    if op == "!=":
        return not _equals(value, target)
    left = _num(value)
    right = _num(target)
    if left is None or right is None:
        return False
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    return False


def _equals(value: Scalar, target: Any) -> bool:
    if value is None or target is None:
        return False
    if isinstance(target, bool) or isinstance(value, bool):
        return _truthy(value) is _as_bool(target)
    lv, rv = _num(value), _num(target)
    if lv is not None and rv is not None:
        return lv == rv
    return str(value) == str(target)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if _num(value) is not None:
        return float(value) != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return _truthy(value)


def _num(value: Any) -> float | None:
    if _is_num(value):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None
