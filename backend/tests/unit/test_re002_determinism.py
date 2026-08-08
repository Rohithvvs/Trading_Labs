"""Deterministic state from engine path (not LLM)."""

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
            self.close = 120 + i * 0.2
            self.volume = 2_000_000

    return [C(i) for i in range(n)]


def test_same_inputs_same_state():
    class SO:
        sector_rs_20 = 6.0

    kwargs = dict(
        symbol="LEAD",
        market_regime=_MR(),
        candles=_candles(),
        technical_results=[_Tech()],
        sector_overlay=SO(),
        user_portfolio={"open_positions_count": 0, "max_positions": 5},
    )
    a = evaluate_re002(build_lab_context(**kwargs))
    b = evaluate_re002(build_lab_context(**kwargs))
    assert a["recommendation_state"] == b["recommendation_state"]
    assert a["strategy_name"] == b["strategy_name"]
