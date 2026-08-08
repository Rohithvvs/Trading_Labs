"""Shortlist-only evaluation: RE-002 must not invent universe expansion."""

from app.services.re002.context import build_lab_context


def test_context_is_per_symbol_snapshot():
    ctx = build_lab_context(symbol="AAA", scan_run_id="scan-1")
    assert ctx.symbol == "AAA"
    assert ctx.scan_run_id == "scan-1"


def test_runner_has_no_universe_scan():
    """Static: runner/engine must not pull full NIFTY500 for evaluation set."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app" / "services" / "re002"
    for name in ("runner.py", "engine.py", "eligibility.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "nifty500" not in text.lower()
        assert "full_universe" not in text.lower()
