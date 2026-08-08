"""SC-006 directional: bear BUY count <= 50% of bull on shared fixture set."""

from app.services.re002.context import build_lab_context
from app.services.re002.engine import evaluate_re002


class _Tech:
    def __init__(self, score=80):
        self.score = score
        self.signal = "bullish"


def _candles(n=60):
    class C:
        def __init__(self, i):
            self.close = 100 + i * 0.1
            self.volume = 1_500_000

    return [C(i) for i in range(n)]


def _eval(regime_state: str, rs: float):
    class MR:
        market_state = regime_state
        trend_state = "BULLISH" if regime_state == "FAVORABLE" else "BEARISH"
        new_entry_allowed = regime_state == "FAVORABLE"

    class SO:
        sector_rs_20 = rs

    ctx = build_lab_context(
        symbol="X",
        market_regime=MR(),
        candles=_candles(),
        technical_results=[_Tech(80)],
        sector_overlay=SO(),
        user_portfolio={"open_positions_count": 0, "max_positions": 10},
    )
    return evaluate_re002(ctx)["recommendation_state"]


def test_bear_buys_not_more_than_half_bull():
    # 10 synthetic symbols with same tech quality, varying mild RS
    bull_buys = 0
    bear_buys = 0
    for i in range(10):
        rs = 2.0 + i * 0.3  # not exceptional for bear
        if _eval("FAVORABLE", rs) == "BUY":
            bull_buys += 1
        if _eval("DEFENSIVE", rs) == "BUY":
            bear_buys += 1
    if bull_buys == 0:
        assert bear_buys == 0
    else:
        assert bear_buys <= 0.5 * bull_buys + 1e-9
