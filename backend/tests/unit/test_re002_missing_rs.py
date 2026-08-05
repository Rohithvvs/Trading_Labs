"""Missing RS never invents ranks; emits REJECT Decision Object path."""

from app.services.re002.context import build_lab_context
from app.services.re002.engine import evaluate_re002
from app.services.re002.rs_features import build_rs_features


class _MR:
    market_state = "FAVORABLE"
    trend_state = "BULLISH"
    new_entry_allowed = True


class _Tech:
    score = 85
    signal = "bullish"


def _candles(n=60):
    class C:
        def __init__(self, i):
            self.close = 100 + i * 0.1
            self.volume = 1_000_000

    return [C(i) for i in range(n)]


def test_missing_rs_reject_no_invented_rank():
    ctx = build_lab_context(
        symbol="NORS",
        market_regime=_MR(),
        candles=_candles(),
        technical_results=[_Tech()],
        sector_overlay=None,
    )
    features = build_rs_features(ctx)
    assert features["rs_vs_market"] is None
    assert features["leadership_rank"] is None
    assert features["rs_available"] is False

    result = evaluate_re002(ctx)
    assert result["recommendation_state"] == "REJECT"
    assert "missing_relative_strength" in result["reason_codes"]
