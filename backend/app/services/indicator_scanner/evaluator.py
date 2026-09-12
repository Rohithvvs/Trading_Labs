"""Series evaluator for compiled Pine-subset indicators. No eval/exec."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

from .ast_nodes import (
    Assignment,
    BinaryOp,
    BoolLit,
    Call,
    Expr,
    Ident,
    Index,
    Member,
    NaLit,
    NumberLit,
    StringLit,
    Ternary,
    UnaryOp,
)
from .compiler import CompiledIndicator, qualified_call_name, qualified_name
from .errors import PineRuntimeError
from .limits import MAX_BARS, MAX_OPERATION_COST
from .ta_functions import (
    Scalar,
    as_float,
    atr,
    crossover,
    crossunder,
    ema,
    rma,
    rolling_extreme,
    rsi,
    shift,
    sma,
)


def _is_num(value: Scalar) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _truthy(value: Scalar) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value != ""
    if _is_num(value):
        return float(value) != 0.0
    return False


def _broadcast(value: Scalar, n: int) -> list[Scalar]:
    return [value] * n


def _align_no_lookahead(src_dates: list[date], src_values: list[Scalar], dest_dates: list[date]) -> list[Scalar]:
    """Map src onto dest dates using the last known src value on or before dest date."""
    out: list[Scalar] = [None] * len(dest_dates)
    j = -1
    n_src = len(src_dates)
    for i, day in enumerate(dest_dates):
        while j + 1 < n_src and src_dates[j + 1] <= day:
            j += 1
        if j >= 0:
            out[i] = src_values[j]
    return out


@dataclass
class BarData:
    dates: list[date]
    open: list[Scalar]
    high: list[Scalar]
    low: list[Scalar]
    close: list[Scalar]
    volume: list[Scalar]

    def __len__(self) -> int:
        return len(self.dates)


@dataclass
class EvalResult:
    as_of: date | None
    outputs: dict[str, Scalar]
    ohlcv: dict[str, Scalar]
    status: str = "ok"
    error_detail: str | None = None
    bar_count: int = 0


class SeriesEngine:
    def __init__(
        self,
        compiled: CompiledIndicator,
        bars: BarData,
        *,
        input_overrides: dict[str, Any] | None = None,
        security_series: dict[str, BarData] | None = None,
        timeframe_period: str = "D",
    ):
        if len(bars) > MAX_BARS:
            raise PineRuntimeError(f"Too many bars ({len(bars)}; max {MAX_BARS}).")
        self.compiled = compiled
        self.bars = bars
        self.n = len(bars)
        self.timeframe_period = timeframe_period
        self.security_series = security_series or {}
        self.ops = 0
        self.env: dict[str, list[Scalar]] = {
            "open": list(bars.open),
            "high": list(bars.high),
            "low": list(bars.low),
            "close": list(bars.close),
            "volume": list(bars.volume),
        }
        self.inputs: dict[str, Scalar] = {}
        for inp in compiled.inputs:
            value: Any = inp.default
            if input_overrides and inp.name in input_overrides:
                value = input_overrides[inp.name]
            elif input_overrides and inp.title in input_overrides:
                value = input_overrides[inp.title]
            self.inputs[inp.name] = value
            self.env[inp.name] = _broadcast(value, self.n)

    def _charge(self, amount: int = 1) -> None:
        self.ops += amount
        if self.ops > MAX_OPERATION_COST:
            raise PineRuntimeError("Indicator exceeded the maximum operation cost.")

    def run(self) -> dict[str, list[Scalar]]:
        for stmt in self.compiled.assignments:
            self._charge(self.n)
            self.env[stmt.name] = self.eval_expr(stmt.expr)
        outputs: dict[str, list[Scalar]] = {}
        for out in self.compiled.outputs:
            self._charge(self.n)
            outputs[out.name] = self.eval_expr(out.expr)
        return outputs

    def last_bar(self) -> EvalResult:
        if self.n == 0:
            return EvalResult(as_of=None, outputs={}, ohlcv={}, status="insufficient_history", error_detail="No bars", bar_count=0)
        if self.n < self.compiled.required_bars:
            return EvalResult(
                as_of=self.bars.dates[-1],
                outputs={},
                ohlcv=self._ohlcv(-1),
                status="insufficient_history",
                error_detail=f"Need at least {self.compiled.required_bars} daily bars; received {self.n}.",
                bar_count=self.n,
            )
        series = self.run()
        i = self.n - 1
        outputs: dict[str, Scalar] = {}
        kinds = {o.name: o.kind for o in self.compiled.outputs}
        for name, values in series.items():
            value = values[i] if i < len(values) else None
            kind = kinds.get(name, "plot")
            if kind in {"plotshape", "alertcondition"}:
                outputs[name] = bool(_truthy(value))
            else:
                outputs[name] = _json_number(value)
        return EvalResult(
            as_of=self.bars.dates[i],
            outputs=outputs,
            ohlcv=self._ohlcv(i),
            status="ok",
            bar_count=self.n,
        )

    def _ohlcv(self, i: int) -> dict[str, Scalar]:
        return {
            "open": _json_number(self.bars.open[i]),
            "high": _json_number(self.bars.high[i]),
            "low": _json_number(self.bars.low[i]),
            "close": _json_number(self.bars.close[i]),
            "volume": _json_number(self.bars.volume[i]),
        }

    def eval_expr(self, expr: Expr) -> list[Scalar]:
        self._charge()
        if isinstance(expr, NumberLit):
            return _broadcast(expr.value, self.n)
        if isinstance(expr, StringLit):
            return _broadcast(expr.value, self.n)
        if isinstance(expr, BoolLit):
            return _broadcast(expr.value, self.n)
        if isinstance(expr, NaLit):
            return _broadcast(None, self.n)
        if isinstance(expr, Ident):
            if expr.name in self.env:
                return list(self.env[expr.name])
            raise PineRuntimeError(f"Unknown identifier '{expr.name}'.")
        if isinstance(expr, Member):
            qname = qualified_name(expr)
            if qname == "timeframe.period":
                return _broadcast(self.timeframe_period, self.n)
            return _broadcast(qname, self.n)
        if isinstance(expr, Index):
            return shift(self.eval_expr(expr.target), expr.offset)
        if isinstance(expr, UnaryOp):
            return self._unary(expr)
        if isinstance(expr, BinaryOp):
            return self._binary(expr)
        if isinstance(expr, Ternary):
            return self._ternary(expr)
        if isinstance(expr, Call):
            return self._call(expr)
        raise PineRuntimeError("Unsupported expression.")

    def _unary(self, expr: UnaryOp) -> list[Scalar]:
        values = self.eval_expr(expr.expr)
        out: list[Scalar] = [None] * self.n
        if expr.op == "not":
            for i, v in enumerate(values):
                out[i] = not _truthy(v)
            return out
        if expr.op == "-":
            for i, v in enumerate(values):
                num = as_float(v)
                out[i] = None if num is None else -num
            return out
        return values

    def _binary(self, expr: BinaryOp) -> list[Scalar]:
        left = self.eval_expr(expr.left)
        right = self.eval_expr(expr.right)
        out: list[Scalar] = [None] * self.n
        op = expr.op
        for i in range(self.n):
            a, b = left[i], right[i]
            if op in {"and", "or"}:
                if op == "and":
                    out[i] = _truthy(a) and _truthy(b)
                else:
                    out[i] = _truthy(a) or _truthy(b)
                continue
            if op in {">", ">=", "<", "<=", "==", "!="}:
                out[i] = _compare(a, b, op)
                continue
            out[i] = _arith(a, b, op)
        return out

    def _ternary(self, expr: Ternary) -> list[Scalar]:
        cond = self.eval_expr(expr.condition)
        then_s = self.eval_expr(expr.then_expr)
        else_s = self.eval_expr(expr.else_expr)
        return [then_s[i] if _truthy(cond[i]) else else_s[i] for i in range(self.n)]

    def _call(self, expr: Call) -> list[Scalar]:
        qname = qualified_call_name(expr)
        if qname == "na":
            values = self.eval_expr(expr.args[0]) if expr.args else _broadcast(None, self.n)
            return [v is None for v in values]
        if qname == "nz":
            values = self.eval_expr(expr.args[0])
            repl: Scalar = 0.0
            if len(expr.args) >= 2:
                repl_series = self.eval_expr(expr.args[1])
                return [values[i] if values[i] is not None else repl_series[i] for i in range(self.n)]
            if "replacement" in expr.kwargs:
                repl_series = self.eval_expr(expr.kwargs["replacement"])
                return [values[i] if values[i] is not None else repl_series[i] for i in range(self.n)]
            return [values[i] if values[i] is not None else repl for i in range(self.n)]
        if qname.startswith("math."):
            return self._math(qname, expr)
        if qname.startswith("ta."):
            return self._ta(qname, expr)
        if qname == "request.security":
            return self._security(expr)
        raise PineRuntimeError(f"Unsupported function '{qname}'.")

    def _math(self, qname: str, expr: Call) -> list[Scalar]:
        series = [self.eval_expr(arg) for arg in expr.args]
        out: list[Scalar] = [None] * self.n
        for i in range(self.n):
            nums = [as_float(s[i]) for s in series]
            if any(v is None for v in nums):
                continue
            vals = [float(v) for v in nums]  # type: ignore[arg-type]
            if qname == "math.max":
                out[i] = max(vals)
            elif qname == "math.min":
                out[i] = min(vals)
            elif qname == "math.abs":
                out[i] = abs(vals[0])
            elif qname == "math.round":
                out[i] = float(round(vals[0]))
            elif qname == "math.floor":
                out[i] = float(math.floor(vals[0]))
            elif qname == "math.ceil":
                out[i] = float(math.ceil(vals[0]))
        return out

    def _ta(self, qname: str, expr: Call) -> list[Scalar]:
        if qname == "ta.atr":
            length = int(self._scalar_number(expr.args[0] if expr.args else NumberLit(value=14)))
            return atr(self.env["high"], self.env["low"], self.env["close"], length)
        if qname in {"ta.crossover", "ta.crossunder"}:
            a = self.eval_expr(expr.args[0])
            b = self.eval_expr(expr.args[1])
            return crossover(a, b) if qname == "ta.crossover" else crossunder(a, b)
        src = self.eval_expr(expr.args[0])
        length = int(self._scalar_number(expr.args[1])) if len(expr.args) >= 2 else 14
        if qname == "ta.sma":
            return sma(src, length)
        if qname == "ta.ema":
            return ema(src, length)
        if qname == "ta.rma":
            return rma(src, length)
        if qname == "ta.highest":
            return rolling_extreme(src, length, high=True)
        if qname == "ta.lowest":
            return rolling_extreme(src, length, high=False)
        if qname == "ta.rsi":
            return rsi(src, length)
        raise PineRuntimeError(f"Unsupported function '{qname}'.")

    def _security(self, expr: Call) -> list[Scalar]:
        symbol = self._scalar_string(expr.args[0])
        timeframe = self._scalar_string(expr.args[1])
        if timeframe not in {"D", "1D", "1d", "daily", self.timeframe_period}:
            raise PineRuntimeError(f"Unsupported security timeframe '{timeframe}'.")
        bars = self.security_series.get(symbol) or self.security_series.get(_norm_symbol(symbol))
        if bars is None:
            return _broadcast(None, self.n)
        nested = SeriesEngine(
            self.compiled,
            bars,
            input_overrides={k: v for k, v in self.inputs.items()},
            security_series={},
            timeframe_period=self.timeframe_period,
        )
        # Copy already-resolved inputs; evaluate only the security expression.
        nested.env.update({k: list(v) for k, v in nested.env.items()})
        values = nested.eval_expr(expr.args[2])
        return _align_no_lookahead(bars.dates, values, self.bars.dates)

    def _scalar_number(self, expr: Expr) -> float:
        values = self.eval_expr(expr)
        for v in reversed(values):
            num = as_float(v)
            if num is not None:
                return num
        raise PineRuntimeError("Expected a numeric length.")

    def _scalar_string(self, expr: Expr) -> str:
        if isinstance(expr, Member) and qualified_name(expr) == "timeframe.period":
            return self.timeframe_period
        values = self.eval_expr(expr)
        for v in values:
            if isinstance(v, str) and v:
                return v
        raise PineRuntimeError("Expected a symbol or timeframe string.")


def _compare(a: Scalar, b: Scalar, op: str) -> bool:
    if a is None or b is None:
        return False
    if _is_num(a) and _is_num(b):
        av, bv = float(a), float(b)  # type: ignore[arg-type]
        if op == ">":
            return av > bv
        if op == ">=":
            return av >= bv
        if op == "<":
            return av < bv
        if op == "<=":
            return av <= bv
        if op == "==":
            return av == bv
        if op == "!=":
            return av != bv
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    return False


def _arith(a: Scalar, b: Scalar, op: str) -> Scalar:
    av = as_float(a)
    bv = as_float(b)
    if av is None or bv is None:
        return None
    if op == "+":
        return av + bv
    if op == "-":
        return av - bv
    if op == "*":
        return av * bv
    if op == "/":
        if bv == 0:
            return None
        return av / bv
    if op == "%":
        if bv == 0:
            return None
        return av % bv
    return None


def _json_number(value: Scalar) -> Scalar:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if _is_num(value):
        num = float(value)  # type: ignore[arg-type]
        if not math.isfinite(num):
            return None
        return num
    return None


def _norm_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def evaluate_indicator(
    compiled: CompiledIndicator,
    bars: BarData,
    *,
    benchmark_by_symbol: dict[str, BarData] | None = None,
    input_overrides: dict[str, Any] | None = None,
) -> EvalResult:
    engine = SeriesEngine(
        compiled,
        bars,
        input_overrides=input_overrides,
        security_series=benchmark_by_symbol or {},
        timeframe_period="D",
    )
    try:
        return engine.last_bar()
    except PineRuntimeError as exc:
        return EvalResult(
            as_of=bars.dates[-1] if bars.dates else None,
            outputs={},
            ohlcv={},
            status="error",
            error_detail=str(exc),
            bar_count=len(bars),
        )
