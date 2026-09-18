"""Extract and evaluate individual strategy entry conditions from the Pine AST.

The scanner matches a stock only when every required entry-condition leaf
passes (logical AND). The collapsed Signal = 1 plot is derived from those
leaves and is never treated as the only displayed or matching condition.
"""

from __future__ import annotations

import re
from typing import Any

from .ast_nodes import BinaryOp, Call, Expr, Ident, Index, Member, NumberLit, Ternary, UnaryOp
from .compiler import CompiledIndicator, qualified_call_name, qualified_name
from .evaluator import Scalar, SeriesEngine, _is_num, _json_number, _truthy

ENTRY_ROOT_NAMES = (
    "scanSignal",
    "scan_signal",
    "longCondition",
    "long_condition",
    "buyCondition",
    "buy_condition",
    "buySignal",
    "buy_signal",
    "entryCondition",
    "entry_condition",
    "eligible",
)

COMPARISON_OPS = {">", ">=", "<", "<=", "==", "!="}
OP_LABELS = {">": ">", ">=": ">=", "<": "<", "<=": "<=", "==": "=", "!=": "≠"}
PRICE_SERIES = {"open", "high", "low", "close", "volume"}
VALIDITY_IDENT = {"hashistory", "has_history", "validbar", "valid_bar", "enoughbars", "enough_bars"}
CONDITIONS_OUTPUT_KEY = "__entry_conditions"


def extract_entry_terms(compiled: CompiledIndicator) -> list[Expr]:
    by_name = {stmt.name: stmt.expr for stmt in compiled.assignments}
    root = _find_entry_root(compiled, by_name)
    if root is None:
        return []
    leaves: list[Expr] = []
    seen: set[str] = set()
    for term in _flatten_and(root, by_name, set()):
        if _is_validity_guard(term, by_name, set()):
            continue
        key = _term_key(term)
        if key in seen:
            continue
        seen.add(key)
        leaves.append(term)
    return leaves


def evaluate_entry_conditions(engine: SeriesEngine, bar_index: int) -> list[dict[str, Any]]:
    if bar_index < 0 or bar_index >= engine.n:
        return []
    terms = strategy_entry_terms(engine.compiled)
    out: list[dict[str, Any]] = []
    by_name = {stmt.name: stmt.expr for stmt in engine.compiled.assignments}
    constants = {inp.name: inp.default for inp in engine.compiled.inputs}
    for index, term in enumerate(terms, start=1):
        name = label_condition(term, by_name, constants)
        if looks_like_aggregate_signal(name):
            continue
        passed: bool | None
        left_value: Scalar = None
        right_value: Scalar = None
        try:
            series = engine.eval_expr(term)
            raw = series[bar_index] if bar_index < len(series) else None
            if raw is None:
                passed = None
            else:
                passed = bool(_truthy(raw))
            if isinstance(term, BinaryOp) and term.op in COMPARISON_OPS:
                left_series = engine.eval_expr(term.left)
                right_series = engine.eval_expr(term.right)
                left_value = _json_number(left_series[bar_index] if bar_index < len(left_series) else None)
                right_value = _json_number(right_series[bar_index] if bar_index < len(right_series) else None)
        except Exception:
            passed = None
        out.append(
            {
                "id": f"c{index}",
                "name": name,
                "passed": False if passed is None else passed,
                "left_value": left_value,
                "right_value": right_value,
                "operator": term.op if isinstance(term, BinaryOp) else None,
            }
        )
    return out


