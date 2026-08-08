"""Weak RS pre-filter always emits REJECT Decision Object (never silent skip)."""

from app.services.re002.context import build_lab_context
from app.services.re002.engine import evaluate_re002


class _MR:
    market_state = "FAVORABLE"
    trend_state = "BULLISH"
    new_entry_allowed = True


class _Tech:
    score = 80
    signal = "bullish"


def _candles(n=60):
    class C:
        def __init__(self, i):
            self.close = 100 + i * 0.1
            self.volume = 1_000_000

    return [C(i) for i in range(n)]


def test_weak_rs_reject_decision_object():
    class SO:
        sector_rs_20 = -3.0

    ctx = build_lab_context(
        symbol="WEAKRS",
        market_regime=_MR(),
        candles=_candles(),
        technical_results=[_Tech()],
        sector_overlay=SO(),
    )
    result = evaluate_re002(ctx)
    assert result["recommendation_state"] == "REJECT"
    assert "weak_relative_strength" in result["reason_codes"]
    assert result.get("evaluation_status") in {"rejected_by_rules", "success"}
