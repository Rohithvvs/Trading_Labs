"""Long-lived experiment id is stamped on Decision Objects when configured."""

from app.services.re002.context import build_lab_context
from app.services.re002.decision_builder import build_decision_object
from app.services.re002.engine import evaluate_re002


class _MR:
    market_state = "FAVORABLE"
    trend_state = "BULLISH"
    new_entry_allowed = True


class _Tech:
    score = 40
    signal = "neutral"


def _candles(n=60):
    class C:
        def __init__(self, i):
            self.close = 50 + i * 0.1
            self.volume = 900_000

    return [C(i) for i in range(n)]


def test_same_experiment_across_scan_runs():
    exp = "exp-long-lived-re002"
    objs = []
    for scan in ("scan-day-1", "scan-day-2"):
        ctx = build_lab_context(
            symbol="XYZ",
            scan_run_id=scan,
            market_regime=_MR(),
            candles=_candles(),
            technical_results=[_Tech()],
            sector_overlay=type("SO", (), {"sector_rs_20": -2.0})(),
            experiment_id=exp,
        )
        raw = evaluate_re002(ctx)
        obj = build_decision_object(ctx, raw)
        objs.append(obj)
        assert obj.experiment_id == exp
        assert obj.scan_run_id == scan
    assert objs[0].experiment_id == objs[1].experiment_id == exp
