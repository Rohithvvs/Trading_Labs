"""All 21 research-lab Pine scans must compile in the Indicator Scanner subset."""

from __future__ import annotations

from app.services.indicator_scanner.compiler import compile_source
from app.services.research_lab.catalog import LAB_STRATEGIES
from app.services.research_lab.pine_catalog import pine_source_for


def test_catalog_has_twenty_one_strategies():
    assert len(LAB_STRATEGIES) == 21
def test_catalog_has_strategies():
    assert len(LAB_STRATEGIES) == 26
    ids = [item.strategy_id for item in LAB_STRATEGIES]
    assert ids[0] == "01_darvas_classic"
    assert ids[0] == "top_01_momentum"
    assert ids[5] == "01_darvas_classic"
    assert ids[-1] == "21_sma_10_50"
    assert len(set(ids)) == 21
    assert len(set(ids)) == 26


def test_every_lab_pine_script_compiles():
    for spec in LAB_STRATEGIES:
        source = pine_source_for(spec)
        compiled = compile_source(source)
        assert compiled.title == spec.scan_title
        assert compiled.required_bars >= 1
        names = {out.name for out in compiled.outputs}
        assert "Signal" in names or "52W Breakout Signal" in names


def test_mean_reversion_pine_uses_sma_rsi_not_wilder():
    source = pine_source_for(LAB_STRATEGIES[5])
    spec = next(s for s in LAB_STRATEGIES if s.strategy_id == "06_mean_reversion")
    source = pine_source_for(spec)
    assert "ta.rsi" not in source
    assert "ta.sma(gain, 14)" in source
    compiled = compile_source(source)
    assert compiled.title.startswith("06")


def test_vol_squeeze_pine_uses_stdev():
    source = pine_source_for(LAB_STRATEGIES[6])
    spec = next(s for s in LAB_STRATEGIES if s.strategy_id == "07_vol_squeeze")
    source = pine_source_for(spec)
    assert "ta.stdev" in source
    compile_source(source)
