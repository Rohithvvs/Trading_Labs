"""Structured strategy configuration. Frontend never encodes evaluation logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CALCULATION_VERSION = "strategy_tester.v1"
DEFAULT_UNIVERSE = "ALL_755"
DEFAULT_TIMEFRAME = "1D"
DEFAULT_CAPITAL = 100_000.0
DEFAULT_WATCH_MIN_PASS_RATIO = 0.5
DEFAULT_WATCH_MIN_PASSED = 1

OPERATORS = (
    ">",
    "<",
    ">=",
    "<=",
    "==",
    "!=",
    "cross_above",
    "cross_below",
    "between",
    "outside",
)

GROUP_OPS = ("AND", "OR", "NOT")
POSITION_SIDES = ("LONG", "SHORT")
RETURN_METHODS = ("SIMPLE",)
UNIVERSE_CODES = ("ALL_755", "NIFTY500")

# Left-operand series name for benchmark ("market gate") filters, e.g. NIFTY 500 Close > NIFTY 500 SMA 50.
# A leaf referencing this series is evaluated against the benchmark index bars, not the stock bars.
BENCHMARK_SERIES = "BENCHMARK_CLOSE"

INDICATOR_ALIASES = {
    "CLOSE": ("CLOSE", None),
    "OPEN": ("OPEN", None),
    "HIGH": ("HIGH", None),
    "LOW": ("LOW", None),
    "VOLUME": ("VOLUME", None),
    "BENCHMARK_CLOSE": ("BENCHMARK_CLOSE", None),
    "BENCHMARK": ("BENCHMARK_CLOSE", None),
    "NIFTY500_CLOSE": ("BENCHMARK_CLOSE", None),
    "NIFTY_500_CLOSE": ("BENCHMARK_CLOSE", None),
    "PREV_CLOSE": ("PREV_CLOSE", None),
    "PREVIOUS_CLOSE": ("PREV_CLOSE", None),
    "PREV_HIGH": ("PREV_HIGH", None),
    "PREVIOUS_DAY_HIGH": ("PREV_HIGH", None),
    "DAILY_RETURN": ("DAILY_RETURN", None),
    "GAP_PCT": ("GAP_PCT", None),
    "GAP": ("GAP_PCT", None),
    "VWAP": ("VWAP", None),
    "RSI": ("RSI", 14),
    "MACD": ("MACD", None),
    "MACD_SIGNAL": ("MACD_SIGNAL", None),
    "MACD_HISTOGRAM": ("MACD_HISTOGRAM", None),
    "MACD_HIST": ("MACD_HISTOGRAM", None),
    "STOCHASTIC": ("STOCH_K", 14),
    "STOCH": ("STOCH_K", 14),
    "STOCH_K": ("STOCH_K", 14),
    "STOCH_D": ("STOCH_D", 14),
    "ROC": ("ROC", 12),
    "ATR": ("ATR", 14),
    "AVG_VOLUME": ("AVG_VOLUME", 20),
    "AVERAGE_VOLUME": ("AVG_VOLUME", 20),
    "REL_VOLUME": ("REL_VOLUME", 20),
    "RELATIVE_VOLUME": ("REL_VOLUME", 20),
    "REL": ("REL_VOLUME", 20),
    "VOL": ("VOLUME", None),
    "MOMENTUM": ("ROC", 60),
    "VOLUME_CHANGE_PCT": ("VOLUME_CHANGE_PCT", None),
    "BB_UPPER": ("BB_UPPER", 20),
    "BB_LOWER": ("BB_LOWER", 20),
    "BB_MIDDLE": ("BB_MIDDLE", 20),
    "BB_WIDTH": ("BB_WIDTH", 20),
    "BOLLINGER_UPPER": ("BB_UPPER", 20),
    "BOLLINGER_LOWER": ("BB_LOWER", 20),
    "HV": ("HV", 20),
    "HISTORICAL_VOLATILITY": ("HV", 20),
}

OPERATOR_ALIASES = {
    "gt": ">",
    "lt": "<",
    "gte": ">=",
    "lte": "<=",
    "eq": "==",
    "neq": "!=",
    "cross above": "cross_above",
    "cross_above": "cross_above",
    "crosses_above": "cross_above",
    "crosses above": "cross_above",
    "crossbelow": "cross_below",
    "cross below": "cross_below",
    "cross_below": "cross_below",
    "crosses_below": "cross_below",
    "crosses below": "cross_below",
    "between": "between",
    "outside": "outside",
}


class StrategyConfigError(ValueError):
    """Invalid strategy configuration."""


@dataclass(frozen=True)
class Operand:
    kind: Literal["series", "literal"]
    name: str | None = None
    period: int | None = None
    std: float | None = None
    value: float | None = None

    def key(self) -> str:
        if self.kind == "literal":
            return f"lit:{self.value}"
        if self.period:
            if self.std is not None:
                return f"{self.name}_{self.period}_{self.std}"
            return f"{self.name}_{self.period}"
        return str(self.name or "")

    def label(self) -> str:
        if self.kind == "literal":
            v = self.value
            if v is None:
                return "null"
            if float(v).is_integer():
                return str(int(v))
            return f"{v:g}"
        name = (self.name or "").upper()
        pretty = {
            "CLOSE": "Close",
            "OPEN": "Open",
            "HIGH": "High",
            "LOW": "Low",
            "VOLUME": "Volume",
            "BENCHMARK_CLOSE": "NIFTY 500 Close",
            "PREV_CLOSE": "Previous Close",
            "PREV_HIGH": "Previous Day High",
            "DAILY_RETURN": "Daily Return",
            "GAP_PCT": "Gap %",
            "AVG_VOLUME": "Average Volume",
            "REL_VOLUME": "Relative Volume",
            "VOLUME_CHANGE_PCT": "Volume Change %",
            "BB_UPPER": "Upper Bollinger Band",
            "BB_LOWER": "Lower Bollinger Band",
            "BB_MIDDLE": "Middle Bollinger Band",
            "BB_WIDTH": "Bollinger Band Width",
            "MACD_SIGNAL": "MACD Signal",
            "MACD_HISTOGRAM": "MACD Histogram",
            "STOCH_K": "Stochastic %K",
            "STOCH_D": "Stochastic %D",
            "HV": "Historical Volatility",
        }.get(name, name.replace("_", " ").title() if name else "")
        if name in {"SMA", "EMA", "WMA"} and self.period:
            return f"{name} {self.period}"
        if name == "HIGH" and self.period:
            return f"{self.period} Day High"
        if name == "LOW" and self.period:
            return f"{self.period} Day Low"
        if name in {"RSI", "ATR", "ROC", "AVG_VOLUME", "BB_UPPER", "BB_LOWER", "BB_MIDDLE", "BB_WIDTH", "HV", "VWAP"} and self.period:
            return f"{pretty} {self.period}"
        return pretty


@dataclass
class FilterNode:
    id: str
    kind: Literal["leaf", "group"]
    op: str | None = None
    left: Operand | None = None
    right: Operand | None = None
    right_high: Operand | None = None
    children: list["FilterNode"] = field(default_factory=list)
    label: str | None = None

    def display_label(self) -> str:
        if self.label:
            return self.label
        if self.kind == "group":
            return self.op or "AND"
        left = self.left.label() if self.left else "?"
        op = _op_label(self.op or ">")
        if (self.op or "") in {"between", "outside"}:
            lo = self.right.label() if self.right else "?"
            hi = self.right_high.label() if self.right_high else "?"
            return f"{left} {op} {lo} and {hi}"
        right = self.right.label() if self.right else "?"
        return f"{left} {op} {right}"

    def leaf_nodes(self) -> list["FilterNode"]:
        if self.kind == "leaf":
            return [self]
        out: list[FilterNode] = []
        for child in self.children:
            out.extend(child.leaf_nodes())
        return out


@dataclass
class SignalRules:
    buy_requires_all: bool = True
    watch_min_passed: int = DEFAULT_WATCH_MIN_PASSED
    watch_min_pass_ratio: float = DEFAULT_WATCH_MIN_PASS_RATIO


@dataclass
class PositionRules:
    side: str = "LONG"
    return_method: str = "SIMPLE"
    entry_rule: str = "WINDOW_START"
    exit_rule: str = "WINDOW_END"
    stop_loss_pct: float | None = None
    target_pct: float | None = None
    trailing_stop_pct: float | None = None
    time_exit_bars: int | None = None


@dataclass
class StrategyDefinitionConfig:
    name: str
    description: str = ""
    universe: str = DEFAULT_UNIVERSE
    timeframe: str = DEFAULT_TIMEFRAME
    root: FilterNode = field(default_factory=lambda: FilterNode(id="root", kind="group", op="AND"))
    position: PositionRules = field(default_factory=PositionRules)
    signal: SignalRules = field(default_factory=SignalRules)
    initial_capital: float = DEFAULT_CAPITAL
    source: dict[str, Any] = field(default_factory=lambda: {"type": "builder"})

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "universe": self.universe,
            "timeframe": self.timeframe,
            "source": self.source,
            "filters": _node_to_dict(self.root),
            "position_rules": {
                "side": self.position.side,
                "return_method": self.position.return_method,
                "entry_rule": self.position.entry_rule,
                "exit_rule": self.position.exit_rule,
                "stop_loss_pct": self.position.stop_loss_pct,
                "target_pct": self.position.target_pct,
                "trailing_stop_pct": self.position.trailing_stop_pct,
                "time_exit_bars": self.position.time_exit_bars,
            },
            "signal_rules": {
                "buy_requires_all": self.signal.buy_requires_all,
                "watch_min_passed": self.signal.watch_min_passed,
                "watch_min_pass_ratio": self.signal.watch_min_pass_ratio,
            },
            "initial_capital": self.initial_capital,
            "calculation_version": CALCULATION_VERSION,
        }


def parse_strategy_config(raw: dict[str, Any] | None) -> StrategyDefinitionConfig:
    if not isinstance(raw, dict):
        raise StrategyConfigError("Strategy configuration must be an object")
    name = str(raw.get("name") or "").strip() or "Untitled strategy"
    description = str(raw.get("description") or "").strip()
    universe = str(raw.get("universe") or DEFAULT_UNIVERSE).strip().upper()
    if universe in {"ALL", "ALL_STOCKS", "NIFTY_500", "NIFTY500"}:
        universe = DEFAULT_UNIVERSE if universe != "NIFTY500" else "NIFTY500"
    if universe not in UNIVERSE_CODES:
        universe = DEFAULT_UNIVERSE
    timeframe = str(raw.get("timeframe") or DEFAULT_TIMEFRAME).strip() or DEFAULT_TIMEFRAME
    root = _parse_root(raw)
    if not root.leaf_nodes():
        raise StrategyConfigError("Strategy must include at least one filter")
    pos_raw = raw.get("position_rules") or raw.get("position") or {}
    if not isinstance(pos_raw, dict):
        pos_raw = {}
    side = str(pos_raw.get("side") or raw.get("side") or "LONG").upper()
    if side not in POSITION_SIDES:
        raise StrategyConfigError("position side must be LONG or SHORT")
    return_method = str(pos_raw.get("return_method") or "SIMPLE").upper()
    if return_method not in RETURN_METHODS:
        raise StrategyConfigError("return_method must be SIMPLE")
    signal_raw = raw.get("signal_rules") or {}
    if not isinstance(signal_raw, dict):
        signal_raw = {}
    try:
        capital = float(raw.get("initial_capital") or DEFAULT_CAPITAL)
    except (TypeError, ValueError) as exc:
        raise StrategyConfigError("initial_capital must be a number") from exc
    if capital <= 0:
        raise StrategyConfigError("initial_capital must be positive")
    watch_ratio = float(signal_raw.get("watch_min_pass_ratio", DEFAULT_WATCH_MIN_PASS_RATIO))
    if not 0 <= watch_ratio <= 1:
        raise StrategyConfigError("watch_min_pass_ratio must be between 0 and 1")
    return StrategyDefinitionConfig(
        name=name,
        description=description,
        universe=universe,
        timeframe=timeframe,
        root=root,
        position=PositionRules(
            side=side,
            return_method=return_method,
            entry_rule=str(pos_raw.get("entry_rule") or "WINDOW_START").upper(),
            exit_rule=str(pos_raw.get("exit_rule") or "WINDOW_END").upper(),
            stop_loss_pct=_opt_float(pos_raw.get("stop_loss_pct")),
            target_pct=_opt_float(pos_raw.get("target_pct")),
            trailing_stop_pct=_opt_float(pos_raw.get("trailing_stop_pct")),
            time_exit_bars=_opt_int(pos_raw.get("time_exit_bars")),
        ),
        signal=SignalRules(
            buy_requires_all=bool(signal_raw.get("buy_requires_all", True)),
            watch_min_passed=max(1, int(signal_raw.get("watch_min_passed", DEFAULT_WATCH_MIN_PASSED))),
            watch_min_pass_ratio=watch_ratio,
        ),
        initial_capital=capital,
        source=raw.get("source") if isinstance(raw.get("source"), dict) else {"type": "builder"},
    )


def required_warmup(config: StrategyDefinitionConfig) -> int:
    """Bars needed before the evaluation bar so indicators are defined (no future bars)."""
    needed = 1
    for leaf in config.root.leaf_nodes():
        for operand in (leaf.left, leaf.right, leaf.right_high):
            if operand is None or operand.kind != "series":
                continue
            period = operand.period or 0
            name = (operand.name or "").upper()
            if name == "MACD":
                needed = max(needed, 26 + 9)
            elif name in {"MACD_SIGNAL", "MACD_HISTOGRAM"}:
                needed = max(needed, 26 + 9)
            elif name == "ATR":
                needed = max(needed, period or 14)
            elif period:
                needed = max(needed, period)
            if (leaf.op or "") in {"cross_above", "cross_below"}:
                needed = max(needed, (period or 1) + 1)
    return needed + 1


def is_benchmark_leaf(node: FilterNode) -> bool:
    """A leaf referencing the benchmark index (market gate) is evaluated against index bars."""
    if node.kind != "leaf":
        return False
    for operand in (node.left, node.right, node.right_high):
        if operand is not None and operand.kind == "series" and (operand.name or "").upper() == BENCHMARK_SERIES:
            return True
    return False


def uses_benchmark(config: StrategyDefinitionConfig) -> bool:
    return any(is_benchmark_leaf(leaf) for leaf in config.root.leaf_nodes())


def collect_series_keys(config: StrategyDefinitionConfig) -> list[Operand]:
    """Stock-series operands for indicator snapshots; benchmark leaves belong to the index series."""
    seen: dict[str, Operand] = {}
    for leaf in config.root.leaf_nodes():
        if is_benchmark_leaf(leaf):
            continue
        for operand in (leaf.left, leaf.right, leaf.right_high):
            if operand is None or operand.kind != "series":
                continue
            seen[operand.key()] = operand
    return list(seen.values())


def _parse_root(raw: dict[str, Any]) -> FilterNode:
    if isinstance(raw.get("root"), dict):
        return _parse_node(raw["root"], "root")
    if isinstance(raw.get("entry_conditions"), dict):
        entry = _parse_node(raw["entry_conditions"], "entry")
        extra = raw.get("filters")
        if isinstance(extra, dict):
            filt = _parse_node(extra, "filters")
            return FilterNode(id="root", kind="group", op="AND", children=[entry, filt])
        if isinstance(extra, list) and extra:
            filt = _parse_filter_list(extra, "filters")
            return FilterNode(id="root", kind="group", op="AND", children=[entry, filt])
        return entry
    filters = raw.get("filters")
    if isinstance(filters, dict):
        return _parse_node(filters, "root")
    if isinstance(filters, list):
        return _parse_filter_list(filters, "root")
    raise StrategyConfigError("Strategy must include filters or entry_conditions")


def _parse_filter_list(items: list[Any], prefix: str) -> FilterNode:
    children = [_parse_node(item, f"{prefix}_{i}") for i, item in enumerate(items)]
    return FilterNode(id=prefix, kind="group", op="AND", children=children)


def _parse_node(raw: Any, default_id: str) -> FilterNode:
    if not isinstance(raw, dict):
        raise StrategyConfigError("Filter node must be an object")
    node_id = str(raw.get("id") or default_id)
    children_raw = raw.get("children") or raw.get("filters")
    group_op = raw.get("op") or raw.get("logic")
    if children_raw is not None or (isinstance(group_op, str) and group_op.upper() in GROUP_OPS and "operator" not in raw and "field" not in raw):
        op = str(group_op or "AND").upper()
        if op not in GROUP_OPS:
            raise StrategyConfigError(f"Unsupported group operator: {op}")
        children_list = children_raw if isinstance(children_raw, list) else []
        children = [_parse_node(child, f"{node_id}_{i}") for i, child in enumerate(children_list)]
        if op == "NOT" and len(children) != 1:
            raise StrategyConfigError("NOT groups must contain exactly one child")
        return FilterNode(
            id=node_id,
            kind="group",
            op=op,
            children=children,
            label=raw.get("label"),
        )
    operator = _parse_operator(raw.get("operator") or raw.get("op"))
    left = _parse_operand(raw.get("left") or raw.get("field"), default_series="CLOSE")
    if operator in {"between", "outside"}:
        lo = (
            raw.get("low")
            if "low" in raw
            else (
                raw.get("right")
                if "right" in raw
                else (
                    raw.get("min")
                    if "min" in raw
                    else (raw.get("value") if not isinstance(raw.get("value"), dict) else None)
                )
            )
        )
        hi = raw.get("high") if "high" in raw else (raw.get("right_high") if "right_high" in raw else raw.get("max"))
        if isinstance(raw.get("value"), (list, tuple)) and len(raw["value"]) == 2:
            lo, hi = raw["value"][0], raw["value"][1]
        if lo is None or hi is None:
            raise StrategyConfigError(f"{operator} requires low and high bounds")
        return FilterNode(
            id=node_id,
            kind="leaf",
            op=operator,
            left=left,
            right=_parse_operand(lo),
            right_high=_parse_operand(hi),
            label=raw.get("label"),
        )
    right_raw = raw.get("right") if "right" in raw else raw.get("value")
    if right_raw is None:
        raise StrategyConfigError("Filter requires a comparison value")
    return FilterNode(
        id=node_id,
        kind="leaf",
        op=operator,
        left=left,
        right=_parse_operand(right_raw),
        label=raw.get("label"),
    )


def _parse_operator(raw: Any) -> str:
    if raw is None:
        raise StrategyConfigError("Filter operator is required")
    text = str(raw).strip().lower().replace("-", "_")
    mapped = OPERATOR_ALIASES.get(text, text)
    if mapped not in OPERATORS:
        raise StrategyConfigError(f"Unsupported operator: {raw}")
    return mapped


def _parse_operand(raw: Any, default_series: str | None = None) -> Operand:
    if raw is None:
        if default_series:
            return Operand(kind="series", name=default_series)
        raise StrategyConfigError("Filter requires a comparison value")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return Operand(kind="literal", value=float(raw))
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise StrategyConfigError("Filter requires a comparison value")
        try:
            return Operand(kind="literal", value=float(text))
        except ValueError:
            return _parse_series_name(text)
    if isinstance(raw, dict):
        if "value" in raw and "indicator" not in raw and "field" not in raw and "name" not in raw:
            return _parse_operand(raw["value"])
        indicator = raw.get("indicator") or raw.get("name") or raw.get("field")
        period = _opt_int(raw.get("period"))
        std = _opt_float(raw.get("std") or raw.get("stddev") or raw.get("mult"))
        if indicator is None:
            raise StrategyConfigError("Operand object requires indicator, field, or value")
        series = _parse_series_name(str(indicator), period_override=period, std_override=std)
        return series
    raise StrategyConfigError(f"Unsupported operand: {raw!r}")


def _parse_series_name(raw: str, period_override: int | None = None, std_override: float | None = None) -> Operand:
    text = raw.strip().upper().replace(" ", "_").replace("-", "_")
    if not text:
        raise StrategyConfigError("Filter requires a comparison value")
    if text in INDICATOR_ALIASES:
        name, default_period = INDICATOR_ALIASES[text]
        return Operand(kind="series", name=name, period=period_override or default_period, std=std_override)
    for prefix in ("SMA", "EMA", "WMA", "RSI", "ATR", "ROC", "HIGH", "LOW", "VWAP", "HV"):
        if text == prefix:
            return Operand(kind="series", name=prefix, period=period_override or _default_period(prefix), std=std_override)
        if text.startswith(prefix + "_"):
            rest = text[len(prefix) + 1 :]
            if rest.isdigit():
                return Operand(kind="series", name=prefix, period=int(rest), std=std_override)
    if text.startswith("BB_"):
        parts = text.split("_")
        band = "_".join(parts[:2]) if len(parts) >= 2 else text
        name = {"BB_UPPER": "BB_UPPER", "BB_LOWER": "BB_LOWER", "BB_MIDDLE": "BB_MIDDLE", "BB_WIDTH": "BB_WIDTH"}.get(band, "BB_MIDDLE")
        period = period_override
        if len(parts) >= 3 and parts[2].isdigit():
            period = int(parts[2])
        return Operand(kind="series", name=name, period=period or 20, std=std_override or 2.0)
    if text.startswith("AVG_VOLUME") or text.startswith("AVERAGE_VOLUME"):
        period = period_override or 20
        if "_" in text:
            tail = text.rsplit("_", 1)[-1]
            if tail.isdigit():
                period = int(tail)
        return Operand(kind="series", name="AVG_VOLUME", period=period)
    # Generic NAME_PERIOD, e.g. REL_VOLUME_20, RSI_14, GAP_PCT is alias-only
    if "_" in text:
        head, tail = text.rsplit("_", 1)
        if tail.isdigit():
            try:
                return _parse_series_name(head, period_override=period_override or int(tail), std_override=std_override)
            except StrategyConfigError:
                pass
    raise StrategyConfigError(f"Unknown indicator or field: {raw}")


def _default_period(name: str) -> int:
    return {
        "SMA": 50,
        "EMA": 20,
        "WMA": 20,
        "RSI": 14,
        "ATR": 14,
        "ROC": 12,
        "HIGH": 20,
        "LOW": 20,
        "VWAP": 20,
        "HV": 20,
    }.get(name, 20)


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _op_label(op: str) -> str:
    return {
        "cross_above": "Cross Above",
        "cross_below": "Cross Below",
        "between": "Between",
        "outside": "Outside",
        "==": "=",
        "!=": "≠",
    }.get(op, op)


def _node_to_dict(node: FilterNode) -> dict[str, Any]:
    if node.kind == "group":
        return {
            "id": node.id,
            "op": node.op,
            "label": node.label,
            "children": [_node_to_dict(c) for c in node.children],
        }
    payload: dict[str, Any] = {
        "id": node.id,
        "label": node.display_label(),
        "operator": node.op,
        "left": _operand_to_dict(node.left),
        "right": _operand_to_dict(node.right),
    }
    if (node.op or "") in {"between", "outside"}:
        payload["low"] = _operand_to_dict(node.right)
        payload["high"] = _operand_to_dict(node.right_high)
    elif node.right_high is not None:
        payload["high"] = _operand_to_dict(node.right_high)
    return payload


def _operand_to_dict(operand: Operand | None) -> dict[str, Any] | None:
    if operand is None:
        return None
    if operand.kind == "literal":
        return {"value": operand.value}
    out: dict[str, Any] = {"indicator": operand.name}
    if operand.period is not None:
        out["period"] = operand.period
    if operand.std is not None:
        out["std"] = operand.std
    return out
