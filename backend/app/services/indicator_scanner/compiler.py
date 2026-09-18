"""Validate a parsed Pine subset program and extract screener metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .ast_nodes import (
    Assignment,
    BinaryOp,
    BoolLit,
    Call,
    Expr,
    ExprStmt,
    Ident,
    Index,
    Member,
    NaLit,
    NumberLit,
    Program,
    StringLit,
    Ternary,
    UnaryOp,
)
from .errors import CompileIssue, PineCompileError
from .limits import (
    LANGUAGE_MODE,
    MAX_INPUTS,
    MAX_LOOKBACK,
    MAX_PLOTS,
    MAX_SECURITY_CALLS,
    SUPPORTED_VERSIONS,
)
from .parser import parse_source

BUILTIN_SERIES = {"open", "high", "low", "close", "volume"}
VISUAL_KWARGS = {
    "style",
    "color",
    "linewidth",
    "location",
    "size",
    "text",
    "overlay",
    "offset",
    "histbase",
    "display",
    "editable",
    "format",
    "precision",
    "trackprice",
    "join",
    "transp",
    "force_overlay",
    "show_last",
    "histbase",
}
VISUAL_ROOTS = {"shape", "location", "size", "color", "style", "display", "format"}

ALLOWED_CALLS = {
    "indicator",
    "plot",
    "plotshape",
    "alertcondition",
    "na",
    "nz",
    "input.int",
    "input.float",
    "input.bool",
    "input.string",
    "input.symbol",
    "math.max",
    "math.min",
    "math.abs",
    "math.round",
    "math.floor",
    "math.ceil",
    "ta.sma",
    "ta.ema",
    "ta.rma",
    "ta.highest",
    "ta.lowest",
    "ta.atr",
    "ta.rsi",
    "ta.crossover",
    "ta.crossunder",
    "ta.stdev",
    "request.security",
}

BANNED_CALL_PREFIXES = (
    "strategy.",
    "label.",
    "line.",
    "box.",
    "table.",
    "polyline.",
    "linefill.",
)
BANNED_CALLS = {
    "strategy",
    "request.security_lower_tf",
    "request.financial",
    "request.earnings",
    "request.dividends",
    "request.quandl",
    "request.seed",
    "array.new",
    "map.new",
    "matrix.new",
    "eval",
    "exec",
}


@dataclass
class InputDef:
    name: str
    title: str
    kind: str
    default: Any
    minval: float | None = None
    maxval: float | None = None
    step: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "kind": self.kind,
            "default": self.default,
            "minval": self.minval,
            "maxval": self.maxval,
            "step": self.step,
        }


@dataclass
class OutputDef:
    name: str
    kind: str  # plot | plotshape | alertcondition
    expr: Expr
    source_line: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "source_line": self.source_line}


@dataclass
class SecurityRef:
    symbol: str
    timeframe: str
    expression: Expr
    source_line: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "timeframe": self.timeframe, "source_line": self.source_line}


@dataclass
class CompiledIndicator:
    title: str
    overlay: bool
    version: int
    language_mode: str
    inputs: list[InputDef]
    outputs: list[OutputDef]
    assignments: list[Assignment]
    security_calls: list[SecurityRef]
    required_bars: int
    required_symbols: list[str]
    warnings: list[CompileIssue]
    source: str

    def to_definition_json(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "overlay": self.overlay,
            "version": self.version,
            "language_mode": self.language_mode,
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "required_bars": self.required_bars,
            "required_symbols": list(self.required_symbols),
            "security_calls": [s.to_dict() for s in self.security_calls],
            "warnings": [w.to_dict() for w in self.warnings],
        }


def compile_source(source: str) -> CompiledIndicator:
    program = parse_source(source)
    return compile_program(program)


def compile_program(program: Program) -> CompiledIndicator:
    if program.version not in SUPPORTED_VERSIONS:
        raise PineCompileError(
            f"Unsupported Pine Script version (v{program.version}). TradingLabs supports a Pine Script v6-compatible subset.",
            line=1,
            column=1,
            code="UNSUPPORTED_VERSION",
        )
    ctx = _CompileCtx(program)
    ctx.run()
    return ctx.result()


class _CompileCtx:
    def __init__(self, program: Program):
        self.program = program
        self.title = "Untitled indicator"
        self.overlay = False
        self.inputs: list[InputDef] = []
        self.outputs: list[OutputDef] = []
        self.assignments: list[Assignment] = []
        self.security_calls: list[SecurityRef] = []
        self.warnings: list[CompileIssue] = []
        self.defined: set[str] = set(BUILTIN_SERIES) | {"timeframe"}
        self.used: set[str] = set()
        self.input_names: dict[str, str] = {}
        self.saw_indicator = False
        self.input_defaults: dict[str, Any] = {}

    def run(self) -> None:
        for stmt in self.program.statements:
            if isinstance(stmt, Assignment):
                self._assignment(stmt)
            elif isinstance(stmt, ExprStmt):
                self._expr_stmt(stmt)
        if not self.saw_indicator:
            raise PineCompileError(
                "Missing indicator() declaration. This is an indicator scanner. Use indicator() instead of strategy().",
                line=1,
                column=1,
                code="MISSING_INDICATOR",
            )
        if not self.outputs:
            raise PineCompileError(
                "Indicator must declare at least one plot(), plotshape(), or alertcondition() output.",
                line=1,
                column=1,
                code="NO_OUTPUTS",
            )
        self._warn_missing_screener_signal_plot()
        for inp in self.inputs:
            if inp.name not in self.used:
                self.warnings.append(
                    CompileIssue(
                        line=1,
                        column=1,
                        severity="warning",
                        code="UNUSED_INPUT",
                        message=f"Input '{inp.title}' is defined but is not used by this indicator.",
                    )
                )

    def result(self) -> CompiledIndicator:
        required = 1
        for stmt in self.assignments:
            required = max(required, self._lookback(stmt.expr, 0))
        for out in self.outputs:
            required = max(required, self._lookback(out.expr, 0))
        for sec in self.security_calls:
            required = max(required, self._lookback(sec.expression, 0))
        symbols = []
        seen: set[str] = set()
        for sec in self.security_calls:
            if sec.symbol not in seen:
                seen.add(sec.symbol)
                symbols.append(sec.symbol)
        return CompiledIndicator(
            title=self.title,
            overlay=self.overlay,
            version=int(self.program.version or 6),
            language_mode=LANGUAGE_MODE,
            inputs=self.inputs,
            outputs=self.outputs,
            assignments=self.assignments,
            security_calls=self.security_calls,
            required_bars=required,
            required_symbols=symbols,
            warnings=self.warnings,
            source=self.program.source,
        )

    def _warn_missing_screener_signal_plot(self) -> None:
        has_signal_plot = any(
            out.kind == "plot" and re.search(r"signal|scan$", out.name or "", re.I) for out in self.outputs
        )
        has_shape = any(out.kind in {"plotshape", "alertcondition"} for out in self.outputs)
        first_plot = next((out for out in self.outputs if out.kind == "plot"), None)
        if has_signal_plot or not has_shape or first_plot is None:
            return
        self.warnings.append(
            CompileIssue(
                line=first_plot.source_line or 1,
                column=1,
                severity="warning",
                code="MISSING_SCREENER_SIGNAL_PLOT",
                message=(
                    "TradingView Pine Screener filters numeric plot() columns. This script's first plot is "
                    f"'{first_plot.name}' (not a 0/1 signal), so setting that column to 1 matches nothing. "
                    "Add plot(buySignal ? 1 : 0, \"Signal\") and filter Signal = 1 on TradingView. "
                    "This scanner matches when the plotshape/alert condition is true on the same 1D bar."
                ),
            )
        )

    def _assignment(self, stmt: Assignment) -> None:
        call = stmt.expr if isinstance(stmt.expr, Call) else None
        qname = qualified_call_name(call) if call else ""
        if qname.startswith("input."):
            self._input_assignment(stmt, call)  # type: ignore[arg-type]
            return
        self._walk(stmt.expr, visual=False)
        self.assignments.append(stmt)
        self.defined.add(stmt.name)

    def _input_assignment(self, stmt: Assignment, call: Call) -> None:
        if len(self.inputs) >= MAX_INPUTS:
            raise PineCompileError(
                f"Too many inputs (max {MAX_INPUTS}).",
                line=stmt.span.line,
                column=stmt.span.column,
                code="TOO_MANY_INPUTS",
            )
        kind = qualified_call_name(call).split(".", 1)[1]
        default, title = self._input_default_and_title(call, kind, stmt)
        minval = self._literal_number(call.kwargs.get("minval"))
        maxval = self._literal_number(call.kwargs.get("maxval"))
        step = self._literal_number(call.kwargs.get("step"))
        inp = InputDef(
            name=stmt.name,
            title=title,
            kind=kind,
            default=default,
            minval=minval,
            maxval=maxval,
            step=step,
        )
        self.inputs.append(inp)
        self.defined.add(stmt.name)
        self.input_names[stmt.name] = title
        self.input_defaults[stmt.name] = default

    def _input_default_and_title(self, call: Call, kind: str, stmt: Assignment) -> tuple[Any, str]:
        if not call.args:
            raise PineCompileError(
                "input.* requires a default value.",
                line=stmt.span.line,
                column=stmt.span.column,
            )
        default = self._const_value(call.args[0], f"input.{kind} default")
        title = stmt.name
        if "title" in call.kwargs:
            title = str(self._const_value(call.kwargs["title"], "title"))
        elif len(call.args) >= 2 and isinstance(call.args[1], StringLit):
            title = call.args[1].value
        if kind == "int":
            default = int(default)
        elif kind == "float":
            default = float(default)
        elif kind == "bool":
            default = bool(default)
        else:
            default = str(default)
        return default, title

    def _expr_stmt(self, stmt: ExprStmt) -> None:
        expr = stmt.expr
        if not isinstance(expr, Call):
            raise PineCompileError(
                "Only assignments and plot/indicator calls are allowed as statements.",
                line=stmt.span.line,
                column=stmt.span.column,
            )
        qname = qualified_call_name(expr)
        if qname == "strategy" or qname.startswith("strategy."):
            raise PineCompileError(
                "This is an indicator scanner. Use indicator() instead of strategy().",
                line=expr.span.line,
                column=expr.span.column,
                code="STRATEGY_NOT_ALLOWED",
            )
        if qname == "indicator":
            self._header(expr)
            return
        if qname in {"plot", "plotshape", "alertcondition"}:
            self._output(expr, qname)
            return
        raise PineCompileError(
            f"Unsupported statement '{qname}()'. Only indicator(), plot(), plotshape(), and alertcondition() may appear as top-level calls.",
            line=expr.span.line,
            column=expr.span.column,
            code="UNSUPPORTED_STATEMENT",
        )

    def _header(self, call: Call) -> None:
        self.saw_indicator = True
        if call.args:
            self.title = str(self._const_value(call.args[0], "indicator title"))
        elif "title" in call.kwargs:
            self.title = str(self._const_value(call.kwargs["title"], "indicator title"))
        if "overlay" in call.kwargs:
            overlay = self._const_value(call.kwargs["overlay"], "overlay")
            self.overlay = bool(overlay)

    def _output(self, call: Call, kind: str) -> None:
        if len(self.outputs) >= MAX_PLOTS:
            raise PineCompileError(
                f"Too many outputs (max {MAX_PLOTS}).",
                line=call.span.line,
                column=call.span.column,
                code="TOO_MANY_PLOTS",
            )
        if not call.args:
            raise PineCompileError(f"{kind}() requires an expression.", line=call.span.line, column=call.span.column)
        expr = call.args[0]
        self._walk(expr, visual=False)
        title = None
        if "title" in call.kwargs:
            title = str(self._const_value(call.kwargs["title"], "title"))
        elif len(call.args) >= 2 and isinstance(call.args[1], StringLit):
            title = call.args[1].value
        if not title:
            title = f"{kind}_{len(self.outputs) + 1}"
        for kw, value in call.kwargs.items():
            if kw == "title":
                continue
            if kw in VISUAL_KWARGS:
                self._walk(value, visual=True)
                continue
            if kind == "alertcondition" and kw == "message":
                self._const_value(value, "message")
                continue
            raise PineCompileError(
                f"Unsupported {kind}() argument '{kw}'.",
                line=call.span.line,
                column=call.span.column,
            )
        for extra in call.args[2 if kind == "plot" and len(call.args) >= 2 else 1 :]:
            self._walk(extra, visual=True)
        self.outputs.append(OutputDef(name=title, kind=kind, expr=expr, source_line=call.span.line))

    def _walk(self, expr: Expr, *, visual: bool) -> None:
        if isinstance(expr, (NumberLit, StringLit, BoolLit, NaLit)):
            return
        if isinstance(expr, Ident):
            if expr.name in BUILTIN_SERIES or expr.name == "timeframe":
                return
            if expr.name in self.defined:
                if expr.name in self.input_names:
                    self.used.add(expr.name)
                return
            if visual and expr.name in VISUAL_ROOTS:
                return
            raise PineCompileError(
                f"Unknown identifier '{expr.name}'.",
                line=expr.span.line,
                column=expr.span.column,
                code="UNKNOWN_IDENT",
            )
        if isinstance(expr, Member):
            qname = qualified_name(expr)
            if qname == "timeframe.period":
                return
            if visual and qname.split(".", 1)[0] in VISUAL_ROOTS:
                return
            if isinstance(expr.object, Ident) and expr.object.name in self.defined:
                return
            # member used as call callee is handled in Call
            if isinstance(expr.object, Ident) and expr.object.name in {"ta", "math", "input", "request"}:
                return
            raise PineCompileError(
                f"Unsupported member access '{qname}'.",
                line=expr.span.line,
                column=expr.span.column,
                code="UNSUPPORTED_MEMBER",
            )
        if isinstance(expr, Index):
            if expr.offset < 0:
                raise PineCompileError("Negative indexing is not allowed.", line=expr.span.line, column=expr.span.column)
            self._walk(expr.target, visual=visual)
            return
        if isinstance(expr, UnaryOp):
            self._walk(expr.expr, visual=visual)
            return
        if isinstance(expr, BinaryOp):
            self._walk(expr.left, visual=visual)
            self._walk(expr.right, visual=visual)
            return
        if isinstance(expr, Ternary):
            self._walk(expr.condition, visual=visual)
            self._walk(expr.then_expr, visual=visual)
            self._walk(expr.else_expr, visual=visual)
            return
        if isinstance(expr, Call):
            self._walk_call(expr, visual=visual)
            return

    def _walk_call(self, call: Call, *, visual: bool) -> None:
        qname = qualified_call_name(call)
        if qname in BANNED_CALLS or qname.startswith(BANNED_CALL_PREFIXES):
            raise PineCompileError(
                f"Unsupported function '{qname}()'.",
                line=call.span.line,
                column=call.span.column,
                code="UNSUPPORTED_FUNCTION",
            )
        if qname == "strategy" or qname.startswith("strategy."):
            raise PineCompileError(
                "This is an indicator scanner. Use indicator() instead of strategy().",
                line=call.span.line,
                column=call.span.column,
                code="STRATEGY_NOT_ALLOWED",
            )
        if visual:
            for arg in call.args:
                self._walk(arg, visual=True)
            for value in call.kwargs.values():
                self._walk(value, visual=True)
            return
        if qname not in ALLOWED_CALLS:
            raise PineCompileError(
                f"Unsupported function '{qname}()'. TradingLabs supports a secure Pine Script v6-compatible subset.",
                line=call.span.line,
                column=call.span.column,
                code="UNSUPPORTED_FUNCTION",
            )
        if qname == "request.security":
            self._security(call)
            return
        if qname.startswith("input."):
            raise PineCompileError(
                "input.* may only appear in assignments, for example lookback = input.int(252, \"Lookback\").",
                line=call.span.line,
                column=call.span.column,
            )
        for arg in call.args:
            self._walk(arg, visual=False)
        for key, value in call.kwargs.items():
            self._walk(value, visual=False)

    def _security(self, call: Call) -> None:
        if len(self.security_calls) >= MAX_SECURITY_CALLS:
            raise PineCompileError(
                f"Too many request.security calls (max {MAX_SECURITY_CALLS}).",
                line=call.span.line,
                column=call.span.column,
                code="TOO_MANY_SECURITY",
            )
        if len(call.args) < 3:
            raise PineCompileError(
                "request.security(symbol, timeframe, expression) requires 3 arguments.",
                line=call.span.line,
                column=call.span.column,
            )
        symbol = self._resolve_symbol(call.args[0])
        timeframe = self._resolve_timeframe(call.args[1])
        expression = call.args[2]
        if contains_security(expression):
            raise PineCompileError(
                "Nested request.security calls are not supported.",
                line=call.span.line,
                column=call.span.column,
                code="NESTED_SECURITY",
            )
        self._walk(expression, visual=False)
        self.security_calls.append(SecurityRef(symbol=symbol, timeframe=timeframe, expression=expression, source_line=call.span.line))

    def _resolve_symbol(self, expr: Expr) -> str:
        if isinstance(expr, StringLit):
            return expr.value
        if isinstance(expr, Ident) and expr.name in self.input_defaults:
            self.used.add(expr.name)
            return str(self.input_defaults[expr.name])
        raise PineCompileError(
            "request.security symbol must be a string literal or input.symbol default in version 1.",
            line=expr.span.line,
            column=expr.span.column,
            code="DYNAMIC_SYMBOL",
        )

    def _resolve_timeframe(self, expr: Expr) -> str:
        if isinstance(expr, StringLit):
            value = expr.value
        elif isinstance(expr, Member) and qualified_name(expr) == "timeframe.period":
            value = "D"
        else:
            raise PineCompileError(
                "request.security timeframe must be timeframe.period or \"D\" in version 1.",
                line=expr.span.line,
                column=expr.span.column,
                code="UNSUPPORTED_TIMEFRAME",
            )
        if value not in {"D", "1D", "1d", "daily"}:
            raise PineCompileError(
                f"Unsupported timeframe '{value}'. Only daily (1D) scans are supported.",
                line=expr.span.line,
                column=expr.span.column,
                code="UNSUPPORTED_TIMEFRAME",
            )
        return "D"

    def _lookback(self, expr: Expr, extra: int) -> int:
        if isinstance(expr, (NumberLit, StringLit, BoolLit, NaLit, Ident)):
            return 1 + extra
        if isinstance(expr, Member):
            return 1 + extra
        if isinstance(expr, Index):
            return self._lookback(expr.target, extra + expr.offset)
        if isinstance(expr, UnaryOp):
            return self._lookback(expr.expr, extra)
        if isinstance(expr, BinaryOp):
            return max(self._lookback(expr.left, extra), self._lookback(expr.right, extra))
        if isinstance(expr, Ternary):
            return max(
                self._lookback(expr.condition, extra),
                self._lookback(expr.then_expr, extra),
                self._lookback(expr.else_expr, extra),
            )
        if isinstance(expr, Call):
            qname = qualified_call_name(expr)
            length = 0
            if qname in {"ta.sma", "ta.ema", "ta.rma", "ta.highest", "ta.lowest", "ta.rsi", "ta.stdev"}:
                if len(expr.args) >= 2:
                    length = self._length_value(expr.args[1])
            elif qname == "ta.atr":
                if expr.args:
                    length = self._length_value(expr.args[0])
            elif qname in {"ta.crossover", "ta.crossunder", "crossover", "crossunder"}:
                child = 1
                for arg in expr.args:
                    child = max(child, self._lookback(arg, 0))
                return child + extra + 1
            child = 1
            for arg in expr.args:
                child = max(child, self._lookback(arg, 0))
            return max(child, length) + extra
        return 1 + extra

    def _length_value(self, expr: Expr) -> int:
        if isinstance(expr, NumberLit):
            length = int(expr.value)
        elif isinstance(expr, Ident) and expr.name in self.input_defaults:
            try:
                length = int(self.input_defaults[expr.name])
            except (TypeError, ValueError):
                length = 1
        else:
            raise PineCompileError(
                "Lookback length must be an integer literal or input.int default in version 1.",
                line=expr.span.line,
                column=expr.span.column,
                code="DYNAMIC_LENGTH",
            )
        if length < 1:
            raise PineCompileError("Lookback length must be >= 1.", line=expr.span.line, column=expr.span.column)
        if length > MAX_LOOKBACK:
            raise PineCompileError(
                f"Lookback length {length} exceeds the maximum of {MAX_LOOKBACK}.",
                line=expr.span.line,
                column=expr.span.column,
                code="LOOKBACK_TOO_LARGE",
            )
        return length

    def _const_value(self, expr: Expr, what: str) -> Any:
        if isinstance(expr, NumberLit):
            return expr.value
        if isinstance(expr, StringLit):
            return expr.value
        if isinstance(expr, BoolLit):
            return expr.value
        if isinstance(expr, UnaryOp) and expr.op == "-" and isinstance(expr.expr, NumberLit):
            return -expr.expr.value
        raise PineCompileError(
            f"{what} must be a constant literal.",
            line=expr.span.line,
            column=expr.span.column,
        )

    def _literal_number(self, expr: Expr | None) -> float | None:
        if expr is None:
            return None
        value = self._const_value(expr, "numeric option")
        return float(value)


def qualified_name(expr: Expr) -> str:
    if isinstance(expr, Ident):
        return expr.name
    if isinstance(expr, Member):
        return f"{qualified_name(expr.object)}.{expr.attr}"
    return ""


def qualified_call_name(call: Call | None) -> str:
    if call is None:
        return ""
    return qualified_name(call.callee)


def contains_security(expr: Expr) -> bool:
    if isinstance(expr, Call) and qualified_call_name(expr) == "request.security":
        return True
    children: list[Expr] = []
    if isinstance(expr, Call):
        children = list(expr.args) + list(expr.kwargs.values())
        children.append(expr.callee)  # type: ignore[arg-type]
    elif isinstance(expr, Member):
        children = [expr.object]
    elif isinstance(expr, Index):
        children = [expr.target]
    elif isinstance(expr, UnaryOp):
        children = [expr.expr]
    elif isinstance(expr, BinaryOp):
        children = [expr.left, expr.right]
    elif isinstance(expr, Ternary):
        children = [expr.condition, expr.then_expr, expr.else_expr]
    return any(contains_security(child) for child in children)



