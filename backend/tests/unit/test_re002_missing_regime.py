"""RE-002 missing market context → REJECT."""

from app.services.re002.context import build_lab_context
from app.services.re002.engine import evaluate_re002


def test_missing_regime_rejects():
    ctx = build_lab_context(symbol="TEST", market_regime=None, candles=[], technical_results=[])
    result = evaluate_re002(ctx)
    assert result["recommendation_state"] == "REJECT"
    assert "missing_market_context" in result["reason_codes"]
    assert result["market_regime"] == "UNKNOWN"
