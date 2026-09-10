"""Tokenizer/parser/compiler tests for the Pine-compatible subset."""

from __future__ import annotations

import pytest

from app.services.indicator_scanner.compiler import compile_source
from app.services.indicator_scanner.errors import PineCompileError
from app.services.indicator_scanner.parser import parse_source
from app.services.indicator_scanner.ema_pullback_template import EMA_PULLBACK_SCAN_SOURCE, EMA_PULLBACK_SCAN_TITLE
from app.services.indicator_scanner.template import BREAKOUT_SCAN_SOURCE, BREAKOUT_SCAN_TITLE


def test_parses_version_and_indicator_declaration():
    program = parse_source('//@version=6\nindicator("Demo", overlay=false)\nplot(close, "Close")\n')
    assert program.version == 6
    compiled = compile_source('//@version=6\nindicator("Demo", overlay=false)\nplot(close, "Close")\n')
    assert compiled.title == "Demo"
    assert compiled.overlay is False


def test_parses_inputs_assignments_nested_math_and_outputs():
    compiled = compile_source(BREAKOUT_SCAN_SOURCE)
    assert compiled.title == BREAKOUT_SCAN_TITLE
    titles = [i.title for i in compiled.inputs]
    assert titles == [
        "Breakout Lookback",
        "Volume SMA Length",
        "ATR Length",
        "ATR Multiplier",
        "Market SMA Length",
        "Benchmark",
    ]
    defaults = {i.title: i.default for i in compiled.inputs}
    assert defaults["Breakout Lookback"] == 252
    assert defaults["Volume SMA Length"] == 20
    assert defaults["ATR Length"] == 14
    assert defaults["ATR Multiplier"] == 3.0
    assert defaults["Market SMA Length"] == 50
    assert defaults["Benchmark"] == "NSE:CNX500"
    out_names = [o.name for o in compiled.outputs]
    assert out_names == [
        "52W Breakout Signal",
        "Close",
        "Prior 252 High",
        "Volume SMA 20",
        "Custom ATR 14",
        "NIFTY 500 Close",
        "NIFTY 500 SMA 50",
        "52W Breakout",
        "52W Breakout Scan",
    ]
    assert compiled.required_bars >= 253
    assert "NSE:CNX500" in compiled.required_symbols
    unused = [w.message for w in compiled.warnings]
    assert any("ATR Multiplier" in msg for msg in unused)


def test_parses_ternary_and_request_security():
    compiled = compile_source(BREAKOUT_SCAN_SOURCE)
    assert any(s.symbol == "NSE:CNX500" for s in compiled.security_calls)
    assert any(o.kind == "plotshape" for o in compiled.outputs)
    assert any(o.kind == "alertcondition" for o in compiled.outputs)


def test_compiles_ema_pullback_swing_scanner():
    compiled = compile_source(EMA_PULLBACK_SCAN_SOURCE)
    assert compiled.title == EMA_PULLBACK_SCAN_TITLE
    out_names = [o.name for o in compiled.outputs]
    assert out_names[0] == "Signal"
    assert "Buy Signal" in out_names
    assert "Swing Long" in out_names
    assert compiled.warnings == []


def test_rejects_strategy():
    with pytest.raises(PineCompileError) as exc:
        compile_source('//@version=6\nstrategy("Nope")\nplot(close, "Close")\n')
    assert "indicator scanner" in str(exc.value).lower()
    assert exc.value.line >= 1


def test_rejects_loops_and_unknown_function():
    with pytest.raises(PineCompileError) as exc:
        compile_source('//@version=6\nindicator("x")\nfor i = 0 to 10\n    plot(close)\n')
    assert "loop" in str(exc.value).lower() or "for" in str(exc.value).lower()
    assert exc.value.line >= 1
    with pytest.raises(PineCompileError) as exc2:
        compile_source('//@version=6\nindicator("x")\nplot(ta.vwap(close), "x")\n')
    assert "unsupported" in str(exc2.value).lower()
    assert exc2.value.line >= 1


def test_rejects_user_function_and_negative_index():
    with pytest.raises(PineCompileError):
        compile_source('//@version=6\nindicator("x")\nfoo() => close\nplot(foo(), "x")\n')
    with pytest.raises(PineCompileError) as exc:
        compile_source('//@version=6\nindicator("x")\nplot(close[-1], "x")\n')
    assert "negative" in str(exc.value).lower() or "index" in str(exc.value).lower()


def test_reports_line_for_unexpected_token():
    with pytest.raises(PineCompileError) as exc:
        compile_source('//@version=6\nindicator("x")\nplot(close, "x")\n@@@\n')
    assert exc.value.line >= 4