def label_condition(expr: Expr, by_name: dict[str, Expr], constants: dict[str, Any] | None = None) -> str:
    constants = constants or {}
    node = _unwrap(expr, by_name, set())
    if isinstance(node, BinaryOp) and node.op in COMPARISON_OPS:
        left = label_operand(node.left, by_name, constants)
        right = label_operand(node.right, by_name, constants)
        return f"{left} {OP_LABELS.get(node.op, node.op)} {right}"
    if isinstance(node, Call):
        qname = qualified_call_name(node)
        if qname in {"ta.crossover", "crossover"} and len(node.args) >= 2:
            return (
                f"{label_operand(node.args[0], by_name, constants)} crosses above "
                f"{label_operand(node.args[1], by_name, constants)}"
            )
        if qname in {"ta.crossunder", "crossunder"} and len(node.args) >= 2:
            return (
                f"{label_operand(node.args[0], by_name, constants)} crosses below "
                f"{label_operand(node.args[1], by_name, constants)}"
            )
    if isinstance(node, Ident):
        return pretty_ident(node.name)
    return pretty_ident(str(node))


def label_operand(expr: Expr, by_name: dict[str, Expr], constants: dict[str, Any] | None = None) -> str:
    constants = constants or {}
    if isinstance(expr, Ident):
        if expr.name.lower() in PRICE_SERIES:
            return expr.name[:1].upper() + expr.name[1:].lower()
        if expr.name in constants and _is_num(constants[expr.name]):
            return _fmt_num(float(constants[expr.name]))
        if expr.name in by_name:
            resolved = _unwrap(by_name[expr.name], by_name, {expr.name})
            if isinstance(resolved, (NumberLit, Call, Index)):
                return label_operand(resolved, by_name, constants)
            if isinstance(resolved, Ident) and resolved.name != expr.name:
                return label_operand(resolved, by_name, constants)
            return pretty_ident(expr.name)
        return pretty_ident(expr.name)
    node = _unwrap(expr, by_name, set())
    if isinstance(node, NumberLit):
        return _fmt_num(node.value)
    if isinstance(node, Ident):
        return label_operand(node, by_name, constants)
    if isinstance(node, Index):
        base = label_operand(node.target, by_name, constants)
        if "High" in base:
            return base if base.startswith("Prior") else f"Prior {base}"
        return base
    if isinstance(node, Call):
        qname = qualified_call_name(node)
        period = _call_period(node, by_name, constants)
        if qname in {"ta.sma", "sma"}:
            src = label_operand(node.args[0], by_name, constants) if node.args else "Close"
            if src.lower() == "volume":
                return f"Average Volume {period or 20}"
            return f"SMA {period or 50}"
        if qname in {"ta.ema", "ema"}:
            return f"EMA {period or 20}"
        if qname in {"ta.rsi", "rsi"}:
            return f"RSI {period or 14}"
        if qname in {"ta.highest", "highest"}:
            return f"Prior {period or 252} High"
        if qname in {"ta.lowest", "lowest"}:
            return f"Prior {period or 252} Low"
        if qname == "request.security" and len(node.args) >= 3:
            inner = label_operand(node.args[2], by_name, constants)
            if inner.lower() == "close":
                return "NIFTY 500 Close"
            return f"NIFTY 500 {inner}"
        if qname == "na":
            inner = label_operand(node.args[0], by_name, constants) if node.args else "value"
            return f"{inner} is na"
    if isinstance(node, Member):
        return pretty_ident(qualified_name(node))
    return pretty_ident(getattr(node, "name", "") or "value")


def pretty_ident(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return "Condition"
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Za-z])(\d)", r"\1 \2", text)
    text = text.replace("_", " ").strip()
    parts: list[str] = []
    for part in text.split():
        low = part.lower()
        if low in {"sma", "ema", "rsi", "atr", "vwap", "wma"}:
            parts.append(low.upper())
        elif low in {"nifty"}:
            parts.append("NIFTY")
        else:
            parts.append(part[:1].upper() + part[1:] if part else part)
    if len(parts) >= 2 and parts[-1].lower() == "prior":
        parts = ["Prior", *parts[:-1]]
    return " ".join(parts)


