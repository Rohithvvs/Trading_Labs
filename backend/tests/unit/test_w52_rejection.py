from app.services.strategies.breakout52w.rejection import breakdown
from app.services.strategies.breakout52w.signal import first_failure


def test_hold_not_counted():
    assert first_failure(in_universe=True, held=True) is None
    rows = breakdown(["close_below_prior_high", "close_below_prior_high", "no_free_slot"], 10)
    by_code = {r["code"]: r for r in rows}
    assert by_code["close_below_prior_high"]["count"] == 2
    assert by_code["no_free_slot"]["count"] == 1
    assert sum(r["count"] for r in rows) == 3
    assert abs(sum(r["pct"] for r in rows) - 30.0) < 0.2


def test_single_first_failure():
    code = first_failure(
        in_universe=True,
        prior_high=None,
        close=None,
        high=None,
        volume=None,
        vol_sma=None,
        market_ok_flag=False,
    )
    assert code == "insufficient_history"
