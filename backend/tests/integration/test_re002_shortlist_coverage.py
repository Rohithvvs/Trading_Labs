"""SC-011: engine always returns a Decision Object for each evaluated symbol (no silent skip)."""

from app.services.re002.context import build_lab_context
from app.services.re002.decision_builder import build_decision_object
from app.services.re002.engine import evaluate_re002


class _MR:
    market_state = "FAVORABLE"
    trend_state = "BULLISH"
    new_entry_allowed = True


class _Tech:
    def __init__(self, score=40):
        self.score = score
        self.signal = "neutral"


def _candles(n=60, start=50.0):
    class C:
        def __init__(self, i):
            self.close = start + i * 0.05
            self.volume = 800_000

    return [C(i) for i in range(n)]


def test_every_symbol_gets_decision_object():
    symbols = ["AAA", "BBB", "CCC"]
    states = []
    for sym in symbols:
        ctx = build_lab_context(
            symbol=sym,
            scan_run_id="scan-sc011",
            market_regime=_MR(),
            candles=_candles(),
            technical_results=[_Tech(40)],
            sector_overlay=type("SO", (), {"sector_rs_20": -1.0})(),
            experiment_id="exp-sc011",
        )
        raw = evaluate_re002(ctx)
        obj = build_decision_object(ctx, raw)
        assert obj.symbol == sym
        assert obj.engine_id == "RE-002"
        assert obj.recommendation_state in {"BUY", "WATCH", "REJECT"}
        assert obj.recommendation_id
        states.append(obj.recommendation_state)
    # Weak RS fixtures should all REJECT (coverage of emission, not silent skip)
    assert all(s == "REJECT" for s in states)