def _find_entry_root(compiled: CompiledIndicator, by_name: dict[str, Expr]) -> Expr | None:
    for name in ENTRY_ROOT_NAMES:
        if name in by_name:
            return by_name[name]
    for out in compiled.outputs:
        if out.kind == "plot" and re.search(r"signal|scan$", out.name or "", re.I):
            return out.expr
    # TradingView Pine Screener columns from plotshape()/alertcondition() are the
    # boolean scan signal when the script has no 0/1 plot(scanSignal ? 1 : 0).
    for out in compiled.outputs:
        if out.kind in {"plotshape", "alertcondition"}:
            return out.expr
    return None


def _flatten_and(expr: Expr, by_name: dict[str, Expr], visited: set[str]) -> list[Expr]:
    node = _unwrap(expr, by_name, visited)
    if isinstance(node, Ternary):
        return _flatten_and(node.condition, by_name, visited)
    if isinstance(node, BinaryOp) and node.op == "and":
        return _flatten_and(node.left, by_name, visited) + _flatten_and(node.right, by_name, visited)
    return [node]


def _unwrap(expr: Expr, by_name: dict[str, Expr], visited: set[str]) -> Expr:
    node = expr
    while isinstance(node, Ident) and node.name in by_name and node.name.lower() not in PRICE_SERIES:
        if node.name in visited:
            break
        visited.add(node.name)
        node = by_name[node.name]
    if isinstance(node, Ternary):
        then_is_one = isinstance(node.then_expr, NumberLit) and float(node.then_expr.value) == 1.0
        else_is_zero = isinstance(node.else_expr, NumberLit) and float(node.else_expr.value) == 0.0
        if then_is_one and else_is_zero:
            return _unwrap(node.condition, by_name, visited)
    return node


def _is_validity_guard(expr: Expr, by_name: dict[str, Expr], visited: set[str]) -> bool:
    node = _unwrap(expr, by_name, visited)
    if isinstance(node, Ident) and node.name.lower() in VALIDITY_IDENT:
        return True
    if isinstance(node, Call) and qualified_call_name(node) == "na":
        return True
    if isinstance(node, UnaryOp) and node.op == "not":
        inner = _unwrap(node.expr, by_name, set(visited))
        if isinstance(inner, Call) and qualified_call_name(inner) == "na":
            return True
    if isinstance(node, BinaryOp) and node.op in {">", ">="}:
        left = _unwrap(node.left, by_name, set(visited))
        right = _unwrap(node.right, by_name, set(visited))
        if _is_zero(right) and _is_price_series(left):
            return True
    return False


def _is_price_series(expr: Expr) -> bool:
    if isinstance(expr, Ident) and expr.name.lower() in PRICE_SERIES:
        return True
    if isinstance(expr, Index):
        return _is_price_series(expr.target)
    return False


def _is_zero(expr: Expr) -> bool:
    return isinstance(expr, NumberLit) and float(expr.value) == 0.0


def _call_period(call: Call, by_name: dict[str, Expr], constants: dict[str, Any] | None = None) -> int | None:
    constants = constants or {}
    qname = qualified_call_name(call)
    arg = None
    if qname in {"ta.sma", "sma", "ta.ema", "ema", "ta.rsi", "rsi", "ta.highest", "highest", "ta.lowest", "lowest"}:
        if len(call.args) >= 2:
            arg = call.args[1]
        elif qname in {"ta.rsi", "rsi"} and call.args:
            arg = call.args[0]
    if arg is None:
        return None
    node = _unwrap(arg, by_name, set())
    if isinstance(node, NumberLit):
        return int(node.value)
    if isinstance(node, Ident):
        if node.name in constants and _is_num(constants[node.name]):
            return int(constants[node.name])
        if node.name in by_name:
            inner = _unwrap(by_name[node.name], by_name, set())
            if isinstance(inner, NumberLit):
                return int(inner.value)
    return None


def _fmt_num(value: float) -> str:
    if not _is_num(value):
        return str(value)
    num = float(value)
    if abs(num - round(num)) < 1e-9:
        return str(int(round(num)))
    return f"{num:.4f}".rstrip("0").rstrip(".")


def _term_key(expr: Expr) -> str:
    if isinstance(expr, BinaryOp):
        return f"{type(expr.left).__name__}:{getattr(expr.left, 'name', '')}:{expr.op}:{type(expr.right).__name__}:{getattr(expr.right, 'name', '')}:{getattr(expr.right, 'value', '')}"
    if isinstance(expr, Ident):
        return f"ident:{expr.name}"
    if isinstance(expr, Call):
        return f"call:{qualified_call_name(expr)}"
    return repr(expr)


def looks_like_aggregate_signal(name: str) -> bool:
    text = (name or "").strip().lower()
    if not text:
        return False
    left = text.split("=")[0].strip()
    if re.search(r"^(eligible\s+)?(signal|scan)$", left):
        return True
    if re.search(r"\beligible\s+signal$", left):
        return True
    if re.search(r"\bbreakout\s+signal$", left):
        return True
    return False


def extract_comparison_assignments(compiled: CompiledIndicator) -> list[Expr]:
    by_name = {stmt.name: stmt.expr for stmt in compiled.assignments}
    leaves: list[Expr] = []
    seen: set[str] = set()
    for stmt in compiled.assignments:
        for term in _flatten_and(stmt.expr, by_name, set()):
            node = _unwrap(term, by_name, set())
            usable = False
            if isinstance(node, BinaryOp) and node.op in COMPARISON_OPS:
                usable = not _is_validity_guard(node, by_name, set())
            elif isinstance(node, Call) and qualified_call_name(node) in {
                "ta.crossover",
                "crossover",
                "ta.crossunder",
                "crossunder",
            }:
                usable = True
            if not usable:
                continue
            key = _term_key(node)
            if key in seen:
                continue
            seen.add(key)
            leaves.append(node)
    return leaves


def collect_entry_terms(compiled: CompiledIndicator) -> list[Expr]:
    by_name = {stmt.name: stmt.expr for stmt in compiled.assignments}
    constants = {inp.name: inp.default for inp in compiled.inputs}
    combined: list[Expr] = []
    seen_labels: set[str] = set()
    for term in extract_entry_terms(compiled) + extract_comparison_assignments(compiled):
        name = label_condition(term, by_name, constants)
        if looks_like_aggregate_signal(name):
            continue
        key = name.strip().lower() or _term_key(term)
        if key in seen_labels:
            continue
        seen_labels.add(key)
        combined.append(term)
    return combined


def strategy_entry_terms(compiled: CompiledIndicator) -> list[Expr]:
    """Leaves of the selected strategy's entry AND-tree. Never the collapsed Signal = 1 plot."""
    by_name = {stmt.name: stmt.expr for stmt in compiled.assignments}
    constants = {inp.name: inp.default for inp in compiled.inputs}
    primary: list[Expr] = []
    seen: set[str] = set()
    for term in extract_entry_terms(compiled):
        name = label_condition(term, by_name, constants)
        if looks_like_aggregate_signal(name):
            continue
        key = name.strip().lower() or _term_key(term)
        if key in seen:
            continue
        seen.add(key)
        primary.append(term)
    if primary:
        return primary
    return collect_entry_terms(compiled)


def entry_condition_defs(compiled: CompiledIndicator) -> list[dict[str, Any]]:
    by_name = {stmt.name: stmt.expr for stmt in compiled.assignments}
    constants = {inp.name: inp.default for inp in compiled.inputs}
    out: list[dict[str, Any]] = []
    for index, term in enumerate(strategy_entry_terms(compiled), start=1):
        name = label_condition(term, by_name, constants)
        if not name or looks_like_aggregate_signal(name):
            continue
        out.append({"id": f"c{index}", "name": name})
    return out


def attach_entry_conditions(
    parsed: dict[str, Any] | None,
    compiled: CompiledIndicator | None = None,
    source_code: str | None = None,
) -> dict[str, Any]:
    data = dict(parsed or {})
    cleaned = _named_condition_defs(data.get("entry_conditions"))
    if cleaned:
        data["entry_conditions"] = cleaned
        return data
    compiled_obj = compiled
    if compiled_obj is None and (source_code or "").strip():
        try:
            from .compiler import compile_source

            compiled_obj = compile_source(source_code)
        except Exception:
            compiled_obj = None
    data["entry_conditions"] = entry_condition_defs(compiled_obj) if compiled_obj is not None else []
    return data


def _named_condition_defs(raw: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not isinstance(raw, list):
        return rows
    for index, item in enumerate(raw, start=1):
        if isinstance(item, str):
            name = item.strip()
            cond_id = f"c{index}"
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            cond_id = str(item.get("id") or f"c{index}")
        else:
            continue
        key = name.lower()
        if not name or looks_like_aggregate_signal(name) or key in seen:
            continue
        seen.add(key)
        rows.append({"id": cond_id, "name": name})
    return rows


def is_aggregate_signal_filter(item: dict[str, Any] | None) -> bool:
    if not isinstance(item, dict):
        return False
    field = str(item.get("field") or "").strip()
    op = str(item.get("operator") or "=").strip()
    value = item.get("value")
    if looks_like_aggregate_signal(field):
        return True
    return looks_like_aggregate_signal(f"{field} {op} {value}")


def usable_condition_rows(items: list | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        key = name.lower()
        if not name or looks_like_aggregate_signal(name) or key in seen:
            continue
        seen.add(key)
        row: dict[str, Any] = {"name": name, "passed": bool(item.get("passed"))}
        if item.get("id"):
            row["id"] = item.get("id")
        if "left_value" in item:
            row["left_value"] = item.get("left_value")
        if "right_value" in item:
            row["right_value"] = item.get("right_value")
        if item.get("operator"):
            row["operator"] = item.get("operator")
        rows.append(row)
    return rows


def all_required_conditions_passed(conditions: list | None) -> bool:
    usable = usable_condition_rows(conditions)
    if not usable:
        return False
    return all(bool(item.get("passed")) for item in usable)


def _compare(left: float, right: float, op: str) -> bool:
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op in {"==", "="}:
        return left == right
    if op == "!=":
        return left != right
    return False


def _numeric_from_expr(
    expr: Expr,
    compiled: CompiledIndicator,
    outputs: dict[str, Any],
    ohlcv: dict[str, Any],
    by_name: dict[str, Expr],
    constants: dict[str, Any],
    visited: set[str] | None = None,
) -> float | None:
    visited = visited or set()
    if isinstance(expr, NumberLit):
        return float(expr.value)
    if isinstance(expr, Ident):
        if expr.name in visited:
            return None
        visited.add(expr.name)
        if expr.name in constants and _is_num(constants[expr.name]):
            return float(constants[expr.name])
        low = expr.name.lower()
        if low in PRICE_SERIES:
            value = (ohlcv or {}).get(low)
            if _is_num(value):
                return float(value)
            titled = expr.name[:1].upper() + expr.name[1:].lower()
            value = (outputs or {}).get(titled)
            if _is_num(value):
                return float(value)
        for out in compiled.outputs:
            if isinstance(out.expr, Ident) and out.expr.name == expr.name:
                value = (outputs or {}).get(out.name)
                if _is_num(value):
                    return float(value)
        pretty = pretty_ident(expr.name)
        for key, value in (outputs or {}).items():
            if str(key).lower() == pretty.lower() and _is_num(value):
                return float(value)
        if expr.name in by_name:
            return _numeric_from_expr(by_name[expr.name], compiled, outputs, ohlcv, by_name, constants, visited)
        return None
    node = _unwrap(expr, by_name, set())
    if isinstance(node, NumberLit):
        return float(node.value)
    if isinstance(node, Ident):
        return _numeric_from_expr(node, compiled, outputs, ohlcv, by_name, constants, visited)
    if isinstance(node, Index):
        if isinstance(node.target, Ident) and node.target.name.lower() == "close" and node.offset == 252:
            value = (outputs or {}).get("Close t-252")
            if _is_num(value):
                return float(value)
        return _numeric_from_expr(node.target, compiled, outputs, ohlcv, by_name, constants, visited)
    if isinstance(node, Call):
        label = label_operand(node, by_name, constants)
        value = (outputs or {}).get(label)
        if _is_num(value):
            return float(value)
        aliases = {
            "Average Volume 20": ("Volume SMA 20", "Volume SMA20"),
            "Prior 252 High": ("Prior 252 High", "Prior 252-Session High"),
            "NIFTY 500 SMA 50": ("NIFTY 500 SMA 50", "NIFTY 500 SMA50"),
        }
        for alias in aliases.get(label, ()):
            value = (outputs or {}).get(alias)
            if _is_num(value):
                return float(value)
    return None


def evaluate_terms_against_outputs(
    compiled: CompiledIndicator,
    terms: list[Expr],
    outputs: dict[str, Any] | None,
    ohlcv: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    by_name = {stmt.name: stmt.expr for stmt in compiled.assignments}
    constants = {inp.name: inp.default for inp in compiled.inputs}
    results: list[dict[str, Any]] = []
    for term in terms:
        name = label_condition(term, by_name, constants)
        if looks_like_aggregate_signal(name):
            continue
        passed = False
        left_value: Scalar = None
        right_value: Scalar = None
        node = _unwrap(term, by_name, set())
        if isinstance(node, BinaryOp) and node.op in COMPARISON_OPS:
            left_value = _numeric_from_expr(node.left, compiled, outputs or {}, ohlcv or {}, by_name, constants)
            right_value = _numeric_from_expr(node.right, compiled, outputs or {}, ohlcv or {}, by_name, constants)
            if left_value is None or right_value is None:
                passed = False
            else:
                passed = _compare(float(left_value), float(right_value), node.op)
        else:
            ident_val = _numeric_from_expr(term, compiled, outputs or {}, ohlcv or {}, by_name, constants)
            if ident_val is None:
                passed = False
            else:
                passed = bool(_truthy(ident_val))
        results.append(
            {
                "name": name,
                "passed": passed,
                "left_value": left_value,
                "right_value": right_value,
                "operator": node.op if isinstance(node, BinaryOp) else None,
            }
        )
    return results


def conditions_for_detail(
    *,
    source_code: str | None,
    outputs: dict[str, Any] | None,
    ohlcv: dict[str, Any] | None,
    stored: list | None,
    filters: list | None,
) -> list[dict[str, Any]]:
    """Individual Scan Filters for Overview. Never keep a lone aggregate Signal = 1 row when the Pine has real conditions."""
    usable_stored = usable_condition_rows(stored)
    if usable_stored:
        return usable_stored

    reconstructed: list[dict[str, Any]] = []
    if source_code and source_code.strip():
        try:
            from .compiler import compile_source

            compiled = compile_source(source_code)
            reconstructed = evaluate_terms_against_outputs(
                compiled,
                strategy_entry_terms(compiled),
                outputs,
                ohlcv,
            )
        except Exception:
            reconstructed = []
    if reconstructed:
        return usable_condition_rows(reconstructed)

    def _from_filters(*, include_signal: bool) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in filters or []:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or "").strip()
            op = str(item.get("operator") or "=").strip()
            value = item.get("value")
            if op == "between":
                name = f"{field} between {item.get('low')} and {item.get('high')}"
            elif value is None or value == "":
                name = field
            else:
                name = f"{field} {op} {value}"
            if not include_signal and looks_like_aggregate_signal(name):
                continue
            passed = False
            if outputs and field in outputs:
                from .filters import _match

                try:
                    passed = bool(_match(outputs.get(field), item))
                except Exception:
                    passed = False
            rows.append({"name": name, "passed": passed})
        return rows

    fallback = _from_filters(include_signal=False)
    if fallback:
        return fallback
    return _from_filters(include_signal=True)
